"""Extract — pull faces or edges out of a shape as their own parametric
element, with propagation.

Each row is one picked face or edge with its own propagation:
  * None      — just the picked element (default);
  * Connected — everything connected to it (faces via shared edges,
    edges via shared vertices);
  * Tangent   — connected AND smooth across the junction (face normals
    aligned along the shared edge, curve tangents aligned at the shared
    vertex), within the row's threshold angle.
Rows may mix faces and edges and may overlap (duplicates are dropped).
Complementary inverts the result within each source object: the output
becomes every face (resp. edge) of the source NOT captured by the rows.

Faces come back as one shell when they connect, edges as wires.
Algorithm versions: 1 returns a lone extracted edge as an Edge (the
single-pick behaviour of earlier versions); 2 always returns wires.

Not implemented: curvature propagation and feature recognition
(depressions, protrusions).
"""

import math

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, make_feature
from .registry import register

#: propagation labels, by the integer stored per row
PROPAGATION = ("None", "Connected", "Tangent")
_DEFAULT_THRESHOLD = 0.5  # degrees


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
    """Generic BFS over a connectivity graph (mode: index into
    PROPAGATION)."""
    picked = list(seeds)
    if mode == 0:
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
            if mode == 2 and not smooth(current, cand, joint, tol_rad):
                continue
            picked.append(cand)
            frontier.append(cand)
    return picked


class Extract(GSFeature):
    TYPE_ID = "GenSurf::Extract"
    ALGO_VERSION = 2
    CUSTOM_PANEL = "extract"
    REQUIRED_LINKS = ("Elements",)
    INPUT_SLOTS = (
        ("Elements", "Faces / edges to extract", ("Face", "Edge"),
         False, True),
    )
    PROPERTIES = (
        ("App::PropertyLinkSubList", "Elements", "Extract",
         "Faces or edges to extract, one row each", None),
        ("App::PropertyIntegerList", "Propagations", "Extract",
         "Per-row propagation: 0 = None, 1 = Connected, 2 = Tangent",
         None),
        ("App::PropertyFloatList", "Thresholds", "Extract",
         "Per-row tangency threshold in degrees (Tangent propagation)",
         None),
        ("App::PropertyBool", "Complementary", "Extract",
         "Keep everything EXCEPT the captured elements", False),
    )

    @staticmethod
    def _rows(obj):
        out = []
        for linked, subs in (obj.Elements or []):
            for sub in (subs if subs else ("",)):
                out.append((linked, sub))
        return out

    def build(self, obj):
        rows = self._rows(obj)
        if not rows:
            raise GSFeatureError("pick at least one face or edge")
        props = list(obj.Propagations or [])
        thresholds = list(obj.Thresholds or [])

        captured = []          # (source_obj, shape) pairs
        sources = {}           # name -> (source_obj, has_faces, has_edges)
        for r, (linked, sub) in enumerate(rows):
            if not sub:
                raise GSFeatureError(
                    f"row {r + 1}: pick a sub-element (face or edge), "
                    "not a whole object")
            picked = linked.Shape.getElement(sub)
            mode = props[r] if r < len(props) and \
                0 <= props[r] < len(PROPAGATION) else 0
            tol = math.radians(thresholds[r] if r < len(thresholds)
                               and thresholds[r] > 0
                               else _DEFAULT_THRESHOLD) + 1e-9

            if picked.ShapeType == "Face":
                found = _propagate([picked], linked.Shape.Faces,
                                   _faces_adjacent, _faces_smooth,
                                   mode, tol)
                flags = (True, False)
            elif picked.ShapeType == "Edge":
                found = _propagate([picked], linked.Shape.Edges,
                                   _edges_shared_vertex, _edges_smooth,
                                   mode, tol)
                flags = (False, True)
            else:
                raise GSFeatureError(
                    f"row {r + 1}: cannot extract a {picked.ShapeType} — "
                    "pick a face or edge")

            prev = sources.get(linked.Name, (linked, False, False))
            sources[linked.Name] = (linked, prev[1] or flags[0],
                                    prev[2] or flags[1])
            for shp in found:
                if not any(shp.isSame(c) for _s, c in captured):
                    captured.append((linked, shp))

        if obj.Complementary:
            result = []
            for _name, (src, has_f, has_e) in sources.items():
                pool = (src.Shape.Faces if has_f else []) + \
                       (src.Shape.Edges if has_e else [])
                for shp in pool:
                    taken = any(shp.isSame(c) for s, c in captured
                                if s is src)
                    if not taken:
                        result.append(shp)
            if not result:
                raise GSFeatureError(
                    "complementary mode captured everything — nothing "
                    "remains")
        else:
            result = [c for _s, c in captured]

        faces = [s for s in result if s.ShapeType == "Face"]
        edges = [s for s in result if s.ShapeType == "Edge"]
        parts = []
        if faces:
            if len(faces) == 1:
                parts.append(faces[0])
            else:
                try:
                    shell = Part.makeShell(faces)
                    if not shell.isNull() and \
                            len(shell.Faces) == len(faces):
                        parts.append(shell)
                    else:
                        parts.extend(faces)
                except Part.OCCError:
                    parts.extend(faces)
        if edges:
            if len(edges) == 1 and not faces and \
                    self.algo_version(obj) < 2:
                return edges[0]
            sorter = getattr(Part, "sortEdges", None) or Part.__sortEdges__
            parts.extend(Part.Wire(g) for g in sorter(edges))
        if not parts:
            raise GSFeatureError("nothing captured")
        return parts[0] if len(parts) == 1 else Part.makeCompound(parts)


def make_extract(doc, name="Extract"):
    return make_feature(doc, Extract, name)


register(Extract, make_extract)
