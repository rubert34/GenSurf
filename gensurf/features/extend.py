"""Extend — natural extrapolation of curves and surfaces (Rhino-style).

One pick defines everything, CATIA-style extremity selection:
  * a curve's end vertex  — the curve is extended past that end,
  * a surface boundary edge — the surface is extended past that edge.

"Natural" means the underlying mathematics is continued, never a bolted-on
tangent ribbon:
  * analytic curves/surfaces (lines, circles, planes, cylinders, cones,
    extrusions, revolutions) — exact parameter-range extension: an arc
    stays on its circle, a cylinder stays the same cylinder;
  * B-spline / Bezier curves — the polynomial of the end span is continued
    exactly (de Casteljau blossom segment beyond the knot range);
  * B-spline surfaces — OCC evaluates the surface beyond its bounds with
    the same polynomial continuation, so the face is simply rebuilt on an
    enlarged parameter rectangle.

Negative lengths shrink instead of extend. The result contains the
original plus the extension (one face / one wire).
"""

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, make_feature
from .registry import register

_SPLINE_TYPES = ("BSplineCurve", "BezierCurve")


# -- exact Bezier machinery ----------------------------------------------


def _blossom(poles, args):
    pts = list(poles)
    for t in args:
        pts = [pts[i] * (1.0 - t) + pts[i + 1] * t
               for i in range(len(pts) - 1)]
    return pts[0]


def bezier_segment(poles, t0, t1):
    """Exact control points of the polynomial restricted to [t0, t1]
    (valid for t outside [0, 1]: pure affine combinations)."""
    n = len(poles) - 1
    return [_blossom(poles, [t0] * (n - i) + [t1] * i)
            for i in range(n + 1)]


def _make_bezier_edge(poles):
    bez = Part.BezierCurve()
    bez.setPoles(poles)
    return bez.toShape()


# -- curve extension ------------------------------------------------------


def _extension_edge_spline(curve, at_last, target):
    """Exact natural continuation of a spline curve end by target length."""
    if type(curve).__name__ == "BezierCurve":
        beziers = [curve]
    else:
        beziers = curve.toBezier()
    span = beziers[-1] if at_last else beziers[0]
    poles = span.getPoles()

    def ext_edge(e):
        seg = bezier_segment(poles, 1.0, 1.0 + e) if at_last \
            else bezier_segment(poles, -e, 0.0)
        return _make_bezier_edge(seg)

    # derivative magnitude at the end for an initial guess, then bisect
    d1 = span.tangent(1.0 if at_last else 0.0)[0]
    scale = max(App.Vector(d1).Length, 1e-9)
    # tangent() returns a unit vector; recover the true speed via points
    p_a = span.value(1.0 if at_last else 0.0)
    p_b = span.value(1.0 - 1e-6 if at_last else 1e-6)
    speed = max((p_a - p_b).Length / 1e-6, 1e-9)
    e = target / speed
    lo, hi = 0.0, e
    while ext_edge(hi).Length < target:
        hi *= 2.0
        if hi > 1e6:
            raise GSFeatureError("extension length calibration diverged")
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if ext_edge(mid).Length < target:
            lo = mid
        else:
            hi = mid
    return ext_edge((lo + hi) / 2.0)


def _extension_edge_analytic(edge, at_last, target):
    """Exact parameter extension for curves whose geometry continues
    beyond the trim (all analytic types)."""
    curve = edge.Curve
    if at_last:
        p_end = edge.LastParameter
        p_new = curve.parameterAtDistance(target, p_end)
        return curve.toShape(p_end, p_new)
    p_end = edge.FirstParameter
    p_new = curve.parameterAtDistance(-target, p_end)
    return curve.toShape(p_new, p_end)


def extend_curve(shape, extremity_point, target, mode="Natural"):
    """Extend the wire/edge past the end nearest to extremity_point."""
    sorter = getattr(Part, "sortEdges", None) or Part.__sortEdges__
    if not shape.Edges:
        raise GSFeatureError("the element contains no curve to extend")
    wires = [Part.Wire(g) for g in sorter(shape.Edges)]
    # the wire whose endpoint matches the picked vertex
    def end_dist(w):
        return min((w.Vertexes[0].Point - extremity_point).Length,
                   (w.Vertexes[-1].Point - extremity_point).Length)
    wire = min(wires, key=end_dist)
    if end_dist(wire) > 1e-6:
        raise GSFeatureError(
            "the picked point is not an end point of the curve")

    # which end, and which edge owns it
    at_first = (wire.Vertexes[0].Point - extremity_point).Length < 1e-6
    end_edge = wire.Edges[0] if at_first else wire.Edges[-1]
    # orient: does the picked point sit at this edge's Last or First param?
    at_last_param = (end_edge.valueAt(end_edge.LastParameter)
                     - extremity_point).Length < 1e-6

    if target < 0:  # negative length shrinks from the picked end
        remove = -target
        if remove >= end_edge.Length - 1e-9:
            raise GSFeatureError(
                "shrink length exceeds the end edge — use Split for "
                "larger cuts")
        if at_last_param:
            t = end_edge.getParameterByLength(end_edge.Length - remove)
            trimmed = end_edge.Curve.toShape(end_edge.FirstParameter, t)
        else:
            t = end_edge.getParameterByLength(remove)
            trimmed = end_edge.Curve.toShape(t, end_edge.LastParameter)
        others = [e for e in wire.Edges if not e.isSame(end_edge)]
        group = sorter(others + [trimmed])[0] if others else [trimmed]
        return Part.Wire(group)

    if mode == "Tangent":
        ext = _tangent_extension_edge(end_edge, at_last_param, target)
    elif mode == "Curvature":
        ext = _curvature_extension_edge(end_edge, at_last_param, target)
    elif type(end_edge.Curve).__name__ in _SPLINE_TYPES:
        # trim the geometric curve to the edge's own range first: after
        # a split, the edge covers only part of the underlying spline
        curve = end_edge.Curve
        try:
            curve = curve.toBSpline(end_edge.FirstParameter,
                                    end_edge.LastParameter)
        except Part.OCCError:
            pass
        ext = _extension_edge_spline(curve, at_last_param, target)
    else:
        ext = _extension_edge_analytic(end_edge, at_last_param, target)

    return Part.Wire(sorter(list(wire.Edges) + [ext])[0])


# -- tangent / curvature approximation modes ------------------------------


def _tangent_extension_edge(edge, at_last_param, target):
    """Linear ribbon: straight continuation along the end tangent."""
    param = edge.LastParameter if at_last_param else edge.FirstParameter
    p = edge.valueAt(param)
    t = edge.tangentAt(param)
    t = App.Vector(t)
    t.normalize()
    if not at_last_param:
        t = t.negative()
    return Part.makeLine(p, p + t * target)


def _osculating_continue(points_inward, arclen):
    """Continue past points_inward[-1] along the osculating circle fitted
    to the last three samples; straight when nearly collinear.
    points_inward: [q2, q1, q0] from inside toward the boundary end q0."""
    q2, q1, q0 = points_inward
    chord = (q0 - q2).Length
    area2 = (q1 - q2).cross(q0 - q2).Length
    if chord < 1e-12 or area2 / max(chord, 1e-12) < 1e-9:
        t = q0 - q1
        t.normalize()
        return q0 + t * arclen
    circle = Part.Arc(q2, q1, q0).toShape().Curve
    center, axis, r = circle.Center, circle.Axis, circle.Radius
    # orientation: rotating q0 about the axis must move along q0-q1 dir
    import math
    ang = math.degrees(arclen / r)
    rot = App.Rotation(axis, ang)
    cand = center + rot.multVec(q0 - center)
    if (cand - q0).dot(q0 - q1) < 0:
        rot = App.Rotation(axis, -ang)
        cand = center + rot.multVec(q0 - center)
    return cand


def _curvature_extension_edge(edge, at_last_param, target):
    """G2 continuation: circular arc matching the end's osculating circle
    (a straight line where the end curvature vanishes)."""
    param = edge.LastParameter if at_last_param else edge.FirstParameter
    span = edge.LastParameter - edge.FirstParameter
    h = max(span * 1e-3, 1e-9)
    sign = -1.0 if at_last_param else 1.0
    q0 = edge.valueAt(param)
    q1 = edge.valueAt(param + sign * h)
    q2 = edge.valueAt(param + sign * 2 * h)

    end = _osculating_continue([q2, q1, q0], target)
    mid = _osculating_continue([q2, q1, q0], target / 2.0)
    straight = (mid - (q0 + end) * 0.5).Length < 1e-9
    if straight:
        return Part.makeLine(q0, end)
    return Part.Arc(q0, mid, end).toShape()


# -- surface extension ----------------------------------------------------


def _boundary_side(face, edge):
    """Which parameter side of the face the edge sits on:
    'umin' | 'umax' | 'vmin' | 'vmax'."""
    u1, u2, v1, v2 = face.ParameterRange
    du, dv = max(u2 - u1, 1e-12), max(v2 - v1, 1e-12)
    votes = {}
    for f in (0.25, 0.5, 0.75):
        p = edge.valueAt(
            edge.FirstParameter
            + f * (edge.LastParameter - edge.FirstParameter))
        u, v = face.Surface.parameter(p)
        candidates = {
            "umin": abs(u - u1) / du, "umax": abs(u - u2) / du,
            "vmin": abs(v - v1) / dv, "vmax": abs(v - v2) / dv,
        }
        best = min(candidates, key=candidates.get)
        if candidates[best] < 0.05:
            votes[best] = votes.get(best, 0) + 1
    if not votes:
        raise GSFeatureError(
            "the picked edge is not a parameter boundary of the surface")
    return max(votes, key=votes.get)


def _side_arclength(surf, side, bounds, d):
    """Arc length of the crossing iso-curve over the extension band."""
    u1, u2, v1, v2 = bounds
    um, vm = (u1 + u2) / 2.0, (v1 + v2) / 2.0
    n = 128
    total = 0.0
    prev = None
    for i in range(n + 1):
        f = i / n
        if side == "umin":
            p = surf.value(u1 - d * f, vm)
        elif side == "umax":
            p = surf.value(u2 + d * f, vm)
        elif side == "vmin":
            p = surf.value(um, v1 - d * f)
        else:
            p = surf.value(um, v2 + d * f)
        if prev is not None:
            total += (p - prev).Length
        prev = p
    return total


def _period_cap(surf, side, span):
    """Max parameter extension before the face closes onto itself, or
    None if unbounded."""
    periodic = surf.isUClosed() if side in ("umin", "umax") \
        else surf.isVClosed()
    if not periodic:
        return None
    try:
        period = surf.UPeriod() if side in ("umin", "umax") \
            else surf.VPeriod()
    except Exception:
        import math
        period = 2 * math.pi
    return max(period - span, 0.0)


def _band_value(surf, side, bounds, du, dt):
    """Surface point: du along the boundary [0..1], dt past it (param)."""
    u1, u2, v1, v2 = bounds
    if side == "umin":
        return surf.value(u1 - dt, v1 + (v2 - v1) * du)
    if side == "umax":
        return surf.value(u2 + dt, v1 + (v2 - v1) * du)
    if side == "vmin":
        return surf.value(u1 + (u2 - u1) * du, v1 - dt)
    return surf.value(u1 + (u2 - u1) * du, v2 + dt)


def _extension_strip(surf, side, bounds, d, mode="Natural", target=None):
    """Extension band as a face. Natural mode samples the beyond-range
    evaluator (exact continuation); Tangent/Curvature build the classic
    approximations from boundary samples."""
    u1, u2, v1, v2 = bounds
    span = (u2 - u1) if side in ("umin", "umax") else (v2 - v1)
    h = max(span * 0.01, 1e-9)
    nu, nt = 33, 9
    grid = []
    for i in range(nu):
        fu = i / (nu - 1)
        row = []
        if mode == "Natural":
            for j in range(nt):
                row.append(_band_value(surf, side, bounds, fu,
                                       d * j / (nt - 1)))
        else:
            b = _band_value(surf, side, bounds, fu, 0.0)
            q1 = _band_value(surf, side, bounds, fu, -h)
            q2 = _band_value(surf, side, bounds, fu, -2 * h)
            try:
                # central difference: the evaluator continues smoothly
                # beyond the range even when the topology refuses to
                qf = _band_value(surf, side, bounds, fu, h)
                tangent = qf - q1
            except Exception:
                tangent = b - q1
            tangent.normalize()
            for j in range(nt):
                arclen = target * j / (nt - 1)
                if arclen == 0.0:
                    row.append(b)
                elif mode == "Tangent":
                    row.append(b + tangent * arclen)
                else:  # Curvature
                    row.append(_osculating_continue([q2, q1, b], arclen))
        grid.append(row)
    strip = Part.BSplineSurface()
    strip.interpolate(grid)
    return strip.toShape()


def extend_face(face, edge, target, mode="Natural"):
    surf = face.Surface
    side = _boundary_side(face, edge)
    u1, u2, v1, v2 = face.ParameterRange
    bounds = (u1, u2, v1, v2)
    span = (u2 - u1) if side in ("umin", "umax") else (v2 - v1)

    if mode != "Natural":
        if target < 0:
            raise GSFeatureError(
                "negative extension only works in Natural mode")
        strip = _extension_strip(surf, side, bounds, 0.0, mode, target)
        try:
            shell = Part.makeShell([face, strip.Faces[0]])
            if not shell.isNull() and len(shell.Faces) == 2:
                return shell
        except Part.OCCError:
            pass
        return Part.makeCompound([face, strip])

    cap = _period_cap(surf, side, span)
    if cap is not None and cap < 1e-9:
        raise GSFeatureError(
            "this boundary direction already covers the full closed "
            "surface — nothing to extend past")

    # calibrate the parameter delta to the requested arc length
    hi = abs(target) * max(u2 - u1, v2 - v1) / max(face.Area, 1e-9) + 1e-6
    while _side_arclength(surf, side, bounds, hi) < abs(target):
        if cap is not None and hi >= cap:
            hi = cap  # clamp: extension closes the surface completely
            break
        hi = min(hi * 2.0, cap) if cap is not None else hi * 2.0
        if hi > 1e9:
            raise GSFeatureError("extension length calibration diverged")
    lo = 0.0
    if _side_arclength(surf, side, bounds, hi) >= abs(target):
        for _ in range(60):
            mid = (lo + hi) / 2.0
            if _side_arclength(surf, side, bounds, mid) < abs(target):
                lo = mid
            else:
                hi = mid
    d = hi
    if target < 0:
        d = -d

    if side == "umin":
        new = (u1 - d, u2, v1, v2)
    elif side == "umax":
        new = (u1, u2 + d, v1, v2)
    elif side == "vmin":
        new = (u1, u2, v1 - d, v2)
    else:
        new = (u1, u2, v1, v2 + d)
    if new[0] >= new[1] or new[2] >= new[3]:
        raise GSFeatureError("negative extension removes the whole surface")

    # exact single-face path: only when the face actually fills its
    # parameter rectangle — rebuilding a trimmed face (hole, non-
    # rectangular outline) from bounds would silently drop the trims
    rect_like = False
    try:
        full = surf.toShape(u1, u2, v1, v2)
        rect_like = abs(full.Area - face.Area) < \
            1e-6 * max(face.Area, 1.0)
    except Part.OCCError:
        pass
    if rect_like:
        try:
            out = surf.toShape(*new)
            if not out.isNull() and out.Faces and out.isValid():
                return out
        except Part.OCCError:
            pass

    if target < 0:
        raise GSFeatureError(
            "negative extension is not supported on this surface type")

    # B-spline path: natural-continuation strip sewn onto the original
    strip = _extension_strip(surf, side, bounds, d)
    try:
        shell = Part.makeShell([face, strip.Faces[0]])
        if not shell.isNull() and len(shell.Faces) == 2:
            return shell
    except Part.OCCError:
        pass
    return Part.makeCompound([face, strip])


# -- the feature ----------------------------------------------------------


class Extend(GSFeature):
    TYPE_ID = "GenSurf::Extend"
    REQUIRED_LINKS = ("Boundary",)
    INPUT_SLOTS = (
        ("Boundary", "Extremity: curve end point or surface boundary edge",
         ("Vertex", "Edge"), False),
        ("Element", "Element to extend (optional when unambiguous)",
         ("Face", "Edge", "Wire"), True),
    )
    ENUMS = {
        "Mode": ("Natural", "Tangent", "Curvature"),
    }
    PROPERTIES = (
        ("App::PropertyLinkSub", "Boundary", "Extend",
         "End vertex of a curve, or boundary edge of a surface", None),
        ("App::PropertyLinkSub", "Element", "Extend",
         "The curve or face to extend, when the extremity alone is "
         "ambiguous (e.g. shells)", None),
        ("App::PropertyDistance", "Length", "Extend",
         "Extension length (negative shrinks, Natural mode only)", "10 mm"),
        ("App::PropertyEnumeration", "Mode", "Extend",
         "Natural: exact mathematical continuation; Tangent: linear "
         "ribbon; Curvature: osculating-circle blend", None),
    )

    def build(self, obj):
        linked, subs = obj.Boundary
        if not subs or not subs[0]:
            raise GSFeatureError(
                "pick a curve end point or a surface boundary edge "
                "(a sub-element, not the whole object)")
        picked = linked.Shape.getElement(subs[0])
        target = obj.Length.getValueAs("mm").Value
        if abs(target) < 1e-9:
            raise GSFeatureError("extension length is zero")

        # the element to extend: explicit pick wins; otherwise the
        # boundary's owning object
        from .base import resolve_linksub
        element = resolve_linksub(obj.Element) if obj.Element \
            else linked.Shape

        mode = getattr(obj, "Mode", "Natural")
        if picked.ShapeType == "Vertex":
            if element.Faces:
                raise GSFeatureError(
                    "a surface corner is ambiguous (two boundary edges "
                    "meet there) — pick the boundary EDGE you want to "
                    "extend across instead of the corner point")
            return extend_curve(element, picked.Point, target, mode)

        if picked.ShapeType == "Edge":
            owner = None
            if element.ShapeType == "Face":
                owner = element  # explicit face pick disambiguates shells
            else:
                for f in element.Faces:
                    if any(picked.isSame(e) for e in f.Edges):
                        owner = f
                        break
            if owner is None:
                if not element.Faces:
                    raise GSFeatureError(
                        "picked edge belongs to no surface — to extend "
                        "a curve, pick its end point instead")
                raise GSFeatureError(
                    "the picked edge is not a boundary of the chosen "
                    "element")
            return extend_face(owner, picked, target, mode)

        raise GSFeatureError(
            f"cannot extend from a {picked.ShapeType}")


def make_extend(doc, name="Extend"):
    return make_feature(doc, Extend, name)


register(Extend, make_extend)
