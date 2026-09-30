#!/usr/bin/env python3
"""
L5X project comparison.

Compares two full-controller L5X exports and reports structural differences while
ignoring live runtime values (tag <Data>, module input/output data) that change on
every upload/save and would otherwise drown the real edits.

Levels reported: controller header, DataTypes, AOIs, Modules (config vs. live data),
controller tags, tasks, programs (program tags + routines). Routines are compared rung by
rung with a sequence diff, so inserting one rung doesn't flag every rung after it, and
replaced rungs get a token-level diff showing only what changed inside the rung.
"""

import copy
import difflib
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Attributes that change on every save/export and carry no logic meaning.
NOISE_ATTRS = {"LastModifiedDate", "EditedDate", "ExportDate"}

HEADER_ATTRS = ("TargetName", "ProcessorType", "MajorRev", "MinorRev", "ProjectCreationDate",
                "LastModifiedDate", "CommPath", "SoftwareRevision")

_TOKEN_RE = re.compile(r"[A-Za-z_][\w:.\[\]]*|\d+\.?\d*|[^\sA-Za-z_\d]")


# --------------------------------------------------------------------------- loading

def load_controller(path: str) -> Tuple[ET.Element, ET.Element]:
    """Parse an L5X file; return (root, Controller element)."""
    root = ET.parse(str(path)).getroot()
    controller = root.find("Controller")
    if controller is None:
        raise ValueError(f"{path}: no <Controller> element - export the whole controller, not a fragment")
    return root, controller


def _by_name(parent: Optional[ET.Element], path: str) -> Dict[str, ET.Element]:
    if parent is None:
        return {}
    return {e.get("Name"): e for e in parent.findall(path)}


# --------------------------------------------------------------------------- serialization

def _scrub(elem: ET.Element, drop_live_data: bool, drop_tag_data: bool) -> ET.Element:
    """Copy of elem with noise attributes removed and (optionally) live values stripped."""
    e = copy.deepcopy(elem)
    for node in e.iter():
        for a in NOISE_ATTRS:
            node.attrib.pop(a, None)
        # <Dependencies> is export metadata derived from the definition itself (the SDK writes it, a
        # Studio export may not) - it is not project content, so it must not show up as a difference.
        for child in list(node):
            if child.tag == "Dependencies":
                node.remove(child)
    if drop_tag_data:  # tag values: <Data> / <Data Format=...> children of a Tag
        for node in e.iter():
            for child in list(node):
                if child.tag == "Data":
                    node.remove(child)
    if drop_live_data:  # module I/O image: Connection/InputTag|OutputTag/Data
        for tag in ("InputTag", "OutputTag"):
            for node in e.iter(tag):
                for child in list(node):
                    if child.tag == "Data":
                        node.remove(child)
    return e


def _lines(elem: ET.Element) -> List[str]:
    return ET.tostring(elem, encoding="unicode").strip().splitlines()


def _unified(a: List[str], b: List[str], limit: int = 12) -> List[str]:
    out = [l for l in difflib.unified_diff(a, b, lineterm="", n=0) if not l.startswith(("---", "+++", "@@"))]
    if len(out) > limit:
        out = out[:limit] + [f"... ({len(out) - limit} more changed lines)"]
    return [l[:240] for l in out]


# --------------------------------------------------------------------------- generic collections

def _compare_collection(a: Dict[str, ET.Element], b: Dict[str, ET.Element],
                        drop_live_data: bool = False, drop_tag_data: bool = False) -> Dict[str, Any]:
    ka, kb = set(a), set(b)
    changed = []
    for name in sorted(ka & kb):
        ea, eb = _scrub(a[name], drop_live_data, drop_tag_data), _scrub(b[name], drop_live_data, drop_tag_data)
        la, lb = _lines(ea), _lines(eb)
        if la != lb:
            changed.append({"name": name, "diff": _unified(la, lb)})
    return {
        "count_a": len(a), "count_b": len(b),
        "only_in_a": sorted(ka - kb), "only_in_b": sorted(kb - ka),
        "changed": changed,
    }


def _compare_tags(a: Dict[str, ET.Element], b: Dict[str, ET.Element]) -> Dict[str, Any]:
    """Tags: definition/description changes vs. value-only changes (reported as a count)."""
    result = _compare_collection(a, b, drop_tag_data=True)
    value_only = 0
    changed_defs = {c["name"] for c in result["changed"]}
    for name in set(a) & set(b):
        if name in changed_defs:
            continue
        if _lines(_scrub(a[name], False, False)) != _lines(_scrub(b[name], False, False)):
            value_only += 1
    result["value_only_changes"] = value_only
    return result


def _compare_modules(a: Dict[str, ET.Element], b: Dict[str, ET.Element]) -> Dict[str, Any]:
    result = _compare_collection(a, b, drop_live_data=True)
    live = 0
    config_names = {c["name"] for c in result["changed"]}
    for name in set(a) & set(b):
        if name not in config_names and _lines(a[name]) != _lines(b[name]):
            live += 1
    result["live_io_data_only_changes"] = live
    return result


# --------------------------------------------------------------------------- routines

def _routine_items(routine: ET.Element) -> List[Tuple[str, str, str]]:
    """(number, comment, text) per rung (RLL) or line (ST); other types as one opaque item."""
    rtype = routine.get("Type", "RLL")
    items: List[Tuple[str, str, str]] = []
    if rtype == "RLL":
        content = routine.find("RLLContent")
        for rung in (content.findall("Rung") if content is not None else []):
            items.append((rung.get("Number", ""), (rung.findtext("Comment") or "").strip(),
                          (rung.findtext("Text") or "").strip()))
    elif rtype == "ST":
        content = routine.find("STContent")
        for line in (content.findall("Line") if content is not None else []):
            items.append((line.get("Number", ""), "", (line.text or "").strip()))
    else:  # FBD / SFC: compare the serialized body as a single unit
        body = _scrub(routine, False, False)
        items.append(("0", "", "\n".join(_lines(body))))
    return items


def _tokens(s: str) -> List[str]:
    return _TOKEN_RE.findall(s)


def _segment_diff(a: str, b: str) -> List[Dict[str, str]]:
    ta, tb = _tokens(a), _tokens(b)
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    segs = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op != "equal":
            segs.append({"a": " ".join(ta[i1:i2])[:400], "b": " ".join(tb[j1:j2])[:400]})
    return segs


def _fmt(item: Tuple[str, str, str]) -> str:
    _, comment, text = item
    return f"[{comment}] || {text}" if comment else text


def _compare_routine(ra: ET.Element, rb: ET.Element) -> Optional[Dict[str, Any]]:
    ia, ib = _routine_items(ra), _routine_items(rb)
    # Routine-level attribute changes (Type, Description, etc.)
    attr_diff = {k: (ra.get(k), rb.get(k)) for k in set(ra.attrib) | set(rb.attrib)
                 if k not in NOISE_ATTRS and ra.get(k) != rb.get(k)}
    # Compare on (comment, text) only so renumbering alone isn't a change.
    ka, kb = [(c, t) for _, c, t in ia], [(c, t) for _, c, t in ib]
    ops = []
    sm = difflib.SequenceMatcher(None, ka, kb, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        entry: Dict[str, Any] = {
            "op": op,
            "a_rungs": [ia[i][0] for i in range(i1, i2)],
            "b_rungs": [ib[j][0] for j in range(j1, j2)],
            "removed": [_fmt(ia[i])[:600] for i in range(i1, i2)],
            "added": [_fmt(ib[j])[:600] for j in range(j1, j2)],
        }
        if op == "replace" and (i2 - i1) == (j2 - j1):
            entry["segments"] = [
                {"rung_a": ia[i1 + k][0], "rung_b": ib[j1 + k][0],
                 "comment_changed": ia[i1 + k][1] != ib[j1 + k][1],
                 "changes": _segment_diff(ia[i1 + k][2], ib[j1 + k][2])}
                for k in range(i2 - i1)
            ]
        ops.append(entry)
    if not ops and not attr_diff:
        return None
    return {"rungs_a": len(ia), "rungs_b": len(ib), "attribute_changes": attr_diff, "ops": ops}


def _compare_programs(ca: ET.Element, cb: ET.Element) -> Dict[str, Any]:
    pa = _by_name(ca.find("Programs"), "Program")
    pb = _by_name(cb.find("Programs"), "Program")
    out: Dict[str, Any] = {"only_in_a": sorted(set(pa) - set(pb)),
                           "only_in_b": sorted(set(pb) - set(pa)), "programs": {}}
    for name in sorted(set(pa) & set(pb)):
        ra = _by_name(pa[name].find("Routines"), "Routine")
        rb = _by_name(pb[name].find("Routines"), "Routine")
        changed = {}
        for rname in sorted(set(ra) & set(rb)):
            d = _compare_routine(ra[rname], rb[rname])
            if d:
                changed[rname] = d
        attr_diff = {k: (pa[name].get(k), pb[name].get(k)) for k in set(pa[name].attrib) | set(pb[name].attrib)
                     if k not in NOISE_ATTRS and pa[name].get(k) != pb[name].get(k)}
        out["programs"][name] = {
            "attribute_changes": attr_diff,
            "tags": _compare_tags(_by_name(pa[name].find("Tags"), "Tag"), _by_name(pb[name].find("Tags"), "Tag")),
            "routines_only_in_a": sorted(set(ra) - set(rb)),
            "routines_only_in_b": sorted(set(rb) - set(ra)),
            "routines_changed": changed,
            "routine_count_a": len(ra), "routine_count_b": len(rb),
        }
    return out


# --------------------------------------------------------------------------- public API

def compare_l5x_files(path_a: str, path_b: str) -> Dict[str, Any]:
    """Full structured comparison of two whole-controller L5X exports (A = baseline, B = other)."""
    root_a, ca = load_controller(path_a)
    root_b, cb = load_controller(path_b)

    header = {k: (ca.get(k), cb.get(k)) for k in HEADER_ATTRS if ca.get(k) != cb.get(k)}
    for k in ("SoftwareRevision",):
        if root_a.get(k) != root_b.get(k):
            header[k] = (root_a.get(k), root_b.get(k))

    result: Dict[str, Any] = {
        "path_a": str(path_a), "path_b": str(path_b),
        "header_differences": {k: {"a": v[0], "b": v[1]} for k, v in header.items()},
        "datatypes": _compare_collection(_by_name(ca.find("DataTypes"), "DataType"),
                                         _by_name(cb.find("DataTypes"), "DataType")),
        "aois": _compare_collection(_by_name(ca.find("AddOnInstructionDefinitions"), "AddOnInstructionDefinition"),
                                    _by_name(cb.find("AddOnInstructionDefinitions"), "AddOnInstructionDefinition")),
        "modules": _compare_modules(_by_name(ca.find("Modules"), "Module"), _by_name(cb.find("Modules"), "Module")),
        "controller_tags": _compare_tags(_by_name(ca.find("Tags"), "Tag"), _by_name(cb.find("Tags"), "Tag")),
        "tasks": _compare_collection(_by_name(ca.find("Tasks"), "Task"), _by_name(cb.find("Tasks"), "Task")),
        "programs": _compare_programs(ca, cb),
    }
    result["summary"] = summarize(result)
    return result


def summarize(r: Dict[str, Any]) -> Dict[str, Any]:
    def coll(c):
        return {"only_in_a": len(c["only_in_a"]), "only_in_b": len(c["only_in_b"]), "changed": len(c["changed"])}

    routines_changed = sum(len(p["routines_changed"]) for p in r["programs"]["programs"].values())
    rung_ops = sum(len(rc["ops"]) for p in r["programs"]["programs"].values() for rc in p["routines_changed"].values())
    return {
        "header_differences": len(r["header_differences"]),
        "datatypes": coll(r["datatypes"]), "aois": coll(r["aois"]), "tasks": coll(r["tasks"]),
        "modules": {**coll(r["modules"]), "live_io_data_only_changes": r["modules"]["live_io_data_only_changes"]},
        "controller_tags": {**coll(r["controller_tags"]), "value_only_changes": r["controller_tags"]["value_only_changes"]},
        "programs_only_in_a": len(r["programs"]["only_in_a"]), "programs_only_in_b": len(r["programs"]["only_in_b"]),
        "routines_changed": routines_changed, "rung_change_blocks": rung_ops,
        "identical": not (routines_changed or rung_ops or r["header_differences"]
                          or any(coll(r[k])["only_in_a"] or coll(r[k])["only_in_b"] or coll(r[k])["changed"]
                                 for k in ("datatypes", "aois", "modules", "controller_tags", "tasks"))),
    }


def render_markdown(r: Dict[str, Any], label_a: Optional[str] = None, label_b: Optional[str] = None) -> str:
    la = label_a or Path(r["path_a"]).name
    lb = label_b or Path(r["path_b"]).name
    out: List[str] = [f"# L5X comparison: {la} vs {lb}", "",
                      f"- **A** (baseline): `{r['path_a']}`", f"- **B**: `{r['path_b']}`", ""]

    if r["header_differences"]:
        out += ["## Controller header", "", "| Field | A | B |", "|---|---|---|"]
        out += [f"| {k} | {v['a']} | {v['b']} |" for k, v in r["header_differences"].items()]
        out.append("")

    def section(title: str, c: Dict[str, Any], extra: str = ""):
        if not (c["only_in_a"] or c["only_in_b"] or c["changed"]):
            out.extend([f"## {title}", "", f"No differences ({c['count_a']} vs {c['count_b']}).{extra}", ""])
            return
        out.extend([f"## {title}", "", f"A: {c['count_a']}, B: {c['count_b']}.{extra}", ""])
        if c["only_in_a"]:
            out.append(f"- Only in A: {', '.join(f'`{n}`' for n in c['only_in_a'])}")
        if c["only_in_b"]:
            out.append(f"- Only in B: {', '.join(f'`{n}`' for n in c['only_in_b'])}")
        for ch in c["changed"]:
            out.append(f"- Changed `{ch['name']}`:")
            out.extend(f"    - `{d}`" for d in ch["diff"][:8])
        out.append("")

    section("Data types", r["datatypes"])
    section("Add-On Instructions", r["aois"])
    section("Tasks", r["tasks"])
    section("Modules (configuration)", r["modules"],
            f" {r['modules']['live_io_data_only_changes']} module(s) differ only in live I/O data (ignored).")
    section("Controller tags (definitions)", r["controller_tags"],
            f" {r['controller_tags']['value_only_changes']} tag(s) differ only in current value (ignored).")

    pr = r["programs"]
    if pr["only_in_a"] or pr["only_in_b"]:
        out += ["## Programs", "", f"- Only in A: {pr['only_in_a']}", f"- Only in B: {pr['only_in_b']}", ""]
    for pname, p in pr["programs"].items():
        out += [f"## Program `{pname}`", ""]
        if p["attribute_changes"]:
            out.append(f"- Program attributes changed: {p['attribute_changes']}")
        t = p["tags"]
        if t["only_in_a"] or t["only_in_b"] or t["changed"]:
            out.append(f"- Program tags: only in A {t['only_in_a']}, only in B {t['only_in_b']}, "
                       f"changed {[c['name'] for c in t['changed']]}")
        if p["routines_only_in_a"] or p["routines_only_in_b"]:
            out.append(f"- Routines only in A: {p['routines_only_in_a']}; only in B: {p['routines_only_in_b']}")
        if not p["routines_changed"]:
            out += [f"- No routine differences ({p['routine_count_a']} vs {p['routine_count_b']} routines).", ""]
            continue
        out.append("")
        for rname, rc in p["routines_changed"].items():
            out += [f"### `{pname}/{rname}` (rungs A={rc['rungs_a']}, B={rc['rungs_b']})", ""]
            if rc["attribute_changes"]:
                out.append(f"- Routine attributes changed: {rc['attribute_changes']}")
            for op in rc["ops"]:
                a_r = ",".join(op["a_rungs"]) or "-"
                b_r = ",".join(op["b_rungs"]) or "-"
                out.append(f"- **{op['op']}** A rung(s) [{a_r}] -> B rung(s) [{b_r}]")
                if "segments" in op:
                    for seg in op["segments"]:
                        if seg["comment_changed"]:
                            out.append(f"    - rung {seg['rung_a']}: comment changed")
                        for ch in seg["changes"]:
                            out.append(f"    - rung {seg['rung_a']}: `{ch['a'] or '(nothing)'}` -> `{ch['b'] or '(nothing)'}`")
                else:
                    out += [f"    - A: `{x[:300]}`" for x in op["removed"]]
                    out += [f"    - B: `{x[:300]}`" for x in op["added"]]
            out.append("")
    return "\n".join(out)
