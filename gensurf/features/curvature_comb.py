"""Curvature Comb — porcupine analysis of a curve.

At each sample the comb tooth points along the negated principal normal
with length proportional to the local curvature; the envelope connects
the tooth tips. Kinks, flat spots and curvature reversals become
immediately visible — the standard styling-quality check.

The comb is ordinary parametric geometry (a compound of tooth edges and
the envelope polyline), so it updates with the curve, prints nowhere,
and needs no custom display code. Scale = 0 picks an automatic scale
(half the curve length at the maximum curvature).
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   curve_wires, oriented_edge_walk, make_feature)
from .registry import register


class CurvatureComb(GSFeature):
    TYPE_ID = "GenSurf::CurvatureComb"
    REQUIRED_LINKS = ("Curve",)
    INPUT_SLOTS = (
        ("Curve", "Curve to analyze", ("Edge", "Wire"), False),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Curve", "Comb",
         "Curve whose curvature is displayed", None),
        ("App::PropertyInteger", "Samples", "Comb",
         "Comb teeth per curve", 50),
        ("App::PropertyFloat", "Scale", "Comb",
         "Tooth length scale (0 = automatic)", 0.0),
    )

    def build(self, obj):
        shape = resolve_linksub(obj.Curve)
        wires = curve_wires(shape)
        n = min(max(int(obj.Samples), 8), 500)

        teeth, tips = [], []
        for wire in wires:
            per_edge = max(4, n // max(1, len(wire.Edges)))
            for edge, samples in zip(
                    (getattr(wire, "OrderedEdges", None) or wire.Edges),
                    oriented_edge_walk(wire, per_edge)):
                u0, u1 = edge.FirstParameter, edge.LastParameter
                for i, (p, _tan) in enumerate(samples):
                    t = u0 + (u1 - u0) * i / per_edge
                    try:
                        k = edge.curvatureAt(t)
                        nrm = App.Vector(edge.normalAt(t))
                    except Part.OCCError:
                        k, nrm = 0.0, None  # straight: no defined normal
                    tips.append((p, k, nrm))

        max_k = max((k for _p, k, _n in tips), default=0.0)
        if max_k < 1e-12:
            raise GSFeatureError(
                "the curve has no curvature to display (straight line)")
        scale = obj.Scale
        total = sum(w.Length for w in wires)
        if scale <= 0:
            scale = 0.5 * total / max_k  # auto: longest tooth = L/2

        tip_pts, prev = [], None
        for p, k, nrm in tips:
            tip = p if (nrm is None or k < 1e-12) else p - nrm * (k * scale)
            if prev is None or (tip - p).Length > 1e-9:
                if (tip - p).Length > 1e-9:
                    teeth.append(Part.makeLine(p, tip))
            tip_pts.append(tip)
            prev = tip

        envelope = []
        for a, b in zip(tip_pts, tip_pts[1:]):
            if (b - a).Length > 1e-9:
                envelope.append(Part.makeLine(a, b))

        if not teeth and not envelope:
            raise GSFeatureError("comb is degenerate")
        return Part.makeCompound(teeth + envelope)


def make_curvature_comb(doc, name="CurvatureComb"):
    return make_feature(doc, CurvatureComb, name)


register(CurvatureComb, make_curvature_comb)
