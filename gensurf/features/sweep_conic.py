"""Sweep Conic — a conic arc built at every station and lofted along the
rails.

Modes:
  * Tangent to 2 surfaces — an exact conic (rational quadratic Bezier)
    from rail 1 to rail 2; the end tangents come from the two tangent
    surfaces, rotated by Angle 1/2 out of their tangent planes, and
    Parameter sets the fullness (0.5 = parabola);
  * Through 5 rails — a section through all five rails at each station
    (an interpolated curve approximating the exact five-point conic).

Not implemented: 3- and 4-rail conics (mixed point and tangent
constraints), parameter and angle laws, end limits and smoothing.
"""


import math

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, make_feature
from .registry import register
from .sweep_common import (rail_wire, stations, tangents, support_face,
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
    REQUIRED_LINKS = ("Rail1",)
    INPUT_SLOTS = (
        ("Rail1", "Rail curve 1", ("Edge", "Wire"), False),
        ("Rail2", "Rail curve 2", ("Edge", "Wire"), True),
        ("Rail3", "Rail curve 3", ("Edge", "Wire"), True),
        ("Rail4", "Rail curve 4", ("Edge", "Wire"), True),
        ("Rail5", "Last rail curve", ("Edge", "Wire"), True),
        ("TangentSurface1", "Tangent surface at rail 1", ("Face",), True),
        ("TangentSurface2", "Tangent surface at rail 2", ("Face",), True),
    )
    ENUMS = {
        "Mode": ("Tangent to 2 surfaces", "Through 5 rails"),
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "Mode", "Sweep",
         "How the conic section is constrained", None),
        ("App::PropertyLinkSub", "Rail1", "Sweep",
         "Rail curve 1", None),
        ("App::PropertyLinkSub", "Rail2", "Sweep",
         "Rail curve 2", None),
        ("App::PropertyLinkSub", "Rail3", "Sweep",
         "Rail curve 3 (five rails)", None),
        ("App::PropertyLinkSub", "Rail4", "Sweep",
         "Rail curve 4 (five rails)", None),
        ("App::PropertyLinkSub", "Rail5", "Sweep",
         "Last rail curve (five rails)", None),
        ("App::PropertyLinkSub", "TangentSurface1", "Sweep",
         "Tangent surface at rail 1", None),
        ("App::PropertyLinkSub", "TangentSurface2", "Sweep",
         "Tangent surface at rail 2", None),
        ("App::PropertyAngle", "Angle1", "Sweep",
         "Tangent angle from tangent surface 1", "0 deg"),
        ("App::PropertyAngle", "Angle2", "Sweep",
         "Tangent angle from tangent surface 2", "0 deg"),
        ("App::PropertyFloat", "Parameter", "Sweep",
         "Conic parameter: <0.5 ellipse, 0.5 parabola, >0.5 hyperbola",
         0.5),
    )

    @staticmethod
    def _tangent_dir(face, p, n, toward, angle_rad):
        """In-station-plane tangent at p from a tangent surface,
        oriented toward the other rail, rotated by the angle."""
        ns = face_normal_at(face, p)
        t = ns.cross(n)  # surface-plane ∩ station-plane direction
        if t.Length < 1e-9:
            raise GSFeatureError(
                "the tangent surface is parallel to the station plane")
        t.normalize()
        if t.dot(toward) < 0:
            t = t.negative()
        if abs(angle_rad) > 1e-12:
            e = n.cross(t)
            t = t * math.cos(angle_rad) + e * math.sin(angle_rad)
        return t

    def build(self, obj):
        mode = obj.Mode
        g1 = rail_wire(obj.Rail1, "rail curve 1")
        p_pts = stations(g1)
        sections = []

        if mode == "Tangent to 2 surfaces":
            if not obj.Rail2:
                raise GSFeatureError("pick rail curve 2")
            if not (obj.TangentSurface1 and obj.TangentSurface2):
                raise GSFeatureError(
                    "the tangent conic needs both tangent surfaces")
            q_pts = stations(rail_wire(obj.Rail2, "rail curve 2"))
            tg = tangents(p_pts)
            f1 = support_face(obj.TangentSurface1, "tangent surface 1")
            f2 = support_face(obj.TangentSurface2, "tangent surface 2")
            a1 = math.radians(obj.Angle1.getValueAs("deg").Value)
            a2 = math.radians(obj.Angle2.getValueAs("deg").Value)
            rho = obj.Parameter
            for p, q, n in zip(p_pts, q_pts, tg):
                q2 = project_to_plane(q, p, n)
                chord = q2 - p
                if chord.Length < 1e-9:
                    raise GSFeatureError("the rails touch")
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

        # Through 5 rails
        others = [obj.Rail2, obj.Rail3, obj.Rail4, obj.Rail5]
        if not all(others):
            raise GSFeatureError("'Through 5 rails' needs all five")
        rails = [p_pts] + [
            stations(rail_wire(g, f"rail curve {i + 2}"))
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
