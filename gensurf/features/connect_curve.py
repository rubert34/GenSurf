"""Connect curve — GSD 'Connect' feature: a blend curve between the
ends of two curves, with per-side continuity and tension (the wireframe
sibling of the surface Blend, kept separate exactly as in CATIA).

Pick one end point of each curve (with an optional explicit Curve per
side, as in the CATIA dialog, when the vertex alone is ambiguous).
Continuity per side:
  * Position  — the connect just starts/ends there,
  * Tangent   — matches the curve's end tangent,
  * Curvature — additionally matches the curve's osculating circle.

The connect is a single quintic Bezier built from Hermite end
conditions (the same mathematics as the surface Blend's sections).
Trim elements assembles both curves and the connect into one wire.
(The 'Base Curve' connect type is not implemented.)
"""

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, make_feature
from .registry import register

_CONT = ("Position", "Tangent", "Curvature")


def _end_of_curve(shape, extremity_point):
    """(edge, at_last_param) for the curve end nearest to the point."""
    best = None
    for e in shape.Edges:
        for at_last, param in ((False, e.FirstParameter),
                               (True, e.LastParameter)):
            d = (e.valueAt(param) - extremity_point).Length
            if best is None or d < best[0]:
                best = (d, e, at_last)
    if best is None or best[0] > 1e-6:
        raise GSFeatureError(
            "the picked point is not an end point of the curve")
    return best[1], best[2]


def _hermite_data(edge, at_last, continuity, tension, span):
    """(point, first_derivative, second_derivative) for one side of the
    connect, on a [0,1] parametrization of chord ~span. Derivatives point
    OUT of the curve (direction of the connect's travel from this end)."""
    param = edge.LastParameter if at_last else edge.FirstParameter
    p = edge.valueAt(param)
    zero = App.Vector(0, 0, 0)
    m = max(tension, 0.05) * span

    if continuity == "Position":
        return p, None, zero  # direction chosen by caller (chord)

    t = App.Vector(edge.tangentAt(param))
    t.normalize()
    if not at_last:
        t = t.negative()  # outward continuation direction
    first = t * m

    second = zero
    if continuity == "Curvature":
        try:
            k = edge.curvatureAt(param)
        except Part.OCCError:
            k = 0.0
        if k > 1e-12:
            center = edge.centerOfCurvatureAt(param)
            n = center - p
            n.normalize()
            second = n * (k * m * m)  # |P''| = kappa * speed^2
    return p, first, second


class ConnectCurve(GSFeature):
    TYPE_ID = "GenSurf::ConnectCurve"
    REQUIRED_LINKS = ("Point1", "Point2")
    INPUT_SLOTS = (
        ("Point1", "End point of the first curve", ("Vertex",), False),
        ("Curve1", "First curve (blank: the point's own curve)",
         ("Edge", "Wire"), True),
        ("Point2", "End point of the second curve", ("Vertex",), False),
        ("Curve2", "Second curve (blank: the point's own curve)",
         ("Edge", "Wire"), True),
    )
    ENUMS = {
        "Continuity1": _CONT,
        "Continuity2": _CONT,
    }
    PROPERTIES = (
        ("App::PropertyLinkSub", "Point1", "Connect",
         "End vertex on the first curve", None),
        ("App::PropertyLinkSub", "Point2", "Connect",
         "End vertex on the second curve", None),
        ("App::PropertyEnumeration", "Continuity1", "Connect",
         "Continuity with the first curve", None),
        ("App::PropertyEnumeration", "Continuity2", "Connect",
         "Continuity with the second curve", None),
        ("App::PropertyFloat", "Tension1", "Connect",
         "Tension on the first side (0.1 - 5)", 1.0),
        ("App::PropertyFloat", "Tension2", "Connect",
         "Tension on the second side (0.1 - 5)", 1.0),
        ("App::PropertyLinkSub", "Curve1", "Connect",
         "Explicit first curve (else the point's own object)", None),
        ("App::PropertyLinkSub", "Curve2", "Connect",
         "Explicit second curve (else the point's own object)", None),
        ("App::PropertyBool", "TrimElements", "Connect",
         "Assemble both curves and the connect into one element", False),
    )

    def __init__(self, obj):
        super().__init__(obj)
        if not hasattr(obj, "Proxy") or obj.Proxy is not self:
            obj.Proxy = self
        # default to Tangent, the CATIA default for Connect
        for prop in ("Continuity1", "Continuity2"):
            if getattr(obj, prop) == "Position":
                setattr(obj, prop, "Tangent")

    @staticmethod
    def _resolve_end(link, curve_link=None):
        linked, subs = link
        if not subs or not subs[0]:
            raise GSFeatureError(
                "pick an END POINT (vertex) of the curve, not the whole "
                "object")
        picked = linked.Shape.getElement(subs[0])
        if picked.ShapeType != "Vertex":
            raise GSFeatureError("the pick must be a vertex")
        from .base import resolve_linksub
        curve_shape = resolve_linksub(curve_link) if curve_link \
            else linked.Shape
        return _end_of_curve(curve_shape, picked.Point)

    def build(self, obj):
        e1, last1 = self._resolve_end(obj.Point1, obj.Curve1)
        e2, last2 = self._resolve_end(obj.Point2, obj.Curve2)

        p1 = e1.valueAt(e1.LastParameter if last1 else e1.FirstParameter)
        p2 = e2.valueAt(e2.LastParameter if last2 else e2.FirstParameter)
        span = max((p2 - p1).Length, 1e-6)

        q0, v0, a0 = _hermite_data(e1, last1, obj.Continuity1,
                                   obj.Tension1, span)
        q1, v1_out, a1 = _hermite_data(e2, last2, obj.Continuity2,
                                       obj.Tension2, span)
        chord = q1 - q0
        chord_dir = App.Vector(chord)
        chord_dir.normalize()
        if v0 is None:
            v0 = chord_dir * max(obj.Tension1, 0.05) * span
        # the connect travels q0 -> q1: its end derivative must point
        # INTO the second curve's outward continuation, i.e. opposite
        v1 = v1_out.negative() if v1_out is not None \
            else chord_dir * max(obj.Tension2, 0.05) * span

        poles = [
            q0,
            q0 + v0 * 0.2,
            q0 + v0 * 0.4 + a0 * 0.05,
            q1 - v1 * 0.4 + a1 * 0.05,
            q1 - v1 * 0.2,
            q1,
        ]
        bez = Part.BezierCurve()
        bez.setPoles(poles)
        connect = bez.toShape()

        if obj.TrimElements:
            from .base import resolve_linksub
            s1 = resolve_linksub(obj.Curve1) if obj.Curve1 \
                else obj.Point1[0].Shape
            s2 = resolve_linksub(obj.Curve2) if obj.Curve2 \
                else obj.Point2[0].Shape
            edges = [e.copy() for e in s1.Edges] + [connect] + \
                [e.copy() for e in s2.Edges]
            try:
                sorter = getattr(Part, "sortEdges", None) \
                    or Part.__sortEdges__
                wires = [Part.Wire(g) for g in sorter(edges)]
                return wires[0] if len(wires) == 1 else \
                    Part.makeCompound(wires)
            except Part.OCCError:
                return Part.makeCompound(edges)
        return connect


def make_connect_curve(doc, name="Connect"):
    return make_feature(doc, ConnectCurve, name)


register(ConnectCurve, make_connect_curve)
