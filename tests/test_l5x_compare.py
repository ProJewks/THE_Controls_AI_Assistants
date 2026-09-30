"""
Tests for l5x_analyzer/l5x_compare.py and the program-label fix in
SDKPoweredL5XAnalyzer.parse_routine_l5x.

Builds two small whole-controller L5X files (A baseline, B edited) in a temp folder and checks:
  * value-only tag changes are NOT reported as definition changes (only counted)
  * a rung insert is exactly one 'insert' op (later rungs aren't flagged as changed)
  * a replaced rung gets a token-level segment diff
  * same-named routines in different programs stay separate
  * module live I/O data is ignored, but a config change (RPI) is reported
  * tags added/removed and description changes are reported
  * parse_routine_l5x labels chunks with their real program and skips AOI-embedded routines

Run with: python tests\\test_l5x_compare.py
Exits 0 and prints "ALL CHECKS PASSED" on success, non-zero otherwise.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from l5x_analyzer.l5x_compare import compare_l5x_files, render_markdown
from l5x_analyzer.sdk_powered_analyzer import SDKPoweredL5XAnalyzer

failures = []


def check(label, condition):
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)


def rung(n, text, comment=None):
    c = f"<Comment>{comment}</Comment>" if comment else ""
    return f'<Rung Number="{n}" Type="N">{c}<Text>{text}</Text></Rung>'


def controller(main_rungs, encoder_rungs, tags, rpi="10000", io_value="1", modified="Fri Aug 07 2026"):
    tag_xml = "".join(tags)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="35.00" TargetName="Proj" TargetType="Controller">
<Controller Use="Target" Name="Proj" ProcessorType="5069-L340ER" MajorRev="35" MinorRev="17" LastModifiedDate="{modified}">
<DataTypes/>
<AddOnInstructionDefinitions>
<AddOnInstructionDefinition Name="MyAOI" Revision="1.0">
<Routines><Routine Name="Logic" Type="RLL"><RLLContent>{rung(0, "NOP();")}</RLLContent></Routine></Routines>
</AddOnInstructionDefinition>
</AddOnInstructionDefinitions>
<Modules>
<Module Name="Drive1" CatalogNumber="X">
<Communications><Connections>
<Connection Name="c1" RPI="{rpi}"><InputTag Name="Drive1:I"><Data Format="Decorated"><Structure><DataValueMember Name="Speed" Value="{io_value}"/></Structure></Data></InputTag></Connection>
</Connections></Communications>
</Module>
</Modules>
<Tags>{tag_xml}</Tags>
<Programs>
<Program Name="Encoder"><Routines><Routine Name="R100_MapInputs" Type="RLL"><RLLContent>{"".join(encoder_rungs)}</RLLContent></Routine></Routines></Program>
<Program Name="MainProgram"><Routines>
<Routine Name="R100_MapInputs" Type="RLL"><RLLContent>{"".join(main_rungs)}</RLLContent></Routine>
</Routines></Program>
</Programs>
</Controller>
</RSLogix5000Content>
"""


def tag(name, value="0", desc=None):
    d = f"<Description><![CDATA[{desc}]]></Description>" if desc else ""
    return (f'<Tag Name="{name}" TagType="Base" DataType="DINT" Radix="Decimal">{d}'
            f'<Data Format="L5K"><![CDATA[{value}]]></Data></Tag>')


def main():
    main_a = [rung(0, "XIC(A)OTE(B);"), rung(1, "XIC(C)OTE(D);", "keep"), rung(2, "XIC(E)OTE(F);"), rung(3, "XIC(G)OTE(H);")]
    main_b = [rung(0, "XIC(A)OTE(B);"), rung(1, "XIC(NEW)OTE(NEWOUT);"), rung(2, "XIC(C)OTE(D);", "keep"),
              rung(3, "XIC(E)OTE(F);"), rung(4, "XIC(G)OTE(H);")]  # rung inserted at 1, rest renumbered
    enc_a = [rung(0, "XIC(P)OTE(Q);"), rung(1, "XIC(R)MOV(1,S);")]
    enc_b = [rung(0, "XIC(P)OTE(Q);"), rung(1, "XIC(R)MOV(1,S)MOV(2700,T);")]
    tags_a = [tag("Same", "1"), tag("ValueOnly", "5"), tag("Removed"), tag("Desc", desc="old")]
    tags_b = [tag("Same", "1"), tag("ValueOnly", "99"), tag("Added"), tag("Desc", desc="new")]

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        fa, fb = tmp / "a.L5X", tmp / "b.L5X"
        fa.write_text(controller(main_a, enc_a, tags_a, rpi="25000", io_value="1"), encoding="utf-8")
        fb.write_text(controller(main_b, enc_b, tags_b, rpi="10000", io_value="777", modified="Thu Aug 20 2026"),
                      encoding="utf-8")
        r = compare_l5x_files(str(fa), str(fb))

        print("\n=== tags ===")
        ct = r["controller_tags"]
        check(f"removed tag reported (got {ct['only_in_a']})", ct["only_in_a"] == ["Removed"])
        check(f"added tag reported (got {ct['only_in_b']})", ct["only_in_b"] == ["Added"])
        check(f"description change reported as definition change (got {[c['name'] for c in ct['changed']]})",
              [c["name"] for c in ct["changed"]] == ["Desc"])
        check(f"value-only change is counted, not reported as a change (got {ct['value_only_changes']})",
              ct["value_only_changes"] == 1)

        print("\n=== modules ===")
        mods = r["modules"]
        check(f"RPI change reported as a config change (got {[c['name'] for c in mods['changed']]})",
              [c["name"] for c in mods["changed"]] == ["Drive1"])
        r_same_rpi = compare_l5x_files(str(fa), str(fa))
        check("identical file compares as identical", r_same_rpi["summary"]["identical"] is True)
        fc = tmp / "c.L5X"
        fc.write_text(controller(main_a, enc_a, tags_a, rpi="25000", io_value="555"), encoding="utf-8")
        r_io = compare_l5x_files(str(fa), str(fc))
        check(f"live I/O data alone is ignored (changed={r_io['modules']['changed']}, "
              f"live_only={r_io['modules']['live_io_data_only_changes']})",
              r_io["modules"]["changed"] == [] and r_io["modules"]["live_io_data_only_changes"] == 1)

        print("\n=== AOIs / header ===")
        check("unchanged AOI is not reported", r["aois"]["changed"] == [] and not r["aois"]["only_in_a"])
        check(f"LastModifiedDate shows in the header diff (got {list(r['header_differences'])})",
              "LastModifiedDate" in r["header_differences"])

        print("\n=== routines: same name in two programs stay separate ===")
        progs = r["programs"]["programs"]
        check(f"both programs compared (got {sorted(progs)})", sorted(progs) == ["Encoder", "MainProgram"])
        check("Encoder/R100_MapInputs changed", "R100_MapInputs" in progs["Encoder"]["routines_changed"])
        check("MainProgram/R100_MapInputs changed", "R100_MapInputs" in progs["MainProgram"]["routines_changed"])

        print("\n=== rung diffs ===")
        ops = progs["MainProgram"]["routines_changed"]["R100_MapInputs"]["ops"]
        check(f"one inserted rung is exactly one op (got {[o['op'] for o in ops]})",
              [o["op"] for o in ops] == ["insert"])
        check("insert op carries the new rung text", any("NEWOUT" in x for x in ops[0]["added"]))
        enc_ops = progs["Encoder"]["routines_changed"]["R100_MapInputs"]["ops"]
        check(f"edited rung is one replace op (got {[o['op'] for o in enc_ops]})",
              [o["op"] for o in enc_ops] == ["replace"])
        seg = enc_ops[0]["segments"][0]["changes"]
        check(f"token diff isolates the added instruction (got {seg})",
              len(seg) == 1 and "MOV ( 2700 , T )" in seg[0]["b"] and seg[0]["a"] == "")

        print("\n=== markdown render ===")
        md = render_markdown(r, "a.L5X", "b.L5X")
        check("markdown names the routines and the added tag",
              "MainProgram/R100_MapInputs" in md and "`Added`" in md)

        print("\n=== parse_routine_l5x: program labels and AOI routines (Bug C) ===")
        analyzer = SDKPoweredL5XAnalyzer()
        chunks = analyzer.parse_routine_l5x(str(fb))
        routine_chunks = [c for c in chunks if c.chunk_type.value == "routine"]
        labels = sorted((c.location.parent_program, c.name) for c in routine_chunks)
        check(f"routines carry their real program, AOI 'Logic' excluded (got {labels})",
              labels == [("Encoder", "R100_MapInputs"), ("MainProgram", "R100_MapInputs")])
        fallback = analyzer.parse_routine_l5x(str(fb), program_name="Fallback")
        check("a real program beats the fallback argument",
              {c.location.parent_program for c in fallback} == {"Encoder", "MainProgram"})

    print("\n=== conversion_hint picks the right advice ===")
    from l5x_analyzer.sdk_powered_analyzer import conversion_hint
    check("import-aborted error points at the import log, not a file lock",
          "import error log" in conversion_hint("XMLSrv_E_IMPORT_ABORTED_NO_CHANGES - The Import was cancelled"))
    check("a locked-file error mentions Studio 5000",
          "Studio 5000" in conversion_hint("The process cannot access the file because it is being used by another process"))

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
