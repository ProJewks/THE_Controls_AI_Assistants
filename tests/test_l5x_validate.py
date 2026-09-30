"""
Tests for l5x_analyzer/l5x_validate.py - the pre-flight checks that run before any ACD is created.

Each check is exercised both ways: it must catch the defect it exists for, and it must NOT fire on
correct input (false positives would make the stage useless, so the AOI-operand rule is also run
over every AOI call in a real Studio export when one is present).

  * identical files validate clean
  * valid new rungs pass; new rungs using undefined tags give a WARNING (not a blocking error)
  * AOI call with the wrong operand count / a '?' operand -> blocking error (the exact defect in
    the TEST project: MDR_Control_AOI calls with 10 operands instead of 8)
  * CDATA stripped (the damage an XML-library round trip does) -> blocking error
  * rung numbering gap / missing ';' / unbalanced brackets -> blocking error
  * malformed XML -> blocking error
  * problems already present in the BASELINE are reported as pre-existing and do not block
  * moving rungs around without changing their text is not reported as a change

Run with: python tests\\test_l5x_validate.py
Exits 0 and prints "ALL CHECKS PASSED" on success, non-zero otherwise.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

from l5x_analyzer import l5x_editor as ed
from l5x_analyzer import l5x_validate as v
from _l5x_fixtures import build_l5x

failures = []


def check(label, condition):
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)
    return condition


def codes(issues):
    return sorted({i["code"] for i in issues})


def main():
    base = build_l5x()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        bpath = tmp / "base.L5X"
        bpath.write_bytes(base.encode("utf-8"))

        def run(edited_text, baseline=bpath):
            epath = tmp / "edited.L5X"
            epath.write_bytes(edited_text.encode("utf-8"))
            return v.validate_changes(str(baseline), str(epath))

        print("\n=== identical file ===")
        r = run(base)
        check(f"identical file is ok with nothing to report ({r['summary']})",
              r["ok"] and not r["introduced_errors"] and not r["preexisting_errors"] and not r["warnings"]
              and not r["changed_routines"])

        print("\n=== valid edits pass ===")
        good, _ = ed.splice_rungs(base, "Main", [{"text": "XIC(Start)XIO(Run)OTE(Local_Count);", "comment": "ok"}], position=1)
        r = run(good)
        check(f"valid new rung: ok, one routine changed, no warnings ({r['summary']})",
              r["ok"] and list(r["changed_routines"]) == ["MainProgram/Main"] and not r["warnings"])
        mod, _ = ed.splice_rungs(base, "Main", [{"text": "XIC(Local:1:I.Pt00.Data)OTE(Run);"}, {"text": "XIC(Local_Count.0)OTE(Timer1.DN);"}])
        check("module tags (Local:1:I.Pt00.Data) and member access don't trigger unknown-tag warnings",
              not run(mod)["warnings"])
        call_ok, _ = ed.splice_rungs(base, "Main", [{"text": "Two_Arg_AOI(AoiInst,Start,Run);"}])
        check("a correct AOI call (instance + 2 required operands) passes", run(call_ok)["ok"])
        moved, _ = ed.splice_rungs(base, "Main", [], position=0, remove_count=1)
        moved, _ = ed.splice_rungs(moved, "Main", [{"text": "XIC(Start)OTE(Run);", "comment": "start the run bit"}])
        r = run(moved)
        check(f"moving a rung to the end (same text) is not reported as a new/changed rung (got {r['changed_routines']})",
              not r["changed_routines"])

        print("\n=== warnings do not block ===")
        unk, _ = ed.splice_rungs(base, "Main", [{"text": "XIC(Never_Defined)OTE(Run);"}])
        r = run(unk)
        check("undefined tag in a NEW rung is a warning, not an error",
              r["ok"] and [w["code"] for w in r["warnings"]] == ["unknown-tag"] and "Never_Defined" in r["warnings"][0]["message"])
        check("...and pre-existing rungs are not scanned for unknown tags (baseline tags only warn when new)",
              "Start" not in str(r["warnings"]))

        print("\n=== blocking errors: AOI calls ===")
        for label, text, want in (
            ("too many operands", "Two_Arg_AOI(AoiInst,Start,Run,Extra);", "aoi-operand-count"),
            ("too few operands", "Two_Arg_AOI(AoiInst,Start);", "aoi-operand-count"),
            ("'?' operand with the right count", "Two_Arg_AOI(AoiInst,?,Run);", "unbound-operand"),
        ):
            bad, _ = ed.splice_rungs(base, "Main", [{"text": text}])
            r = run(bad)
            check(f"{label} -> blocked with '{want}' (got ok={r['ok']}, {codes(r['introduced_errors'])})",
                  not r["ok"] and want in codes(r["introduced_errors"]))
        # the exact TEST-project defect, scaled down: '?,?' sitting where the real operands belong and
        # the real operands pushed past the end (there: 10 operands where MDR_Control_AOI needs 8)
        defect, _ = ed.splice_rungs(base, "Main", [{"text": "Two_Arg_AOI(AoiInst,?,?,Start,Run);"}])
        r = run(defect)
        check(f"'?,?' inserted before the real operands (the TEST-project defect) is caught twice ({codes(r['introduced_errors'])})",
              not r["ok"] and {"aoi-operand-count", "unbound-operand"} <= set(codes(r["introduced_errors"])))

        print("\n=== blocking errors: CDATA, syntax, structure ===")
        stripped = good.replace("<![CDATA[Count := Count + 1;]]>", "Count := Count + 1;")
        r = run(stripped)
        check(f"ST line stripped of CDATA -> 'cdata-missing' ({codes(r['introduced_errors'])})",
              not r["ok"] and "cdata-missing" in codes(r["introduced_errors"]))
        import re
        stripped2 = re.sub(r"<!\[CDATA\[(\[5,'Hello.*?\])\]\]>", lambda m: m.group(1), good, flags=re.S)
        assert stripped2 != good, "test setup: STRING CDATA was not stripped"
        r = run(stripped2)
        check("STRING tag data stripped of CDATA -> 'cdata-missing'", not r["ok"] and "cdata-missing" in codes(r["introduced_errors"]))
        check("an element with child elements (Decorated data) is correctly NOT treated as missing CDATA",
              "cdata-missing" not in codes(run(good)["introduced_errors"]))
        gap = good.replace('<Rung Number="2" Type="N">', '<Rung Number="7" Type="N">', 1)
        r = run(gap)
        check(f"rung numbering gap -> 'rung-numbering' ({codes(r['introduced_errors'])})",
              not r["ok"] and "rung-numbering" in codes(r["introduced_errors"]))
        nosemi = good.replace("XIC(Start)XIO(Run)OTE(Local_Count);", "XIC(Start)XIO(Run)OTE(Local_Count)")
        r = run(nosemi)
        check("rung text missing ';' -> 'rung-syntax'", not r["ok"] and "rung-syntax" in codes(r["introduced_errors"]))
        unbal = good.replace("XIC(Start)XIO(Run)OTE(Local_Count);", "XIC(Start)XIO(Run)OTE(Local_Count;")
        r = run(unbal)
        check("unbalanced parentheses -> 'rung-syntax'", not r["ok"] and "rung-syntax" in codes(r["introduced_errors"]))
        r = run(good.replace("</RSLogix5000Content>", ""))
        check("malformed XML -> 'xml-parse'", not r["ok"] and codes(r["introduced_errors"]) == ["xml-parse"])

        print("\n=== problems already in the baseline don't block ===")
        broken_base = build_l5x(main_rungs=[("Two_Arg_AOI(AoiInst,Start);", None), ("XIC(Start)OTE(Run);", None)])
        bp2 = tmp / "broken_base.L5X"
        bp2.write_bytes(broken_base.encode("utf-8"))
        edit_ok, _ = ed.splice_rungs(broken_base, "Main", [{"text": "XIC(Run)OTE(Start);"}])
        r = run(edit_ok, baseline=bp2)
        check(f"baseline already had a bad AOI call: reported as pre-existing, edit still ok ({r['summary']})",
              r["ok"] and "aoi-operand-count" in codes(r["preexisting_errors"]) and not r["introduced_errors"])
        edit_bad, _ = ed.splice_rungs(broken_base, "Main", [{"text": "Two_Arg_AOI(AoiInst,Start,Run,Run);"}])
        r = run(edit_bad, baseline=bp2)
        check("...but a NEW bad call on top of it is still blocked", not r["ok"] and len(r["introduced_errors"]) == 1)
        cd_base = build_l5x().replace("<![CDATA[Count := Count + 1;]]>", "Count := Count + 1;")
        bp3 = tmp / "cdata_base.L5X"
        bp3.write_bytes(cd_base.encode("utf-8"))
        edit_cd, _ = ed.splice_rungs(cd_base, "Main", [{"text": "NOP();"}], position=0)
        r = run(edit_cd, baseline=bp3)
        check("a CDATA problem that was already in the baseline stays pre-existing after line numbers shift",
              r["ok"] and "cdata-missing" in codes(r["preexisting_errors"]))

        print("\n=== no false positives on a real Studio export ===")
        real = Path(__file__).resolve().parents[2] / "Claude Directory" / "PLC_Copilot" / "THD_LG_CP2.L5X"
        if not real.exists():
            print("  SKIPPED - no real L5X export found next to the project")
        else:
            r = v.validate_changes(str(real), str(real))
            check(f"real project validates clean against itself ({r['summary']})",
                  r["ok"] and not r["preexisting_errors"])
            text = real.read_bytes().decode("utf-8")
            import re
            prog = re.search(r'<Program\b[^>]*\bName="([^"]+)"', text).group(1)
            rname = next(n for n in re.findall(r'<Routine\b[^>]*\bName="([^"]+)"', text[text.index(f'Name="{prog}"'):][:2_000_000])
                         if not _raises(lambda n=n: ed.list_rungs(text, n, prog)))
            edited, _ = ed.splice_rungs(text, rname, [{"text": "NOP();", "comment": "validator smoke test"}], position=0, program=prog)
            ep = tmp / "real_edited.L5X"
            ep.write_bytes(edited.encode("utf-8"))
            r = v.validate_changes(str(real), str(ep))
            check(f"inserting a rung into {prog}/{rname} of the real file is ok ({r['summary']})", r["ok"] and not r["introduced_errors"])

    print()
    if failures:
        print(f"=== {len(failures)} CHECK(S) FAILED ===")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("=== ALL CHECKS PASSED ===")
    sys.exit(0)


def _raises(fn):
    try:
        fn()
        return False
    except ed.L5XEditError:
        return True


if __name__ == "__main__":
    main()
