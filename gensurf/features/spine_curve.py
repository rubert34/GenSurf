"""Spine Curve — GSD 'Spine' feature: the curve that crosses a set of
ordered section planes (or planar curves) orthogonally — the natural
sweeping spine for a Multi-Section surface.

Each section contributes an anchor point (the plane's position / the
curve's centroid) and a tangent (the plane's normal, oriented
consistently along the travel). The spine interpolates the anchors with
those tangents imposed. A Start point replaces the first anchor;
Reverse Direction flips the travel.

Not implemented: the Guide table (spine derived from guide curves) and
'Computed start point'.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, plane_from_link,
                   make_feature)
from .registry import register
from .point import _vertex_point


def _section_frame(entry):
    """(anchor, normal) for one Sections entry (obj, subs)."""
    linked, subs = entry
    subs = list(subs) if subs else []
    planar = plane_from_link((linked, subs))
    if planar is not None:
        position, normal = planar
        shape = getattr(linked, "Shape", None)
        if shape is not None and subs and subs[0]:
            shape = shape.getElement(subs[0])
        if shape is not None and not shape.isNull() \
                and getattr(shape, "Faces", None):
            position = shape.Faces[0].CenterOfMass
        return App.Vector(position), App.Vector(normal)

    shape = linked.Shape.getElement(subs[0]) if subs and subs[0] \
        else linked.Shape
    edges = shape.Edges
    if not edges:
        raise GSFeatureError(
            f"section {linked.Label} is neither a plane nor a curve")
    plane = Part.makeCompound(edges).findPlane()
    if plane is None:
        raise GSFeatureError(
            f"section curve {linked.Label} is not planar — a spine "
            "section needs a plane direction")
    total = sum(e.Length for e in edges)
    anchor = App.Vector(0, 0, 0)
    for e in edges:
        anchor += e.CenterOfMass * (e.Length / total)
    return anchor, App.Vector(plane.Axis)


class SpineCurve(GSFeature):
    TYPE_ID = "GenSurf::SpineCurve"
    REQUIRED_LINKS = ("Sections",)
    INPUT_SLOTS = (
        ("Sections", "Section planes / planar curves in order (2+)",
         ("Face", "Edge", "Wire"), False, True),
        ("StartPoint", "Start point (replaces the first anchor)",
         ("Vertex",), True),
    )
    PROPERTIES = (
        ("App::PropertyLinkSubList", "Sections", "Spine",
         "Ordered section planes or planar curves", None),
        ("App::PropertyLinkSub", "StartPoint", "Spine",
         "Optional start point on the first section", None),
        ("App::PropertyBool", "ReverseDirection", "Spine",
         "Reverse the spine's travel direction", False),
    )

    def build(self, obj):
        frames = [_section_frame(entry) for entry in obj.Sections]
        if len(frames) < 2:
            raise GSFeatureError("a spine needs at least two sections")

        pts = [f[0] for f in frames]
        if obj.StartPoint:
            pts[0] = _vertex_point(obj.StartPoint, "Start point")

        for i in range(len(pts) - 1):
            if (pts[i + 1] - pts[i]).Length < 1e-9:
                raise GSFeatureError(
                    f"sections {i + 1} and {i + 2} coincide")

        # orient each normal along the local travel direction
        tangents = []
        for i, (_anchor, n) in enumerate(frames):
            prev_pt = pts[i - 1] if i > 0 else pts[i]
            next_pt = pts[i + 1] if i + 1 < len(pts) else pts[i]
            travel = next_pt - prev_pt
            d = App.Vector(n)
            if d.Length < 1e-12:
                raise GSFeatureError(f"section {i + 1} has no normal")
            d.normalize()
            if d.dot(travel) < 0:
                d = d.negative()
            if obj.ReverseDirection:
                d = d.negative()
            # chordal parametrization wants unit-magnitude tangents
            tangents.append(d)

        if obj.ReverseDirection:
            pts = pts[::-1]
            tangents = tangents[::-1]

        bs = Part.BSplineCurve()
        try:
            bs.interpolate(Points=pts, PeriodicFlag=False,
                           Tangents=tangents,
                           TangentFlags=[True] * len(pts), Scale=False)
        except Part.OCCError as err:
            raise GSFeatureError(f"spine interpolation failed ({err})")
        return bs.toShape()


def make_spine_curve(doc, name="Spine"):
    return make_feature(doc, SpineCurve, name)


register(SpineCurve, make_spine_curve)
