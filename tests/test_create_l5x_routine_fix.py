"""
Regression test for create_l5x_routine's silent canned-template fallback,
using the EXACT specification from this session that triggered it originally
(the R_DivertConfirmations routine spec, which the generator's small fixed
pattern library has no match for).

Also verifies: a real, simple, in-library warehouse-automation request (which
SHOULD match a real pattern) still succeeds normally - the fix must not turn
genuine successes into false failures.

Run with: python test_create_l5x_routine_fix.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

os.environ.setdefault("STUDIO5000_DOC_PATHS",
    r"C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000;"
    r"C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v36\Bin\Help\ENU\rs5000;"
    r"C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v37\Bin\Help\ENU\rs5000")

from mcp_server.studio5000_mcp_server import Studio5000MCPServer

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        failures.append(label)


async def main():
    paths = os.environ["STUDIO5000_DOC_PATHS"].split(";")
    doc_root = {"v35": paths[0], "v36": paths[1], "v37": paths[2]}

    print("=== Constructing real Studio5000MCPServer (this loads doc parsers, may take a bit) ===")
    server = Studio5000MCPServer(doc_root)
    print("Server constructed.")

    complex_spec = (
        "Write a Structured Text (ST) routine named R_DivertConfirmations, language type ST (not ladder). "
        "Watches every carton-tracking AOI instance on the MABS line for a confirmable outcome and feeds "
        "them into FB_THE_SCN's existing confirmation handshake, one message at a time, spread across scans."
    )

    print("\n=== create_l5x_routine with today's complex out-of-library ST specification ===")
    result_complex = await server.create_l5x_routine({
        "name": "R_DivertConfirmations",
        "controller_name": "THD_LG_CP2",
        "specification": complex_spec,
        "save_path": None
    })
    print(f"  result: success={result_complex.get('success')}, error={result_complex.get('error', '')[:150]}")
    check("complex out-of-library spec now reports success=False (was silently success=True before the fix)",
          result_complex.get('success') is False)
    check("failure message explains the pattern-matching limitation, not a stack trace",
          'pattern' in str(result_complex.get('error', '')).lower()
          or 'usable ladder rungs' in str(result_complex.get('error', '')).lower())
    check("no canned Start_Test/Test_Timer content leaked into the response",
          'Start_Test' not in str(result_complex))

    print("\n=== create_l5x_routine explicitly requesting language='ST' must be rejected clearly ===")
    result_st = await server.create_l5x_routine({
        "name": "AnySTRoutine",
        "specification": "trivial",
        "language": "ST"
    })
    print(f"  result: success={result_st.get('success')}, error={result_st.get('error', '')[:150]}")
    check("explicit ST request is rejected rather than silently generating RLL",
          result_st.get('success') is False and 'not supported' in str(result_st.get('error', '')).lower())

    print("\n=== create_l5x_routine with a simple in-library request should still genuinely succeed ===")
    result_simple = await server.create_l5x_routine({
        "name": "ConveyorTest",
        "controller_name": "THD_LG_CP2",
        "specification": "Simple conveyor motor start/stop control with a photo eye and a start/stop pushbutton"
    })
    print(f"  result: success={result_simple.get('success')}, rungs_created={result_simple.get('rungs_created')}")
    check("simple in-library conveyor request still succeeds (fix must not break real successes)",
          result_simple.get('success') is True)

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
