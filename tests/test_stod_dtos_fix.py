"""
Regression test for the instruction-name extraction bug: titles like
"DINT to String (DTOS)" and "String to DINT (STOD)" were previously indexed
under "DINT" (the first ALL-CAPS run in the title) instead of their real
abbreviation in parentheses. Requires stale instruction_index_cache_*.json
files to have been cleared first so this actually re-parses with the fix.
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
    print("=== Constructing real Studio5000MCPServer (fresh parse, no stale cache) ===")
    server = Studio5000MCPServer(doc_root)

    print("\n=== get_instruction('DTOS') ===")
    dtos = await server.get_instruction("DTOS")
    print(f"  {dtos}")
    check("DTOS is now found", dtos is not None)

    print("\n=== get_instruction('STOD') ===")
    stod = await server.get_instruction("STOD")
    print(f"  {stod}")
    check("STOD is now found", stod is not None)

    print("\n=== validate_ladder_logic no longer reports DTOS as invalid ===")
    val = await server.validate_ladder_logic({
        "ladder_logic": "Msg := CONCAT(Msg, DTOS(ConfirmSeqNo));",
        "instructions_used": ["CONCAT", "DTOS"],
        "language": "ST"
    })
    inst_val = {v['instruction']: v['is_valid'] for v in val.get('instruction_validations', [])}
    print(f"  instruction_validations: {inst_val}")
    check("DTOS validates as a real instruction now", inst_val.get('DTOS') is True)

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
