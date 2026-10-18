"""Compact geometric fingerprints of shapes, for "recomputes identically"
regression tests.

A fingerprint records the topology counts, the measures (area, length,
volume), the bounding box and the vertex centroid of a shape. Two
fingerprints match when the counts and type are equal and every number
agrees within a relative tolerance.
"""

import math

_NUMBERS = ("area", "length", "volume")


def fingerprint(shape):
    """Fingerprint of a Part.Shape as a JSON-friendly dict (None for an
    empty or null shape)."""
    if shape is None or shape.isNull():
        return None
    bb = shape.BoundBox
    verts = shape.Vertexes
    n = max(len(verts), 1)
    return {
        "type": shape.ShapeType,
        "solids": len(shape.Solids),
        "faces": len(shape.Faces),
        "edges": len(shape.Edges),
        "vertexes": len(verts),
        "area": shape.Area,
        "length": shape.Length,
        "volume": shape.Volume if shape.Solids else 0.0,
        "bbox": [bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax],
        "centroid": [sum(v.X for v in verts) / n,
                     sum(v.Y for v in verts) / n,
                     sum(v.Z for v in verts) / n],
    }


def _close(a, b, rel):
    return math.isclose(a, b, rel_tol=rel, abs_tol=rel)


def differences(got, want, rel=1e-7):
    """List of human-readable differences between two fingerprints
    (empty when they match)."""
    if got is None or want is None:
        return [] if got is want else [f"{got!r} != {want!r}"]
    out = []
    for key in ("type", "solids", "faces", "edges", "vertexes"):
        if got[key] != want[key]:
            out.append(f"{key}: {got[key]} != {want[key]}")
    for key in _NUMBERS:
        if not _close(got[key], want[key], rel):
            out.append(f"{key}: {got[key]!r} != {want[key]!r}")
    for key in ("bbox", "centroid"):
        if not all(_close(a, b, rel) for a, b in zip(got[key], want[key])):
            out.append(f"{key}: {got[key]} != {want[key]}")
    return out
