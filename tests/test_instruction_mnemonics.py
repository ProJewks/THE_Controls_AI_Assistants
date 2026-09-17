"""
Regression test for the validator's instruction-allowlist fix.

Guards two things:

1. The "union, never replace" floor. The parsed Rockwell documentation index
   is NOT a superset of the old hardcoded COMMON_INSTRUCTIONS set - on v35,
   COP and JMP are both real, common instructions that the parsed index
   doesn't contain at all (confirmed directly against
   instruction_index_cache_v35.json), and v37's parsed index is additionally
   missing JSR, SBR and DTOS. A naive "replace the hardcoded set with the
   documentation index" would newly reject COP()/JMP()/MIN()/MAX()/GRT(),
   and on v37 also JSR()/SBR(). plc_language.mnemonics.known_instructions()
   must always include CURATED_MNEMONICS as a floor, regardless of what the
   documentation index for a given version does or doesn't contain.

2. Unknown instructions are warnings, not hard errors. The extraction regex
   in SDKVerifier._validate_instructions_fast matches any capitalized
   identifier followed by '(', which includes every AOI/UDT-instance call.
   A GTPS-style project calling FB_MDR_AI2(...) must still validate
   successfully, with the unrecognized name surfaced as a warning so a
   genuine typo stays visible without failing legitimate logic.

Run with: python test_instruction_mnemonics.py
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
from plc_language import instruction_mnemonics

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        failures.append(label)


# These are real, common instructions confirmed absent from at least one
# version's parsed documentation index (see module docstring). If any of
# these ever stop validating, the floor union has regressed.
NAIVE_SWAP_REGRESSIONS = ["COP", "JMP", "MIN", "MAX", "GRT", "JSR", "SBR"]


async def main():
    paths = os.environ["STUDIO5000_DOC_PATHS"].split(";")
    doc_root = {"v35": paths[0], "v36": paths[1], "v37": paths[2]}
    print("=== Constructing real Studio5000MCPServer (registers documented mnemonics) ===")
    server = Studio5000MCPServer(doc_root)

    print("\n=== Floor union: naive-swap regressions must stay recognized on every version ===")
    for version in ["v35", "v36", "v37", None]:
        known = instruction_mnemonics.known_instructions(version)
        for mnemonic in NAIVE_SWAP_REGRESSIONS:
            check(f"{mnemonic} recognized (version={version})", mnemonic in known)

    print("\n=== An AOI call must validate successfully with a warning, not a hard error ===")
    result = await server.validate_ladder_logic({
        "ladder_logic": "XIC(Start_PB)FB_MDR_AI2(FB_MDR_AI2_01,Speed_SP,Zone_Active);",
        "instructions_used": ["XIC"]
    })
    print(f"  is_valid: {result.get('is_valid')}")
    print(f"  warnings: {result.get('warnings')}")
    check("AOI call does not fail validation", result.get("is_valid") is True)
    check(
        "a warning names the unrecognized AOI call",
        any("FB_MDR_AI2" in w for w in result.get("warnings", []))
    )
    sdk_verification = result.get("sdk_verification", {})
    check(
        "SDK-level verification itself reports success (warning, not error)",
        sdk_verification.get("success") is True
    )

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
