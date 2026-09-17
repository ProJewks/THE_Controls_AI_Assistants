"""
Regression test for the exact-match tag cross-reference (l5x_analyzer/l5x_xref.py)
and its MCP-facing tools (find_tag_references, search_tag_references).

Fixture tests/_regression_fixtures/XrefProject/XrefRoutine.L5X exercises:
  - basic read (XIC) / write (OTE) classification
  - a branch bracket with two reads and one write
  - MOV (source read, destination write)
  - TON (the timer structure operand is a write)
  - JSR (operand 0 is a routine name, not a tag - must not be indexed)
  - an AOI call (unrecognized instruction - operands are tags with
    access='unknown', the call itself is reported in aoi_calls/possible_aoi_calls)
  - an array index with an identifier index (Arr[Idx].Bit - Idx is also its
    own reference) and a bit address (Sts.3)
  - tags named PV/IO/TIMER - the exact regression that would fail if anyone
    later wires the parsed instruction documentation into the xref's
    exclusion set instead of the curated-only plc_language.reserved_mnemonics()

XrefProjectB reuses the tag name Motor_1 to verify project_name scoping and
that indexing a second project doesn't contaminate the first project's xref
(the same invariant test_contamination_fix.py guards for chunks).

Run with: python test_tag_xref.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from l5x_analyzer.l5x_vector_db import L5XVectorDatabase
from l5x_analyzer.l5x_mcp_integration import L5XSDKMCPIntegration
from l5x_analyzer.l5x_xref import L5XTagXref

FIXTURES = Path(__file__).parent / "_regression_fixtures"
XREF_PROJECT = str(FIXTURES / "XrefProject")
XREF_PROJECT_B = str(FIXTURES / "XrefProjectB")

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        failures.append(label)


async def main():
    db = L5XVectorDatabase(cache_dir=str(Path(__file__).parent / "_regression_test_cache"))
    integration = L5XSDKMCPIntegration(vector_db=db)

    print("\n=== Indexing XrefProject ===")
    r = db.index_exported_l5x_files(XREF_PROJECT)
    check("XrefProject indexed successfully", r is True)

    # --- Direct L5XTagXref checks (project-scoped) -------------------------

    xref = db.get_xref(project_name="XrefProject")
    check("get_xref succeeded (not an error dict)", not isinstance(xref, dict))

    all_symbols = set(xref.by_symbol.keys())
    print(f"\n  Indexed symbols: {sorted(all_symbols)}")

    print("\n=== Instruction mnemonics must never appear as indexed symbols ===")
    for mnemonic in ("XIC", "XIO", "OTE", "MOV", "TON", "JSR"):
        check(f"{mnemonic} is not an indexed symbol", mnemonic not in all_symbols)

    print("\n=== Basic read/write classification ===")
    check("Motor_1.Running indexed", "Motor_1.Running" in all_symbols)
    check("Motor_1.Running is a read (XIC)",
          any(r.access == "read" for r in xref.lookup("Motor_1.Running", include_members=False)))
    check("Motor_1_Cmd is a write (OTE)",
          any(r.access == "write" for r in xref.lookup("Motor_1_Cmd", include_members=False)))

    print("\n=== Branch bracket: two reads, one write ===")
    check("Perm_A read", any(r.access == "read" for r in xref.lookup("Perm_A", include_members=False)))
    check("Perm_B read", any(r.access == "read" for r in xref.lookup("Perm_B", include_members=False)))
    check("Combined_Out write", any(r.access == "write" for r in xref.lookup("Combined_Out", include_members=False)))

    print("\n=== MOV: source read, destination write ===")
    check("Src_Val read", any(r.access == "read" for r in xref.lookup("Src_Val", include_members=False)))
    check("Dest_Val write", any(r.access == "write" for r in xref.lookup("Dest_Val", include_members=False)))

    print("\n=== TON: timer structure operand is a write ===")
    check("Delay_Tmr write", any(r.access == "write" for r in xref.lookup("Delay_Tmr", include_members=False)))

    print("\n=== JSR: operand 0 is a routine name, must NOT be indexed as a tag ===")
    check("SubRoutine is not an indexed symbol", "SubRoutine" not in all_symbols)

    print("\n=== AOI call: operands are tags (access=unknown), the call itself is visible ===")
    check("MyAOI itself is not a tag symbol", "MyAOI" not in all_symbols)
    check("MyAOI_Inst (AOI instance) is indexed", "MyAOI_Inst" in all_symbols)
    check("Motor_1 (base tag, from AOI operand) is indexed",
          any(r.base_tag == "Motor_1" for refs in xref.by_symbol.values() for r in refs))
    check("Speed_SP (AOI operand) is indexed", "Speed_SP" in all_symbols)
    check("MYAOI recorded in aoi_calls", "MYAOI" in xref.aoi_calls)

    print("\n=== Array index with identifier + bit address ===")
    check("Arr[Idx].Bit indexed (base=Arr)",
          any(r.symbol == "Arr[Idx].Bit" and r.base_tag == "Arr" for r in xref.by_symbol.get("Arr[Idx].Bit", [])))
    check("Idx indexed as its own reference", "Idx" in all_symbols)
    check("Sts.3 (bit address) indexed", "Sts.3" in all_symbols)

    print("\n=== Glossary-collision tags (PV/IO/TIMER) must still be indexed as tags ===")
    check("PV indexed as a tag", "PV" in all_symbols)
    check("IO indexed as a tag", "IO" in all_symbols)
    check("TIMER indexed as a tag", "TIMER" in all_symbols)
    check("Reg_Out write", any(r.access == "write" for r in xref.lookup("Reg_Out", include_members=False)))

    print("\n=== Case-insensitive lookup ===")
    check("lookup('motor_1.running') finds Motor_1.Running (case-insensitive)",
          len(xref.lookup("motor_1.running", include_members=False)) >= 1)

    print("\n=== include_members: asking for the base tag also returns its members ===")
    motor_1_with_members = xref.lookup("Motor_1", include_members=True)
    check("lookup('Motor_1', include_members=True) includes Motor_1.Running",
          any(r.symbol == "Motor_1.Running" for r in motor_1_with_members))

    # --- MCP-facing tool checks ---------------------------------------------

    print("\n=== find_tag_references MCP tool ===")
    result = await integration.find_tag_references("Motor_1_Cmd", project_name="XrefProject")
    check("find_tag_references succeeded", result.get("success") is True)
    check("find_tag_references reports a write reference",
          any(r["access"] == "write" for r in result.get("references", [])))
    check("find_tag_references includes limitations/coverage note", "limitations" in result)

    print("\n=== find_tag_references with access filter ===")
    write_only = await integration.find_tag_references("Combined_Out", project_name="XrefProject", access="write")
    check("access='write' filter returns only writes",
          write_only.get("success") is True and
          all(r["access"] == "write" for r in write_only.get("references", [])) and
          len(write_only.get("references", [])) >= 1)

    print("\n=== search_tag_references MCP tool (pattern search) ===")
    search_result = await integration.search_tag_references("^Motor_1", project_name="XrefProject")
    check("search_tag_references succeeded", search_result.get("success") is True)
    check("search_tag_references('^Motor_1') finds Motor_1 and Motor_1.Running and Motor_1_Cmd",
          {"Motor_1", "Motor_1.Running", "Motor_1_Cmd"} <= set(search_result.get("symbols", {}).keys()))

    print("\n=== find_tag_references for a project that hasn't been indexed must error clearly ===")
    missing = await integration.find_tag_references("Motor_1", project_name="NeverIndexedXrefProject")
    check("unindexed project lookup returns success=False", missing.get("success") is False)

    # --- Project scoping / invalidation across two indexed projects --------

    print("\n=== Indexing XrefProjectB (reuses tag name Motor_1) ===")
    r = db.index_exported_l5x_files(XREF_PROJECT_B)
    check("XrefProjectB indexed successfully", r is True)

    print("\n=== Re-indexing must refresh the xref, not silently keep a stale cached one ===")
    xref_a_after = db.get_xref(project_name="XrefProject")
    check("XrefProject's xref still resolves after indexing XrefProjectB", not isinstance(xref_a_after, dict))
    check("XrefProject's Motor_1_Cmd still present after XrefProjectB was indexed",
          "Motor_1_Cmd" in xref_a_after.by_symbol)

    xref_b = db.get_xref(project_name="XrefProjectB")
    check("get_xref(XrefProjectB) succeeded", not isinstance(xref_b, dict))
    check("XrefProjectB has its own output tag", "ProjectB_Only_Output" in xref_b.by_symbol)
    check("XrefProjectB's xref does NOT contain XrefProject-only tags (no cross-contamination)",
          "Motor_1_Cmd" not in xref_b.by_symbol)

    combined = db.get_xref(project_name=None)
    check("get_xref(project_name=None) combines both projects",
          not isinstance(combined, dict) and
          "Motor_1_Cmd" in combined.by_symbol and "ProjectB_Only_Output" in combined.by_symbol)

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
