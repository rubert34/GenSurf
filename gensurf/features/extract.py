"""Extract — GSD 'Extract' feature: pull a sub-element (face or edge)
out of a body/shape as its own parametric element, with propagation.

Propagation types (from CATIA's Extract Definition):
  * No propagation    — just the picked element (CATIA default);
  * Point continuity  — everything connected to it (faces via shared
    edges, edges via shared vertices);
  * Tangent continuity — connected AND smooth across the junction
    (face normals aligned along the shared edge / curve tangents
    aligned at the shared vertex).

Curvature / Depression / Protrusion propagation (BiW feature
recognition) are not implemented yet.
"""

import math

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, make_feature
from .registry import register

_PROP = ("No propagation", "Point continuity", "Tangent continuity")


def _faces_adjacent(f1, f2):
    """Shared edge between two faces, or None."""
    for e1 in f1.Edges:
        for e2 in f2.Edges:
            if e1.isSame(e2):
                return e1
    return None


def _faces_smooth(f1, f2, edge, tol_rad):
    """Normals aligned across the shared edge (sampled)."""
    for frac in (0.25, 0.5, 0.75):
        p = edge.valueAt(edge.FirstParameter
                         + frac * (edge.LastParameter
                                   - edge.FirstParameter))
        angs = []
        for f in (f1, f2):
            u, v = f.Surface.parameter(p)
            angs.append(App.Vector(f.normalAt(u, v)))
        ang = angs[0].getAngle(angs[1])
        if min(ang, math.pi - ang) > tol_rad:
            return False
    return True


def _edges_shared_vertex(e1, e2):
    for v1 in e1.Vertexes:
        for v2 in e2.Vertexes:
            if (v1.Point - v2.Point).Length < 1e-7:
                return v1.Point
    return None


def _edges_smooth(e1, e2, p, tol_rad):
    def tangent(e):
        try:
            param = e.Curve.parameter(p)
        except Part.OCCError:
            param = e.FirstParameter \
                if (e.valueAt(e.FirstParameter) - p).Length < \
                   (e.valueAt(e.LastParameter) - p).Length \
                else e.LastParameter
        t = App.Vector(e.tangentAt(param))
        t.normalize()
        return t
    ang = tangent(e1).getAngle(tangent(e2))
    return min(ang, math.pi - ang) < tol_rad


def _propagate(seeds, pool, connected, smooth, mode, tol_rad):
    """Generic BFS over a connectivity graph."""
    picked = list(seeds)
    if mode == "No propagation":
        return picked
    frontier = list(picked)
    while frontier:
        current = frontier.pop()
        for cand in pool:
            if any(cand.isSame(t) for t in picked):
                continue
            joint = connected(current, cand)
            if joint is None:
                continue
            if mode == "Tangent continuity" and \
                    not smooth(current, cand, joint, tol_rad):
                continue
            picked.append(cand)
            frontier.append(cand)
    return picked


class Extract(GSFeature):
    TYPE_ID = "GenSurf::Extract"
    REQUIRED_LINKS = ("Element",)
    INPUT_SLOTS = (
        ("Element", "Face or edge to extract", ("Face", "Edge"), False),
    )
    ENUMS = {
        "Propagation": _PROP,
    }
    PROPERTIES = (
        ("App::PropertyLinkSub", "Element", "Extract",
         "Sub-element to extract from its object", None),
        ("App::PropertyEnumeration", "Propagation", "Extract",
         "How the extraction propagates to neighbours", None),
        ("App::PropertyAngle", "SmoothAngle", "Extract",
         "Smoothness threshold for tangent propagation", "0.5 deg"),
    )

    def build(self, obj):
        linked, subs = obj.Element
        if not subs or not subs[0]:
            raise GSFeatureError(
                "pick a FACE or EDGE sub-element to extract")
        picked = linked.Shape.getElement(subs[0])
        tol = obj.SmoothAngle.getValueAs("rad").Value + 1e-9
        mode = obj.Propagation

        if picked.ShapeType == "Face":
            pool = linked.Shape.Faces
            out = _propagate(
                [picked], pool,
                _faces_adjacent,
                _faces_smooth,
                mode, tol)
            if len(out) == 1:
                return out[0]
            try:
                shell = Part.makeShell(out)
                if not shell.isNull() and len(shell.Faces) == len(out):
                    return shell
            except Part.OCCError:
                pass
            return Part.makeCompound(out)

        if picked.ShapeType == "Edge":
            pool = linked.Shape.Edges
            out = _propagate(
                [picked], pool,
                _edges_shared_vertex,
                _edges_smooth,
                mode, tol)
            if len(out) == 1:
                return out[0]
            sorter = getattr(Part, "sortEdges", None) or Part.__sortEdges__
            wires = [Part.Wire(g) for g in sorter(out)]
            return wires[0] if len(wires) == 1 \
                else Part.makeCompound(wires)

        raise GSFeatureError(
            f"cannot extract a {picked.ShapeType} — pick a face or edge")


def make_extract(doc, name="Extract"):
    return make_feature(doc, Extract, name)


register(Extract, make_extract)
