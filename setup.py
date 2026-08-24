#!/usr/bin/env python3
"""
One-command installer for the Studio 5000 AI Assistant MCP server.

Run this after cloning the repo:

    python setup.py

It will:
  1. Check you're on Python 3.12 (required by the Studio 5000 SDK)
  2. Detect (or let you pick) which Studio 5000 Logix Designer version to use
     - Defaults to v35, but any installed version (v36, v37, v38, ...) works
  3. Install Python dependencies from requirements.txt
  4. Find and install the Studio 5000 Logix Designer SDK wheel, if present
  5. Generate ready-to-use MCP config files with the correct paths for THIS
     machine (mcp_config.local.json, claude_desktop_config.snippet.json,
     and a project-level .mcp.json for Claude Code)
  6. Optionally write the server straight into your Claude Desktop config
  7. Run the built-in --test to confirm everything works

Useful flags:
    python setup.py --version 36          # use a specific Studio 5000 version
    python setup.py --yes                 # accept every default, no prompts
    python setup.py --write-claude-desktop  # merge into Claude Desktop's config
    python setup.py --skip-sdk            # skip installing the SDK wheel
    python setup.py --skip-deps           # skip "pip install -r requirements.txt"
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SERVER_SCRIPT = REPO_ROOT / "src" / "mcp_server" / "studio5000_mcp_server.py"
DEFAULT_VERSION = "35"

PROGRAM_FILES_ROOTS = [
    Path(r"C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU"),
    Path(r"C:\Program Files\Rockwell Software\Studio 5000\Logix Designer\ENU"),
]
SDK_ROOT = Path(r"C:\Users\Public\Documents\Studio 5000\Logix Designer SDK\python")
CLAUDE_DESKTOP_CONFIG = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"


def doc_root_for(version, base=None):
    base = base or PROGRAM_FILES_ROOTS[0]
    return base / f"v{version}" / "Bin" / "Help" / "ENU" / "rs5000"


def discover_versions():
    found = {}
    for root in PROGRAM_FILES_ROOTS:
        if not root.exists():
            continue
        for entry in root.iterdir():
            m = re.fullmatch(r"v(\d+)", entry.name, re.IGNORECASE)
            if not m or not entry.is_dir():
                continue
            candidate = entry / "Bin" / "Help" / "ENU" / "rs5000"
            if (candidate / "17691.htm").exists():
                found[m.group(1)] = candidate
    return found


def find_sdk_wheel():
    if not SDK_ROOT.exists():
        return None
    wheels = sorted(SDK_ROOT.glob("logix_designer_sdk-*-py3-none-any.whl"))
    return wheels[-1] if wheels else None


def choose_version(requested, non_interactive):
    versions = discover_versions()

    if requested:
        if requested in versions:
            print(f"Using Studio 5000 v{requested} (auto-detected at {versions[requested]})")
            return requested, versions[requested]
        guess = doc_root_for(requested)
        print(f"Studio 5000 v{requested} wasn't auto-detected; assuming the default install path:\n  {guess}")
        return requested, guess

    if versions:
        print("Detected Studio 5000 Logix Designer installation(s):")
        for v in sorted(versions, key=int):
            marker = "  <- default" if v == DEFAULT_VERSION else ""
            print(f"  v{v}   {versions[v]}{marker}")
        default = DEFAULT_VERSION if DEFAULT_VERSION in versions else sorted(versions, key=int)[-1]
        if non_interactive:
            return default, versions[default]
        typed = input(f"\nWhich version should the assistant use? [{default}]: ").strip() or default
        if typed in versions:
            return typed, versions[typed]
        print(f"v{typed} wasn't in the detected list; using the standard install path guess for it.")
        return typed, doc_root_for(typed)

    print("No Studio 5000 installation was auto-detected on this machine.")
    if non_interactive:
        print(f"Falling back to the default: v{DEFAULT_VERSION}")
        return DEFAULT_VERSION, doc_root_for(DEFAULT_VERSION)
    typed = input(f"Enter your Studio 5000 Logix Designer major version number [{DEFAULT_VERSION}]: ").strip() or DEFAULT_VERSION
    return typed, doc_root_for(typed)


def run(cmd, **kwargs):
    print(f"$ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, **kwargs)


def check_python():
    if sys.version_info[:2] != (3, 12):
        print(
            f"WARNING: You're running Python {sys.version_info.major}.{sys.version_info.minor}. "
            "The Studio 5000 SDK requires Python 3.12 specifically. "
            "Install Python 3.12 and re-run this script with it (e.g. `py -3.12 setup.py`) "
            "if the SDK install step below fails."
        )


def install_dependencies(skip_deps):
    if skip_deps:
        print("Skipping dependency install (--skip-deps).")
        return
    run([sys.executable, "-m", "pip", "install", "-r", str(REPO_ROOT / "requirements.txt")], check=True)


def install_sdk(skip_sdk):
    if skip_sdk:
        print("Skipping Studio 5000 SDK install (--skip-sdk).")
        return None
    wheel = find_sdk_wheel()
    if not wheel:
        print(
            "Could not find the Studio 5000 Logix Designer SDK wheel at:\n"
            f"  {SDK_ROOT}\\logix_designer_sdk-*-py3-none-any.whl\n"
            "Skipping .ACD file support — documentation search and L5X generation still work."
        )
        return None
    run([sys.executable, "-m", "pip", "install", str(wheel)], check=True)
    return wheel


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {path}")


def build_configs(doc_root, sdk_wheel):
    env = {
        "STUDIO5000_DOC_PATH": str(doc_root),
    }
    if sdk_wheel or SDK_ROOT.exists():
        env["STUDIO5000_SDK_PATH"] = str(SDK_ROOT)

    mcp_config = {
        "mcpServers": {
            "studio5000-docs": {
                "command": sys.executable,
                "args": [str(SERVER_SCRIPT), "--doc-root", str(doc_root)],
                "cwd": str(REPO_ROOT),
            }
        }
    }
    write_json(REPO_ROOT / "mcp_config.local.json", mcp_config)

    claude_desktop_snippet = {
        "mcpServers": {
            "studio5000-ai-assistant": {
                "command": sys.executable,
                "args": [str(SERVER_SCRIPT)],
                "cwd": str(REPO_ROOT),
                "env": env,
            }
        }
    }
    write_json(REPO_ROOT / "claude_desktop_config.snippet.json", claude_desktop_snippet)

    # Claude Code project-scope config
    write_json(REPO_ROOT / ".mcp.json", claude_desktop_snippet)

    return claude_desktop_snippet


def maybe_write_claude_desktop(snippet, write_flag, non_interactive):
    if not write_flag:
        if non_interactive:
            return
        answer = input(
            f"\nMerge this server straight into Claude Desktop's config?\n  {CLAUDE_DESKTOP_CONFIG}\n[y/N]: "
        ).strip().lower()
        if answer != "y":
            print("Skipped. Use claude_desktop_config.snippet.json to add it manually.")
            return

    CLAUDE_DESKTOP_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if CLAUDE_DESKTOP_CONFIG.exists():
        backup = CLAUDE_DESKTOP_CONFIG.with_suffix(".json.bak")
        backup.write_bytes(CLAUDE_DESKTOP_CONFIG.read_bytes())
        print(f"Backed up existing config to {backup}")
        try:
            existing = json.loads(CLAUDE_DESKTOP_CONFIG.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("WARNING: existing claude_desktop_config.json was not valid JSON; starting fresh.")
            existing = {}

    existing.setdefault("mcpServers", {})
    existing["mcpServers"]["studio5000-ai-assistant"] = snippet["mcpServers"]["studio5000-ai-assistant"]
    write_json(CLAUDE_DESKTOP_CONFIG, existing)
    print("Restart Claude Desktop for the change to take effect.")


def run_self_test(doc_root):
    print("\nRunning the built-in self-test...")
    result = run(
        [sys.executable, str(SERVER_SCRIPT), "--doc-root", str(doc_root), "--test"],
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", dest="version", help="Studio 5000 major version to use, e.g. 35, 36, 37 (default: auto-detect, falling back to 35)")
    parser.add_argument("--yes", action="store_true", help="Accept defaults, no interactive prompts")
    parser.add_argument("--write-claude-desktop", action="store_true", help="Merge the server into Claude Desktop's config without asking")
    parser.add_argument("--skip-sdk", action="store_true", help="Don't install the Studio 5000 SDK wheel")
    parser.add_argument("--skip-deps", action="store_true", help="Don't run pip install -r requirements.txt")
    args = parser.parse_args()

    print("Studio 5000 AI Assistant — setup\n" + "=" * 40)
    check_python()

    version, doc_root = choose_version(args.version, args.yes)
    if not (doc_root / "17691.htm").exists():
        print(
            f"NOTE: {doc_root} doesn't look like a valid Studio 5000 documentation folder.\n"
            "You can pass --doc-root manually to the server later, or re-run with --version."
        )

    install_dependencies(args.skip_deps)
    sdk_wheel = install_sdk(args.skip_sdk)
    snippet = build_configs(doc_root, sdk_wheel)
    maybe_write_claude_desktop(snippet, args.write_claude_desktop, args.yes)

    ok = run_self_test(doc_root)

    print("\n" + "=" * 40)
    if ok:
        print("Setup complete! The self-test passed.")
    else:
        print("Setup finished, but the self-test reported problems — see the output above.")
    print(f"Studio 5000 version in use: v{version}")
    print(f"Documentation path:         {doc_root}")
    print("Generated files:")
    print("  mcp_config.local.json                (Cursor / generic MCP config)")
    print("  claude_desktop_config.snippet.json    (paste into Claude Desktop config, if not auto-written)")
    print("  .mcp.json                             (Claude Code project-scope MCP config)")
    print("\nIf you skipped the Claude Desktop merge, add the contents of")
    print("claude_desktop_config.snippet.json under \"mcpServers\" in:")
    print(f"  {CLAUDE_DESKTOP_CONFIG}")
    print("then restart Claude Desktop.")


if __name__ == "__main__":
    main()
