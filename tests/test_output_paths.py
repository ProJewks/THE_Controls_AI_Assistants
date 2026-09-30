"""
Tests for sdk_interface/output_paths.py - the naming/folder rules behind export_acd_to_l5x,
import_l5x_to_acd and compare_l5x_projects.

Checks: folders are created on demand, new outputs always get a fresh revision/timestamp
name and never collide with an existing file, and protected targets are refused.

Run with: python tests\\test_output_paths.py
Exits 0 and prints "ALL CHECKS PASSED" on success, non-zero otherwise.
"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sdk_interface import output_paths as op

failures = []


def check(label, condition):
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}")
    if not condition:
        failures.append(label)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        acd = tmp / "Job" / "MyProject.ACD"
        acd.parent.mkdir()
        acd.write_bytes(b"x")

        print("\n=== default folders are created next to the source ===")
        out = op.resolve_output_dir(acd, "l5x")
        check(f"L5X folder is <src>/L5X_Exports/<stem> (got {out})",
              out == acd.parent / "L5X_Exports" / "MyProject" and out.is_dir())
        check("ACD folder is ACD_Revisions",
              op.resolve_output_dir(acd, "acd").parent.name == "ACD_Revisions")
        check("compare folder is Compare_Reports",
              op.resolve_output_dir(acd, "compare").parent.name == "Compare_Reports")
        custom = tmp / "elsewhere" / "deep"
        check("explicit output_dir is used and created",
              op.resolve_output_dir(acd, "l5x", custom) == custom and custom.is_dir())
        try:
            op.resolve_output_dir(acd, "bogus")
            check("unknown kind raises", False)
        except ValueError:
            check("unknown kind raises", True)

        print("\n=== ACD revisions increment and never reuse a name ===")
        l5x = tmp / "Job" / "MyProject_20260930_121500.L5X"
        l5x.write_text("<x/>")
        p1 = op.versioned_acd_path(l5x)
        check(f"first revision is _r001 (got {p1.name})", p1.name == "MyProject_r001.ACD")
        p1.write_bytes(b"1")
        p2 = op.versioned_acd_path(l5x)
        check(f"second revision is _r002 (got {p2.name})", p2.name == "MyProject_r002.ACD")
        p2.write_bytes(b"2")
        (p1.parent / "MyProject_r007.ACD").write_bytes(b"7")
        p3 = op.versioned_acd_path(l5x)
        check(f"next revision follows the highest existing one (got {p3.name})", p3.name == "MyProject_r008.ACD")
        check("a custom project_name is honored",
              op.versioned_acd_path(l5x, project_name="Renamed").name == "Renamed_r001.ACD")
        check("revision suffix is not stacked when the source is itself a revision",
              op.versioned_acd_path(tmp / "Job" / "MyProject_r002.L5X").name == "MyProject_r008.ACD")

        print("\n=== timestamped L5X names never collide ===")
        fixed = datetime(2026, 9, 30, 12, 15, 0)
        t1 = op.next_timestamped_path(out, "MyProject", "L5X", now=fixed)
        check(f"timestamp name (got {t1.name})", t1.name == "MyProject_20260930_121500.L5X")
        t1.write_text("a")
        t2 = op.next_timestamped_path(out, "MyProject", "L5X", now=fixed)
        check(f"same-second collision gets an _rNNN suffix (got {t2.name})",
              t2.name == "MyProject_20260930_121500_r002.L5X" and not t2.exists())
        v = op.versioned_l5x_path(acd)
        check("versioned_l5x_path returns a path that does not exist", not v.exists() and v.parent == out)

        print("\n=== compare report names ===")
        c = op.versioned_compare_path(acd, tmp / "Job" / "Other.ACD", "md")
        check(f"compare name contains both stems (got {c.name})",
              c.name.startswith("MyProject_vs_Other_") and c.suffix == ".md")

        print("\n=== Studio 5000 project-name rules (no leading digit/spaces/special chars/double underscores) ===")
        check("valid name has no problems", op.project_name_problems("THD_Lacey_CP1") == [])
        for bad, why in (("1Sorter", "number"), ("My Project", "space"), ("A-B", "special"), ("A.B", "special"),
                         ("A#B", "special"), ("A@B", "special"), ("A$B", "special"),
                         ("A__B", "consecutive"), ("Sorter_", "underscore"), ("", "empty")):
            check(f"{bad!r} is rejected ({why})", any(why in p for p in op.project_name_problems(bad)))
        for raw in ("1Sorter", "My Project", "A-B", "A.B", "A#B", "A__B", "Sorter_", "Bad@na$me", "  ", "THD_Lacey_CP1"):
            check(f"sanitize_project_name({raw!r}) -> valid name ({op.sanitize_project_name(raw)!r})",
                  op.project_name_problems(op.sanitize_project_name(raw)) == [])

        print("\n=== every generated file name obeys the rules (the old timestamps used a dash) ===")
        awkward = tmp / "Job" / "My Project-v2 #1 (copy).ACD"
        awkward.write_bytes(b"x")
        gen_l5x = op.versioned_l5x_path(awkward)
        check(f"L5X export from an awkward ACD name is compliant (got {gen_l5x.name})",
              op.project_name_problems(gen_l5x.stem) == [])
        gen_l5x.write_text("<x/>")
        gen_acd = op.versioned_acd_path(gen_l5x)
        check(f"ACD revision from that L5X is compliant (got {gen_acd.name})",
              op.project_name_problems(gen_acd.stem) == [])
        check(f"ACD revision still ends in _r001 (got {gen_acd.name})", gen_acd.stem.endswith("_r001"))
        check("a user-supplied project_name is sanitized too",
              op.project_name_problems(op.versioned_acd_path(gen_l5x, project_name="Bad Name-1").stem) == [])
        check("date and time are joined by an underscore, never a dash",
              "-" not in op.next_timestamped_path(out, "X", "L5X").name)
        legacy = tmp / "Job" / "Legacy_20260930-121500.L5X"
        check("older dashed-timestamp exports are still recognised and cleaned",
              op.derive_base_name(legacy.stem) == ("Legacy", False))
        check("derive_base_name flags a genuinely invalid name as changed",
              op.derive_base_name("My Project") == ("My_Project", True))

        print("\n=== protected targets are refused ===")
        check("existing file is refused", op.is_protected_target(acd) is not None)
        live = tmp / "Job" / "THD_LG_CP2.ACD"
        check("live project name is refused even when absent", op.is_protected_target(live) is not None)
        check("case-insensitive protected name", op.is_protected_target(tmp / "thd_lg_cp2.acd") is not None)
        assets = tmp / "Assets" / "New.ACD"
        check("anything under Assets is refused", op.is_protected_target(assets) is not None)
        check("a fresh ordinary path is allowed", op.is_protected_target(tmp / "Job" / "Fresh.ACD") is None)
        os.environ["STUDIO5000_PROTECTED_FILES"] = "Foo.ACD; Bar.ACD"
        try:
            check("env override replaces the protected list",
                  op.is_protected_target(tmp / "bar.acd") is not None
                  and op.is_protected_target(tmp / "THD_LG_CP2.ACD") is None)
        finally:
            del os.environ["STUDIO5000_PROTECTED_FILES"]

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
