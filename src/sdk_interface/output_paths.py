"""
Output path helpers for ACD/L5X conversion and comparison tools.

Rules (shared by export_acd_to_l5x, import_l5x_to_acd, compare_l5x_projects):
  * Outputs go into per-kind subfolders next to the source file, created on demand.
  * A returned path never exists yet - every new output gets a revision/timestamp
    in its name, so nothing is ever overwritten.
  * Protected targets (live project names, Assets folders) are refused.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

KIND_FOLDERS = {
    "l5x": "L5X_Exports",
    "acd": "ACD_Revisions",
    "compare": "Compare_Reports",
}

DEFAULT_PROTECTED_FILES = "THD_LG_CP2.ACD"

_REV_RE = re.compile(r"_r(\d{3,})$", re.IGNORECASE)
# Timestamps use an underscore between date and time: Studio 5000 project names may not contain
# dashes. The optional "-" is only for recognising files exported before this rule was enforced.
_TS_RE = re.compile(r"_\d{8}[-_]\d{6}(_r\d{3,})?$")
_INVALID_CHARS_RE = re.compile(r"[^A-Za-z0-9_]")
_MULTI_UNDERSCORE_RE = re.compile(r"_{2,}")
TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


def protected_names() -> set:
    """Lower-cased protected file names (env STUDIO5000_PROTECTED_FILES, ';' or ',' separated)."""
    raw = os.environ.get("STUDIO5000_PROTECTED_FILES", DEFAULT_PROTECTED_FILES)
    return {n.strip().lower() for n in re.split(r"[;,]", raw) if n.strip()}


def is_protected_target(path: Union[str, Path]) -> Optional[str]:
    """Return a reason string if `path` must not be written to, else None."""
    p = Path(path)
    if p.exists():
        return f"target already exists: {p}"
    if p.name.lower() in protected_names():
        return f"target name is protected: {p.name}"
    if any(part.lower() == "assets" for part in p.parts[:-1]):
        return f"target is inside a read-only Assets folder: {p}"
    return None


def resolve_output_dir(source_path: Union[str, Path], kind: str,
                       output_dir: Optional[Union[str, Path]] = None) -> Path:
    """
    Folder for a new output, created if missing.

    Default: <source_dir>/<Kind folder>/<SourceStem>/ . An explicit output_dir is used as-is.
    """
    if kind not in KIND_FOLDERS:
        raise ValueError(f"Unknown output kind '{kind}' (expected one of {sorted(KIND_FOLDERS)})")
    src = Path(source_path)
    if output_dir:
        out = Path(output_dir)
    else:
        out = _project_root(src) / KIND_FOLDERS[kind] / _base_stem(src.stem)
    out.mkdir(parents=True, exist_ok=True)
    return out


def _project_root(src: Path) -> Path:
    """Folder the output subfolders hang off. A source that already lives in one of our
    output folders (<root>/<Kind folder>/<name>/file) maps back to <root>, so exports,
    revisions and reports for one project stay together instead of nesting."""
    if src.parent.parent.name in KIND_FOLDERS.values():
        return src.parent.parent.parent
    return src.parent


def _strip_rev(stem: str) -> str:
    return _REV_RE.sub("", stem)


def _base_stem(stem: str) -> str:
    """Project name without an export timestamp or revision suffix (and made name-safe)."""
    return derive_base_name(stem)[0]


def derive_base_name(stem: str) -> tuple:
    """(valid project name, True if it had to be changed) from a file stem: the timestamp and
    revision suffixes we add are removed first, so only a genuinely invalid name counts as changed."""
    raw = _strip_rev(_TS_RE.sub("", stem))
    clean = sanitize_project_name(raw)
    return clean, clean != raw


def project_name_problems(name: str) -> list:
    """
    Why `name` can't be used as a Studio 5000 project name (empty list = fine).

    Rules (as found converting L5X -> ACD): cannot start with a number, no spaces, no special
    characters (dashes, periods, # @ $ and the like - letters, digits and underscore only), and no
    consecutive underscores. A trailing underscore is also flagged because our "_rNNN" revision
    suffix would turn it into consecutive underscores.
    """
    problems = []
    if not name:
        return ["name is empty"]
    if name[0].isdigit():
        problems.append("starts with a number")
    if " " in name:
        problems.append("contains a space")
    bad = sorted(set(_INVALID_CHARS_RE.findall(name)) - {" "})
    if bad:
        problems.append("contains special characters: " + " ".join(repr(c) for c in bad))
    if "__" in name:
        problems.append("contains consecutive underscores")
    if name.endswith("_"):
        problems.append("ends with an underscore")
    return problems


def sanitize_project_name(name: str) -> str:
    """Closest valid project name: invalid characters -> '_', underscore runs collapsed,
    leading digits prefixed with 'P_', trailing underscores dropped, never empty."""
    cleaned = _MULTI_UNDERSCORE_RE.sub("_", _INVALID_CHARS_RE.sub("_", name or "")).strip("_")
    if not cleaned:
        return "Project"
    return f"P_{cleaned}" if cleaned[0].isdigit() else cleaned


def next_revision_path(directory: Union[str, Path], stem: str, ext: str) -> Path:
    """<stem>_r001.<ext>, <stem>_r002.<ext>, ... - max existing revision + 1 (case-insensitive ext)."""
    directory = Path(directory)
    ext = ext.lstrip(".")
    base = _strip_rev(stem)
    pat = re.compile(rf"^{re.escape(base)}_r(\d{{3,}})\.{re.escape(ext)}$", re.IGNORECASE)
    highest = 0
    if directory.exists():
        for f in directory.iterdir():
            m = pat.match(f.name)
            if m:
                highest = max(highest, int(m.group(1)))
    return directory / f"{base}_r{highest + 1:03d}.{ext}"


def next_timestamped_path(directory: Union[str, Path], stem: str, ext: str,
                          now: Optional[datetime] = None) -> Path:
    """<stem>_<YYYYMMDD_HHMMSS>.<ext>; adds _rNNN if that exact name already exists."""
    directory = Path(directory)
    ext = ext.lstrip(".")
    ts = (now or datetime.now()).strftime(TIMESTAMP_FORMAT)
    candidate = directory / f"{stem}_{ts}.{ext}"
    n = 1
    while candidate.exists():
        n += 1
        candidate = directory / f"{stem}_{ts}_r{n:03d}.{ext}"
    return candidate


def versioned_l5x_path(acd_path: Union[str, Path], output_dir: Optional[Union[str, Path]] = None) -> Path:
    src = Path(acd_path)
    out = resolve_output_dir(src, "l5x", output_dir)
    return next_timestamped_path(out, _base_stem(src.stem), "L5X")


def versioned_acd_path(l5x_path: Union[str, Path], output_dir: Optional[Union[str, Path]] = None,
                       project_name: Optional[str] = None) -> Path:
    src = Path(l5x_path)
    out = resolve_output_dir(src, "acd", output_dir)
    return next_revision_path(out, sanitize_project_name(project_name) if project_name else _base_stem(src.stem), "ACD")


def versioned_compare_path(path_a: Union[str, Path], path_b: Union[str, Path], ext: str,
                           output_dir: Optional[Union[str, Path]] = None) -> Path:
    a, b = Path(path_a), Path(path_b)
    out = resolve_output_dir(a, "compare", output_dir)
    stem = f"{_base_stem(a.stem)}_vs_{_base_stem(b.stem)}"
    return next_timestamped_path(out, stem, ext)
