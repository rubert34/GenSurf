"""Intersection — GSD 'Intersection' feature.

Intersects two elements of any dimension:
  * curve x curve      — points; when the curves share a common area,
    Result switches between the common Curve and its end Points;
  * curve x surface    — points (or the lying-on curve if coincident);
  * surface x surface  — intersection curve(s);
  * surface x solid    — Contour (section curves) or Surface (the part
    of the surface inside the solid).

Options from the CATIA dialog:
  * Extend linear supports for intersection (per element) — straight
    edges and planar faces are extended far enough to intersect;
  * Intersect non coplanar line segments — for two skew lines, the
    midpoint of their common perpendicular;
  * 'Extrapolate intersection on first element' is not implemented.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   make_feature)
from .registry import register


def _extend_linear(shape, other):
    """Extend straight edges / planar faces beyond the combined extents."""
    bb = shape.BoundBox
    bb.add(other.BoundBox)
    span = max(bb.DiagonalLength, 1.0) * 2.0

    if shape.ShapeType == "Edge" and isinstance(shape.Curve, Part.Line):
        d = App.Vector(shape.Curve.Direction)
        c = (shape.Vertexes[0].Point + shape.Vertexes[-1].Point) * 0.5
        return Part.makeLine(c - d * span, c + d * span)
    if shape.ShapeType == "Face" and isinstance(shape.Surface, Part.Plane):
        pos = shape.CenterOfMass
        n = shape.Surface.Axis
        u = n.cross(App.Vector(0, 0, 1))
        if u.Length < 1e-9:
            u = n.cross(App.Vector(0, 1, 0))
        u.normalize()
        v = n.cross(u)
        corner = pos - u * span - v * span
        return Part.makePlane(2 * span, 2 * span, corner, n, u)
    return shape  # only *linear* supports are extended


def _wires_or_compound(edges):
    sorter = getattr(Part, "sortEdges", None) or Part.__sortEdges__
    wires = [Part.Wire(g) for g in sorter(edges)]
    return wires[0] if len(wires) == 1 else Part.makeCompound(wires)


def _vertices_result(points, what):
    uniq = []
    for p in points:
        if all((p - q).Length > 1e-7 for q in uniq):
            uniq.append(p)
    if not uniq:
        raise GSFeatureError(f"no intersection found ({what})")
    verts = [Part.Vertex(p) for p in uniq]
    return verts[0] if len(verts) == 1 else Part.makeCompound(verts)


class Intersection(GSFeature):
    TYPE_ID = "GenSurf::Intersection"
    REQUIRED_LINKS = ("Element1", "Element2")
    INPUT_SLOTS = (
        ("Element1", "First element",
         ("Edge", "Wire", "Face", "Shell"), False),
        ("Element2", "Second element",
         ("Edge", "Wire", "Face", "Shell"), False),
    )
    ENUMS = {
        "CurveResult": ("Curve", "Points"),
        "SurfaceResult": ("Contour", "Surface"),
    }
    PROPERTIES = (
        ("App::PropertyLinkSub", "Element1", "Intersection",
         "First element", None),
        ("App::PropertyLinkSub", "Element2", "Intersection",
         "Second element", None),
        ("App::PropertyBool", "ExtendLinear1", "Intersection",
         "Extend the first element's linear supports for intersection",
         False),
        ("App::PropertyBool", "ExtendLinear2", "Intersection",
         "Extend the second element's linear supports for intersection",
         False),
        ("App::PropertyEnumeration", "CurveResult", "Intersection",
         "Curves intersection with common area: resulting element", None),
        ("App::PropertyEnumeration", "SurfaceResult", "Intersection",
         "Surface-part intersection: resulting element", None),
        ("App::PropertyBool", "NonCoplanarSegments", "Intersection",
         "Intersect non coplanar line segments (midpoint of the common "
         "perpendicular)", False),
    )

    def build(self, obj):
        a = resolve_linksub(obj.Element1)
        b = resolve_linksub(obj.Element2)

        if obj.ExtendLinear1:
            a = _extend_linear(a, b)
        if obj.ExtendLinear2:
            b = _extend_linear(b, a)

        a_curve = bool(a.Edges) and not a.Faces and not a.Solids
        b_curve = bool(b.Edges) and not b.Faces and not b.Solids

        # -- curve x curve -------------------------------------------------
        if a_curve and b_curve:
            overlap = None
            try:
                overlap = a.common(b)
            except Part.OCCError:
                pass
            if overlap is not None and overlap.Edges:
                if obj.CurveResult == "Curve":
                    return _wires_or_compound(overlap.Edges)
                pts = []
                for e in overlap.Edges:
                    pts.append(e.Vertexes[0].Point)
                    pts.append(e.Vertexes[-1].Point)
                return _vertices_result(pts, "common-area end points")

            sec = a.section(b)
            if sec.Vertexes:
                return _vertices_result(
                    [v.Point for v in sec.Vertexes], "curve intersection")

            if obj.NonCoplanarSegments:
                dist, pts, _info = a.distToShape(b)
                p1, p2 = pts[0]
                return Part.Vertex((p1 + p2) * 0.5)
            raise GSFeatureError(
                "the curves do not intersect (for skew line segments, "
                "enable 'Intersect non coplanar line segments')")

        # -- curve x surface (either order) --------------------------------
        if a_curve or b_curve:
            curve, surf = (a, b) if a_curve else (b, a)
            sec = curve.section(surf)
            if sec.Edges:  # curve lying on the surface
                return _wires_or_compound(sec.Edges)
            if not sec.Vertexes:
                raise GSFeatureError(
                    "the curve does not intersect the surface")
            return _vertices_result(
                [v.Point for v in sec.Vertexes], "curve-surface")

        # -- surface x solid -----------------------------------------------
        if a.Solids or b.Solids:
            surf, solid = (a, b) if b.Solids else (b, a)
            if obj.SurfaceResult == "Surface":
                com = surf.common(solid)
                if not com.Faces:
                    raise GSFeatureError(
                        "the surface does not pass through the part")
                faces = com.Faces
                return faces[0] if len(faces) == 1 else \
                    Part.makeCompound(faces)
            sec = surf.section(solid)
            if not sec.Edges:
                raise GSFeatureError(
                    "the surface does not intersect the part")
            return _wires_or_compound(sec.Edges)

        # -- surface x surface ---------------------------------------------
        sec = a.section(b)
        if sec.Edges:
            return _wires_or_compound(sec.Edges)
        if sec.Vertexes:  # touching at points only
            return _vertices_result(
                [v.Point for v in sec.Vertexes], "surface tangency points")
        raise GSFeatureError("the surfaces do not intersect")


def make_intersection(doc, name="Intersect"):
    return make_feature(doc, Intersection, name)


register(Intersection, make_intersection)
