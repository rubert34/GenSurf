"""Shape Fillet — GSD 'Fillet' feature (BiTangent type): a rolling-ball
fillet surface between two supports.

The supports are mutually trimmed at their intersection (each keeps one
side — Reverse side 1/2 flips which), sewn into a shell, and the shared
edge is filleted at the given radius. Supports that already share a
boundary edge are sewn and filleted directly.

Not implemented: the TriTangent type (no OCC entry point), Chordal
radius, the radius Law, the conic parameter, untrimmed supports and the
Extremities modes — supports are always trimmed, matching the dialog's
default 'Trim support 1/2' state.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   make_feature)
from .registry import register
from .split import side_value


def _kept_piece(face, other, reverse):
    """Trim `face` by `other`, keeping one side of the intersection."""
    _compound, mapping = face.generalFuse([other], 1e-6)
    pieces = [p for p in (mapping[0] if mapping else []) if p.Faces]
    if len(pieces) < 2:
        return None  # no traversal — the faces may share an edge already
    scored = [(side_value(p, other), p) for p in pieces]
    wanted = [p for s, p in scored if (s < 0) == bool(reverse) and s != 0]
    if not wanted:
        wanted = [max(scored, key=lambda sp: abs(sp[0]))[1]]
    return wanted[0]


class ShapeFillet(GSFeature):
    TYPE_ID = "GenSurf::ShapeFillet"
    REQUIRED_LINKS = ("Support1", "Support2")
    INPUT_SLOTS = (
        ("Support1", "First support surface", ("Face", "Shell"), False),
        ("Support2", "Second support surface", ("Face", "Shell"), False),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Support1", "Fillet",
         "First support surface", None),
        ("App::PropertyLinkSub", "Support2", "Fillet",
         "Second support surface", None),
        ("App::PropertyDistance", "Radius", "Fillet",
         "Fillet radius", "5 mm"),
        ("App::PropertyBool", "ReverseSide1", "Fillet",
         "Keep the other side of support 1", False),
        ("App::PropertyBool", "ReverseSide2", "Fillet",
         "Keep the other side of support 2", False),
    )

    def build(self, obj):
        s1 = resolve_linksub(obj.Support1)
        s2 = resolve_linksub(obj.Support2)
        f1 = s1.Faces[0] if s1.Faces else None
        f2 = s2.Faces[0] if s2.Faces else None
        if f1 is None or f2 is None:
            raise GSFeatureError("both supports must carry a surface")
        radius = obj.Radius.getValueAs("mm").Value
        if radius < 1e-9:
            raise GSFeatureError("radius is zero")

        k1 = _kept_piece(f1, f2, obj.ReverseSide1)
        k2 = _kept_piece(f2, f1, obj.ReverseSide2)
        if k1 is None or k2 is None:
            # supports may already meet at a shared boundary
            k1, k2 = f1, f2

        comp = Part.makeCompound([k1.copy(), k2.copy()])
        comp.sewShape()
        if not comp.Shells:
            raise GSFeatureError(
                "the supports do not intersect (and share no boundary) — "
                "nothing to fillet")
        shell = comp.Shells[0]

        shared = [e for e in shell.Faces[0].Edges
                  if len(shell.Faces) > 1 and
                  any(e.isSame(e2) for e2 in shell.Faces[1].Edges)]
        if not shared:
            raise GSFeatureError(
                "no common edge between the trimmed supports")
        try:
            result = shell.makeFillet(radius, shared)
        except Part.OCCError as err:
            raise GSFeatureError(
                f"fillet of radius {radius} mm failed — it may be too "
                f"large for these supports ({err})")
        if result.isNull() or not result.Faces:
            raise GSFeatureError("fillet produced no surface")
        return result


def make_shape_fillet(doc, name="ShapeFillet"):
    return make_feature(doc, ShapeFillet, name)


register(ShapeFillet, make_shape_fillet)
