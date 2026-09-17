"""
Regression test for validate_ladder_logic's ST-blindness, using the exact ST
code from today's R_DivertConfirmations routine (the same snippet that earlier
produced "SDK Build Error: No valid instructions found in rung N" for legitimate
IF/FOR/END_IF lines).
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


ST_CODE = """IF ConfirmInFlight THEN
\tTheScanner(IN_DP_Divert_Log := 0);
\tConfirmInFlight := 0;
END_IF;

FOR i := 1 TO 10 DO
\tIF ThirtyDT[i].OUT_Confirm AND ConfirmQueueCount < 20 THEN
\t\tConfirmSeqNo := ConfirmSeqNo + 1;
\t\tCASE ThirtyDT[i].OUT_ConfirmReason OF
\t\t\t1: ReasonStr := 'DIVERTED';
\t\t\t3: ReasonStr := 'FELLTHROUGH';
\t\tELSE
\t\t\tReasonStr := 'LOST';
\t\tEND_CASE;
\t\tMsg := CONCAT(Msg, DTOS(ConfirmSeqNo));
\tEND_IF;
END_FOR;

IF NOT ConfirmInFlight AND ConfirmQueueCount > 0 THEN
\tTheScanner(IN_DP_Divert_Log := 1);
\tConfirmInFlight := 1;
END_IF;"""


async def main():
    paths = os.environ["STUDIO5000_DOC_PATHS"].split(";")
    doc_root = {"v35": paths[0], "v36": paths[1], "v37": paths[2]}
    print("=== Constructing real Studio5000MCPServer ===")
    server = Studio5000MCPServer(doc_root)

    print("\n=== validate_ladder_logic WITHOUT language flag (old default behavior) ===")
    old_result = await server.validate_ladder_logic({
        "ladder_logic": ST_CODE,
        "instructions_used": ["IF", "FOR", "CASE", "CONCAT", "DTOS"]
    })
    old_errors = old_result.get('errors', [])
    print(f"  old-path error count: {len(old_errors)} (expected: still buggy without the language flag)")

    print("\n=== validate_ladder_logic WITH language='ST' (the fix) ===")
    new_result = await server.validate_ladder_logic({
        "ladder_logic": ST_CODE,
        "instructions_used": ["IF", "FOR", "CASE", "CONCAT", "DTOS"],
        "language": "ST"
    })
    new_errors = new_result.get('errors', [])
    print(f"  new-path errors: {new_errors}")
    check("no 'No valid instructions found in rung' errors with language='ST'",
          not any('valid instructions found in rung' in e for e in new_errors))
    check("no 'Unknown or invalid instruction' SDK-build errors with language='ST'",
          not any('SDK Build Error' in e for e in new_errors))
    check("a clear warning explains why SDK verification was skipped for ST",
          any('skipped for language=' in w for w in new_result.get('warnings', [])))

    print("\n=== A simple valid RLL rung must still validate normally (fix must not break RLL path) ===")
    rll_result = await server.validate_ladder_logic({
        "ladder_logic": "XIC(Start)OTE(Motor);",
        "instructions_used": ["XIC", "OTE"]
    })
    check(f"simple valid RLL rung still validates with instruction-level success (got instruction_validations={rll_result.get('instruction_validations')})",
          all(v.get('is_valid') for v in rll_result.get('instruction_validations', [])))

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
