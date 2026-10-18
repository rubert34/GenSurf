"""Offset Curve on Surface — a curve at a constant distance from another
curve, lying on the same support.

  * On a planar support (or a planar curve with no support) the offset
    is exact (OCC 2D offset), with Sharp or Round corner treatment.
  * On a curved support the offset is computed by sampling: each
    sample moves sideways (tangent x surface normal) and is re-projected
    onto the support. Euclidean mode converges the straight-line
    distance; Geodesic mode marches the distance along the surface.

The distance is either Distance or set by a Point the offset must pass
through (its distance to the curve is used, on the point's side);
ReverseDirection flips the side and BothSides builds both offsets.
Not implemented: a distance law, smoothing, and extrapolating the
result up to the support's boundary.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   plane_from_link, curve_wires, oriented_edge_walk,
                   make_feature)
from .registry import register

_SAMPLES = 60


class OffsetCurveOnSurface(GSFeature):
    TYPE_ID = "GenSurf::OffsetCurveOnSurface"
    REQUIRED_LINKS = ("Curve",)
    INPUT_SLOTS = (
        ("Curve", "Curve to offset", ("Edge", "Wire"), False),
        ("Support", "Support surface (blank: curve's own plane)",
         ("Face", "Shell"), True),
        ("Point", "Point the offset passes through", ("Vertex",), True),
    )
    ENUMS = {
        "DistanceMode": ("Euclidean", "Geodesic"),
        "CornerType": ("Sharp", "Round"),
    }
    PROPERTIES = (
        ("App::PropertyLinkSub", "Curve", "Offset Curve",
         "Curve to offset", None),
        ("App::PropertyLinkSub", "Support", "Offset Curve",
         "Support surface the offset lies on", None),
        ("App::PropertyDistance", "Distance", "Offset Curve",
         "Offset distance", "1 mm"),
        ("App::PropertyLinkSub", "Point", "Offset Curve",
         "Overrides Distance: the offset passes through this point",
         None),
        ("App::PropertyEnumeration", "DistanceMode", "Offset Curve",
         "Distance measured straight (Euclidean) or along the support "
         "(Geodesic)", None),
        ("App::PropertyEnumeration", "CornerType", "Offset Curve",
         "Corner treatment on planar supports", None),
        ("App::PropertyBool", "ReverseDirection", "Offset Curve",
         "Offset to the other side", False),
        ("App::PropertyBool", "BothSides", "Offset Curve",
         "Create the offset on both sides", False),
    )

    # -- planar (exact) path ----------------------------------------------

    @staticmethod
    def _planar_offset(wire, dist, corner, normal):
        # single straight segment: no intrinsic plane — plain translation
        if len(wire.Edges) == 1 and isinstance(wire.Edges[0].Curve,
                                               Part.Line):
            t = App.Vector(wire.Edges[0].tangentAt(
                wire.Edges[0].FirstParameter))
            s = t.cross(normal)
            if s.Length < 1e-9:
                raise GSFeatureError(
                    "the line is parallel to the offset plane normal — "
                    "give a support surface")
            s.normalize()
            a = wire.Edges[0].Vertexes[0].Point + s * dist
            b = wire.Edges[0].Vertexes[-1].Point + s * dist
            return Part.Wire([Part.makeLine(a, b)])
        join = 2 if corner == "Sharp" else 0
        try:
            off = wire.makeOffset2D(dist, join, False, True)  # open result
        except Part.OCCError as err:
            raise GSFeatureError(f"offset failed at {dist} mm ({err})")
        if not off.Edges:
            raise GSFeatureError(f"offset at {dist} mm is empty")
        return off

    # -- curved-support (sampled) path ------------------------------------

    @staticmethod
    def _side_dir(face, p, tangent):
        u, v = face.Surface.parameter(p)
        n = face.normalAt(u, v)
        s = tangent.cross(n)
        if s.Length < 1e-9:
            raise GSFeatureError(
                "curve tangent is parallel to the surface normal")
        s.normalize()
        return s

    @staticmethod
    def _project(face, p):
        u, v = face.Surface.parameter(p)
        return App.Vector(face.Surface.value(u, v))

    def _sampled_offset(self, wire, face, dist, mode):
        pts = []
        n_samples = max(8, _SAMPLES // max(1, len(wire.Edges)))
        # walk in travel order so reversed edges don't flip the side
        for samples in oriented_edge_walk(wire, n_samples):
            for p, tan in samples:
                if pts and (p - pts[-1][0]).Length < 1e-9:
                    continue
                pts.append((p, tan))

        out = []
        sign = 1.0 if dist >= 0 else -1.0
        d = abs(dist)
        for p, tan in pts:
            s = self._side_dir(face, p, tan) * sign
            if mode == "Geodesic":
                steps = max(8, int(d / max(d / 24.0, 1e-3)))
                step = d / steps
                cur, direc = App.Vector(p), App.Vector(s)
                for _ in range(steps):
                    nxt = self._project(face, cur + direc * step)
                    move = nxt - cur
                    if move.Length < 1e-12:
                        break
                    direc = move.normalize()
                    cur = nxt
                out.append(cur)
            else:  # Euclidean: converge |q - p| = d on the surface
                q = self._project(face, p + s * d)
                for _ in range(4):
                    w = q - p
                    if w.Length < 1e-9:
                        break
                    q = self._project(face, p + w.normalize() * d)
                out.append(q)

        if len(out) < 2:
            raise GSFeatureError("offset collapsed to a point")
        bs = Part.BSplineCurve()
        try:
            bs.interpolate(out)
        except Part.OCCError as err:
            raise GSFeatureError(f"could not fit the offset curve ({err})")
        return Part.Wire([bs.toShape()])

    # -- distances / sides -------------------------------------------------

    def _point_distance(self, obj, wire, face):
        """Signed offset so the result passes through obj.Point."""
        from .point import _vertex_point
        pt = _vertex_point(obj.Point, "Point")
        dist, pairs, _info = Part.Vertex(pt).distToShape(wire)
        if dist < 1e-9:
            raise GSFeatureError("the point lies on the curve")
        on_curve = pairs[0][1]
        # tangent at the closest point
        best, tan = None, None
        for e in wire.Edges:
            try:
                t = e.Curve.parameter(on_curve)
            except Part.OCCError:
                continue
            t = min(max(t, e.FirstParameter), e.LastParameter)
            q = e.valueAt(t)
            dd = (q - on_curve).Length
            if best is None or dd < best:
                best, tan = dd, App.Vector(e.tangentAt(t))
        if tan is None:
            tan = App.Vector(1, 0, 0)
        if face is not None:
            s = self._side_dir(face, on_curve, tan)
        else:
            plane = Part.makeCompound(wire.Edges).findPlane()
            n = plane.Axis if plane else App.Vector(0, 0, 1)
            s = tan.cross(n)
            if s.Length < 1e-9:
                raise GSFeatureError(
                    "the curve tangent is parallel to the plane normal "
                    "— give a support surface")
            s.normalize()
        side = 1.0 if (pt - on_curve).dot(s) >= 0 else -1.0
        return dist * side

    def build(self, obj):
        src = resolve_linksub(obj.Curve)
        wires = curve_wires(src)
        if len(wires) != 1:
            raise GSFeatureError("pick a single connected curve")
        wire = wires[0]

        face, normal = None, None
        planar = plane_from_link(obj.Support) if obj.Support else None
        if planar is not None:
            normal = planar[1]
        elif obj.Support:
            sup = resolve_linksub(obj.Support)
            faces = [sup] if sup.ShapeType == "Face" else sup.Faces
            if not faces:
                raise GSFeatureError("support contains no surface")
            face = faces[0]
        else:
            plane = Part.makeCompound(wire.Edges).findPlane()
            if plane is None:
                is_line = len(wire.Edges) == 1 and isinstance(
                    wire.Edges[0].Curve, Part.Line)
                if not is_line:
                    raise GSFeatureError(
                        "a non-planar curve needs a support surface")
                normal = App.Vector(0, 0, 1)  # default plane for a line
            else:
                normal = plane.Axis

        if obj.Point:
            dist = self._point_distance(obj, wire, face)
        else:
            dist = obj.Distance.getValueAs("mm").Value
            if abs(dist) < 1e-9:
                return wire.copy()
            if obj.ReverseDirection:
                dist = -dist

        def one_side(d):
            if face is not None:
                return self._sampled_offset(wire, face, d, obj.DistanceMode)
            return self._planar_offset(wire, d, obj.CornerType, normal)

        result = one_side(dist)
        if obj.BothSides and not obj.Point:
            other = one_side(-dist)
            result = Part.makeCompound([result, other])
        return result


def make_offset_curve_on_surface(doc, name="OffsetCurveOnSurface"):
    return make_feature(doc, OffsetCurveOnSurface, name)


register(OffsetCurveOnSurface, make_offset_curve_on_surface)
