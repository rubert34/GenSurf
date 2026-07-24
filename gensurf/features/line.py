"""Line — GSD 'Line' feature with CATIA's main line types.

  * Point-Point       — between two picked points;
  * Point-Direction   — from a point along a direction (reference edge /
    planar face normal, or explicit vector) over Length;
  * Tangent to curve  — tangent at a picked point of a curve;
  * Normal to surface — surface normal at a picked point.

Start/End extend the line beyond its defining span (CATIA's Start/End),
Mirrored extent applies End symmetrically to both sides.
('Angle/Normal to curve' and 'Bisecting' are not implemented yet;
infinite lines are not representable as bounded B-rep and are skipped.)
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, make_feature,
                   resolve_linksub, direction_from_ref)
from .registry import register

_TYPES = ("Point-Point", "Point-Direction", "Tangent to curve",
          "Normal to surface")


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


class Line(GSFeature):
    TYPE_ID = "GenSurf::Line"
    REQUIRED_LINKS = ()
    INPUT_SLOTS = (
        ("Point1", "Start point", ("Vertex",), True),
        ("Point2", "End point (Point-Point)", ("Vertex",), True),
        ("DirectionRef", "Direction ref / curve / surface",
         ("Edge", "Face"), True),
    )
    ENUMS = {
        "LineType": _TYPES,
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "LineType", "Line",
         "How the line is defined", None),
        ("App::PropertyLinkSub", "Point1", "Line",
         "Start point (all types); point on curve/surface for tangent/"
         "normal types", None),
        ("App::PropertyLinkSub", "Point2", "Line",
         "End point (Point-Point)", None),
        ("App::PropertyLinkSub", "DirectionRef", "Line",
         "Direction reference (Point-Direction), curve (Tangent), or "
         "surface (Normal)", None),
        ("App::PropertyVector", "Direction", "Line",
         "Explicit direction (Point-Direction without a reference)",
         App.Vector(0, 0, 1)),
        ("App::PropertyDistance", "Length", "Line",
         "Line length (direction-based types)", "20 mm"),
        ("App::PropertyDistance", "Start", "Line",
         "Extension before the start point", "0 mm"),
        ("App::PropertyDistance", "End", "Line",
         "Extension after the end", "0 mm"),
        ("App::PropertyBool", "MirroredExtent", "Line",
         "Apply the extent symmetrically around the start point", False),
    )

    def _span(self, obj):
        """(anchor_point, unit_direction, natural_length)."""
        kind = obj.LineType
        if kind == "Point-Point":
            p1 = _vertex_point(obj.Point1, "Point 1")
            p2 = _vertex_point(obj.Point2, "Point 2")
            d = p2 - p1
            if d.Length < 1e-12:
                raise GSFeatureError("the two points coincide")
            length = d.Length
            d.normalize()
            return p1, d, length

        length = obj.Length.getValueAs("mm").Value
        if length < 1e-9:
            raise GSFeatureError("length is zero")
        p1 = _vertex_point(obj.Point1, "Point 1")

        if kind == "Point-Direction":
            if obj.DirectionRef:
                d = App.Vector(direction_from_ref(
                    resolve_linksub(obj.DirectionRef)))
            else:
                d = App.Vector(obj.Direction)
            if d.Length < 1e-12:
                raise GSFeatureError("direction is null")
            d.normalize()
            return p1, d, length

        if kind == "Tangent to curve":
            if not obj.DirectionRef:
                raise GSFeatureError("Tangent: pick the curve")
            shape = resolve_linksub(obj.DirectionRef)
            edge = shape if shape.ShapeType == "Edge" else shape.Edges[0]
            try:
                param = edge.Curve.parameter(p1)
            except Part.OCCError:
                raise GSFeatureError(
                    "the picked point does not lie on the curve")
            d = App.Vector(edge.tangentAt(param))
            d.normalize()
            return p1, d, length

        if kind == "Normal to surface":
            if not obj.DirectionRef:
                raise GSFeatureError("Normal: pick the surface")
            face = resolve_linksub(obj.DirectionRef, expect="Face")
            u, v = face.Surface.parameter(p1)
            anchor = face.Surface.value(u, v)
            d = App.Vector(face.normalAt(u, v))
            d.normalize()
            return anchor, d, length

        raise GSFeatureError(f"line type {kind} not implemented")

    def build(self, obj):
        anchor, d, length = self._span(obj)
        start_ext = obj.Start.getValueAs("mm").Value
        end_ext = obj.End.getValueAs("mm").Value

        if obj.MirroredExtent:
            a = anchor - d * (length + end_ext)
            b = anchor + d * (length + end_ext)
        else:
            a = anchor - d * start_ext
            b = anchor + d * (length + end_ext)
        if (b - a).Length < 1e-12:
            raise GSFeatureError("resulting line has zero length")
        return Part.makeLine(a, b)


def make_line(doc, name="Line"):
    return make_feature(doc, Line, name)


register(Line, make_line)
