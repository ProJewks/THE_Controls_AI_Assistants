"""
MCP server exposing AutoCAD 2027 drawing/document operations to Claude Code
via AutoCAD's native COM Automation API.
"""

from __future__ import annotations

import logging
import math
import sys
from typing import Any, Optional

from mcp.server.mcpserver import MCPServer

from . import com_thread, connection, helpers

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("autocad-mcp")

mcp = MCPServer("autocad-mcp")


def _app_doc_model():
    app = connection.get_application()
    doc = connection.get_document(app)
    return app, doc, doc.ModelSpace


def _apply_layer(entity: Any, layer: Optional[str], doc: Any) -> None:
    if not layer:
        return
    try:
        doc.Layers.Item(layer)
    except Exception:
        doc.Layers.Add(layer)
    entity.Layer = layer


# --------------------------------------------------------------------------
# Status / document management
# --------------------------------------------------------------------------


@mcp.tool()
def autocad_status() -> dict:
    """Check whether AutoCAD is reachable and report version/document info."""

    def _do():
        app = connection.get_application()
        info: dict[str, Any] = {
            "connected": True,
            "name": app.Name,
            "version": app.Version,
            "visible": app.Visible,
            "document_count": app.Documents.Count,
        }
        if app.Documents.Count > 0:
            info["active_document"] = app.ActiveDocument.Name
            info["active_document_path"] = app.ActiveDocument.FullName
        return info

    try:
        return com_thread.run(_do)
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


@mcp.tool()
def list_open_drawings() -> list[dict]:
    """List every DWG document currently open in AutoCAD."""

    def _do():
        app = connection.get_application()
        active_name = app.ActiveDocument.Name if app.Documents.Count else None
        return [
            {
                "name": d.Name,
                "path": d.FullName,
                "saved": d.Saved,
                "active": d.Name == active_name,
            }
            for d in app.Documents
        ]

    return com_thread.run(_do)


@mcp.tool()
def open_drawing(path: str) -> dict:
    """Open an existing DWG file in AutoCAD, making it the active document."""

    def _do():
        app = connection.get_application()
        doc = app.Documents.Open(path)
        app.ActiveDocument = doc
        return {"opened": doc.Name, "path": doc.FullName}

    return com_thread.run(_do)


@mcp.tool()
def new_drawing(template_path: Optional[str] = None) -> dict:
    """Create a new drawing, optionally from a DWT template file."""

    def _do():
        app = connection.get_application()
        doc = app.Documents.Add(template_path) if template_path else app.Documents.Add()
        app.ActiveDocument = doc
        return {"created": doc.Name}

    return com_thread.run(_do)


@mcp.tool()
def save_drawing() -> dict:
    """Save the active drawing in place."""

    def _do():
        _, doc, _ = _app_doc_model()
        doc.Save()
        return {"saved": doc.Name, "path": doc.FullName}

    return com_thread.run(_do)


@mcp.tool()
def save_drawing_as(path: str) -> dict:
    """Save the active drawing to a new DWG path."""

    def _do():
        _, doc, _ = _app_doc_model()
        doc.SaveAs(path)
        return {"saved": doc.Name, "path": doc.FullName}

    return com_thread.run(_do)


@mcp.tool()
def close_drawing(save: bool = True) -> dict:
    """Close the active drawing."""

    def _do():
        _, doc, _ = _app_doc_model()
        name = doc.Name
        doc.Close(save)
        return {"closed": name, "saved": save}

    return com_thread.run(_do)


# --------------------------------------------------------------------------
# Layers
# --------------------------------------------------------------------------


@mcp.tool()
def list_layers() -> list[dict]:
    """List all layers in the active drawing."""

    def _do():
        _, doc, _ = _app_doc_model()
        current = doc.ActiveLayer.Name
        return [
            {
                "name": layer.Name,
                "color": layer.Color,
                "locked": layer.Lock,
                "frozen": layer.Freeze,
                "visible": layer.LayerOn,
                "current": layer.Name == current,
            }
            for layer in doc.Layers
        ]

    return com_thread.run(_do)


@mcp.tool()
def create_layer(name: str, color_index: Optional[int] = None) -> dict:
    """Create a layer (AutoCAD Color Index 1-255, e.g. 1=red, 2=yellow, 3=green, 5=blue)."""

    def _do():
        _, doc, _ = _app_doc_model()
        try:
            layer = doc.Layers.Item(name)
        except Exception:
            layer = doc.Layers.Add(name)
        if color_index is not None:
            layer.Color = color_index
        return {"name": layer.Name, "color": layer.Color}

    return com_thread.run(_do)


@mcp.tool()
def set_current_layer(name: str) -> dict:
    """Make the named layer the active/current layer for new entities."""

    def _do():
        _, doc, _ = _app_doc_model()
        doc.ActiveLayer = doc.Layers.Item(name)
        return {"current_layer": name}

    return com_thread.run(_do)


# --------------------------------------------------------------------------
# Entity creation
# --------------------------------------------------------------------------


@mcp.tool()
def draw_line(start: list[float], end: list[float], layer: Optional[str] = None) -> dict:
    """Draw a line between two points [x, y] or [x, y, z]."""

    def _do():
        _, doc, model = _app_doc_model()
        line = model.AddLine(
            helpers.point_variant(helpers.as_point3d(start)),
            helpers.point_variant(helpers.as_point3d(end)),
        )
        _apply_layer(line, layer, doc)
        return helpers.entity_summary(line)

    return com_thread.run(_do)


@mcp.tool()
def draw_circle(center: list[float], radius: float, layer: Optional[str] = None) -> dict:
    """Draw a circle given a center point and radius."""

    def _do():
        _, doc, model = _app_doc_model()
        circle = model.AddCircle(helpers.point_variant(helpers.as_point3d(center)), radius)
        _apply_layer(circle, layer, doc)
        return helpers.entity_summary(circle)

    return com_thread.run(_do)


@mcp.tool()
def draw_arc(
    center: list[float],
    radius: float,
    start_angle_deg: float,
    end_angle_deg: float,
    layer: Optional[str] = None,
) -> dict:
    """Draw an arc. Angles are in degrees, measured counterclockwise from the X axis."""

    def _do():
        _, doc, model = _app_doc_model()
        arc = model.AddArc(
            helpers.point_variant(helpers.as_point3d(center)),
            radius,
            math.radians(start_angle_deg),
            math.radians(end_angle_deg),
        )
        _apply_layer(arc, layer, doc)
        return helpers.entity_summary(arc)

    return com_thread.run(_do)


@mcp.tool()
def draw_polyline(
    points: list[list[float]], closed: bool = False, layer: Optional[str] = None
) -> dict:
    """Draw a 2D lightweight polyline through the given [x, y] points."""

    def _do():
        _, doc, model = _app_doc_model()
        flat = helpers.flatten_points(points, dims=2)
        pline = model.AddLightWeightPolyline(helpers.point_variant(flat))
        if closed:
            pline.Closed = True
        _apply_layer(pline, layer, doc)
        return helpers.entity_summary(pline)

    return com_thread.run(_do)


@mcp.tool()
def draw_rectangle(
    corner1: list[float], corner2: list[float], layer: Optional[str] = None
) -> dict:
    """Draw an axis-aligned rectangle between two opposite corner points [x, y]."""

    def _do():
        _, doc, model = _app_doc_model()
        x1, y1 = corner1[0], corner1[1]
        x2, y2 = corner2[0], corner2[1]
        flat = helpers.flatten_points([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dims=2)
        pline = model.AddLightWeightPolyline(helpers.point_variant(flat))
        pline.Closed = True
        _apply_layer(pline, layer, doc)
        return helpers.entity_summary(pline)

    return com_thread.run(_do)


@mcp.tool()
def add_text(
    position: list[float], text: str, height: float = 2.5, layer: Optional[str] = None
) -> dict:
    """Add a single-line text entity at the given insertion point."""

    def _do():
        _, doc, model = _app_doc_model()
        entity = model.AddText(
            text, helpers.point_variant(helpers.as_point3d(position)), height
        )
        _apply_layer(entity, layer, doc)
        return helpers.entity_summary(entity)

    return com_thread.run(_do)


@mcp.tool()
def add_mtext(
    position: list[float],
    text: str,
    width: float = 50.0,
    height: Optional[float] = None,
    layer: Optional[str] = None,
) -> dict:
    """Add a multiline text (MTEXT) entity at the given insertion point."""

    def _do():
        _, doc, model = _app_doc_model()
        entity = model.AddMText(
            helpers.point_variant(helpers.as_point3d(position)), width, text
        )
        if height is not None:
            entity.Height = height
        _apply_layer(entity, layer, doc)
        return helpers.entity_summary(entity)

    return com_thread.run(_do)


@mcp.tool()
def insert_block(
    block_name: str,
    insertion_point: list[float],
    x_scale: float = 1.0,
    y_scale: float = 1.0,
    z_scale: float = 1.0,
    rotation_deg: float = 0.0,
    layer: Optional[str] = None,
) -> dict:
    """Insert a block reference (block must already exist in the drawing)."""

    def _do():
        _, doc, model = _app_doc_model()
        entity = model.InsertBlock(
            helpers.point_variant(helpers.as_point3d(insertion_point)),
            block_name,
            x_scale,
            y_scale,
            z_scale,
            math.radians(rotation_deg),
        )
        _apply_layer(entity, layer, doc)
        return helpers.entity_summary(entity)

    return com_thread.run(_do)


@mcp.tool()
def list_blocks() -> list[dict]:
    """List block definitions available in the drawing's block table."""

    def _do():
        _, doc, _ = _app_doc_model()
        blocks = []
        for block in doc.Blocks:
            try:
                if block.IsLayout:
                    continue
            except Exception:
                pass
            blocks.append({"name": block.Name, "entity_count": block.Count})
        return blocks

    return com_thread.run(_do)


# --------------------------------------------------------------------------
# Entity query / edit
# --------------------------------------------------------------------------


@mcp.tool()
def list_entities(
    layer: Optional[str] = None, entity_type: Optional[str] = None, limit: int = 200
) -> dict:
    """List entities in model space, optionally filtered by layer or entity type
    (e.g. 'AcDbLine', 'AcDbCircle', 'AcDbText')."""

    def _do():
        _, doc, model = _app_doc_model()
        results = []
        truncated = False
        for entity in model:
            if layer and entity.Layer != layer:
                continue
            if entity_type and entity.ObjectName != entity_type:
                continue
            if len(results) >= limit:
                truncated = True
                break
            results.append(helpers.entity_summary(entity))
        return {"count": len(results), "truncated": truncated, "entities": results}

    return com_thread.run(_do)


@mcp.tool()
def get_entity(handle: str) -> dict:
    """Get full details for one entity by its AutoCAD handle."""

    def _do():
        _, doc, _ = _app_doc_model()
        entity = helpers.find_by_handle(doc, handle)
        return helpers.entity_detail(entity)

    return com_thread.run(_do)


@mcp.tool()
def delete_entity(handle: str) -> dict:
    """Delete (erase) one entity by its AutoCAD handle."""

    def _do():
        _, doc, _ = _app_doc_model()
        entity = helpers.find_by_handle(doc, handle)
        summary = helpers.entity_summary(entity)
        entity.Delete()
        return {"deleted": summary}

    return com_thread.run(_do)


@mcp.tool()
def move_entity(handle: str, dx: float, dy: float, dz: float = 0.0) -> dict:
    """Move one entity by a relative displacement [dx, dy, dz]."""

    def _do():
        _, doc, _ = _app_doc_model()
        entity = helpers.find_by_handle(doc, handle)
        entity.Move(
            helpers.point_variant([0.0, 0.0, 0.0]),
            helpers.point_variant([dx, dy, dz]),
        )
        return helpers.entity_summary(entity)

    return com_thread.run(_do)


# --------------------------------------------------------------------------
# View / escape hatches
# --------------------------------------------------------------------------


@mcp.tool()
def zoom_extents() -> dict:
    """Zoom the active viewport to fit all drawing content."""

    def _do():
        app = connection.get_application()
        app.ZoomExtents()
        return {"zoomed": "extents"}

    return com_thread.run(_do)


@mcp.tool()
def run_command(command: str) -> dict:
    """Send a raw AutoCAD command-line string (as you'd type at the command
    prompt). Multiple steps can be space-separated, e.g. '_CIRCLE 0,0 5'."""

    def _do():
        _, doc, _ = _app_doc_model()
        text = command if command.endswith(("\n", " ")) else command + "\n"
        doc.SendCommand(text)
        return {"sent": command}

    return com_thread.run(_do)


@mcp.tool()
def run_autolisp(code: str) -> dict:
    """Execute a raw AutoLISP expression via the command line, e.g.
    '(command "_LINE" (list 0 0 0) (list 10 10 0) "")'. Fire-and-forget:
    the return value of the expression is not captured."""

    def _do():
        _, doc, _ = _app_doc_model()
        doc.SendCommand(f"(progn {code} )\n")
        return {"sent": code}

    return com_thread.run(_do)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
