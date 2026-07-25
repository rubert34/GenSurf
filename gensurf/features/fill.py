"""Fill — GSD 'Fill' feature: n-sided patch bounded by a closed loop,
with per-edge continuity, CATIA-style.

OCC entry point: BRepOffsetAPI_MakeFilling — the constrained-filling
solver, driven with TRUE per-edge continuity orders: Position (G0),
Tangent (G1) and Curvature (G2) constraints are imposed against each
edge's own support surface, exactly as in CATIA. Optional passing
points pull the patch through them.

Fallback: if MakeFilling fails on a given input, the previous
GeomPlate plate-surface path (with sampled continuation-row
approximation of G1/G2) is used instead.
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
                # use the RAW edges: wrapping through Part.Wire heals
                # them and breaks the isSame ownership match below
                edges = [shape] if shape.ShapeType == "Edge" \
                    else shape.Edges
                for e in edges:
                    yield e, _owner_face(linked, e), order

    def _collect(self, obj):
        """(plain_edges, [(edge, support_face, order)], points) or None
        while the boundary is empty."""
        plain, constrained = [], []
        for shape in resolve_linksublist(obj.Boundary or []):
            for w in curve_wires(shape):
                plain.extend(w.Edges)
        for links, order in ((obj.BoundaryTangent, 1),
                             (obj.BoundaryCurvature, 2)):
            for e, face, o in self._constrained_picks(links, order):
                constrained.append((e, face, o))
        if not plain and not constrained:
            App.Console.PrintWarning(
                "[GenSurf] Fill: waiting for boundary curves\n")
            return None
        points = []
        if obj.PassingPoints:
            for shape in resolve_linksublist(obj.PassingPoints):
                if shape.ShapeType != "Vertex":
                    raise GSFeatureError(
                        "passing points must be vertex picks")
                points.append(App.Vector(shape.Point))
        return plain, constrained, points

    @staticmethod
    def _check_loop(all_edges):
        sorter = getattr(Part, "sortEdges", None) or Part.__sortEdges__
        groups = sorter(list(all_edges))
        if len(groups) != 1:
            raise GSFeatureError(
                f"boundary splits into {len(groups)} separate chains — "
                "it must form one connected loop")
        wire = Part.Wire(groups[0])
        if not wire.isClosed():
            raise GSFeatureError(
                "boundary is not closed — the curves must form a loop")
        return wire

    def _build_filling(self, plain, constrained, points):
        """True per-edge continuity via BRepOffsetAPI_MakeFilling."""
        mf = Part.BRepOffsetAPI.MakeFilling()
        for e in plain:
            mf.add(Constraint=e, Order=0, IsBound=True)
        for e, face, order in constrained:
            mf.add(Constraint=e, Support=face, Order=order, IsBound=True)
        for p in points:
            mf.add(p)
        mf.build()
        if not mf.isDone():
            raise GSFeatureError("filling solver did not converge")
        result = mf.shape()
        if result.isNull() or not result.Faces \
                or result.Faces[0].Area < 1e-12:
            raise GSFeatureError("fill produced no valid patch")
        return result

    def build(self, obj):
        collected = self._collect(obj)
        if collected is None:
            return None  # idle: boundary not picked yet
        plain, constrained, points = collected
        wire = self._check_loop(plain + [c[0] for c in constrained])

        # primary path: the real constrained-filling solver
        try:
            return self._build_filling(plain, constrained, points)
        except (Part.OCCError, GSFeatureError) as err:
            App.Console.PrintWarning(
                f"[GenSurf] Fill: MakeFilling failed ({err}) — falling "
                "back to the plate solver\n")

        # fallback: GeomPlate with sampled continuation rows
        edges = list(wire.Edges)
        support_rows = []
        for e, face, o in constrained:
            support_rows.extend(_support_rows(e, face, o))

        plane = _fit_plane(wire.discretize(Number=100))
        builder = GeomPlate.BuildPlateSurface(plane)
        for e in edges:
            builder.add(GeomPlate.CurveConstraint(
                e.Curve.trim(e.FirstParameter, e.LastParameter), 0))
        for row in support_rows:
            builder.add(GeomPlate.CurveConstraint(
                row.trim(row.FirstParameter, row.LastParameter), 0))
        for p in points:
            builder.add(GeomPlate.PointConstraint(p, 0))

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
