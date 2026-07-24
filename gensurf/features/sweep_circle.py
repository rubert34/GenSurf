"""Sweep Circle — GSD 'Swept Surface', Circle profile type: a circle or
circular arc constructed at every station and lofted along the guides.

Subtypes (per the dialog schematics):
  * Three guides        — the arc through G1, G2, G3 at each station;
  * Two guides and radius — arc of given radius through G1 and G2;
    Solution cycles center side and arc/complement (CATIA's solutions);
  * Center and radius   — full circles centered on the center curve, in
    the plane normal to it (the classic tube);
  * Center and two angles — arcs around the center curve; the radius
    and the zero direction come from the reference curve, the arc spans
    Angle 1 to Angle 2.

Not implemented: the tangency-surface subtypes, radius/angle Laws,
relimiters and smooth-sweeping options.
"""

import math

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, make_feature
from .registry import register
from .sweep_common import (guide_wire, stations, tangents,
                           project_to_plane, loft_sections)

_TWO_PI = 2.0 * math.pi


def _circumcircle(p1, p2, p3):
    n = (p2 - p1).cross(p3 - p1)
    if n.Length < 1e-9:
        raise GSFeatureError("the three guides are locally collinear")
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
    REQUIRED_LINKS = ("Guide1",)
    INPUT_SLOTS = (
        ("Guide1", "Guide curve 1 / center curve", ("Edge", "Wire"),
         False),
        ("Guide2", "Guide curve 2 / reference curve", ("Edge", "Wire"),
         True),
        ("Guide3", "Guide curve 3 (three guides)", ("Edge", "Wire"),
         True),
    )
    ENUMS = {
        "Subtype": ("Three guides", "Two guides and radius",
                    "Center and radius", "Center and two angles"),
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "Subtype", "Sweep",
         "How the circle is constructed at each station", None),
        ("App::PropertyLinkSub", "Guide1", "Sweep",
         "Guide 1 / center curve", None),
        ("App::PropertyLinkSub", "Guide2", "Sweep",
         "Guide 2 / reference curve", None),
        ("App::PropertyLinkSub", "Guide3", "Sweep",
         "Guide 3 (three guides)", None),
        ("App::PropertyDistance", "Radius", "Sweep",
         "Circle radius (radius-based subtypes)", "20 mm"),
        ("App::PropertyAngle", "Angle1", "Sweep",
         "Arc start angle (center and two angles)", "0 deg"),
        ("App::PropertyAngle", "Angle2", "Sweep",
         "Arc end angle (center and two angles)", "180 deg"),
        ("App::PropertyInteger", "Solution", "Sweep",
         "Cycles the possible arcs (two guides and radius)", 0),
    )

    def build(self, obj):
        subtype = obj.Subtype
        g1 = guide_wire(obj.Guide1, "guide curve 1")
        p_pts = stations(g1)
        sections = []

        if subtype == "Three guides":
            if not (obj.Guide2 and obj.Guide3):
                raise GSFeatureError("'Three guides' needs guides 2 and 3")
            q_pts = stations(guide_wire(obj.Guide2, "guide curve 2"))
            r_pts = stations(guide_wire(obj.Guide3, "guide curve 3"))
            for p, q, r in zip(p_pts, q_pts, r_pts):
                c, n, rad = _circumcircle(p, q, r)
                sections.append(Part.Wire([_arc_through(c, n, rad,
                                                        p, q, r)]))
            return loft_sections(sections)

        if subtype == "Two guides and radius":
            if not obj.Guide2:
                raise GSFeatureError(
                    "'Two guides and radius' needs guide curve 2")
            radius = obj.Radius.getValueAs("mm").Value
            if radius < 1e-9:
                raise GSFeatureError("radius is zero")
            q_pts = stations(guide_wire(obj.Guide2, "guide curve 2"))
            tg = tangents(p_pts)
            sol = obj.Solution % 4
            for p, q, n in zip(p_pts, q_pts, tg):
                q2 = project_to_plane(q, p, n)
                chord = q2 - p
                half = chord.Length * 0.5
                if half < 1e-9:
                    raise GSFeatureError("the guides touch")
                if radius < half - 1e-9:
                    raise GSFeatureError(
                        f"radius {radius} mm is smaller than half the "
                        f"guide distance ({half:.3f} mm)")
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

        if subtype == "Center and radius":
            radius = obj.Radius.getValueAs("mm").Value
            if radius < 1e-9:
                raise GSFeatureError("radius is zero")
            tg = tangents(p_pts)
            for p, n in zip(p_pts, tg):
                sections.append(Part.Wire(
                    [Part.Circle(p, n, radius).toShape()]))
            return loft_sections(sections)

        # Center and two angles
        if not obj.Guide2:
            raise GSFeatureError(
                "'Center and two angles' needs the reference curve "
                "(guide curve 2)")
        q_pts = stations(guide_wire(obj.Guide2, "reference curve"))
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
