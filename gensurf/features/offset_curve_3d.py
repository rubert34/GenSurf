"""Offset Curve 3D — a curve offset perpendicular to a direction.

At every point the curve moves along (direction x tangent), so that,
viewed along the direction, the two curves are parallel at the given
distance (the classic flange or rebate construction).

Implementation: sampled offset re-interpolated as a B-spline, one curve
per input edge; consecutive offsets are connected into a wire when they
touch. Not implemented yet: rounding the corner gaps that open at
tangency breaks (radius and tension); the gaps are bridged with
straight segments.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   direction_from_ref, curve_wires, oriented_edge_walk,
                   make_feature)
from .registry import register

_SAMPLES = 48


class OffsetCurve3D(GSFeature):
    TYPE_ID = "GenSurf::OffsetCurve3D"
    REQUIRED_LINKS = ("Curve",)
    INPUT_SLOTS = (
        ("Curve", "Curve to offset", ("Edge", "Wire"), False),
        ("DirectionRef", "Direction (edge / planar face, optional)",
         ("Edge", "Face"), True),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Curve", "Offset Curve 3D",
         "Curve to offset", None),
        ("App::PropertyLinkSub", "DirectionRef", "Offset Curve 3D",
         "Direction reference: straight edge or planar face normal", None),
        ("App::PropertyVector", "Direction", "Offset Curve 3D",
         "Explicit direction (used when no reference is picked)",
         App.Vector(0, 0, 1)),
        ("App::PropertyDistance", "Offset", "Offset Curve 3D",
         "Offset distance", "1 mm"),
        ("App::PropertyBool", "ReverseDirection", "Offset Curve 3D",
         "Offset to the other side", False),
    )

    def build(self, obj):
        src = resolve_linksub(obj.Curve)
        wires = curve_wires(src)
        if len(wires) != 1:
            raise GSFeatureError("pick a single connected curve")
        wire = wires[0]

        if obj.DirectionRef:
            d = App.Vector(direction_from_ref(
                resolve_linksub(obj.DirectionRef)))
        else:
            d = App.Vector(obj.Direction)
        if d.Length < 1e-12:
            raise GSFeatureError("the offset direction is null")
        d.normalize()

        dist = obj.Offset.getValueAs("mm").Value
        if abs(dist) < 1e-9:
            return wire.copy()
        if obj.ReverseDirection:
            dist = -dist

        pieces = []
        # walk in travel order so reversed edges don't flip the side
        for samples in oriented_edge_walk(wire, _SAMPLES):
            pts = []
            for p, tan in samples:
                s = d.cross(tan)
                if s.Length < 1e-9:
                    raise GSFeatureError(
                        "curve tangent is parallel to the offset "
                        "direction — the offset side is undefined there")
                s.normalize()
                q = p + s * dist
                if pts and (q - pts[-1]).Length < 1e-9:
                    continue
                pts.append(q)
            if len(pts) < 2:
                continue
            bs = Part.BSplineCurve()
            try:
                bs.interpolate(pts)
            except Part.OCCError as err:
                raise GSFeatureError(
                    f"could not fit the offset curve ({err})")
            pieces.append(bs.toShape())
        if not pieces:
            raise GSFeatureError("offset produced no curve")

        # bridge corner gaps between consecutive edge offsets
        chain = [pieces[0]]
        for nxt in pieces[1:]:
            a = chain[-1].Vertexes[-1].Point
            b = nxt.Vertexes[0].Point
            if (b - a).Length > 1e-7:
                chain.append(Part.makeLine(a, b))
            chain.append(nxt)
        try:
            return Part.Wire(chain)
        except Part.OCCError:
            return Part.makeCompound(chain)


def make_offset_curve_3d(doc, name="OffsetCurve3D"):
    return make_feature(doc, OffsetCurve3D, name)


register(OffsetCurve3D, make_offset_curve_3d)
