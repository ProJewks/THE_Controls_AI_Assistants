"""Small helpers for talking to the AutoCAD COM API."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

import pythoncom
import win32com.client


def point_variant(coords: Sequence[float]) -> Any:
    """Wrap a flat sequence of doubles as the SAFEARRAY COM expects for points."""
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(c) for c in coords]
    )


def int_variant(values: Sequence[int]) -> Any:
    return win32com.client.VARIANT(
        pythoncom.VT_ARRAY | pythoncom.VT_I4, [int(v) for v in values]
    )


def as_point3d(point: Iterable[float]) -> list[float]:
    pt = [float(c) for c in point]
    if len(pt) == 2:
        pt.append(0.0)
    if len(pt) != 3:
        raise ValueError("Point must have 2 or 3 coordinates [x, y] or [x, y, z]")
    return pt


def flatten_points(points: Sequence[Sequence[float]], dims: int = 2) -> list[float]:
    """Flatten a list of [x,y] or [x,y,z] points into a flat list for COM calls."""
    flat: list[float] = []
    for p in points:
        p = list(p)
        flat.extend(float(c) for c in p[:dims])
    return flat


def entity_summary(entity: Any) -> dict[str, Any]:
    """Cheap summary used when listing many entities."""
    info: dict[str, Any] = {
        "handle": entity.Handle,
        "type": entity.ObjectName,
        "layer": entity.Layer,
    }
    for attr in ("Length", "Radius", "Area"):
        try:
            info[attr.lower()] = getattr(entity, attr)
        except Exception:
            pass
    return info


def entity_detail(entity: Any) -> dict[str, Any]:
    """Fuller property dump used when inspecting a single entity."""
    info: dict[str, Any] = {
        "handle": entity.Handle,
        "type": entity.ObjectName,
        "layer": entity.Layer,
        "color": _safe(lambda: entity.Color),
        "linetype": _safe(lambda: entity.Linetype),
    }

    geometry_attrs = {
        "StartPoint": "start_point",
        "EndPoint": "end_point",
        "Center": "center",
        "Radius": "radius",
        "Length": "length",
        "Area": "area",
        "Volume": "volume",
        "TextString": "text",
        "Height": "height",
        "InsertionPoint": "insertion_point",
        "Name": "block_name",
        "Rotation": "rotation",
        "XScaleFactor": "x_scale",
        "YScaleFactor": "y_scale",
        "ZScaleFactor": "z_scale",
        "StartAngle": "start_angle",
        "EndAngle": "end_angle",
        "Closed": "closed",
    }
    for com_attr, key in geometry_attrs.items():
        if hasattr(entity, com_attr):
            value = _safe(lambda a=com_attr: getattr(entity, a))
            if value is not None:
                info[key] = _coerce(value)

    if hasattr(entity, "Coordinates"):
        coords = _safe(lambda: list(entity.Coordinates))
        if coords is not None:
            info["coordinates"] = coords

    bbox = _safe(lambda: entity.GetBoundingBox())
    if bbox is not None:
        min_pt, max_pt = bbox
        info["bounding_box"] = {"min": list(min_pt), "max": list(max_pt)}

    return info


def _coerce(value: Any) -> Any:
    if hasattr(value, "__iter__") and not isinstance(value, str):
        return list(value)
    return value


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


def find_by_handle(doc: Any, handle: str) -> Any:
    try:
        return doc.HandleToObject(str(handle))
    except Exception as exc:
        raise ValueError(f"No entity found with handle {handle!r}") from exc
