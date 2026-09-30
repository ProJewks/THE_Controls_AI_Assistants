"""
End-to-end test of the staged ACD workflow against the real Logix Designer SDK.

    open_acd_workspace -> edit_l5x_rungs / add_l5x_tags -> validate_l5x_changes
                       -> commit_l5x_to_acd (dry run, then confirm) -> independent re-export

The rule being tested: NO ACD is created until commit_l5x_to_acd is called with confirm=true, and
the source ACD and the baseline export are never modified.

Checks
  * a workspace (baseline + working copy) is created and no ACD_Revisions folder exists yet
  * the source ACD and the baseline L5X are byte-identical after every stage
  * edit tools refuse the baseline and any non-working file
  * edits produce a valid working copy (CDATA intact), validation passes and shows the diff
  * the commit DRY RUN creates nothing - not even the ACD_Revisions folder
  * a working copy with damage (CDATA stripped) is BLOCKED and creates nothing
  * the confirmed commit creates <name>_r001.ACD, re-exports it and verifies it matches
  * an independent export of the new ACD contains exactly the edits (new rung + new tag)
  * a second confirmed commit gives _r002 and never overwrites _r001

Needs the Logix Designer SDK and a few minutes (each SDK open is ~20-30 s). Skipped if the SDK is
not installed.

Run with: python tests\\test_acd_workflow.py
Exits 0 and prints "ALL CHECKS PASSED" on success, non-zero otherwise.
"""
import asyncio
import hashlib
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from logix_designer_sdk import LogixProject
except ImportError:
    print("SKIPPED - Logix Designer SDK is not installed; the workflow could not be exercised end to end")
    sys.exit(0)

from l5x_analyzer import l5x_editor as ed
from l5x_analyzer.l5x_vector_db import L5XVectorDatabase
from l5x_analyzer.l5x_mcp_integration import L5XSDKMCPIntegration

failures = []


def check(label, condition):
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}", flush=True)
    if not condition:
        failures.append(label)
    return condition


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


PROGRAM_XML = """<Programs>
<Program Name="MainProgram" TestEdits="false" MainRoutineName="MainRoutine" Disabled="false" UseAsFolder="false">
<Tags/>
<Routines>
<Routine Name="MainRoutine" Type="RLL">
<RLLContent>
<Rung Number="0" Type="N">
<Comment>
<![CDATA[start the run bit]]>
</Comment>
<Text>
<![CDATA[XIC(Start)OTE(Run);]]>
</Text>
</Rung>
<Rung Number="1" Type="N">
<Text>
<![CDATA[XIC(Run)OTE(Indicator);]]>
</Text>
</Rung>
<Rung Number="2" Type="N">
<Text>
<![CDATA[XIO(Start)OTU(Run);]]>
</Text>
</Rung>
</RLLContent>
</Routine>
</Routines>
</Program>
</Programs>""".replace("\n", "\r\n")

TASK_XML = """<Tasks>
<Task Name="MainTask" Type="CONTINUOUS" Priority="10" Watchdog="500" DisableUpdateOutputs="false" InhibitTask="false">
<ScheduledPrograms>
<ScheduledProgram Name="MainProgram"/>
</ScheduledPrograms>
</Task>
</Tasks>""".replace("\n", "\r\n")


async def make_source_acd(tmp: Path) -> Path:
    """Build a small but real project: SDK-created controller + a program/routine/tags injected as text."""
    seed, seed_l5x = tmp / "seed.ACD", tmp / "seed.L5X"
    p = await LogixProject.create_new_project(str(seed), 35, "5069-L340ER", "Flow_Project")
    await p.save_as(str(seed_l5x), False, False)
    p.close()
    text = seed_l5x.read_bytes().decode("utf-8")
    text = text.replace("<Programs/>", PROGRAM_XML, 1).replace("<Tasks/>", TASK_XML, 1)
    text, _ = ed.add_tags(text, [{"name": "Start", "data_type": "BOOL"}, {"name": "Run", "data_type": "BOOL"},
                                 {"name": "Indicator", "data_type": "BOOL"}])
    src_l5x = tmp / "Flow_Project_source.L5X"
    src_l5x.write_bytes(text.encode("utf-8"))
    proj = await LogixProject.open_logix_project(str(src_l5x))  # imports the L5X
    acd = tmp / "Flow_Project.ACD"
    await proj.save_as(str(acd), False, False)
    proj.close()
    return acd


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="acd_workflow_"))
    try:
        print("\n=== setup: build a small source project with the SDK ===", flush=True)
        (tmp / "x").mkdir()
        acd = await make_source_acd(tmp / "x")
        check("source ACD created", acd.exists())
        src_hash = sha(acd)
        integ = L5XSDKMCPIntegration(vector_db=L5XVectorDatabase(cache_dir=str(tmp / "cache")))
        folder = acd.parent

        print("\n=== stage 1: open_acd_workspace ===", flush=True)
        ws = await integ.open_acd_workspace(str(acd))
        check(f"workspace opened ({ws.get('error', 'ok')})", ws.get("success") is True)
        baseline, work = Path(ws["baseline_l5x"]), Path(ws["working_l5x"])
        check("baseline and working copy exist in L5X_Exports/<name>/",
              baseline.exists() and work.exists() and baseline.parent.parent.name == "L5X_Exports")
        check("working copy name ends in _work, baseline does not", work.stem.endswith("_work") and not baseline.stem.endswith("_work"))
        check("working copy starts byte-identical to the baseline", sha(baseline) == sha(work))
        check("NO ACD_Revisions folder and no new ACD exists after opening", not (folder / "ACD_Revisions").exists())
        ov = ws["overview"]
        check(f"overview lists the routine and its 3 rungs (got {ov['programs']})",
              ov["programs"].get("MainProgram") == [{"routine": "MainRoutine", "type": "RLL", "rungs": 3}])
        base_hash = sha(baseline)

        print("\n=== stage 2: edits go to the working copy only ===", flush=True)
        r = await integ.edit_l5x_rungs(str(baseline), "MainRoutine", "insert", rungs=[{"text": "NOP();"}])
        check("edit tool refuses the BASELINE file", r.get("success") is False and "not a working copy" in r.get("error", ""))
        r = await integ.edit_l5x_rungs(str(tmp / "x" / "nothing.L5X"), "MainRoutine", "insert", rungs=[{"text": "NOP();"}])
        check("edit tool refuses a missing file", r.get("success") is False)
        r = await integ.add_l5x_tags(str(work), [{"name": "Lamp", "data_type": "BOOL", "description": "new lamp"}])
        check(f"add_l5x_tags ok ({r.get('error', 'ok')})", r.get("success") is True and r["validation"]["ok"] is True)
        r = await integ.edit_l5x_rungs(str(work), "MainRoutine", "insert", position=2,
                                       rungs=[{"text": "XIC(Run)OTE(Lamp);", "comment": "lamp follows run"}])
        check(f"insert rung ok ({r.get('error', 'ok')})", r.get("success") is True and r["validation"]["ok"] is True)
        check("edit result shows the rungs around the edit", [x["number"] for x in r["edit"]["rungs_around_edit"]][:2] == [1, 2])
        r = await integ.edit_l5x_rungs(str(work), "MainRoutine", "insert", rungs=[{"text": "XIC(Run)OTE(Lamp)"}])
        check("an invalid rung is rejected and the file is unchanged", r.get("success") is False)
        r = await integ.edit_l5x_rungs(str(work), "MainRoutine", "insert", rungs=[{"text": "XIC(Undefined_Tag)OTE(Lamp);"}])
        check("an undefined tag is a warning, not a failure", r.get("success") is True and r["validation"]["warnings"])
        r = await integ.edit_l5x_rungs(str(work), "MainRoutine", "delete", position=4)
        check("...and that rung can be deleted again", r.get("success") is True and not r["validation"]["warnings"])
        check("baseline is byte-identical after the edits", sha(baseline) == base_hash)
        check("source ACD is byte-identical after the edits", sha(acd) == src_hash)
        check("NO ACD_Revisions folder after editing", not (folder / "ACD_Revisions").exists())

        print("\n=== stage 3: validate_l5x_changes ===", flush=True)
        v = await integ.validate_l5x_changes(str(work))
        check("validation passes and reports ready_to_commit", v.get("ready_to_commit") is True)
        check(f"diff shows the changed routine and the new tag ({v['diff_summary']})",
              v["diff_summary"]["routines_changed"] == 1 and v["diff_summary"]["controller_tags"]["only_in_b"] == 1
              and "MainRoutine" in v["diff_markdown"] and "Lamp" in v["diff_markdown"])
        check("validate created no files", not (folder / "ACD_Revisions").exists())

        print("\n=== stage 4a: commit DRY RUN creates nothing ===", flush=True)
        d = await integ.commit_l5x_to_acd(str(work))
        check(f"dry run succeeds and names the ACD it would create ({d.get('would_create')})",
              d.get("success") is True and d.get("dry_run") is True and d["would_create"].endswith("Flow_Project_r001.ACD"))
        check("dry run created NO ACD_Revisions folder and no ACD", not (folder / "ACD_Revisions").exists())

        print("\n=== stage 4b: a damaged working copy is BLOCKED ===", flush=True)
        good_text = work.read_bytes()
        work.write_bytes(good_text.replace(b"<![CDATA[XIC(Run)OTE(Lamp);]]>", b"XIC(Run)OTE(Lamp);"))
        blocked = await integ.commit_l5x_to_acd(str(work), confirm=True)
        check(f"commit with CDATA stripped is blocked ({blocked.get('error', '')[:70]})",
              blocked.get("success") is False and blocked.get("blocked") is True)
        check("blocked commit created nothing", not (folder / "ACD_Revisions").exists())
        work.write_bytes(good_text)

        print("\n=== stage 4c: confirmed commit creates the ACD and verifies it ===", flush=True)
        c = await integ.commit_l5x_to_acd(str(work), confirm=True)
        check(f"commit succeeded ({c.get('error', 'ok')})", c.get("success") is True)
        new_acd = Path(c["output"])
        check("new ACD is <name>_r001.ACD under ACD_Revisions/<name>/",
              new_acd.name == "Flow_Project_r001.ACD" and new_acd.parent.parent.name == "ACD_Revisions" and new_acd.exists())
        ver = c.get("verification", {})
        check(f"verification re-exported the new ACD and it matches the working copy ({ver.get('message') or ver})",
              ver.get("verified") is True and not ver.get("differences"))
        check("source ACD still byte-identical after the commit", sha(acd) == src_hash)
        check("baseline still byte-identical after the commit", sha(baseline) == base_hash)
        check("the ACD name has no dashes / spaces / double underscores",
              all(ch.isalnum() or ch == "_" for ch in new_acd.stem) and "__" not in new_acd.stem)

        print("\n=== independent check: export the new ACD and read it ===", flush=True)
        out = tmp / "check.L5X"
        proj = await LogixProject.open_logix_project(str(new_acd))
        await proj.save_as(str(out), False, False)
        proj.close()
        root = ET.fromstring(out.read_bytes().lstrip(b"\xef\xbb\xbf"))
        rungs = [(r.get("Number"), (r.findtext("Text") or "").strip()) for r in
                 root.findall("Controller/Programs/Program/Routines/Routine[@Name='MainRoutine']/RLLContent/Rung")]
        check(f"the routine has the original 3 rungs plus the inserted one, in order (got {rungs})",
              [t for _, t in rungs] == ["XIC(Start)OTE(Run);", "XIC(Run)OTE(Indicator);", "XIC(Run)OTE(Lamp);", "XIO(Start)OTU(Run);"])
        check("the new tag exists in the new ACD",
              any(t.get("Name") == "Lamp" for t in root.findall("Controller/Tags/Tag")))

        print("\n=== a second commit is a new revision, never an overwrite ===", flush=True)
        first_hash = sha(new_acd)
        c2 = await integ.commit_l5x_to_acd(str(work), confirm=True, verify=False)
        check(f"second commit is Flow_Project_r002.ACD (got {Path(c2.get('output', 'x')).name})",
              c2.get("success") is True and Path(c2["output"]).name == "Flow_Project_r002.ACD")
        check("_r001.ACD was not touched", sha(new_acd) == first_hash)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"=== {len(failures)} CHECK(S) FAILED ===")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("=== ALL CHECKS PASSED ===")
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
