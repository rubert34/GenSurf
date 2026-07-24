"""Split — GSD 'Split' feature: cut an element by a cutter, keep one side.

OCC entry point: BOPAlgo_Builder via ``shape.generalFuse`` — splits the
element by the cutter into pieces (the fuse map tells which pieces belong
to the element); a deterministic side rule then selects which pieces
survive, and KeepOtherSide flips it (CATIA's "Other side" button).

Side rules:
  * cutter has faces          — signed distance along the cutter's normal
                                at the closest point (works for surface
                                and curve elements alike).
  * curve cutting a surface   — sign of dot(p - c, n x t): element normal
                                x cutter tangent at the closest point.
  * curve cutting a curve     — the piece containing the element's start
                                vertex is the default side.

Datum planes (App::Plane or a GenSurf datum plane) used as cutters are
expanded to a face large enough to cover the whole element — the plane
is infinite conceptually; its display patch size must not matter.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub, make_feature,
                   plane_from_link)
from .registry import register


def cutter_shape_for(link, element):
    """Resolve a cutter link; planar datums become faces sized to the
    element's bounding box."""
    plane = plane_from_link(link)
    linked = link[0]
    is_datum = getattr(linked, "TypeId", "") == "App::Plane" or \
        getattr(linked, "GSType", "") == "GenSurf::DatumPlane"
    if plane is not None and is_datum:
        position, normal = plane
        bb = element.BoundBox
        size = max(bb.DiagonalLength, 1.0) * 2.0
        center = App.Vector(bb.Center)
        center = center - normal * (center - position).dot(normal)
        return Part.Plane(center, normal).toShape(-size, size, -size, size)
    return resolve_linksub(link)


def side_value(piece, cutter, element_start=None):
    """Signed side measure of a piece relative to the cutter."""
    p = piece.CenterOfMass
    dist, pairs, _ = piece.distToShape(cutter)  # noqa: F841
    c = pairs[0][1] if pairs else cutter.CenterOfMass

    if cutter.Faces:
        face = min(cutter.Faces, key=lambda f: f.distToShape(
            Part.Vertex(c))[0])
        u, v = face.Surface.parameter(c)
        normal = face.normalAt(u, v)
        return (p - c).dot(normal)

    if cutter.Edges and piece.Faces:
        edge = min(cutter.Edges, key=lambda e: e.distToShape(
            Part.Vertex(c))[0])
        t = edge.tangentAt(edge.Curve.parameter(c)) \
            if hasattr(edge.Curve, "parameter") else edge.tangentAt(
                (edge.FirstParameter + edge.LastParameter) / 2)
        face = piece.Faces[0]
        u, v = face.Surface.parameter(c)
        n = face.normalAt(u, v)
        return (p - c).dot(n.cross(t))

    if element_start is not None:
        # curve cut by curve: sign by whether the piece holds the start
        d = piece.distToShape(Part.Vertex(element_start))[0]
        return 1.0 if d < 1e-6 else -1.0

    raise GSFeatureError("cannot determine sides for this cutter type")


def split_keep(element, cutter, keep_other=False):
    """Split element by cutter, return the kept pieces (list).

    Uses generalFuse (BOPAlgo_Builder): its map reports which result
    pieces originate from the element, excluding the cutter's own pieces.
    """
    _compound, mapping = element.generalFuse([cutter], 1e-6)
    pieces = list(mapping[0]) if mapping and mapping[0] else []
    if len(pieces) < 2:
        raise GSFeatureError(
            "cutter does not fully traverse the element (a cut that stops "
            "mid-surface cannot split it)")

    start = element.Vertexes[0].Point if element.Vertexes else None
    scored = [(side_value(p, cutter, start), p) for p in pieces]
    wanted = [p for s, p in scored if (s < 0) == bool(keep_other) and s != 0]
    if not wanted:
        wanted = [max(scored, key=lambda sp: abs(sp[0]))[1]]
    return wanted


class Split(GSFeature):
    TYPE_ID = "GenSurf::Split"
    REQUIRED_LINKS = ("Element", "Cutter")
    INPUT_SLOTS = (
        ("Element", "Element to split (surface or curve)",
         ("Face", "Shell", "Edge", "Wire"), False),
        ("Cutter", "Cutting element (surface, plane or curve)",
         ("Face", "Shell", "Edge", "Wire"), False),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Element", "Split",
         "Element to be split", None),
        ("App::PropertyLinkSub", "Cutter", "Split",
         "Element that does the cutting", None),
        ("App::PropertyBool", "KeepOtherSide", "Split",
         "Keep the other side of the cut", False),
    )

    def build(self, obj):
        element = resolve_linksub(obj.Element)
        cutter = cutter_shape_for(obj.Cutter, element)
        kept = split_keep(element, cutter, obj.KeepOtherSide)
        return kept[0] if len(kept) == 1 else Part.makeCompound(kept)


def make_split(doc, name="Split"):
    return make_feature(doc, Split, name)


register(Split, make_split)
