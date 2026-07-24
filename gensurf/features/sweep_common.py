"""Shared machinery for the four Swept Surface operators.

Sampled-station engine: the driving guide(s) are discretized into
synchronized stations (index-matched, arc-length spaced); each operator
constructs its section geometry per station (line / circle arc / conic);
the stations are lofted (or ruled) into the swept surface.
"""

import FreeCAD as App
import Part

from .base import GSFeatureError, resolve_linksub, curve_wires

STATIONS = 25


def guide_wire(link, what):
    """Resolve a link to a single connected wire."""
    shape = resolve_linksub(link)
    wires = curve_wires(shape)
    if len(wires) != 1:
        raise GSFeatureError(f"{what} must be a single connected curve")
    return wires[0]


def stations(wire, n=STATIONS):
    """n arc-length-spaced points along the wire."""
    pts = wire.discretize(n)
    return [App.Vector(p) for p in pts]


def tangents(pts):
    """Finite-difference unit tangents along a station point list."""
    out = []
    for i in range(len(pts)):
        a = pts[i - 1] if i > 0 else pts[i]
        b = pts[i + 1] if i + 1 < len(pts) else pts[i]
        t = b - a
        if t.Length < 1e-12:
            raise GSFeatureError("guide has coincident sample points")
        t.normalize()
        out.append(t)
    return out


def support_face(link, what):
    shape = resolve_linksub(link)
    faces = [shape] if shape.ShapeType == "Face" else shape.Faces
    if not faces:
        raise GSFeatureError(f"{what} carries no surface")
    return faces[0]


def face_normal_at(face, p):
    u, v = face.Surface.parameter(p)
    n = App.Vector(face.normalAt(u, v))
    n.normalize()
    return n


def rail_curve(pts):
    """B-spline through station points (a rail of the swept surface)."""
    bs = Part.BSplineCurve()
    try:
        bs.interpolate(pts)
    except Part.OCCError as err:
        raise GSFeatureError(f"could not fit the swept rail ({err})")
    return bs.toShape()


def ruled_between(a_pts, b_pts):
    """Ruled surface between two synchronized rails."""
    face = Part.makeRuledSurface(rail_curve(a_pts), rail_curve(b_pts))
    if face.isNull() or not face.Faces:
        raise GSFeatureError("sweep produced no surface")
    return face


def loft_sections(wires):
    """Loft through per-station section wires. Ruled: a smooth
    (C2 ThruSections) loft through many stations overshoots between
    them; with ~25 stations the ruled join is the accurate choice."""
    try:
        result = Part.makeLoft(wires, False, True)
    except Part.OCCError as err:
        raise GSFeatureError(f"sweep loft failed ({err})")
    if result.isNull() or not result.Faces:
        raise GSFeatureError("sweep produced no surface")
    return result


def project_to_plane(q, p, n):
    """q projected into the plane through p with normal n."""
    w = q - p
    return q - n * w.dot(n)


def conic_arc(p, apex, q, rho):
    """Rational quadratic Bezier: the conic from p to q with tangents
    through the apex; rho is CATIA's conic parameter (0.5 = parabola)."""
    rho = min(max(rho, 0.01), 0.99)
    bez = Part.BezierCurve()
    bez.increase(2)
    bez.setPoles([p, apex, q])
    bez.setWeight(2, rho / (1.0 - rho))
    return bez.toShape()
