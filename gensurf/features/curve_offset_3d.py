"""3D Curve Offset — GSD '3D Curve Offset' feature.

Offsets a 3D curve perpendicular to a pulling direction: at every point
the curve moves along (pulling direction x tangent), so that viewed
along the pulling direction the two curves are parallel at the given
offset (the classic flange/rabbet construction).

Implementation: sampled offset re-interpolated as a B-spline, one curve
per input edge; consecutive offsets are connected into a wire when they
touch. The CATIA '3D corner parameters' (Radius / Tension), which round
the corner discontinuities that appear at tangency breaks, are not
implemented yet — corner gaps are bridged with straight segments.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   direction_from_ref, curve_wires, make_feature)
from .registry import register

_SAMPLES = 48


class CurveOffset3D(GSFeature):
    TYPE_ID = "GenSurf::CurveOffset3D"
    REQUIRED_LINKS = ("Curve",)
    INPUT_SLOTS = (
        ("Curve", "Curve to offset", ("Edge", "Wire"), False),
        ("PullingDirection", "Pulling direction (edge / planar face)",
         ("Edge", "Face"), True),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Curve", "CurveOffset",
         "Curve to offset", None),
        ("App::PropertyLinkSub", "PullingDirection", "CurveOffset",
         "Direction reference: straight edge or planar face normal", None),
        ("App::PropertyVector", "Direction", "CurveOffset",
         "Explicit pulling direction (used when no reference is picked)",
         App.Vector(0, 0, 1)),
        ("App::PropertyDistance", "Offset", "CurveOffset",
         "Offset distance", "1 mm"),
        ("App::PropertyBool", "ReverseDirection", "CurveOffset",
         "Offset to the other side", False),
    )

    def build(self, obj):
        src = resolve_linksub(obj.Curve)
        wires = curve_wires(src)
        if len(wires) != 1:
            raise GSFeatureError("pick a single connected curve")
        wire = wires[0]

        if obj.PullingDirection:
            d = App.Vector(direction_from_ref(
                resolve_linksub(obj.PullingDirection)))
        else:
            d = App.Vector(obj.Direction)
        if d.Length < 1e-12:
            raise GSFeatureError("pulling direction is null")
        d.normalize()

        dist = obj.Offset.getValueAs("mm").Value
        if abs(dist) < 1e-9:
            return wire.copy()
        if obj.ReverseDirection:
            dist = -dist

        pieces = []
        for edge in wire.Edges:
            pts = []
            u0, u1 = edge.FirstParameter, edge.LastParameter
            for i in range(_SAMPLES + 1):
                t = u0 + (u1 - u0) * i / _SAMPLES
                p = App.Vector(edge.valueAt(t))
                tan = App.Vector(edge.tangentAt(t))
                s = d.cross(tan)
                if s.Length < 1e-9:
                    raise GSFeatureError(
                        "curve tangent is parallel to the pulling "
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


def make_curve_offset_3d(doc, name="CurveOffset"):
    return make_feature(doc, CurveOffset3D, name)


register(CurveOffset3D, make_curve_offset_3d)
