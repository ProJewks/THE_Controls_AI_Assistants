"""
extract_routine_content must return EVERY rung that exists in the indexed routine.

History: it used to run a semantic search capped at 50 hits across the whole project and then
filter, so long routines came back with only some of their rungs (R08_ProductSortation: 7 of 16)
and nothing said rungs were missing.

This test does not hardcode counts. Ground truth is read straight from the L5X XML with its own
parser (no code shared with the indexer), then compared rung-for-rung against what
extract_routine_content returns, for EVERY routine:
  * same rung numbers (nothing missing, nothing extra), ascending order
  * identical rung text for each rung
  * rung comment preserved where the XML has one
  * 'summary' rung_count and 'full' rung chunks agree with the XML
Datasets:
  1. Synthetic project: a 120-rung routine (far beyond any search cap) plus a same-named routine
     in a second program, to prove programs don't bleed into each other.
  2. The real L5X exports found under 07 Compare (skipped loudly if none are present).

Run with: python tests\\test_extract_routine_completeness.py
Exits 0 and prints "ALL CHECKS PASSED" on success, non-zero otherwise.
"""
import asyncio
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from l5x_analyzer.l5x_vector_db import L5XVectorDatabase
from l5x_analyzer.l5x_mcp_integration import L5XSDKMCPIntegration

failures = []
checked_rungs = 0


def check(label, condition):
    if not condition:
        print(f"  [FAIL] {label}")
        failures.append(label)
    return condition


def ground_truth(l5x_path):
    """{(program, routine): {rung_number: (text, comment)}} for every RLL routine, from raw XML."""
    root = ET.parse(str(l5x_path)).getroot()
    truth = {}
    for program in root.iter("Program"):
        for routine in program.findall("Routines/Routine"):
            if routine.get("Type", "RLL") != "RLL":
                continue
            rungs = {}
            content = routine.find("RLLContent")
            for rung in (content.findall("Rung") if content is not None else []):
                text_el, comment_el = rung.find("Text"), rung.find("Comment")
                rungs[int(rung.get("Number"))] = (
                    text_el.text if text_el is not None and text_el.text is not None else "",
                    comment_el.text if comment_el is not None else None,
                )
            truth[(program.get("Name"), routine.get("Name"))] = rungs
    return truth


async def verify_project(integration, project_dir, l5x_files, label):
    global checked_rungs
    truth = {}
    for f in l5x_files:
        truth.update(ground_truth(f))
    print(f"\n=== {label}: {len(truth)} routine(s), {sum(len(v) for v in truth.values())} rung(s) in the XML ===")

    acd_like = str(project_dir)  # stem == the project name index_exported_l5x_files used
    bad_before = len(failures)
    for (program, routine), expected in sorted(truth.items()):
        tag = f"{program}/{routine}"
        res = await integration.extract_routine_content(acd_like, routine, program, "rungs_only")
        if not check(f"{tag}: rungs_only succeeded (got {res.get('error')})", res.get("success") is True):
            continue
        got = res["rungs"]
        nums = [r["rung_number"] for r in got]
        check(f"{tag}: rung numbers match the XML exactly - XML has {len(expected)}, got {len(got)}; "
              f"missing={sorted(set(expected) - set(nums))[:10]} extra={sorted(set(nums) - set(expected))[:10]}",
              sorted(nums) == sorted(expected) and len(nums) == len(set(nums)))
        check(f"{tag}: rungs are in ascending order", nums == sorted(nums))
        check(f"{tag}: total_rungs ({res.get('total_rungs')}) equals rungs returned ({len(got)})",
              res.get("total_rungs") == len(got))
        for r in got:
            want = expected.get(r["rung_number"])
            if want is None:
                continue
            checked_rungs += 1
            check(f"{tag} rung {r['rung_number']}: text differs from the XML",
                  r["logic"] == want[0])
            if want[1]:
                check(f"{tag} rung {r['rung_number']}: comment lost", r["comment"] == want[1])

        summary = await integration.extract_routine_content(acd_like, routine, program, "summary")
        check(f"{tag}: summary rung_count {summary.get('rung_count')} equals XML {len(expected)}",
              summary.get("rung_count") == len(expected))
        full = await integration.extract_routine_content(acd_like, routine, program, "full")
        full_rungs = [c for c in full.get("chunks", []) if c["type"] == "ladder_rung"]
        check(f"{tag}: full format has {len(expected)} rung chunks (got {len(full_rungs)})",
              len(full_rungs) == len(expected))
    print(f"  {'OK' if len(failures) == bad_before else 'PROBLEMS FOUND'} - {label}")


def synthetic_l5x():
    def routine(name, n):
        rungs = "".join(
            f'<Rung Number="{i}" Type="N">' + (f"<Comment>comment {i}</Comment>" if i % 7 == 0 else "")
            + f"<Text>XIC(Tag_{name}_{i})OTE(Out_{name}_{i});</Text></Rung>"
            for i in range(n))
        return f'<Routine Name="{name}" Type="RLL"><RLLContent>{rungs}</RLLContent></Routine>'

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<RSLogix5000Content SchemaRevision="1.0" SoftwareRevision="35.00" TargetName="Synth" TargetType="Controller">
<Controller Use="Target" Name="Synth" ProcessorType="5069-L340ER" MajorRev="35" MinorRev="17">
<Programs>
<Program Name="MainProgram"><Routines>{routine("LongRoutine", 120)}{routine("Shared", 4)}</Routines></Program>
<Program Name="Encoder"><Routines>{routine("Shared", 9)}</Routines></Program>
</Programs>
</Controller>
</RSLogix5000Content>
"""


async def main():
    work = Path(tempfile.mkdtemp(prefix="extract_completeness_"))
    try:
        db = L5XVectorDatabase(cache_dir=str(work / "cache"))
        integration = L5XSDKMCPIntegration(vector_db=db)

        synth_dir = work / "SynthLong"
        synth_dir.mkdir()
        (synth_dir / "Synth.L5X").write_text(synthetic_l5x(), encoding="utf-8")
        check("synthetic project indexed", db.index_exported_l5x_files(str(synth_dir)) is True)
        await verify_project(integration, synth_dir, [synth_dir / "Synth.L5X"], "Synthetic (120-rung routine)")

        compare_dir = Path(__file__).resolve().parents[2] / "Claude Directory" / "PLC_Copilot" / "07 Compare"
        candidates = sorted((compare_dir / "L5X_Exports").glob("*/*.L5X")) if compare_dir.exists() else []
        if not candidates:
            print("\n=== Real exports: SKIPPED - no L5X_Exports found under 07 Compare "
                  "(synthetic coverage above still applies) ===")
        seen = set()
        for i, l5x in enumerate(candidates):
            if l5x.parent.name in seen:  # one export per project is enough
                continue
            seen.add(l5x.parent.name)
            proj_dir = work / f"Real{i}_{l5x.parent.name}"
            proj_dir.mkdir()
            shutil.copy(l5x, proj_dir / l5x.name)
            check(f"{l5x.parent.name} indexed", db.index_exported_l5x_files(str(proj_dir)) is True)
            await verify_project(integration, proj_dir, [proj_dir / l5x.name], f"Real export {l5x.parent.name}")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"\nRungs compared one-by-one against the XML: {checked_rungs}")
    if checked_rungs == 0:
        failures.append("no rungs were compared - the test proved nothing")
    if failures:
        print(f"=== {len(failures)} CHECK(S) FAILED ===")
        for f in failures[:40]:
            print(f"  - {f}")
        sys.exit(1)
    print("=== ALL CHECKS PASSED ===")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
