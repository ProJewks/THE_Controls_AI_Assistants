"""
Cache directory resolution for the vector databases.

The vector DBs used to take a bare relative name ("l5x_vector_cache") and mkdir it in
the process working directory. Claude Desktop launches MCP servers from a protected
folder (System32 / the app install dir), where that mkdir fails with
"[WinError 5] Access is denied: 'l5x_vector_cache'" - even when the folder already
exists elsewhere.

Resolution order for a relative name:
  1. STUDIO5000_CACHE_ROOT (env), if set - one fixed location regardless of launcher.
  2. The working directory, if it is writable - keeps existing caches that were built
     when the server was launched from a project folder (Claude Code CLI).
  3. <repo>/cache - always writable fallback.
Absolute paths are used as given.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_FALLBACK_ROOT = Path(__file__).resolve().parent.parent / "cache"


def resolve_cache_dir(cache_dir) -> Path:
    p = Path(cache_dir)
    if p.is_absolute():
        p.mkdir(parents=True, exist_ok=True)
        return p

    env_root = os.environ.get("STUDIO5000_CACHE_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root) / p)
    else:
        candidates.append(Path.cwd() / p)
    candidates.append(_FALLBACK_ROOT / p)

    last_err = None
    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            # mkdir on an existing dir can succeed without write access; prove it.
            probe = c / ".write_test"
            probe.write_text("")
            probe.unlink()
            if c != candidates[0]:
                logger.warning("Cache dir %s not usable; using %s", candidates[0], c)
            return c
        except OSError as e:
            last_err = e
    raise last_err
