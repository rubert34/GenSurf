"""Sweep Arc — a circle or circular arc built at every station and lofted
along the rails.

Modes:
  * Through 3 rails — the arc through rails 1, 2 and 3 at each station;
  * 2 rails + radius — an arc of given radius through rails 1 and 2;
    Solution selects the center side and the arc or its complement;
  * Center rail + radius — full circles centered on rail 1, in the
    plane normal to it (a tube);
  * Center rail + angles — arcs around rail 1; rail 2 gives the radius
    and the zero direction, and the arc spans Angle 1 to Angle 2.

Not implemented: arcs tangent to surfaces, radius and angle laws, end
limits and smoothing.
"""


import math

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, make_feature
from .registry import register
from .sweep_common import (rail_wire, stations, tangents,
                           project_to_plane, loft_sections)

_TWO_PI = 2.0 * math.pi


def _circumcircle(p1, p2, p3):
    n = (p2 - p1).cross(p3 - p1)
    if n.Length < 1e-9:
        raise GSFeatureError("the three rails are locally collinear")
    n.normalize()
    a, b = p2 - p1, p3 - p1
    axb = a.cross(b)
    c = p1 + (b * a.dot(a) - a * b.dot(b)).cross(axb) * \
        (1.0 / (2 * axb.dot(axb)))
    return c, n, (p1 - c).Length


def _arc_through(c, n, r, pa, pm, pb):
    """Arc from pa to pb passing through pm on circle (c, n, r)."""
    circ = Part.Circle(c, n, r)
    ta, tm, tb = (circ.parameter(p) for p in (pa, pm, pb))
    span = (tb - ta) % _TWO_PI
    if span < 1e-9:
        span = _TWO_PI
    if (tm - ta) % _TWO_PI > span + 1e-9:
        ta, span = tb, _TWO_PI - span
    return Part.ArcOfCircle(circ, ta, ta + span).toShape()


class SweepCircle(GSFeature):
    TYPE_ID = "GenSurf::SweepCircle"
    REQUIRED_LINKS = ("Rail1",)
    INPUT_SLOTS = (
        ("Rail1", "Rail curve 1 / center curve", ("Edge", "Wire"),
         False),
        ("Rail2", "Rail curve 2 / reference curve", ("Edge", "Wire"),
         True),
        ("Rail3", "Rail curve 3 (three rails)", ("Edge", "Wire"),
         True),
    )
    ENUMS = {
        "Mode": ("Through 3 rails", "2 rails + radius",
                 "Center rail + radius", "Center rail + angles"),
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "Mode", "Sweep",
         "How the circle is constructed at each station", None),
        ("App::PropertyLinkSub", "Rail1", "Sweep",
         "Rail 1 / center curve", None),
        ("App::PropertyLinkSub", "Rail2", "Sweep",
         "Rail 2 / reference curve", None),
        ("App::PropertyLinkSub", "Rail3", "Sweep",
         "Rail 3 (three rails)", None),
        ("App::PropertyDistance", "Radius", "Sweep",
         "Circle radius (radius-based modes)", "20 mm"),
        ("App::PropertyAngle", "Angle1", "Sweep",
         "Arc start angle (Center rail + angles mode)", "0 deg"),
        ("App::PropertyAngle", "Angle2", "Sweep",
         "Arc end angle (Center rail + angles mode)", "180 deg"),
        ("App::PropertyInteger", "Solution", "Sweep",
         "Cycles the possible arcs (two rails and radius)", 0),
    )

    def build(self, obj):
        mode = obj.Mode
        g1 = rail_wire(obj.Rail1, "rail curve 1")
        p_pts = stations(g1)
        sections = []

        if mode == "Through 3 rails":
            if not (obj.Rail2 and obj.Rail3):
                raise GSFeatureError("'Through 3 rails' needs rails 2 and 3")
            q_pts = stations(rail_wire(obj.Rail2, "rail curve 2"))
            r_pts = stations(rail_wire(obj.Rail3, "rail curve 3"))
            for p, q, r in zip(p_pts, q_pts, r_pts):
                c, n, rad = _circumcircle(p, q, r)
                sections.append(Part.Wire([_arc_through(c, n, rad,
                                                        p, q, r)]))
            return loft_sections(sections)

        if mode == "2 rails + radius":
            if not obj.Rail2:
                raise GSFeatureError(
                    "'2 rails + radius' needs rail curve 2")
            radius = obj.Radius.getValueAs("mm").Value
            if radius < 1e-9:
                raise GSFeatureError("radius is zero")
            q_pts = stations(rail_wire(obj.Rail2, "rail curve 2"))
            tg = tangents(p_pts)
            sol = obj.Solution % 4
            for p, q, n in zip(p_pts, q_pts, tg):
                q2 = project_to_plane(q, p, n)
                chord = q2 - p
                half = chord.Length * 0.5
                if half < 1e-9:
                    raise GSFeatureError("the rails touch")
                if radius < half - 1e-9:
                    raise GSFeatureError(
                        f"radius {radius} mm is smaller than half the "
                        f"rail distance ({half:.3f} mm)")
                m = p + chord * 0.5
                w = n.cross(chord)
                w.normalize()
                if sol & 1:
                    w = -w
                c = m + w * math.sqrt(max(radius * radius
                                          - half * half, 0.0))
                circ = Part.Circle(c, n, radius)
                ta, tb = circ.parameter(p), circ.parameter(q2)
                span = (tb - ta) % _TWO_PI
                if span > math.pi:  # default to the minor arc
                    ta, span = tb, _TWO_PI - span
                if sol & 2:  # complementary arc
                    ta, span = (ta + span) % _TWO_PI, _TWO_PI - span
                sections.append(Part.Wire(
                    [Part.ArcOfCircle(circ, ta, ta + span).toShape()]))
            return loft_sections(sections)

        if mode == "Center rail + radius":
            radius = obj.Radius.getValueAs("mm").Value
            if radius < 1e-9:
                raise GSFeatureError("radius is zero")
            tg = tangents(p_pts)
            for p, n in zip(p_pts, tg):
                sections.append(Part.Wire(
                    [Part.Circle(p, n, radius).toShape()]))
            return loft_sections(sections)

        # Center rail + angles
        if not obj.Rail2:
            raise GSFeatureError(
                "'Center rail + angles' needs the reference curve "
                "(rail curve 2)")
        q_pts = stations(rail_wire(obj.Rail2, "reference curve"))
        tg = tangents(p_pts)
        a1 = math.radians(obj.Angle1.getValueAs("deg").Value)
        a2 = math.radians(obj.Angle2.getValueAs("deg").Value)
        span = (a2 - a1) % _TWO_PI
        if span < 1e-9:
            span = _TWO_PI
        for p, q, n in zip(p_pts, q_pts, tg):
            u = project_to_plane(q, p, n) - p
            radius = u.Length
            if radius < 1e-9:
                raise GSFeatureError(
                    "the reference curve touches the center curve")
            u.normalize()
            v = n.cross(u)
            start = p + (u * math.cos(a1) + v * math.sin(a1)) * radius
            circ = Part.Circle(p, n, radius)
            t0 = circ.parameter(start)
            sections.append(Part.Wire(
                [Part.ArcOfCircle(circ, t0, t0 + span).toShape()]))
        return loft_sections(sections)


def make_sweep_circle(doc, name="SweepCircle"):
    return make_feature(doc, SweepCircle, name)


register(SweepCircle, make_sweep_circle)
