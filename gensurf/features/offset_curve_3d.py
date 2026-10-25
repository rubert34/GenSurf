"""Offset Curve 3D — a curve offset perpendicular to a direction.

At every point the curve moves along (direction x tangent), so that,
viewed along the direction, the two curves are parallel at the given
distance (the classic flange or rebate construction).

Where the curve runs parallel to the direction, the curve seen along the
direction folds back on itself, and direction x tangent reverses. Version
2 of the algorithm keeps the offset on the same side through such folds
(it only follows a reversal at a corner between edges, where the curve
really turns back); version 1, kept for documents built with it, switched
sides there. Both versions warn when it happens, and when the direction
lies in the plane of a planar curve (the offset then moves the curve out
of its plane: to offset within the plane, use the plane's normal as the
direction, or Offset Curve on Surface).

Implementation: sampled offset re-interpolated as a B-spline, one curve
per input edge; consecutive offsets are connected into a wire when they
touch. Not implemented yet: rounding the corner gaps that open at
tangency breaks (radius and tension); the gaps are bridged with
straight segments.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, GenSurfError, WARNING,
                   resolve_linksub, direction_from_ref, curve_wires,
                   oriented_edge_walk, make_feature)
from .registry import register

_SAMPLES = 48
_PARALLEL = 1e-9  # |direction x tangent| below this: no side defined


class OffsetCurve3D(GSFeature):
    TYPE_ID = "GenSurf::OffsetCurve3D"
    #: 1: side = direction x tangent at each sample (switches sides where
    #: the curve folds back seen along the direction); 2: one side kept
    ALGO_VERSION = 2
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

        walk = oriented_edge_walk(wire, _SAMPLES)
        source = "DirectionRef" if obj.DirectionRef else "Direction"
        if self.algo_version(obj) < 2:
            sides, folds = self._sides_v1(walk, d)
            if folds:
                self.report(obj, GenSurfError(
                    "offset-side-flips",
                    "the offset switches sides where the curve runs "
                    "parallel to the direction; right-click the feature "
                    "and choose Upgrade to current algorithm to keep one "
                    "side", [source], severity=WARNING))
        else:
            sides, folds = self._sides(walk, d)
            if self._direction_in_plane(wire, d):
                self.report(obj, GenSurfError(
                    "direction-in-curve-plane",
                    "the direction lies in the curve's plane, so the "
                    "offset moves the curve out of its plane; to offset "
                    "within the plane, use the plane's normal as the "
                    "direction, or Offset Curve on Surface",
                    [source], severity=WARNING))
            elif folds:
                self.report(obj, GenSurfError(
                    "tangent-parallel-to-direction",
                    f"the curve runs parallel to the direction at {folds} "
                    "place(s), where it folds back seen along the "
                    "direction; the offset keeps the same side there",
                    [source], severity=WARNING))

        pieces = []
        for samples, edge_sides in zip(walk, sides):
            pts = []
            for (p, _tan), side in zip(samples, edge_sides):
                q = p + side * dist
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


    @staticmethod
    def _sides_v1(walk, d):
        """Version 1: side = direction x tangent at every sample. Returns
        (sides per edge, number of side reversals inside edges)."""
        sides, folds = [], 0
        for samples in walk:
            edge_sides, prev = [], None
            for _p, tan in samples:
                side = d.cross(tan)
                if side.Length < _PARALLEL:
                    raise GSFeatureError(
                        "curve tangent is parallel to the offset "
                        "direction — the offset side is undefined there")
                side.normalize()
                if prev is not None and side.dot(prev) < 0:
                    folds += 1
                edge_sides.append(side)
                prev = side
            sides.append(edge_sides)
        return sides, folds

    @staticmethod
    def _sides(walk, d):
        """Version 2: direction x tangent, times a sign that toggles where
        the side reverses inside an edge (the tangent passed parallel to
        the direction: a fold), so the offset stays on one side. At a
        corner between edges a reversal is a real turn and is followed.
        Where the tangent is parallel to the direction the neighbouring
        side is used. Returns (sides per edge, number of folds)."""
        raw = [[d.cross(tan) for _p, tan in samples] for samples in walk]
        units = []
        for side in (s for edge in raw for s in edge):
            if side.Length < _PARALLEL:
                units.append(None)
            else:
                side = App.Vector(side)
                side.normalize()
                units.append(side)
        if all(u is None for u in units):
            raise GSFeatureError(
                "the curve runs along the offset direction everywhere — "
                "no offset side exists")
        # parallel samples take their neighbour's side (forward, then
        # backward for a leading run)
        last = None
        for i, u in enumerate(units):
            if u is None:
                units[i] = last
            else:
                last = u
        nxt = None
        for i in range(len(units) - 1, -1, -1):
            if units[i] is None:
                units[i] = nxt
            else:
                nxt = units[i]
        sign, folds, sides, k = 1.0, 0, [], 0
        for edge in raw:
            edge_sides, prev = [], None
            for u in units[k:k + len(edge)]:
                if prev is not None and u.dot(prev) < 0:
                    sign = -sign
                    folds += 1
                prev = u
                edge_sides.append(u * sign)
            sides.append(edge_sides)
            k += len(edge)
        return sides, folds

    @staticmethod
    def _direction_in_plane(wire, d):
        """True for a planar (not straight) curve whose plane contains
        the direction."""
        try:
            plane = wire.findPlane()
        except Part.OCCError:
            plane = None
        if plane is None:
            return False
        if all(isinstance(e.Curve, Part.Line) for e in wire.Edges) and \
                len(wire.Edges) == 1:
            return False  # a straight line lies in every plane
        normal = App.Vector(plane.Axis)
        return abs(normal.dot(d)) < 1e-6


def make_offset_curve_3d(doc, name="OffsetCurve3D"):
    return make_feature(doc, OffsetCurve3D, name)


register(OffsetCurve3D, make_offset_curve_3d)
