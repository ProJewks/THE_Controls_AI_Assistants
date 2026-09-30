#!/usr/bin/env python3
"""
Byte-preserving L5X editing.

Why this exists: parsing an L5X with an XML library and writing it back silently drops every
<![CDATA[ ]]> wrapper. Logix then rejects the file on import ("String invalid", "Required CDATA
for element 'Line' was missing"). These helpers splice new XML text into the raw file instead, so
everything outside the edit - CDATA, whitespace, attribute order, line endings, BOM - stays
byte-for-byte identical.

All functions take and return text (decode the file as UTF-8 without stripping the BOM, write it
back the same way) and raise L5XEditError with a readable message when an edit can't be made.
"""

import re
from typing import Any, Dict, List, Optional, Tuple


class L5XEditError(ValueError):
    """An edit could not be applied (target not found, invalid logic text, duplicate tag...)."""


# ----------------------------------------------------------------------------- text helpers

def detect_eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def cdata(value: str) -> str:
    """CDATA section for value; a literal ']]>' is split across two sections."""
    return "<![CDATA[" + value.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _attr_name_re(tag: str, name: str) -> "re.Pattern":
    return re.compile(rf'<{tag}\b[^>]*?\bName="{re.escape(name)}"[^>]*>')


# ----------------------------------------------------------------------------- locating scopes

def find_program_span(text: str, program: str) -> Tuple[int, int]:
    m = _attr_name_re("Program", program).search(text)
    if not m:
        raise L5XEditError(f"Program '{program}' not found")
    end = text.find("</Program>", m.end())
    if end < 0:
        raise L5XEditError(f"Program '{program}' has no closing tag")
    return m.start(), end


def find_aoi_span(text: str, aoi: str) -> Tuple[int, int]:
    m = _attr_name_re("AddOnInstructionDefinition", aoi).search(text)
    if not m:
        raise L5XEditError(f"Add-On Instruction '{aoi}' not found")
    end = text.find("</AddOnInstructionDefinition>", m.end())
    if end < 0:
        raise L5XEditError(f"Add-On Instruction '{aoi}' has no closing tag")
    return m.start(), end


def _rll_bounds(text: str, routine: str, program: Optional[str], aoi: Optional[str]) -> Tuple[int, int, bool]:
    """(content_start, content_end, was_self_closing) for the routine's <RLLContent>.

    content_start is just after '<RLLContent>', content_end is the index of '</RLLContent>'.
    For a self-closing '<RLLContent/>' both are the index where the element begins.
    """
    s0, s1 = find_aoi_span(text, aoi) if aoi else find_program_span(text, program or "MainProgram")
    where = f"Add-On Instruction '{aoi}'" if aoi else f"program '{program or 'MainProgram'}'"
    m = _attr_name_re("Routine", routine).search(text, s0, s1)
    if not m:
        raise L5XEditError(f"Routine '{routine}' not found in {where}")
    r_end = text.find("</Routine>", m.end(), s1 + 1)
    if r_end < 0:
        raise L5XEditError(f"Routine '{routine}' has no closing tag")
    head = text[m.start():m.end()]
    rtype = re.search(r'\bType="([^"]*)"', head)
    if rtype and rtype.group(1) != "RLL":
        raise L5XEditError(f"Routine '{routine}' is a {rtype.group(1)} routine, not ladder (RLL)")
    sc = re.compile(r"<RLLContent\s*/>").search(text, m.end(), r_end)
    if sc:
        return sc.start(), sc.start(), True
    o = text.find("<RLLContent>", m.end(), r_end)
    c = text.find("</RLLContent>", m.end(), r_end + 1)
    if o < 0 or c < 0:
        raise L5XEditError(f"Routine '{routine}' has no <RLLContent>")
    return o + len("<RLLContent>"), c, False


_RUNG_RE = re.compile(r"<Rung\b[^>]*>.*?</Rung>", re.S)


def list_rungs(text: str, routine: str, program: Optional[str] = "MainProgram",
               aoi: Optional[str] = None) -> List[Dict[str, Any]]:
    """[{number, start, end, text, comment}] for every rung of the routine, in file order."""
    c0, c1, _ = _rll_bounds(text, routine, program, aoi)
    out = []
    for m in _RUNG_RE.finditer(text, c0, c1):
        body = m.group(0)
        num = re.search(r'\bNumber="(\d+)"', body)
        t = re.search(r"<Text>\s*(?:<!\[CDATA\[(.*?)\]\]>|(.*?))\s*</Text>", body, re.S)
        c = re.search(r"<Comment>\s*(?:<!\[CDATA\[(.*?)\]\]>|(.*?))\s*</Comment>", body, re.S)
        out.append({
            "number": int(num.group(1)) if num else len(out),
            "start": m.start(), "end": m.end(),
            "text": (t.group(1) if t and t.group(1) is not None else (t.group(2) if t else "")) or "",
            "comment": ((c.group(1) if c.group(1) is not None else c.group(2)) if c else None),
        })
    return out


# ----------------------------------------------------------------------------- rung editing

def check_rung_text(rung_text: str) -> None:
    """Cheap structural checks so obviously broken logic never gets into the file."""
    t = (rung_text or "").strip()
    if not t:
        raise L5XEditError("rung text is empty")
    if not t.endswith(";"):
        raise L5XEditError(f"rung text must end with ';': {t[:80]!r}")
    depth_p = depth_b = 0
    for ch in t:
        depth_p += ch == "("
        depth_p -= ch == ")"
        depth_b += ch == "["
        depth_b -= ch == "]"
        if depth_p < 0 or depth_b < 0:
            raise L5XEditError(f"unbalanced brackets in rung text: {t[:80]!r}")
    if depth_p or depth_b:
        raise L5XEditError(f"unbalanced brackets in rung text: {t[:80]!r}")


def build_rung_xml(number: int, text: str, comment: Optional[str], eol: str, rung_type: str = "N") -> str:
    check_rung_text(text)
    lines = [f'<Rung Number="{number}" Type="{rung_type}">']
    if comment:
        lines += ["<Comment>", cdata(comment), "</Comment>"]
    lines += ["<Text>", cdata(text.strip()), "</Text>", "</Rung>"]
    return eol.join(lines)


def splice_rungs(text: str, routine: str, rungs: List[Dict[str, Any]], position: Optional[int] = None,
                 remove_count: int = 0, program: Optional[str] = "MainProgram",
                 aoi: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Remove `remove_count` rungs starting at `position`, insert `rungs` there, renumber the rest.

    insert  = splice_rungs(..., rungs=[...], position=p)                 (remove_count 0)
    delete  = splice_rungs(..., rungs=[],    position=p, remove_count=n)
    replace = splice_rungs(..., rungs=[...], position=p, remove_count=n)
    position=None appends at the end. Returns (new_text, info).
    """
    eol = detect_eol(text)
    c0, c1, self_closing = _rll_bounds(text, routine, program, aoi)
    existing = list_rungs(text, routine, program, aoi) if not self_closing else []
    n = len(existing)
    pos = n if position is None else position
    if not 0 <= pos <= n:
        raise L5XEditError(f"position {pos} is out of range - routine '{routine}' has {n} rung(s) (0..{n})")
    if remove_count < 0 or pos + remove_count > n:
        raise L5XEditError(f"cannot remove {remove_count} rung(s) at position {pos} - routine has {n} rung(s)")

    new_xml = [build_rung_xml(pos + i, r["text"], r.get("comment"), eol, r.get("type", "N"))
               for i, r in enumerate(rungs)]
    # Everything else in the routine is preserved exactly; only rung numbers after the edit shift.
    tail_first = pos + remove_count
    shift = len(rungs) - remove_count

    if self_closing:
        body = eol + "".join(x + eol for x in new_xml)
        new_text = text[:c0] + "<RLLContent>" + body + "</RLLContent>" + text[c0:].split("/>", 1)[1]
        return new_text, _info(routine, program, aoi, 0, pos, 0, len(rungs), len(rungs))

    cut_start = existing[pos]["start"] if pos < n else c1
    if remove_count:
        cut_end = existing[pos + remove_count - 1]["end"]
        if text.startswith(eol, cut_end):
            cut_end += len(eol)
    else:
        cut_end = cut_start
    tail = text[cut_end:c1]
    if shift and tail_first < n:
        counter = {"i": tail_first + shift}

        def renumber(m: "re.Match") -> str:
            k = counter["i"]
            counter["i"] += 1
            return re.sub(r'\bNumber="\d+"', f'Number="{k}"', m.group(0), count=1)

        tail = re.sub(r"<Rung\b[^>]*>", renumber, tail)
    inserted = "".join(x + eol for x in new_xml)
    new_text = text[:cut_start] + inserted + tail + text[c1:]
    return new_text, _info(routine, program, aoi, n, pos, remove_count, len(rungs), n + shift)


def _info(routine, program, aoi, before, pos, removed, added, after) -> Dict[str, Any]:
    return {"routine": routine, "program": None if aoi else (program or "MainProgram"), "aoi": aoi,
            "rungs_before": before, "position": pos, "removed": removed, "added": added, "rungs_after": after}


# ----------------------------------------------------------------------------- tag adding

SUPPORTED_TAG_TYPES = ("BOOL", "SINT", "INT", "DINT", "REAL", "TIMER", "COUNTER")
_TAG_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def check_tag_name(name: str) -> None:
    if (not _TAG_NAME_RE.match(name or "") or "__" in name or name.endswith("_") or len(name) > 40):
        raise L5XEditError(
            f"invalid tag name {name!r}: letters, digits and underscores only, must not start with a digit, "
            "no consecutive or trailing underscores, max 40 characters")


def _l5k_real(f: float) -> str:
    """REAL in Studio's L5K style: 8 decimals and a 3-digit exponent (5.92175543e-001)."""
    mantissa, exp = f"{f:.8e}".split("e")
    return f"{mantissa}e{exp[0]}{abs(int(exp)):03d}"


def _tag_xml(tag: Dict[str, Any], eol: str, style: Dict[str, bool]) -> str:
    name, dtype = tag["name"], str(tag["data_type"]).upper()
    if dtype not in SUPPORTED_TAG_TYPES:
        raise L5XEditError(
            f"tag '{name}': data type {dtype!r} is not supported for text-level creation "
            f"(supported: {', '.join(SUPPORTED_TAG_TYPES)}). Create other types in Studio 5000.")
    check_tag_name(name)
    attrs = f'Name="{name}"'
    if style["class"]:
        attrs += ' Class="Standard"'
    attrs += f' TagType="Base" DataType="{dtype}"'
    if dtype in ("SINT", "INT", "DINT", "BOOL"):
        attrs += ' Radix="Decimal"'
    elif dtype == "REAL":
        attrs += ' Radix="Float"'
    attrs += ' Constant="false" ExternalAccess="Read/Write"'
    if style["opc"]:
        attrs += ' OpcUaAccess="None"'

    lines = [f"<Tag {attrs}>"]
    if tag.get("description"):
        lines += ["<Description>", cdata(tag["description"]), "</Description>"]

    init = tag.get("initial_value", 0)
    try:
        if dtype == "BOOL":
            v = 1 if int(init) else 0
            l5k, dec = str(v), f'<DataValue DataType="BOOL" Radix="Decimal" Value="{v}"/>'
        elif dtype in ("SINT", "INT", "DINT"):
            v = int(init)
            l5k, dec = str(v), f'<DataValue DataType="{dtype}" Radix="Decimal" Value="{v}"/>'
        elif dtype == "REAL":
            f = float(init)
            l5k = _l5k_real(f)
            dec = f'<DataValue DataType="REAL" Radix="Float" Value="{f:.8g}"/>'
        elif dtype == "TIMER":
            pre = int(tag.get("preset", 0))
            l5k = f"[0,{pre},0]"
            dec = eol.join([
                '<Structure DataType="TIMER">',
                f'<DataValueMember Name="PRE" DataType="DINT" Radix="Decimal" Value="{pre}"/>',
                '<DataValueMember Name="ACC" DataType="DINT" Radix="Decimal" Value="0"/>',
                '<DataValueMember Name="EN" DataType="BOOL" Value="0"/>',
                '<DataValueMember Name="TT" DataType="BOOL" Value="0"/>',
                '<DataValueMember Name="DN" DataType="BOOL" Value="0"/>',
                '</Structure>'])
        else:  # COUNTER
            pre = int(tag.get("preset", 0))
            l5k = f"[0,{pre},0]"
            dec = eol.join([
                '<Structure DataType="COUNTER">',
                f'<DataValueMember Name="PRE" DataType="DINT" Radix="Decimal" Value="{pre}"/>',
                '<DataValueMember Name="ACC" DataType="DINT" Radix="Decimal" Value="0"/>',
                '<DataValueMember Name="CU" DataType="BOOL" Value="0"/>',
                '<DataValueMember Name="CD" DataType="BOOL" Value="0"/>',
                '<DataValueMember Name="DN" DataType="BOOL" Value="0"/>',
                '<DataValueMember Name="OV" DataType="BOOL" Value="0"/>',
                '<DataValueMember Name="UN" DataType="BOOL" Value="0"/>',
                '</Structure>'])
    except (TypeError, ValueError):
        raise L5XEditError(f"tag '{name}': initial value {init!r} is not valid for {dtype}")
    lines += ['<Data Format="L5K">', cdata(l5k), "</Data>", '<Data Format="Decorated">', dec, "</Data>", "</Tag>"]
    return eol.join(lines)


def _tags_bounds(text: str, program: Optional[str]) -> Tuple[int, int, int, int, int]:
    """(insert_at, scope_start, scope_end, self_closing_start, self_closing_end) for a Tags container.

    Returns insertion index (just before '</Tags>'), the search scope, and - if the container is
    self-closing - the span of that '<Tags/>' element (else -1, -1).
    """
    if program:
        s0, s1 = find_program_span(text, program)
        where = f"program '{program}'"
    else:
        s0 = 0
        s1 = text.find("<Programs")
        s1 = len(text) if s1 < 0 else s1
        where = "the controller"
    m = re.search(r"<Tags(?:\s[^>]*)?>|<Tags\s*/>", text[s0:s1])
    if not m:
        raise L5XEditError(f"no <Tags> section found in {where}")
    start = s0 + m.start()
    if m.group(0).rstrip().endswith("/>"):
        return -1, s0, s1, start, s0 + m.end()
    end = text.find("</Tags>", s0 + m.end(), s1 + 10)
    if end < 0:
        raise L5XEditError(f"<Tags> in {where} has no closing tag")
    return end, start, end, -1, -1


def add_tags(text: str, tags: List[Dict[str, Any]], program: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """Append simple (non-UDT, non-array) tags to the controller (or a program) scope."""
    if not tags:
        raise L5XEditError("no tags given")
    eol = detect_eol(text)
    insert_at, t0, t1, sc0, sc1 = _tags_bounds(text, program)

    first = re.search(r"<Tag\b[^>]*>", text[t0:] if sc0 < 0 else "")
    head = first.group(0) if first else ""
    style = {"class": 'Class="Standard"' in head, "opc": "OpcUaAccess=" in head}

    seen = set()
    scope_text = text[t0:t1] if sc0 < 0 else ""
    for t in tags:
        name = t.get("name", "")
        check_tag_name(name)
        if name in seen or re.search(rf'<Tag\b[^>]*?\bName="{re.escape(name)}"', scope_text):
            raise L5XEditError(f"tag '{name}' already exists in {'program ' + program if program else 'the controller'} scope")
        seen.add(name)
    xml = "".join(_tag_xml(t, eol, style) + eol for t in tags)
    if sc0 >= 0:  # <Tags/> -> <Tags> ... </Tags>
        new_text = text[:sc0] + "<Tags>" + eol + xml + "</Tags>" + text[sc1:]
    else:
        new_text = text[:insert_at] + xml + text[insert_at:]
    return new_text, {"scope": program or "controller", "added": sorted(seen)}
