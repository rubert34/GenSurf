"""Point — GSD 'Point' feature with CATIA's point types.

Point type drives which inputs are used:
  * Coordinates — X/Y/Z, optionally relative to a Reference point;
  * On curve    — a curve + Ratio (0..1 of arc length from its start);
  * On plane / On surface — a picked point projected onto the support;
  * Center      — center of a circular / elliptic edge;
  * Between     — two points + Ratio.

('Tangent on curve' is a multi-solution solver and is not implemented
yet.)
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, make_feature, curve_wires,
                   resolve_linksub)
from .registry import register

_TYPES = ("Coordinates", "On curve", "On plane", "On surface",
          "Center", "Between")


def _vertex_point(link, what):
    if not link:
        raise GSFeatureError(f"{what}: pick a point (vertex)")
    linked, subs = link
    shape = linked.Shape.getElement(subs[0]) if subs and subs[0] \
        else linked.Shape
    if shape.ShapeType != "Vertex":
        if len(shape.Vertexes) == 1:
            shape = shape.Vertexes[0]
        else:
            raise GSFeatureError(f"{what}: pick a single point (vertex)")
    return App.Vector(shape.Point)


class Point(GSFeature):
    TYPE_ID = "GenSurf::Point"
    REQUIRED_LINKS = ()
    INPUT_SLOTS = (
        ("Curve", "Curve (On curve / Center)", ("Edge", "Wire"), True),
        ("Support", "Support (On plane / On surface)", ("Face",), True),
        ("RefPoint", "Reference / first point", ("Vertex",), True),
        ("Point2", "Second point (Between)", ("Vertex",), True),
    )
    ENUMS = {
        "PointType": _TYPES,
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "PointType", "Point",
         "How the point is defined", None),
        ("App::PropertyDistance", "X", "Point", "X coordinate", "0 mm"),
        ("App::PropertyDistance", "Y", "Point", "Y coordinate", "0 mm"),
        ("App::PropertyDistance", "Z", "Point", "Z coordinate", "0 mm"),
        ("App::PropertyLinkSub", "Curve", "Point",
         "Curve for On curve / Center types", None),
        ("App::PropertyFloat", "Ratio", "Point",
         "Arc-length ratio (On curve / Between)", 0.5),
        ("App::PropertyLinkSub", "Support", "Point",
         "Plane or surface to project onto", None),
        ("App::PropertyLinkSub", "RefPoint", "Point",
         "Reference point (Coordinates offset, projection source, "
         "first point of Between)", None),
        ("App::PropertyLinkSub", "Point2", "Point",
         "Second point (Between)", None),
    )

    def build(self, obj):
        kind = obj.PointType
        xyz = App.Vector(obj.X.getValueAs("mm").Value,
                         obj.Y.getValueAs("mm").Value,
                         obj.Z.getValueAs("mm").Value)

        if kind == "Coordinates":
            base = App.Vector(0, 0, 0)
            if obj.RefPoint:
                base = _vertex_point(obj.RefPoint, "reference")
            return Part.Vertex(base + xyz)

        if kind == "On curve":
            if not obj.Curve:
                raise GSFeatureError("On curve: pick a curve")
            wire = curve_wires(resolve_linksub(obj.Curve))[0]
            ratio = min(max(obj.Ratio, 0.0), 1.0)
            pts = wire.discretize(Number=200)
            acc = [0.0]
            for a, b in zip(pts, pts[1:]):
                acc.append(acc[-1] + (b - a).Length)
            target = acc[-1] * ratio
            for i in range(1, len(acc)):
                if acc[i] >= target:
                    span = acc[i] - acc[i - 1] or 1.0
                    w = (target - acc[i - 1]) / span
                    return Part.Vertex(pts[i - 1] * (1 - w) + pts[i] * w)
            return Part.Vertex(pts[-1])

        if kind in ("On plane", "On surface"):
            if not obj.Support:
                raise GSFeatureError(f"{kind}: pick a support face")
            if not obj.RefPoint:
                raise GSFeatureError(
                    f"{kind}: pick the point to project (RefPoint)")
            face = resolve_linksub(obj.Support, expect="Face")
            p = _vertex_point(obj.RefPoint, "point to project")
            if kind == "On plane":
                surf = face.Surface
                if not isinstance(surf, Part.Plane):
                    raise GSFeatureError("On plane: support is not planar")
                n = surf.Axis
                proj = p - n * (p - surf.Position).dot(n)
                return Part.Vertex(proj)
            u, v = face.Surface.parameter(p)
            return Part.Vertex(face.Surface.value(u, v))

        if kind == "Center":
            if not obj.Curve:
                raise GSFeatureError("Center: pick a circular edge")
            shape = resolve_linksub(obj.Curve)
            edge = shape if shape.ShapeType == "Edge" else shape.Edges[0]
            curve = edge.Curve
            center = getattr(curve, "Center", None)
            if center is None:
                center = getattr(curve, "Location", None)
            if center is None:
                raise GSFeatureError(
                    "Center: the edge has no center (not a circle, "
                    "ellipse or sphere edge)")
            return Part.Vertex(App.Vector(center))

        if kind == "Between":
            p1 = _vertex_point(obj.RefPoint, "first point")
            p2 = _vertex_point(obj.Point2, "second point")
            r = obj.Ratio
            return Part.Vertex(p1 * (1 - r) + p2 * r)

        raise GSFeatureError(f"point type {kind} not implemented")


def make_point(doc, name="Point"):
    return make_feature(doc, Point, name)


register(Point, make_point)
