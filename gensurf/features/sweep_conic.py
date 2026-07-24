"""Sweep Conic — GSD 'Swept Surface', Conic profile type: a conic arc
constructed at every station and lofted along the guides.

Subtypes:
  * Two guide curves  — a true conic (rational quadratic Bezier) from
    guide 1 to guide 2; the end tangents come from the tangency
    surfaces (rotated by Angle 1/2 from their tangent planes, per the
    schematic), the conic Parameter sets the fullness (0.5 = parabola);
  * Five guide curves — a section through all five guides at each
    station (interpolated curve — an approximation of the exact
    five-point conic).

Not implemented: 'Three/Four guide curves' (mixed point + tangency
constraints), parameter/angle Laws, relimiters, smooth-sweeping
options.
"""

import math

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, make_feature
from .registry import register
from .sweep_common import (guide_wire, stations, tangents, support_face,
                           face_normal_at, project_to_plane,
                           loft_sections, conic_arc)


def _intersect_lines(p, d1, q, d2, n):
    """Intersection of two coplanar lines (plane normal n), or None
    when they are parallel."""
    w = q - p
    denom = d1.cross(d2).dot(n)
    if abs(denom) < 1e-9:
        return None
    s = w.cross(d2).dot(n) / denom
    return p + d1 * s


_QUARTER = math.sqrt(0.5)  # rational weight of an exact conic quarter


def _parallel_tangent_conic(p, q, d1, n, rho):
    """Conic from p to q whose end tangents are parallel (no finite
    apex): the half-ellipse with conjugate diameters chord/2 and the
    bulge d1·b, built exactly as two conic quarters."""
    from .sweep_common import conic_arc
    rho = min(max(rho, 0.01), 0.99)
    chord = q - p
    m = p + chord * 0.5
    b = chord.Length * 0.5 * rho / (1.0 - rho)
    shoulder = m + d1 * b
    cd = App.Vector(chord)
    cd.normalize()
    w_rho = _QUARTER / (1.0 + _QUARTER)  # weight -> conic parameter
    a1 = _intersect_lines(p, d1, shoulder, cd, n)
    a2 = _intersect_lines(q, d1, shoulder, cd, n)
    if a1 is None or a2 is None:
        raise GSFeatureError(
            "the conic tangents are parallel to the chord — the "
            "section is degenerate")
    return [conic_arc(p, a1, shoulder, w_rho),
            conic_arc(shoulder, a2, q, w_rho)]


class SweepConic(GSFeature):
    TYPE_ID = "GenSurf::SweepConic"
    REQUIRED_LINKS = ("Guide1",)
    INPUT_SLOTS = (
        ("Guide1", "Guide curve 1", ("Edge", "Wire"), False),
        ("Guide2", "Guide curve 2", ("Edge", "Wire"), True),
        ("Guide3", "Guide curve 3", ("Edge", "Wire"), True),
        ("Guide4", "Guide curve 4", ("Edge", "Wire"), True),
        ("Guide5", "Last guide curve", ("Edge", "Wire"), True),
        ("Tangency1", "Tangency surface at guide 1", ("Face",), True),
        ("Tangency2", "Tangency surface at guide 2", ("Face",), True),
    )
    ENUMS = {
        "Subtype": ("Two guide curves", "Five guide curves"),
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "Subtype", "Sweep",
         "How the conic section is constrained", None),
        ("App::PropertyLinkSub", "Guide1", "Sweep",
         "Guide curve 1", None),
        ("App::PropertyLinkSub", "Guide2", "Sweep",
         "Guide curve 2", None),
        ("App::PropertyLinkSub", "Guide3", "Sweep",
         "Guide curve 3 (five guides)", None),
        ("App::PropertyLinkSub", "Guide4", "Sweep",
         "Guide curve 4 (five guides)", None),
        ("App::PropertyLinkSub", "Guide5", "Sweep",
         "Last guide curve (five guides)", None),
        ("App::PropertyLinkSub", "Tangency1", "Sweep",
         "Tangency surface at guide 1", None),
        ("App::PropertyLinkSub", "Tangency2", "Sweep",
         "Tangency surface at guide 2", None),
        ("App::PropertyAngle", "Angle1", "Sweep",
         "Tangent angle from tangency surface 1", "0 deg"),
        ("App::PropertyAngle", "Angle2", "Sweep",
         "Tangent angle from tangency surface 2", "0 deg"),
        ("App::PropertyFloat", "Parameter", "Sweep",
         "Conic parameter: <0.5 ellipse, 0.5 parabola, >0.5 hyperbola",
         0.5),
    )

    @staticmethod
    def _tangent_dir(face, p, n, toward, angle_rad):
        """In-station-plane tangent at p from a tangency surface,
        oriented toward the other guide, rotated by the angle."""
        ns = face_normal_at(face, p)
        t = ns.cross(n)  # surface-plane ∩ station-plane direction
        if t.Length < 1e-9:
            raise GSFeatureError(
                "the tangency surface is parallel to the station plane")
        t.normalize()
        if t.dot(toward) < 0:
            t = t.negative()
        if abs(angle_rad) > 1e-12:
            e = n.cross(t)
            t = t * math.cos(angle_rad) + e * math.sin(angle_rad)
        return t

    def build(self, obj):
        subtype = obj.Subtype
        g1 = guide_wire(obj.Guide1, "guide curve 1")
        p_pts = stations(g1)
        sections = []

        if subtype == "Two guide curves":
            if not obj.Guide2:
                raise GSFeatureError("pick guide curve 2")
            if not (obj.Tangency1 and obj.Tangency2):
                raise GSFeatureError(
                    "the two-guides conic needs both tangency surfaces")
            q_pts = stations(guide_wire(obj.Guide2, "guide curve 2"))
            tg = tangents(p_pts)
            f1 = support_face(obj.Tangency1, "tangency surface 1")
            f2 = support_face(obj.Tangency2, "tangency surface 2")
            a1 = math.radians(obj.Angle1.getValueAs("deg").Value)
            a2 = math.radians(obj.Angle2.getValueAs("deg").Value)
            rho = obj.Parameter
            for p, q, n in zip(p_pts, q_pts, tg):
                q2 = project_to_plane(q, p, n)
                chord = q2 - p
                if chord.Length < 1e-9:
                    raise GSFeatureError("the guides touch")
                d1 = self._tangent_dir(f1, p, n, chord, a1)
                d2 = self._tangent_dir(f2, q2, n, chord.negative(), a2)
                apex = _intersect_lines(p, d1, q2, d2, n)
                if apex is None:  # parallel tangents: half-ellipse
                    sections.append(Part.Wire(
                        _parallel_tangent_conic(p, q2, d1, n, rho)))
                else:
                    sections.append(Part.Wire(
                        [conic_arc(p, apex, q2, rho)]))
            return loft_sections(sections)

        # Five guide curves
        others = [obj.Guide2, obj.Guide3, obj.Guide4, obj.Guide5]
        if not all(others):
            raise GSFeatureError("'Five guide curves' needs all five")
        rails = [p_pts] + [
            stations(guide_wire(g, f"guide curve {i + 2}"))
            for i, g in enumerate(others)]
        for k in range(len(p_pts)):
            pts = [rails[j][k] for j in range(5)]
            bs = Part.BSplineCurve()
            try:
                bs.interpolate(pts)
            except Part.OCCError as err:
                raise GSFeatureError(
                    f"section interpolation failed ({err})")
            sections.append(Part.Wire([bs.toShape()]))
        return loft_sections(sections)


def make_sweep_conic(doc, name="SweepConic"):
    return make_feature(doc, SweepConic, name)


register(SweepConic, make_sweep_conic)
