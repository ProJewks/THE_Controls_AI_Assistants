"""
Regression test for the cross-project contamination bug found this session.

Reproduces the exact failure mode: two different "projects" (ProjectA, ProjectB)
each contain a routine with the SAME name ("SharedRoutineName") but different
content. Before the fix: indexing ProjectB after ProjectA wiped ProjectA's chunks
from chunks_data entirely (self.chunks_data = l5x_chunks, a wholesale replace),
while indexed_projects kept listing BOTH as present - so a query for ProjectA
would pass the "is this indexed?" check but silently return ProjectB's data.

Run with: python test_contamination_fix.py
Exits 0 and prints "ALL CHECKS PASSED" if the fix holds, non-zero otherwise.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from l5x_analyzer.l5x_vector_db import L5XVectorDatabase
from l5x_analyzer.l5x_mcp_integration import L5XSDKMCPIntegration

FIXTURES = Path(__file__).parent / "_regression_fixtures"
PROJECT_A = str(FIXTURES / "ProjectA")
PROJECT_B = str(FIXTURES / "ProjectB")

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        failures.append(label)


async def main():
    db = L5XVectorDatabase(cache_dir=str(Path(__file__).parent / "_regression_test_cache"))
    integration = L5XSDKMCPIntegration(vector_db=db)

    print("\n=== Indexing ProjectA (2 rungs) ===")
    r = db.index_exported_l5x_files(PROJECT_A)
    check("ProjectA indexed successfully", r is True)

    print("\n=== Indexing ProjectB (5 rungs) - historically this wiped ProjectA ===")
    r = db.index_exported_l5x_files(PROJECT_B)
    check("ProjectB indexed successfully", r is True)

    print("\n=== Both projects should still be listed as indexed ===")
    check("ProjectA in indexed_projects", "ProjectA" in db.indexed_projects)
    check("ProjectB in indexed_projects", "ProjectB" in db.indexed_projects)

    print("\n=== chunks_data should contain BOTH projects' chunks (not just the last-indexed one) ===")
    project_names_present = {getattr(c, 'project_name', None) for c in db.chunks_data}
    check(f"chunks_data has chunks from both projects (found: {project_names_present})",
          {'ProjectA', 'ProjectB'} <= project_names_present)

    print("\n=== get_project_overview for ProjectA must return ProjectA's own data, not ProjectB's ===")
    overview_a = await integration.get_project_overview(PROJECT_A)
    check("get_project_overview(ProjectA) succeeded", overview_a.get('success') is True)
    routines_a = overview_a.get('routines', [])
    check(f"get_project_overview(ProjectA) reports project_name=ProjectA (got: {overview_a.get('project_name')})",
          overview_a.get('project_name') == 'ProjectA')

    print("\n=== get_project_overview for ProjectB must return ProjectB's own data ===")
    overview_b = await integration.get_project_overview(PROJECT_B)
    check("get_project_overview(ProjectB) succeeded", overview_b.get('success') is True)
    check(f"get_project_overview(ProjectB) reports project_name=ProjectB (got: {overview_b.get('project_name')})",
          overview_b.get('project_name') == 'ProjectB')

    print("\n=== analyze_routine_structure WITHOUT acd_path on an ambiguous name must error clearly, not blend/guess ===")
    ambiguous = await integration.analyze_routine_structure("SharedRoutineName")
    check(f"ambiguous lookup returns success=False (got: {ambiguous})", ambiguous.get('success') is False)
    err_text = str(ambiguous.get('error', ''))
    check("ambiguous lookup's error mentions ambiguity", 'ambigu' in err_text.lower())

    print("\n=== analyze_routine_structure WITH acd_path=ProjectA must return the 2-rung version ===")
    scoped_a = await integration.analyze_routine_structure("SharedRoutineName", acd_path=PROJECT_A)
    check(f"scoped ProjectA lookup succeeded (got: {scoped_a})", scoped_a.get('success') is True)
    if scoped_a.get('success'):
        rung_count_a = scoped_a['analysis']['rung_count']
        check(f"ProjectA's SharedRoutineName has 2 rungs (got: {rung_count_a})", rung_count_a == 2)

    print("\n=== analyze_routine_structure WITH acd_path=ProjectB must return the 5-rung version ===")
    scoped_b = await integration.analyze_routine_structure("SharedRoutineName", acd_path=PROJECT_B)
    check(f"scoped ProjectB lookup succeeded (got: {scoped_b})", scoped_b.get('success') is True)
    if scoped_b.get('success'):
        rung_count_b = scoped_b['analysis']['rung_count']
        check(f"ProjectB's SharedRoutineName has 5 rungs (got: {rung_count_b})", rung_count_b == 5)

    print("\n=== extract_routine_content must honor acd_path (it used to search every project) ===")
    ext_a = await integration.extract_routine_content(PROJECT_A, "SharedRoutineName", output_format="rungs_only")
    check(f"extract(ProjectA) succeeded (got: {ext_a.get('error', 'ok')})", ext_a.get('success') is True)
    check(f"extract(ProjectA) returns ProjectA's 2 rungs (got: {ext_a.get('total_rungs')})",
          ext_a.get('total_rungs') == 2)
    ext_b = await integration.extract_routine_content(PROJECT_B, "SharedRoutineName", output_format="rungs_only")
    check(f"extract(ProjectB) returns ProjectB's 5 rungs (got: {ext_b.get('total_rungs')})",
          ext_b.get('total_rungs') == 5)
    ext_none = await integration.extract_routine_content(str(FIXTURES / "NeverIndexedProject.ACD"), "SharedRoutineName")
    check(f"extract with a non-matching acd_path refuses to blend projects (got: {ext_none})",
          ext_none.get('success') is False and set(ext_none.get('candidates', [])) == {'ProjectA', 'ProjectB'})

    print("\n=== search fallback must respect project_name (used to ignore it) ===")
    text_hits = db._text_search("SharedRoutineName", 50, None, "ProjectA")
    check(f"text search scoped to ProjectA returns only ProjectA chunks ({len(text_hits)} hits)",
          text_hits and all(h.project_name == 'ProjectA' for h in text_hits))

    print("\n=== get_project_overview for a NEVER-indexed project must error clearly, not substitute ===")
    fake_overview = await integration.get_project_overview(str(FIXTURES / "NeverIndexedProject"))
    check(f"unindexed project lookup returns success=False (got: {fake_overview})",
          fake_overview.get('success') is False)
    check("unindexed project error lists what IS indexed instead of silently substituting",
          set(fake_overview.get('indexed_projects', [])) == {'ProjectA', 'ProjectB'})

    print()
    if failures:
        print(f"=== {len(failures)} CHECK(S) FAILED ===")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("=== ALL CHECKS PASSED ===")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
