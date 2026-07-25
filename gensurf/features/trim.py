"""Trim — GSD 'Trim' feature: mutual cut of two elements, keeping one
side of each, joined into a single result.

OCC entry points: BOPTools.SplitAPI.slice per element (see split.py),
then BRepBuilderAPI_Sewing via Part.makeShell for surface results (or
wire assembly for curve results), falling back to a compound when the
kept pieces do not join cleanly.
"""

import Part

from .base import GSFeature, GSFeatureError, resolve_linksub, make_feature
from .registry import register
from .split import cutter_shape_for, split_keep


class Trim(GSFeature):
    TYPE_ID = "GenSurf::Trim"
    HIDE_INPUTS = ("Element1", "Element2")
    REQUIRED_LINKS = ("Element1", "Element2")
    INPUT_SLOTS = (
        ("Element1", "First element",
         ("Face", "Shell", "Edge", "Wire"), False),
        ("Element2", "Second element",
         ("Face", "Shell", "Edge", "Wire"), False),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Element1", "Trim",
         "First element to trim", None),
        ("App::PropertyLinkSub", "Element2", "Trim",
         "Second element to trim", None),
        ("App::PropertyBool", "KeepOtherSide1", "Trim",
         "Keep the other side of the first element", False),
        ("App::PropertyBool", "KeepOtherSide2", "Trim",
         "Keep the other side of the second element", False),
    )

    @staticmethod
    def _join(pieces):
        face_pieces = [p for p in pieces if p.Faces]
        edge_pieces = [p for p in pieces if not p.Faces and p.Edges]
        faces = [f for p in face_pieces for f in p.Faces]
        if faces:
            surface = None
            try:
                shell = Part.makeShell(faces)
                if not shell.isNull() and shell.Faces:
                    surface = shell
            except Part.OCCError:
                pass
            if surface is None:
                surface = Part.makeCompound(face_pieces)
            if edge_pieces:  # mixed surface x curve trim: keep both
                return Part.makeCompound([surface] + edge_pieces)
            return surface
        edges = [e for p in pieces for e in p.Edges]
        if edges:
            try:
                sorter = getattr(Part, "sortEdges", None) or \
                    Part.__sortEdges__
                wires = [Part.Wire(group) for group in sorter(edges)]
                return wires[0] if len(wires) == 1 \
                    else Part.makeCompound(wires)
            except Part.OCCError:
                pass
            return Part.makeCompound(pieces)
        raise GSFeatureError("trim result is empty")

    def build(self, obj):
        e1 = resolve_linksub(obj.Element1)
        e2 = resolve_linksub(obj.Element2)

        cutter_for_1 = cutter_shape_for(obj.Element2, e1)
        cutter_for_2 = cutter_shape_for(obj.Element1, e2)

        kept1 = split_keep(e1, cutter_for_1, obj.KeepOtherSide1)
        kept2 = split_keep(e2, cutter_for_2, obj.KeepOtherSide2)
        return self._join(kept1 + kept2)


def make_trim(doc, name="Trim"):
    return make_feature(doc, Trim, name)


register(Trim, make_trim)
