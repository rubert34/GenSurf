"""Blend surface — GSD 'Blend' feature.

Connects two curves with controllable continuity to their support
surfaces on each side:

  * Position  — G0, the blend simply reaches the curve.
  * Tangency  — G1, the blend leaves the support tangentially (cross
                tangent = support normal x curve tangent).
  * Curvature — G2, additionally matches the support's cross-boundary
                curvature (sampled by finite differences on the support).

Method (no single OCC API provides CATIA blends): both curves are
discretized (arc-length or parameter coupling, auto-oriented), a quintic
Hermite blend curve is built per sample pair from the end conditions,
and the family is lofted via BRepOffsetAPI_ThruSections (Part.makeLoft).
Tension scales the end derivative magnitudes, exactly like CATIA's
tension parameter.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub, make_feature,
                   curve_wires)
from .registry import register

_CONTINUITY = ("Position", "Tangency", "Curvature")


class BlendSurface(GSFeature):
    TYPE_ID = "GenSurf::BlendSurface"
    REQUIRED_LINKS = ("Curve1", "Curve2")
    INPUT_SLOTS = (
        ("Curve1", "First curve", ("Edge", "Wire"), False),
        ("Support1", "First support (tangency/curvature)", ("Face",), True),
        ("Curve2", "Second curve", ("Edge", "Wire"), False),
        ("Support2", "Second support (tangency/curvature)", ("Face",), True),
    )
    ENUMS = {
        "Continuity1": _CONTINUITY,
        "Continuity2": _CONTINUITY,
        "Coupling": ("ArcLength", "Parameter"),
        "Borders": ("Align to supports", "Natural"),
    }
    PROPERTIES = (
        ("App::PropertyLinkSub", "Curve1", "Blend",
         "First boundary curve", None),
        ("App::PropertyLinkSub", "Support1", "Blend",
         "Support surface of the first curve", None),
        ("App::PropertyLinkSub", "Curve2", "Blend",
         "Second boundary curve", None),
        ("App::PropertyLinkSub", "Support2", "Blend",
         "Support surface of the second curve", None),
        ("App::PropertyEnumeration", "Continuity1", "Blend",
         "Continuity with the first support", None),
        ("App::PropertyEnumeration", "Continuity2", "Blend",
         "Continuity with the second support", None),
        ("App::PropertyFloat", "Tension1", "Blend",
         "Tension on the first side (0.1 - 5)", 1.0),
        ("App::PropertyFloat", "Tension2", "Blend",
         "Tension on the second side (0.1 - 5)", 1.0),
        ("App::PropertyBool", "ReverseTangent1", "Blend",
         "Flip the departure side on the first support", False),
        ("App::PropertyBool", "ReverseTangent2", "Blend",
         "Flip the departure side on the second support", False),
        ("App::PropertyEnumeration", "Coupling", "Blend",
         "How sample points on both curves are matched", None),
        ("App::PropertyBool", "AutoOrient", "Blend",
         "Automatically align the direction of the second curve", True),
        ("App::PropertyInteger", "Samples", "Blend",
         "Number of blend sections (quality vs speed)", 24),
        ("App::PropertyEnumeration", "Borders", "Blend",
         "Side edges: continue the supports' own border edges, or "
         "leave naturally along the coupling direction", None),
    )

    # -- geometry helpers --------------------------------------------------

    @staticmethod
    def _sample(wire, n, coupling):
        if coupling == "Parameter" and len(wire.Edges) == 1:
            edge = wire.Edges[0]
            f, l = edge.FirstParameter, edge.LastParameter
            return [edge.valueAt(f + (l - f) * i / (n - 1)) for i in range(n)]
        return wire.discretize(Number=n)

    @staticmethod
    def _polyline_tangents(pts):
        tangents = []
        for i in range(len(pts)):
            a = pts[max(i - 1, 0)]
            b = pts[min(i + 1, len(pts) - 1)]
            t = b.sub(a)
            if t.Length < 1e-12:
                t = App.Vector(1, 0, 0)
            t.normalize()
            tangents.append(t)
        return tangents

    @staticmethod
    def _surface_point(surface, near):
        u, v = surface.parameter(near)
        return surface.value(u, v)

    @staticmethod
    def _border_continuation(support, corner, curve_tangent):
        """Direction continuing the support's side border past a corner
        of the blend curve, or None if no border edge meets it."""
        ct = App.Vector(curve_tangent)
        ct.normalize()
        for e in support.Edges:
            for vtx, at_start in ((e.Vertexes[0], True),
                                  (e.Vertexes[-1], False)):
                if (vtx.Point - corner).Length > 1e-6:
                    continue
                param = e.FirstParameter if at_start else e.LastParameter
                t = App.Vector(e.tangentAt(param))
                t.normalize()
                if not at_start:
                    t = t.negative()  # point from the corner into the edge
                if abs(t.dot(ct)) > 0.9:
                    continue  # that's the blend curve itself
                return t.negative()  # continuation OUT of the support
        return None

    def _end_condition(self, point, edge_tangent, support, continuity,
                       tension, length, toward, reverse=False,
                       border=None):
        """First and second derivative of the blend curve at one end,
        for a [0,1] parametrization of span ~length. ``border`` is an
        optional (direction, weight) steering the departure toward the
        support's border continuation (side-edge alignment)."""

        def steer(direction, normal=None):
            if border is None:
                return direction
            bdir, w = border
            mixed = direction * (1.0 - w) + bdir * w
            if normal is not None:  # stay in the support tangent plane
                mixed = mixed - normal * mixed.dot(normal)
            if mixed.Length < 1e-9:
                return direction
            mixed.normalize()
            return mixed

        m = max(tension, 0.05) * length
        zero = App.Vector(0, 0, 0)
        if continuity == "Position" or support is None:
            d = App.Vector(toward)
            if d.Length < 1e-12:
                return zero, zero
            d.normalize()
            return steer(d) * m, zero

        u, v = support.Surface.parameter(point)
        normal = support.normalAt(u, v)
        cross = normal.cross(edge_tangent)
        if cross.Length < 1e-9:
            d = App.Vector(toward)
            if d.Length < 1e-12:
                return zero, zero  # coincident sample points
            d.normalize()
            return d * m, zero
        cross.normalize()
        if cross.dot(toward) < 0:
            cross = cross.negative()

        # the support surface lies opposite `cross` — always sample there
        inward = cross.negative()
        tangent = cross.negative() if reverse else cross
        tangent = steer(tangent, normal)

        first = tangent * m
        second = zero
        if continuity == "Curvature":
            # sample the support's cross-boundary section inward and take a
            # one-sided finite-difference second derivative
            h = max(length * 0.01, 1e-3)
            q1 = self._surface_point(support.Surface, point + inward * h)
            q2 = self._surface_point(support.Surface, point + inward * (2 * h))
            k = (point - q1 * 2 + q2).multiply(1.0 / (h * h))
            second = k.multiply(m * m)
        return first, second

    # -- build -------------------------------------------------------------

    def build(self, obj):
        wires1 = curve_wires(resolve_linksub(obj.Curve1))
        wires2 = curve_wires(resolve_linksub(obj.Curve2))
        if len(wires1) > 1 or len(wires2) > 1:
            App.Console.PrintWarning(
                f"[GenSurf] {obj.Name}: multiple curves in input, "
                "blending the first of each\n")
        w1, w2 = wires1[0], wires2[0]

        sup1 = resolve_linksub(obj.Support1, expect="Face") \
            if obj.Support1 else None
        sup2 = resolve_linksub(obj.Support2, expect="Face") \
            if obj.Support2 else None
        if obj.Continuity1 != "Position" and sup1 is None:
            raise GSFeatureError(
                f"Continuity1 = {obj.Continuity1} needs Support1")
        if obj.Continuity2 != "Position" and sup2 is None:
            raise GSFeatureError(
                f"Continuity2 = {obj.Continuity2} needs Support2")

        n = min(max(int(obj.Samples), 5), 200)
        pts1 = self._sample(w1, n, obj.Coupling)
        pts2 = self._sample(w2, n, obj.Coupling)

        if obj.AutoOrient:
            straight = (pts1[0] - pts2[0]).Length + (pts1[-1] - pts2[-1]).Length
            flipped = (pts1[0] - pts2[-1]).Length + (pts1[-1] - pts2[0]).Length
            if flipped < straight:
                pts2 = list(reversed(pts2))

        tan1 = self._polyline_tangents(pts1)
        tan2 = self._polyline_tangents(pts2)

        # side-edge alignment: continuation of each support's border
        # edge at the four corners, faded over the outer sections
        align = getattr(obj, "Borders", "Align to supports") == \
            "Align to supports"
        corners = {}
        if align:
            for side, sup, pts, tan in ((1, sup1, pts1, tan1),
                                        (2, sup2, pts2, tan2)):
                if sup is None:
                    continue
                for endkey, idx in (("start", 0), ("end", n - 1)):
                    d = self._border_continuation(sup, pts[idx], tan[idx])
                    if d is not None:
                        corners[(side, endkey)] = d
        zone = max(2, n // 5)

        def border_for(side, i):
            import math as _math
            if (side, "start") in corners and i < zone:
                w = 0.5 * (1 + _math.cos(_math.pi * i / zone))
                return (corners[(side, "start")], w)
            if (side, "end") in corners and i > n - 1 - zone:
                w = 0.5 * (1 + _math.cos(_math.pi * (n - 1 - i) / zone))
                return (corners[(side, "end")], w)
            return None

        sections = []
        for i, (p0, p1, t0, t1) in enumerate(zip(pts1, pts2, tan1, tan2)):
            length = max((p1 - p0).Length, 1e-6)
            v0, a0 = self._end_condition(
                p0, t0, sup1, obj.Continuity1, obj.Tension1,
                length, p1 - p0, obj.ReverseTangent1, border_for(1, i))
            v1_in, a1 = self._end_condition(
                p1, t1, sup2, obj.Continuity2, obj.Tension2,
                length, p0 - p1, obj.ReverseTangent2, border_for(2, i))
            v1 = v1_in.negative()  # P'(1) points out of the blend, into side 2

            # quintic Hermite -> Bezier poles
            poles = [
                p0,
                p0 + v0 * 0.2,
                p0 + v0 * 0.4 + a0 * 0.05,
                p1 - v1 * 0.4 + a1 * 0.05,
                p1 - v1 * 0.2,
                p1,
            ]
            bez = Part.BezierCurve()
            bez.setPoles(poles)
            sections.append(Part.Wire([bez.toShape()]))

        try:
            surface = Part.makeLoft(sections, False, False)
        except Part.OCCError as err:
            raise GSFeatureError(f"blend loft failed: {err}")
        if surface.isNull() or not surface.Faces:
            raise GSFeatureError("blend produced no surface")
        return surface


def make_blend_surface(doc, name="Blend"):
    return make_feature(doc, BlendSurface, name)


register(BlendSurface, make_blend_surface)
