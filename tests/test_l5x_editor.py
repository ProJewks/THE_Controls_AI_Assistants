"""
Tests for l5x_analyzer/l5x_editor.py - byte-preserving L5X edits.

The property that matters: an edit changes ONLY what was asked. Everything else - CDATA wrappers,
CRLF line endings, BOM, other routines, other programs - stays identical byte for byte. The
reason this module exists is that re-saving an L5X through an XML library strips CDATA and Logix
then rejects the file on import.

Checks
  * insert / replace / delete, then undo -> the ORIGINAL BYTES come back exactly
  * rung numbers are renumbered 0..N-1; other routines (incl. same-named routine in another
    program) are byte-identical
  * CDATA is preserved everywhere (count only changes by the new rung's own text/comment), and a
    comment containing ']]>' is escaped safely
  * CRLF and LF files both work; BOM kept
  * empty <RLLContent/> routine can be filled
  * invalid logic / positions / routine types / names are rejected with the file untouched
  * add_tags: each supported type, V37 vs V35 tag style copied from the file, program scope,
    '<Tags/>' expansion, duplicate / invalid / unsupported rejected
  * the same round-trip-to-original-bytes property on a real Studio export when one is present

Run with: python tests\\test_l5x_editor.py
Exits 0 and prints "ALL CHECKS PASSED" on success, non-zero otherwise.
"""
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from l5x_analyzer import l5x_editor as ed
from _l5x_fixtures import build_l5x

failures = []


def check(label, condition):
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)
    return condition


def parse(text):
    return ET.fromstring(text.encode("utf-8").lstrip(b"\xef\xbb\xbf"))


def raises(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except ed.L5XEditError as e:
        return str(e)
    return None


def main():
    base = build_l5x()
    NEW = [{"text": "XIC(Start)OTE(Run2);", "comment": "new rung"}]

    print("\n=== insert / replace / delete and undo -> original bytes ===")
    ins, info = ed.splice_rungs(base, "Main", NEW, position=1)
    check(f"insert reports 3 -> 4 rungs (got {info['rungs_before']} -> {info['rungs_after']})",
          (info["rungs_before"], info["rungs_after"]) == (3, 4))
    rungs = ed.list_rungs(ins, "Main")
    check(f"rung numbers are 0..3 in order (got {[r['number'] for r in rungs]})", [r["number"] for r in rungs] == [0, 1, 2, 3])
    check("new rung sits at position 1 with its text and comment",
          rungs[1]["text"] == NEW[0]["text"] and rungs[1]["comment"] == "new rung")
    check("old rung 1 moved to position 2 (text unchanged)", rungs[2]["text"] == "XIC(Run)TON(Timer1,?,?);")
    rep, _ = ed.splice_rungs(ins, "Main", [{"text": "XIC(X)OTE(Y);"}], position=1, remove_count=1)
    check("replace changes exactly that rung", ed.list_rungs(rep, "Main")[1]["text"] == "XIC(X)OTE(Y);"
          and len(ed.list_rungs(rep, "Main")) == 4)
    back, _ = ed.splice_rungs(rep, "Main", [], position=1, remove_count=1)
    check("insert -> replace -> delete returns the ORIGINAL BYTES", back == base)
    app, _ = ed.splice_rungs(base, "Main", NEW)  # position=None appends
    check("position=None appends at the end", ed.list_rungs(app, "Main")[-1]["text"] == NEW[0]["text"])
    multi, _ = ed.splice_rungs(base, "Main", [{"text": "NOP();"}, {"text": "NOP();"}], position=0)
    check("inserting two rungs at 0 renumbers the old rungs to 2..4",
          [r["number"] for r in ed.list_rungs(multi, "Main")] == [0, 1, 2, 3, 4])
    back2, _ = ed.splice_rungs(multi, "Main", [], position=0, remove_count=2)
    check("...and deleting them restores the original bytes", back2 == base)

    print("\n=== nothing outside the target routine changes ===")
    check("same-named routine in the other program is byte-identical",
          ed.list_rungs(ins, "Main", "Other")[0]["text"] == "NOP();"
          and ins[ins.index('<Program Name="Other"'):] == base[base.index('<Program Name="Other"'):])
    check("text before the routine is byte-identical", ins[:ins.index('<Routine Name="Main" Type="RLL">')]
          == base[:base.index('<Routine Name="Main" Type="RLL">')])
    check("ST routine and STRING tag text (CDATA) untouched",
          "<![CDATA[Count := Count + 1;]]>" in ins and "<![CDATA[Msg := 'it''s ok';]]>" in ins
          and "Hello$00" in ins)
    check("BOM and CRLF preserved", ins.startswith("﻿") and "\r\n" in ins and "\n" not in ins.replace("\r\n", ""))
    check("result is well-formed XML", parse(ins) is not None)
    check(f"CDATA count rose by exactly 2 for a rung with comment (was {base.count('<![CDATA[')}, now {ins.count('<![CDATA[')})",
          ins.count("<![CDATA[") == base.count("<![CDATA[") + 2)

    print("\n=== CDATA escaping and line endings ===")
    tricky, _ = ed.splice_rungs(base, "Main", [{"text": "NOP();", "comment": "end ]]> of cdata"}], position=0)
    check("a comment containing ']]>' stays well-formed and round-trips",
          parse(tricky) is not None and ed.list_rungs(tricky, "Main")[0]["comment"] == "end ]]]]><![CDATA[> of cdata")
    lf = build_l5x(eol="\n", bom=False)
    lf_ins, _ = ed.splice_rungs(lf, "Main", NEW, position=0)
    check("LF file stays LF, no BOM added", "\r" not in lf_ins and not lf_ins.startswith("﻿"))

    print("\n=== empty <RLLContent/> routine ===")
    filled, info = ed.splice_rungs(base, "EmptyRoutine", NEW + [{"text": "NOP();"}])
    check(f"empty routine filled with 2 rungs (got {info['rungs_after']})", info["rungs_after"] == 2
          and [r["number"] for r in ed.list_rungs(filled, "EmptyRoutine")] == [0, 1] and parse(filled) is not None)

    print("\n=== Add-On Instruction Logic routine ===")
    aoi, _ = ed.splice_rungs(base, "Logic", [{"text": "XIO(A)OTU(B);"}], aoi="Two_Arg_AOI")
    check("AOI Logic routine can be edited", [r["text"] for r in ed.list_rungs(aoi, "Logic", aoi="Two_Arg_AOI")]
          == ["XIC(A)OTE(B);", "XIO(A)OTU(B);"])

    print("\n=== rejected edits (nothing returned, nothing to write) ===")
    for label, kw in (
        ("rung text without ';'", dict(rungs=[{"text": "XIC(A)OTE(B)"}], position=0)),
        ("unbalanced brackets", dict(rungs=[{"text": "XIC(A;"}], position=0)),
        ("empty rung text", dict(rungs=[{"text": "  "}], position=0)),
        ("position past the end", dict(rungs=NEW, position=99)),
        ("negative position", dict(rungs=NEW, position=-1)),
        ("removing more rungs than exist", dict(rungs=[], position=2, remove_count=5)),
    ):
        check(f"rejects: {label}", raises(ed.splice_rungs, base, "Main", **kw) is not None)
    check("rejects an ST routine", "not ladder" in (raises(ed.splice_rungs, base, "Script", NEW) or ""))
    check("rejects an unknown routine", "not found" in (raises(ed.splice_rungs, base, "Nope", NEW) or ""))
    check("rejects an unknown program", "not found" in (raises(ed.splice_rungs, base, "Main", NEW, program="Nope") or ""))

    print("\n=== add_tags ===")
    tags = [
        {"name": "New_Bool", "data_type": "BOOL", "initial_value": 1, "description": "a flag ]]> here"},
        {"name": "New_Dint", "data_type": "DINT", "initial_value": 42},
        {"name": "New_Sint", "data_type": "SINT"},
        {"name": "New_Int", "data_type": "INT", "initial_value": -7},
        {"name": "New_Real", "data_type": "REAL", "initial_value": 0.5},
        {"name": "New_Timer", "data_type": "TIMER", "preset": 2500},
        {"name": "New_Counter", "data_type": "COUNTER", "preset": 10},
    ]
    added, tinfo = ed.add_tags(base, tags)
    root = parse(added)
    names = [t.get("Name") for t in root.findall("Controller/Tags/Tag")]
    check(f"all 7 tags added to the controller scope, existing ones kept (got {len(names)})",
          len(names) == 5 + 7 and set(tinfo["added"]) == {t["name"] for t in tags})
    by = {t.get("Name"): t for t in root.findall("Controller/Tags/Tag")}
    check("V37 style copied from the file (Class=Standard, OpcUaAccess=None)",
          by["New_Dint"].get("Class") == "Standard" and by["New_Dint"].get("OpcUaAccess") == "None")
    check("DINT value in L5K and Decorated form",
          "42" in added and 'DataType="DINT" Radix="Decimal" Value="42"' in added)
    check("REAL uses Studio's 3-digit exponent L5K form", "5.00000000e-001" in added)
    check("TIMER preset written to both forms", "[0,2500,0]" in added and 'Name="PRE" DataType="DINT" Radix="Decimal" Value="2500"' in added)
    check("every new Data value is inside CDATA",
          all(re.search(rf'<Tag Name="{t["name"]}".*?<Data Format="L5K">\r\n<!\[CDATA\[', added, re.S) for t in tags))
    check("tag description with ']]>' is escaped and the file stays well-formed",
          by["New_Bool"].find("Description") is not None and "]]]]><![CDATA[>" in added)
    check("everything before the insertion is byte-identical",
          added[:added.index("</Tags>")].startswith(base[:base.index("</Tags>")]))
    v35 = build_l5x(v37=False)
    v35_added, _ = ed.add_tags(v35, [{"name": "Plain", "data_type": "DINT"}])
    plain = [t for t in parse(v35_added).findall("Controller/Tags/Tag") if t.get("Name") == "Plain"][0]
    check("V35 style copied too (no Class / OpcUaAccess)", plain.get("Class") is None and plain.get("OpcUaAccess") is None)
    prog_added, pinfo = ed.add_tags(base, [{"name": "Prog_Flag", "data_type": "BOOL"}], program="MainProgram")
    pr = parse(prog_added)
    check("program scope adds to that program only",
          "Prog_Flag" in [t.get("Name") for t in pr.findall("Controller/Programs/Program[@Name='MainProgram']/Tags/Tag")]
          and "Prog_Flag" not in [t.get("Name") for t in pr.findall("Controller/Tags/Tag")])
    empty_prog, _ = ed.add_tags(base, [{"name": "In_Other", "data_type": "BOOL"}], program="Other")
    check("a self-closing <Tags/> (program 'Other') is expanded", "In_Other" in
          [t.get("Name") for t in parse(empty_prog).findall("Controller/Programs/Program[@Name='Other']/Tags/Tag")])
    sc = build_l5x(tags_self_closing=True)
    sc_added, _ = ed.add_tags(sc, [{"name": "First", "data_type": "DINT"}])
    check("a self-closing controller <Tags/> is expanded",
          [t.get("Name") for t in parse(sc_added).findall("Controller/Tags/Tag")] == ["First"])
    check("rejects a duplicate tag name", "already exists" in (raises(ed.add_tags, base, [{"name": "Start", "data_type": "BOOL"}]) or ""))
    check("same name allowed in program scope when only the controller has it",
          raises(ed.add_tags, base, [{"name": "Start", "data_type": "BOOL"}], program="Other") is None)
    for bad in ("1Tag", "My Tag", "A__B", "Trail_", "", "Has-Dash", "X" * 41):
        check(f"rejects tag name {bad!r}", raises(ed.add_tags, base, [{"name": bad, "data_type": "DINT"}]) is not None)
    check("rejects an unsupported type (UDT / STRING)", "not supported" in (raises(ed.add_tags, base, [{"name": "S", "data_type": "STRING"}]) or ""))
    check("rejects a bad initial value", raises(ed.add_tags, base, [{"name": "Z", "data_type": "DINT", "initial_value": "abc"}]) is not None)
    check("rejects duplicates within one request",
          raises(ed.add_tags, base, [{"name": "Twice", "data_type": "DINT"}, {"name": "Twice", "data_type": "DINT"}]) is not None)

    print("\n=== real Studio export: edit and undo must give back the original bytes ===")
    real = next((p for p in (Path(__file__).resolve().parents[2] / "Claude Directory" / "PLC_Copilot" / "THD_LG_CP2.L5X",)
                 if p.exists()), None)
    if real is None:
        print("  SKIPPED - no real L5X export found next to the project (synthetic coverage above still applies)")
    else:
        text = real.read_bytes().decode("utf-8")
        prog = re.search(r'<Program\b[^>]*\bName="([^"]+)"', text).group(1)
        routine = next(r for r in re.findall(r'<Routine\b[^>]*\bName="([^"]+)"[^>]*\bType="RLL"', text)
                       if len(ed.list_rungs(text, r, prog)) >= 2) if False else None
        # pick the first ladder routine in the first program that has rungs
        for rname in re.findall(r'<Routine\b[^>]*\bName="([^"]+)"', text[text.index(f'Name="{prog}"'):][:2_000_000]):
            try:
                if len(ed.list_rungs(text, rname, prog)) >= 2:
                    routine = rname
                    break
            except ed.L5XEditError:
                continue
        check(f"found a ladder routine to edit ({prog}/{routine})", routine is not None)
        if routine:
            n = len(ed.list_rungs(text, routine, prog))
            e1, _ = ed.splice_rungs(text, routine, [{"text": "XIC(Test_A)OTE(Test_B);", "comment": "t"}], position=1, program=prog)
            e2, _ = ed.splice_rungs(e1, routine, [{"text": "NOP();"}], position=1, remove_count=1, program=prog)
            e3, _ = ed.splice_rungs(e2, routine, [], position=1, remove_count=1, program=prog)
            check(f"{len(text):,} byte file: insert/replace/delete returns the original bytes exactly", e3 == text)
            check(f"rung count went {n} -> {n + 1} and back", len(ed.list_rungs(e1, routine, prog)) == n + 1)
            check("CDATA count of the real file only grew by the new rung's own 2 sections",
                  e1.count("<![CDATA[") == text.count("<![CDATA[") + 2)
            add, _ = ed.add_tags(text, [{"name": "Zz_Editor_Test", "data_type": "DINT"}])
            check("adding a tag to the real file keeps every other byte", add.replace(
                add[add.index('<Tag Name="Zz_Editor_Test"'):add.index("</Tag>", add.index('<Tag Name="Zz_Editor_Test"')) + len("</Tag>\r\n")], "") == text)

    print()
    if failures:
        print(f"=== {len(failures)} CHECK(S) FAILED ===")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("=== ALL CHECKS PASSED ===")
    sys.exit(0)


if __name__ == "__main__":
    main()
