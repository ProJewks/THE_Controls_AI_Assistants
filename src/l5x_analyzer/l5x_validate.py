#!/usr/bin/env python3
"""
Pre-flight validation of an edited L5X against its baseline.

Runs BEFORE any ACD is created. Every check is reported as an issue with a code, a location and
a message. Issues present in the baseline already are reported separately ("pre-existing") from
issues the edits introduced ("introduced"); only introduced errors block a commit.

Checks
  xml-parse           file is well-formed XML
  cdata-missing       an element Logix requires CDATA for (Text, Line, Comment, Description,
                      DefaultData, L5K/String Data ...) has plain text instead - the exact damage
                      an XML-library round trip does
  rung-numbering      rung numbers in a routine are 0..N-1 in order
  rung-syntax         rung text ends with ';' and has balanced ( ) and [ ]
  aoi-operand-count   a call to an Add-On Instruction has a different number of operands than the
                      definition requires (instance + every Required parameter)
  unbound-operand     a '?' placeholder operand in a rung
  unknown-tag         (warning) a tag referenced by a NEW or CHANGED rung isn't defined anywhere
                      in the controller, its program, or the module list
"""

import re
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

_TAG_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?::[A-Za-z0-9_]+)*(?:\.[A-Za-z0-9_]+|\[[^\]]*\])*")
# Elements whose text Logix requires inside CDATA when the element has no child elements.
_CDATA_ELEMENTS = ("Text", "Line", "Comment", "Description", "DefaultData", "Data", "RevisionNote",
                   "AdditionalHelpText", "RevisionExtension", "SoftwareRevisionNote")
_ELEM_RE = re.compile(r"<(%s)\b([^>/]*)>(.*?)</\1>" % "|".join(_CDATA_ELEMENTS), re.S)


def _issue(severity: str, code: str, where: str, message: str) -> Dict[str, str]:
    return {"severity": severity, "code": code, "where": where, "message": message}


def _key(i: Dict[str, str]) -> Tuple[str, str, str]:
    # CDATA problems are located by line number, which shifts whenever lines are inserted above them.
    where = "" if i["code"] == "cdata-missing" else i["where"]
    return (i["code"], where, i["message"])


# ----------------------------------------------------------------------------- helpers

def split_operands(arg_text: str) -> List[str]:
    """Split call arguments on top-level commas (commas inside [ ] or ( ) are kept)."""
    out, depth, cur = [], 0, []
    for ch in arg_text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur or out:
        out.append("".join(cur).strip())
    return out


def _find_calls(text: str, name: str) -> List[str]:
    """Argument strings of every call `name(...)` in a rung."""
    calls = []
    for m in re.finditer(rf"(?<![A-Za-z0-9_]){re.escape(name)}\(", text):
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += text[i] == "("
            depth -= text[i] == ")"
            i += 1
        if depth == 0:
            calls.append(text[m.end():i - 1])
    return calls


def _expected_operands(aoi: ET.Element) -> int:
    """Operands of a ladder call: the instance tag plus every parameter marked Required
    (Input, InOut and Output alike). Visible-but-optional parameters are not operands - they are
    reached through the instance tag's members. Verified against every AOI call in two real projects."""
    return 1 + sum(1 for p in aoi.findall("Parameters/Parameter")
                   if p.get("Required") == "true" and p.get("Name") not in ("EnableIn", "EnableOut"))


def _rungs(routine: ET.Element) -> List[Tuple[int, str]]:
    content = routine.find("RLLContent")
    out = []
    for r in (content.findall("Rung") if content is not None else []):
        out.append((int(r.get("Number", "-1")), (r.findtext("Text") or "").strip()))
    return out


def _program_routines(controller: ET.Element):
    for prog in controller.findall("Programs/Program"):
        for r in prog.findall("Routines/Routine"):
            if r.get("Type", "RLL") == "RLL":
                yield prog.get("Name"), r


def _defined_names(controller: ET.Element, program: Optional[str]) -> Set[str]:
    names = {t.get("Name") for t in controller.findall("Tags/Tag")}
    names |= {m.get("Name") for m in controller.findall("Modules/Module")}
    if program:
        for p in controller.findall("Programs/Program"):
            if p.get("Name") == program:
                names |= {t.get("Name") for t in p.findall("Tags/Tag")}
    return {n for n in names if n}


# ----------------------------------------------------------------------------- checks

def check_cdata(raw: str) -> List[Dict[str, str]]:
    """Elements that must use CDATA but contain bare text."""
    issues = []
    for m in _ELEM_RE.finditer(raw):
        inner = m.group(3)
        stripped = inner.strip()
        if not stripped or stripped.startswith("<![CDATA["):
            continue
        if re.search(r"<[A-Za-z]", stripped):  # has child elements (e.g. Decorated data) - no CDATA expected
            continue
        line = raw.count("\n", 0, m.start()) + 1
        issues.append(_issue("error", "cdata-missing", f"line {line} <{m.group(1)}>",
                             f"text of <{m.group(1)}> is not in a CDATA section: {stripped[:60]!r}"))
    return issues


def check_controller(controller: ET.Element, scope: Optional[Set[Tuple[str, str]]] = None
                     ) -> List[Dict[str, str]]:
    """Rung-level checks. `scope` (set of (program, routine)) limits which routines are checked."""
    issues = []
    aois = {a.get("Name"): a for a in controller.findall("AddOnInstructionDefinitions/AddOnInstructionDefinition")}
    expected = {n: _expected_operands(a) for n, a in aois.items()}
    for prog, routine in _program_routines(controller):
        if scope is not None and (prog, routine.get("Name")) not in scope:
            continue
        where0 = f"{prog}/{routine.get('Name')}"
        rungs = _rungs(routine)
        if [n for n, _ in rungs] != list(range(len(rungs))):
            issues.append(_issue("error", "rung-numbering", where0,
                                 f"rung numbers are {[n for n, _ in rungs][:12]}..., expected 0..{len(rungs) - 1}"))
        for num, text in rungs:
            where = f"{where0} rung {num}"
            if not text.endswith(";"):
                issues.append(_issue("error", "rung-syntax", where, f"rung text does not end with ';': {text[-40:]!r}"))
            if text.count("(") != text.count(")") or text.count("[") != text.count("]"):
                issues.append(_issue("error", "rung-syntax", where, "unbalanced ( ) or [ ] in rung text"))
            for name, want in expected.items():
                for args in _find_calls(text, name):
                    ops = split_operands(args)
                    if len(ops) != want:
                        issues.append(_issue("error", "aoi-operand-count", where,
                                             f"{name} is called with {len(ops)} operand(s) but its definition needs {want}"))
                    if any(o == "?" for o in ops):
                        issues.append(_issue("error", "unbound-operand", where,
                                             f"{name} has unbound '?' operand(s): {args[:100]}"))
    return issues


def changed_routines(base: ET.Element, edited: ET.Element) -> Dict[Tuple[str, str], List[str]]:
    """{(program, routine): [rung texts that are new or changed]} - multiset difference vs baseline."""
    base_map = {(p, r.get("Name")): Counter(t for _, t in _rungs(r)) for p, r in _program_routines(base)}
    out = {}
    for p, r in _program_routines(edited):
        key = (p, r.get("Name"))
        before = base_map.get(key, Counter())
        new = []
        remaining = before.copy()
        for _, t in _rungs(r):
            if remaining[t] > 0:
                remaining[t] -= 1
            else:
                new.append(t)
        if new or key not in base_map:
            out[key] = new
    return out


def check_unknown_tags(edited: ET.Element, changes: Dict[Tuple[str, str], List[str]]) -> List[Dict[str, str]]:
    issues = []
    for (prog, routine), texts in changes.items():
        defined = _defined_names(edited, prog)
        for text in texts:
            # strip string literals and numeric constants before looking for tag names
            cleaned = re.sub(r"'[^']*'", "", text)
            cleaned = re.sub(r"(?<![A-Za-z0-9_.:])[-+]?\d[\d.eE+-]*", "", cleaned)
            opcodes = set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\(", cleaned))
            for tok in _TAG_TOKEN_RE.findall(cleaned):
                base = re.split(r"[.\[]", tok)[0].split(":")[0]
                if base in opcodes or base in defined or base in ("Local",) or not base:
                    continue
                issues.append(_issue("warning", "unknown-tag", f"{prog}/{routine}",
                                     f"'{base}' is referenced by a new/changed rung but isn't a defined tag or module "
                                     f"(rung: {text[:70]}...)"))
    # one warning per (routine, tag)
    seen, unique = set(), []
    for i in issues:
        k = (i["where"], re.match(r"'([^']*)'", i["message"]).group(1))
        if k not in seen:
            seen.add(k)
            unique.append(i)
    return unique


# ----------------------------------------------------------------------------- entry point

def _load(raw: str) -> ET.Element:
    root = ET.fromstring(raw.encode("utf-8").lstrip(b"\xef\xbb\xbf"))
    c = root.find("Controller")
    if c is None:
        raise ValueError("no <Controller> element - the file must be a whole-controller export")
    return c


def validate_changes(baseline_path: str, edited_path: str) -> Dict[str, Any]:
    """Validate `edited_path` against `baseline_path`. Returns a structured report."""
    base_raw = open(baseline_path, "rb").read().decode("utf-8")
    edit_raw = open(edited_path, "rb").read().decode("utf-8")

    try:
        edited = _load(edit_raw)
    except (ET.ParseError, ValueError) as e:
        return {"ok": False, "introduced_errors": [_issue("error", "xml-parse", edited_path, str(e))],
                "preexisting_errors": [], "warnings": [], "changed_routines": {}, "summary": "file is not valid XML"}
    base = _load(base_raw)

    changes = changed_routines(base, edited)
    edited_issues = check_cdata(edit_raw) + check_controller(edited)
    base_issues = check_cdata(base_raw) + check_controller(base)
    base_keys = {_key(i) for i in base_issues}

    introduced = [i for i in edited_issues if _key(i) not in base_keys and i["severity"] == "error"]
    # cdata line numbers shift when lines are inserted, so also match pre-existing cdata problems by text
    preexisting = [i for i in edited_issues if _key(i) in base_keys]
    warnings = check_unknown_tags(edited, changes)

    # Order-insensitive line counts (O(n), fine for 40k+ line files): how many lines the edits
    # added and removed relative to the baseline, renumbered rung headers included.
    base_count, edit_count = Counter(base_raw.splitlines()), Counter(edit_raw.splitlines())
    lines_added = sum((edit_count - base_count).values())
    lines_removed = sum((base_count - edit_count).values())
    changed_lines = max(lines_added, lines_removed)

    ok = not introduced
    summary = (f"{len(changes)} routine(s) changed, +{lines_added}/-{lines_removed} line(s) vs the baseline; "
               f"{len(introduced)} introduced error(s), {len(preexisting)} pre-existing, {len(warnings)} warning(s)")
    return {
        "ok": ok,
        "introduced_errors": introduced,
        "preexisting_errors": preexisting,
        "warnings": warnings,
        "changed_routines": {f"{p}/{r}": {"new_or_changed_rungs": len(t)} for (p, r), t in changes.items()},
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "changed_lines": changed_lines,
        "summary": summary,
    }
