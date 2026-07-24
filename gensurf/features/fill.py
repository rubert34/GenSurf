"""Fill — GSD 'Fill' feature: n-sided patch bounded by a closed loop,
with per-edge continuity, CATIA-style.

OCC entry point: GeomPlate_BuildPlateSurface via Part.GeomPlate — the
plate-surface solver CATIA's Fill is built on. The result is a trimmed
B-spline patch (many spans), same character as CATIA's.

Per-edge continuity: distribute boundary picks across three slots —
Position (any curve), Tangent and Curvature (must be edges of a support
surface). The GeomPlate Python binding cannot express curve-on-surface
constraints directly, so tangency/curvature are enforced by auxiliary
constraint rows sampled from the support's own tangent-plane
(respectively osculating) continuation just inside the patch — a close
approximation whose error shrinks with the inset (2% of edge length).

Optional passing points pull the patch through them (CATIA's point
constraint).
"""

import FreeCAD as App
import Part
from Part import GeomPlate

from .base import (GSFeature, GSFeatureError, resolve_linksublist,
                   make_feature, curve_wires)
from .registry import register


def _fit_plane(points):
    """Best-fit plane (Newell's method) as the plate's init surface."""
    centroid = App.Vector(0, 0, 0)
    for p in points:
        centroid += p
    centroid = centroid * (1.0 / len(points))
    normal = App.Vector(0, 0, 0)
    for a, b in zip(points, points[1:] + points[:1]):
        normal.x += (a.y - b.y) * (a.z + b.z)
        normal.y += (a.z - b.z) * (a.x + b.x)
        normal.z += (a.x - b.x) * (a.y + b.y)
    if normal.Length < 1e-12:
        normal = App.Vector(0, 0, 1)
    normal.normalize()
    return Part.Plane(centroid, normal)


def _owner_face(linked, edge):
    for f in linked.Shape.Faces:
        if any(edge.isSame(e) for e in f.Edges):
            return f
    raise GSFeatureError(
        "a Tangent/Curvature boundary must be an edge of a surface "
        f"({linked.Label} pick has no owning face)")


def _support_rows(edge, face, order, n=15):
    """Constraint rows continuing the support past the edge: one row for
    tangency (G1), two following the osculating cross-section for
    curvature (G2). Rows cover the central 90% of the edge to avoid
    fighting the corner constraints."""
    from .extend import _osculating_continue

    eps = max(edge.Length * 0.02, 0.05)
    surf = face.Surface
    rows = {1: [], 2: []}
    f0, f1 = edge.FirstParameter, edge.LastParameter
    for i in range(n):
        f = 0.05 + 0.9 * i / (n - 1)
        p = edge.valueAt(f0 + f * (f1 - f0))
        t_edge = edge.tangentAt(f0 + f * (f1 - f0))
        u, v = surf.parameter(p)
        normal = face.normalAt(u, v)
        cross = normal.cross(t_edge)
        if cross.Length < 1e-9:
            continue
        cross.normalize()
        # point away from the support interior (toward the patch)
        probe = p + cross * eps
        if face.distToShape(Part.Vertex(probe))[0] < eps * 0.5:
            cross = cross.negative()

        if order == 1:
            rows[1].append(p + cross * eps)
        else:
            # follow the support's curved cross-section outward
            q1 = _surface_point(surf, p - cross * eps)
            q2 = _surface_point(surf, p - cross * (2 * eps))
            rows[1].append(_osculating_continue([q2, q1, p], eps))
            rows[2].append(_osculating_continue([q2, q1, p], 2 * eps))

    out = []
    for pts in (rows[1], rows[2]):
        if len(pts) >= 4:
            bs = Part.BSplineCurve()
            bs.interpolate(pts)
            out.append(bs)
    return out


def _surface_point(surface, near):
    u, v = surface.parameter(near)
    return surface.value(u, v)


class Fill(GSFeature):
    TYPE_ID = "GenSurf::Fill"
    REQUIRED_LINKS = ()  # boundary may live in any of the three slots
    INPUT_SLOTS = (
        ("Boundary", "Boundary — Position (curves / sketch edges)",
         ("Edge", "Wire"), True, True),
        ("BoundaryTangent", "Boundary — Tangent (edges of a surface)",
         ("Edge",), True, True),
        ("BoundaryCurvature", "Boundary — Curvature (edges of a surface)",
         ("Edge",), True, True),
        ("PassingPoints", "Passing points (optional)",
         ("Vertex",), True, True),
    )
    PROPERTIES = (
        ("App::PropertyLinkSubList", "Boundary", "Fill",
         "Boundary curves joined with Position (G0) continuity", None),
        ("App::PropertyLinkSubList", "BoundaryTangent", "Fill",
         "Boundary edges joined tangent (G1) to their surface", None),
        ("App::PropertyLinkSubList", "BoundaryCurvature", "Fill",
         "Boundary edges joined curvature-continuous (G2)", None),
        ("App::PropertyLinkSubList", "PassingPoints", "Fill",
         "Optional points the patch must pass through", None),
    )

    @staticmethod
    def _constrained_picks(links, order):
        """Yield (edge, owner_face, order) for support-bound slots."""
        for entry in links or []:
            linked, subs = entry
            for sub in (subs if subs else ("",)):
                shape = linked.Shape.getElement(sub) if sub \
                    else linked.Shape
                for w in curve_wires(shape):
                    for e in w.Edges:
                        yield e, _owner_face(linked, e), order

    def build(self, obj):
        edges = []          # loop assembly
        support_rows = []   # extra plate constraints

        for shape in resolve_linksublist(obj.Boundary or []):
            for w in curve_wires(shape):
                edges.extend(w.Edges)
        for links, order in ((obj.BoundaryTangent, 1),
                             (obj.BoundaryCurvature, 2)):
            for e, face, o in self._constrained_picks(links, order):
                edges.append(e)
                support_rows.extend(_support_rows(e, face, o))

        if not edges:
            App.Console.PrintWarning(
                "[GenSurf] Fill: waiting for boundary curves\n")
            return None  # idle: boundary not picked yet
        sorter = getattr(Part, "sortEdges", None) or Part.__sortEdges__
        groups = sorter(edges)
        if len(groups) != 1:
            raise GSFeatureError(
                f"boundary splits into {len(groups)} separate chains — "
                "it must form one connected loop")
        wire = Part.Wire(groups[0])
        if not wire.isClosed():
            raise GSFeatureError(
                "boundary is not closed — the curves must form a loop")

        plane = _fit_plane(wire.discretize(Number=100))
        builder = GeomPlate.BuildPlateSurface(plane)
        for e in wire.Edges:
            builder.add(GeomPlate.CurveConstraint(
                e.Curve.trim(e.FirstParameter, e.LastParameter), 0))
        for row in support_rows:
            builder.add(GeomPlate.CurveConstraint(
                row.trim(row.FirstParameter, row.LastParameter), 0))

        if obj.PassingPoints:
            for shape in resolve_linksublist(obj.PassingPoints):
                if shape.ShapeType != "Vertex":
                    raise GSFeatureError(
                        "passing points must be vertex picks")
                builder.add(GeomPlate.PointConstraint(
                    App.Vector(shape.Point), 0))

        try:
            builder.perform()
        except Part.OCCError as err:
            raise GSFeatureError(f"plate solver failed: {err}")
        if not builder.isDone():
            raise GSFeatureError("plate solver did not converge")

        approx = builder.surface().makeApprox()
        face = Part.Face(approx, wire)
        face.validate()  # computes the boundary pcurves
        if face.isNull() or not face.isValid() or face.Area < 1e-12:
            raise GSFeatureError("fill produced no valid patch")
        return face


def make_fill(doc, name="Fill"):
    return make_feature(doc, Fill, name)


register(Fill, make_fill)
