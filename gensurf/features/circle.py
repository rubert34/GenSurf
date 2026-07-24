"""Circle — GSD 'Circle' feature.

Circle types implemented:
  * Center and radius      — center point, support plane for the normal;
  * Center and point       — radius from the distance to the point;
  * Two points and radius  — on the support plane; Second solution picks
    the mirrored center;
  * Three points           — the circumcircle;
  * Center and axis        — axis line + point: circle centered on the
    axis, in the plane through the point normal to the axis.

Circle limitations: Whole circle, Start/End angles, Trimmed ends (arc
bounded by the defining points), Complementary (the other arc).
('Bitangent and radius', 'Bitangent and point', 'Tritangent' and
'Center and tangent' need tangency solving and are not implemented yet;
'Geometry on support' projection and axis computation are skipped.)
"""

import math

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   plane_from_link, axis_from_link, make_feature)
from .registry import register
from .point import _vertex_point

_TYPES = ("Center and radius", "Center and point",
          "Two points and radius", "Three points", "Center and axis")
_LIMITS = ("Whole circle", "Start/End angles", "Trimmed ends",
           "Complementary")

_TWO_PI = 2.0 * math.pi


def _plane_frame(normal):
    """Stable (u, v) in-plane frame for angle measurement."""
    n = App.Vector(normal)
    n.normalize()
    u = App.Vector(1, 0, 0) - n * n.x
    if u.Length < 1e-9:
        u = App.Vector(0, 1, 0) - n * n.y
    u.normalize()
    return u, n.cross(u)


class Circle(GSFeature):
    TYPE_ID = "GenSurf::Circle"
    REQUIRED_LINKS = ()
    INPUT_SLOTS = (
        ("Center", "Center point", ("Vertex",), True),
        ("Point1", "Point 1 (point-based types)", ("Vertex",), True),
        ("Point2", "Point 2", ("Vertex",), True),
        ("Point3", "Point 3 (Three points)", ("Vertex",), True),
        ("Support", "Support plane", ("Face",), True),
        ("Axis", "Axis (Center and axis)", ("Edge",), True),
    )
    ENUMS = {
        "CircleType": _TYPES,
        "Limitation": _LIMITS,
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "CircleType", "Circle",
         "How the circle is defined", None),
        ("App::PropertyEnumeration", "Limitation", "Circle",
         "Circle limitations: whole, angles, trimmed, complementary",
         None),
        ("App::PropertyLinkSub", "Center", "Circle",
         "Center point", None),
        ("App::PropertyLinkSub", "Point1", "Circle",
         "First defining point", None),
        ("App::PropertyLinkSub", "Point2", "Circle",
         "Second defining point", None),
        ("App::PropertyLinkSub", "Point3", "Circle",
         "Third defining point (Three points)", None),
        ("App::PropertyLinkSub", "Support", "Circle",
         "Support plane giving the circle's plane", None),
        ("App::PropertyLinkSub", "Axis", "Circle",
         "Axis line (Center and axis)", None),
        ("App::PropertyDistance", "Radius", "Circle",
         "Radius (radius-based types)", "20 mm"),
        ("App::PropertyBool", "SecondSolution", "Circle",
         "Other center for Two points and radius", False),
        ("App::PropertyAngle", "Start", "Circle",
         "Arc start angle (Start/End angles limitation)", "0 deg"),
        ("App::PropertyAngle", "End", "Circle",
         "Arc end angle (Start/End angles limitation)", "180 deg"),
    )

    def _support_normal(self, obj, default=None):
        if obj.Support:
            planar = plane_from_link(obj.Support)
            if planar is not None:
                return planar[1]
            raise GSFeatureError("the support must be planar")
        return default if default is not None else App.Vector(0, 0, 1)

    def _definition(self, obj):
        """(center, normal, radius, trim_a, trim_mid, trim_b) or None to
        idle while the type's picks are incomplete."""
        kind = obj.CircleType

        if kind == "Center and radius":
            if not obj.Center:
                return None
            c = _vertex_point(obj.Center, "Center")
            r = obj.Radius.getValueAs("mm").Value
            if r < 1e-9:
                raise GSFeatureError("radius is zero")
            return c, self._support_normal(obj), r, None, None, None

        if kind == "Center and point":
            if not (obj.Center and obj.Point1):
                return None
            c = _vertex_point(obj.Center, "Center")
            p = _vertex_point(obj.Point1, "Point")
            n = self._support_normal(obj)
            w = p - c
            w = w - n * w.dot(n)  # radius measured in the circle plane
            if w.Length < 1e-9:
                raise GSFeatureError("the point coincides with the center")
            return c, n, w.Length, None, None, None

        if kind == "Two points and radius":
            if not (obj.Point1 and obj.Point2):
                return None
            p1 = _vertex_point(obj.Point1, "Point 1")
            p2 = _vertex_point(obj.Point2, "Point 2")
            n = self._support_normal(obj)
            r = obj.Radius.getValueAs("mm").Value
            chord = p2 - p1
            chord = chord - n * chord.dot(n)
            half = chord.Length * 0.5
            if half < 1e-9:
                raise GSFeatureError("the two points coincide")
            if r < half - 1e-9:
                raise GSFeatureError(
                    f"radius {r} mm is smaller than half the distance "
                    f"between the points ({half:.3f} mm)")
            m = p1 + chord * 0.5
            w = n.cross(chord)
            w.normalize()
            h = math.sqrt(max(r * r - half * half, 0.0))
            if obj.SecondSolution:
                w = -w
            return m + w * h, n, r, p1, None, p2

        if kind == "Three points":
            if not (obj.Point1 and obj.Point2 and obj.Point3):
                return None
            p1 = _vertex_point(obj.Point1, "Point 1")
            p2 = _vertex_point(obj.Point2, "Point 2")
            p3 = _vertex_point(obj.Point3, "Point 3")
            n = (p2 - p1).cross(p3 - p1)
            if n.Length < 1e-9:
                raise GSFeatureError("the three points are collinear")
            n.normalize()
            # circumcenter: intersect perpendicular bisectors
            a, b = p2 - p1, p3 - p1
            a2, b2 = a.dot(a), b.dot(b)
            axb = a.cross(b)
            c = p1 + (b * a2 - a * b2).cross(axb) * (1.0 / (2 * axb.dot(axb)))
            return c, n, (p1 - c).Length, p1, p2, p3

        if kind == "Center and axis":
            if not (obj.Axis and obj.Point1):
                return None
            base, d = axis_from_link(obj.Axis)
            p = _vertex_point(obj.Point1, "Point")
            w = p - base
            foot = base + d * w.dot(d)
            r = (p - foot).Length
            if r < 1e-9:
                raise GSFeatureError("the point lies on the axis")
            return foot, App.Vector(d), r, None, None, None

        raise GSFeatureError(f"circle type {kind} not implemented")

    def build(self, obj):
        definition = self._definition(obj)
        if definition is None:
            return None  # idle until the type's picks are complete
        center, normal, radius, pa, pm, pb = definition
        circ = Part.Circle(center, normal, radius)
        limit = obj.Limitation

        if limit == "Whole circle":
            return circ.toShape()

        if limit == "Start/End angles":
            u, v = _plane_frame(normal)
            a0 = math.radians(obj.Start.getValueAs("deg").Value)
            a1 = math.radians(obj.End.getValueAs("deg").Value)
            if abs(a1 - a0) < 1e-9 or abs(abs(a1 - a0) - _TWO_PI) < 1e-9:
                return circ.toShape()
            t0 = circ.parameter(center + (u * math.cos(a0) +
                                          v * math.sin(a0)) * radius)
            t1 = circ.parameter(center + (u * math.cos(a1) +
                                          v * math.sin(a1)) * radius)
            if t1 <= t0 + 1e-12:
                t1 += _TWO_PI
            return Part.ArcOfCircle(circ, t0, t1).toShape()

        # Trimmed ends / Complementary need bounding points
        if pa is None or pb is None:
            raise GSFeatureError(
                f"'{limit}' needs a point-bounded circle type "
                "(Two points and radius / Three points)")
        ta = circ.parameter(pa)
        tb = circ.parameter(pb)
        span = (tb - ta) % _TWO_PI
        if span < 1e-9:
            span = _TWO_PI
        arc_a, arc_span = ta, span
        if pm is not None:  # the kept arc must contain the middle point
            tm = circ.parameter(pm)
            if (tm - ta) % _TWO_PI > span + 1e-9:
                arc_a, arc_span = tb, _TWO_PI - span
        elif span > math.pi:  # no middle point: keep the minor arc
            arc_a, arc_span = tb, _TWO_PI - span
        if limit == "Complementary":
            arc_a = (arc_a + arc_span) % _TWO_PI
            arc_span = _TWO_PI - arc_span
        return Part.ArcOfCircle(circ, arc_a, arc_a + arc_span).toShape()


def make_circle(doc, name="Circle"):
    return make_feature(doc, Circle, name)


register(Circle, make_circle)
