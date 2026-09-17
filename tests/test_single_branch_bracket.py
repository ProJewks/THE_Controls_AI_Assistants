"""
Regression test for the single-branch-bracket defect in validate_ladder_logic.

Found the hard way: a rung generated for THD_LG_CP2's FB_30DT_AOI redesign
(2026-09-16) - `[GEQ(State,30) LEQ(State,40) EQU(CommandPosition,0) ]XIC(...)...`
- passed validate_ladder_logic with zero errors, then failed a real Studio 5000
import with "Failed to set the 'Text' property (Syntax error found while
scanning import file.)" pointing at that exact rung. A '[...]' in RLL neutral
text exists to hold comma-separated parallel branches; a bracket with no
top-level comma is meaningless syntax Studio 5000's importer rejects outright,
but the validator's syntax check only ever counted '(' / ')' balance - it
never looked at '[' / ']' at all, so this whole defect class was invisible to
it. Fixed in sdk_verifier.py's new _validate_branch_brackets.

This test also covers the two ways a naive fix could go wrong: mistaking a
comma inside an instruction's own parameter list (e.g. the '0' in
'EQU(CommandPosition,0)') for a branch-separator comma, and mistaking an
array-index bracket (e.g. 'IN_Sensor[0]') for an empty/single branch group.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from verification.sdk_verifier import sdk_verifier

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        failures.append(label)


async def main():
    print("=== Single-branch bracket (the real bug that broke a real import) ===")
    r = await sdk_verifier.verify_ladder_logic(
        "[GEQ(State,30) LEQ(State,40) EQU(CommandPosition,0) ]XIC(Zone2_ReadyToReceive)TOF(Zone2_Charge_Timer,?,?);",
        {"controller_type": "5069-L350ERS2"},
    )
    check("single-branch bracket is now rejected", not r.success)
    check(
        "error code is SINGLE_BRANCH_BRACKET",
        any(e.code == "SINGLE_BRANCH_BRACKET" for e in r.errors),
    )

    print("\n=== Same rung, fixed (brackets removed - only one branch existed anyway) ===")
    r = await sdk_verifier.verify_ladder_logic(
        "GEQ(State,30)LEQ(State,40)EQU(CommandPosition,0)XIC(Zone2_ReadyToReceive)TOF(Zone2_Charge_Timer,?,?);",
        {"controller_type": "5069-L350ERS2"},
    )
    check("fixed rung (no brackets) passes", r.success)

    print("\n=== Legitimate two-branch bracket must NOT false-positive (real FB_MDR_AI2 rung 18) ===")
    r = await sdk_verifier.verify_ladder_logic(
        "XIC(I_Operational)XIO(O_Disable_Outputs)[[[XIO(IN_Right_to_LeftZone) ,XIC(Left_only_zone) ] "
        "XIC(Zone_Left_Ready_To_Receive) ,[XIC(IN_Right_to_LeftZone) ,XIC(Right_only_zone) ] "
        "XIC(Zone_Right_Ready_To_Receive) ] [OTE(Handshakes.0) ,OTE(Local_Upstream_Empty) ] "
        ",XIC(Downstream.0) OTE(Handshakes.1) ];",
        {"controller_type": "5069-L350ERS2"},
    )
    check("legitimate nested multi-branch rung still passes", r.success)

    print("\n=== Comma inside an instruction's own parameter list must not count as a branch separator ===")
    r = await sdk_verifier.verify_ladder_logic(
        "[XIC(A) EQU(X,0) ]OTE(Y);",
        {"controller_type": "5069-L350ERS2"},
    )
    check(
        "a bracket with an in-parameter comma but no real branch comma is still flagged",
        not r.success and any(e.code == "SINGLE_BRANCH_BRACKET" for e in r.errors),
    )

    print("\n=== Array-index bracket must not be mistaken for an empty branch group ===")
    r = await sdk_verifier.verify_ladder_logic(
        "XIC(IN_Sensor[0])OTE(Zone1_Occupied);",
        {"controller_type": "5069-L350ERS2"},
    )
    check("array indexing is exempt from the single-branch check", r.success)

    print("\n=== Unbalanced '[' must be caught (was previously undetected entirely) ===")
    r = await sdk_verifier.verify_ladder_logic(
        "[XIC(A) ,XIC(B)OTE(C);",
        {"controller_type": "5069-L350ERS2"},
    )
    check(
        "unclosed bracket is now caught",
        not r.success and any(e.code == "UNBALANCED_BRACKET" for e in r.errors),
    )

    print("\n=== RES must be recognized (was previously an UNKNOWN_INSTRUCTION false positive) ===")
    r = await sdk_verifier.verify_ladder_logic(
        "NEQ(State,20)RES(TMR_PositionTimeout);",
        {"controller_type": "5069-L350ERS2"},
    )
    check("RES is now a known instruction", r.success)

    if failures:
        print(f"\n=== {len(failures)} CHECK(S) FAILED ===")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\n=== ALL CHECKS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())
