"""Spline — GSD 'Spline' feature: an interpolated curve through an
ordered list of points, with optional per-point tangent directions and
tensions, closable, optionally lying on a support.

Per-point constraints follow the MultiSection row-mapping pattern:
TangentRows holds 1-based point indices, TangentDirections the matching
direction references (straight edge / planar face normal), Tensions the
matching magnitudes (negative tension reverses the tangent — CATIA's
Reverse Tgt.). Points are projected onto the support when 'Geometry on
support' is set (exact on planar supports; on curved supports the spline
interpolates projected points but is not constrained to the surface
between them). Per-point curvature directions are not implemented.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   resolve_linksublist, direction_from_ref, make_feature)
from .registry import register


class Spline(GSFeature):
    TYPE_ID = "GenSurf::Spline"
    REQUIRED_LINKS = ("Points",)
    INPUT_SLOTS = (
        ("Points", "Spline points in order (2+)", ("Vertex",), False, True),
        ("Support", "Support (Geometry on support)", ("Face",), True),
        ("TangentDirections", "Tangent directions (row-mapped)",
         ("Edge", "Face"), True, True),
    )
    PROPERTIES = (
        ("App::PropertyLinkSubList", "Points", "Spline",
         "Ordered points the spline passes through", None),
        ("App::PropertyBool", "CloseSpline", "Spline",
         "Close the spline into a periodic curve", False),
        ("App::PropertyLinkSub", "Support", "Spline",
         "Support surface: points are projected onto it", None),
        ("App::PropertyLinkSubList", "TangentDirections", "Spline",
         "Direction references for constrained points", None),
        ("App::PropertyIntegerList", "TangentRows", "Spline",
         "1-based point index for each tangent direction", []),
        ("App::PropertyFloatList", "Tensions", "Spline",
         "Tension per tangent direction (negative reverses)", []),
    )

    def build(self, obj):
        pts = []
        for shape in resolve_linksublist(obj.Points):
            if shape.ShapeType != "Vertex":
                if len(shape.Vertexes) == 1:
                    shape = shape.Vertexes[0]
                else:
                    raise GSFeatureError(
                        "spline points must be single vertices")
            p = App.Vector(shape.Point)
            if pts and (p - pts[-1]).Length < 1e-9:
                # silent dedup would desynchronize TangentRows indices
                raise GSFeatureError(
                    f"points {len(pts)} and {len(pts) + 1} coincide — "
                    "remove the duplicate pick")
            pts.append(p)
        if len(pts) < 2:
            raise GSFeatureError("a spline needs at least two points")

        face = None
        if obj.Support:
            sup = resolve_linksub(obj.Support)
            faces = [sup] if sup.ShapeType == "Face" else sup.Faces
            if not faces:
                raise GSFeatureError("support contains no surface")
            face = faces[0]
            proj = []
            for p in pts:
                u, v = face.Surface.parameter(p)
                proj.append(App.Vector(face.Surface.value(u, v)))
            pts = proj

        # per-point tangent constraints (row-mapped)
        dirs = resolve_linksublist(obj.TangentDirections)
        rows = list(obj.TangentRows or [])
        tens = list(obj.Tensions or [])
        if dirs and len(rows) != len(dirs):
            raise GSFeatureError(
                f"{len(dirs)} tangent directions but {len(rows)} row "
                "indices — set TangentRows to the point index of each")

        tangents, flags = None, None
        if dirs:
            tangents = [App.Vector(0, 0, 0)] * len(pts)
            flags = [False] * len(pts)
            for k, ref in enumerate(dirs):
                row = rows[k]
                if not 1 <= row <= len(pts):
                    raise GSFeatureError(
                        f"tangent row {row} is out of range (1 - "
                        f"{len(pts)})")
                d = App.Vector(direction_from_ref(ref))
                d.normalize()
                t = tens[k] if k < len(tens) else 1.0
                if abs(t) < 0.05:
                    t = 0.05 if t >= 0 else -0.05
                # chordal parametrization: tension ~1 is the natural
                # magnitude; larger values push the curve further along
                tangents[row - 1] = d * t
                flags[row - 1] = True

        bs = Part.BSplineCurve()
        try:
            if tangents is not None:
                bs.interpolate(Points=pts, PeriodicFlag=obj.CloseSpline,
                               Tangents=tangents, TangentFlags=flags,
                               Scale=False)
            else:
                bs.interpolate(Points=pts, PeriodicFlag=obj.CloseSpline)
        except Part.OCCError as err:
            raise GSFeatureError(f"spline interpolation failed ({err})")
        return bs.toShape()


def make_spline(doc, name="Spline"):
    return make_feature(doc, Spline, name)


register(Spline, make_spline)
