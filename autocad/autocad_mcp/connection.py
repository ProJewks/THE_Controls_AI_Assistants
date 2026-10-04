"""
AutoCAD COM connection handling.

Uses the version-agnostic "AutoCAD.Application" ProgID rather than a
version-pinned one (e.g. "AutoCAD.Application.25"), so this works against
whatever AutoCAD release is actually registered on the machine (AutoCAD 2027
here) without needing code changes when AutoCAD is upgraded.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import pythoncom
import win32com.client

logger = logging.getLogger("autocad-mcp.connection")

PROGID = "AutoCAD.Application"

_app: Optional[Any] = None


class AutoCADConnectionError(RuntimeError):
    pass


def _try_get_active() -> Optional[Any]:
    try:
        return win32com.client.GetActiveObject(PROGID)
    except Exception:
        return None


def _try_launch() -> Any:
    app = win32com.client.Dispatch(PROGID)
    app.Visible = True
    # Give a freshly launched AutoCAD a moment to finish initializing
    # before anything touches Documents/ActiveDocument.
    for _ in range(30):
        try:
            _ = app.Documents.Count
            return app
        except Exception:
            time.sleep(0.5)
    return app


def get_application(force_reconnect: bool = False) -> Any:
    """Return a live AutoCAD.Application COM object, launching AutoCAD if needed."""
    global _app

    pythoncom.CoInitialize()

    if not force_reconnect and _app is not None:
        try:
            _ = _app.Name  # health check
            return _app
        except Exception:
            _app = None

    app = _try_get_active()
    if app is None:
        logger.info("No running AutoCAD instance found; launching %s", PROGID)
        app = _try_launch()
    else:
        logger.info("Attached to existing AutoCAD instance")

    if app is None:
        raise AutoCADConnectionError(
            "Could not attach to or launch AutoCAD via COM. "
            "Confirm AutoCAD 2027 is installed and its COM automation "
            "components are registered."
        )

    app.Visible = True
    _app = app
    return app


def get_document(app: Optional[Any] = None) -> Any:
    """Return the active document, creating a new drawing if none is open."""
    app = app or get_application()
    if app.Documents.Count == 0:
        app.Documents.Add()
    return app.ActiveDocument


def get_modelspace(doc: Optional[Any] = None) -> Any:
    doc = doc or get_document()
    return doc.ModelSpace
