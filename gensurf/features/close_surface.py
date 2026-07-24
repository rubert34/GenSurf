"""Close Surface — GSD 'Close Surface' (Volumes): turns a closed set
of surfaces into a solid.

The picked surfaces are sewn into a shell; if the shell still has open
boundaries, planar openings are capped with flat faces (as CATIA does)
before solidifying. Non-planar openings cannot be capped automatically
— close them first with a Fill or Blend surface and include it in the
selection.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksublist,
                   make_feature)
from .registry import register
from .boundary import free_boundary_edges


class CloseSurface(GSFeature):
    TYPE_ID = "GenSurf::CloseSurface"
    REQUIRED_LINKS = ("Elements",)
    INPUT_SLOTS = (
        ("Elements", "Surfaces forming a closed volume",
         ("Face", "Shell"), False, True),
    )
    PROPERTIES = (
        ("App::PropertyLinkSubList", "Elements", "CloseSurface",
         "Surfaces to solidify", None),
        ("App::PropertyBool", "CapPlanarHoles", "CloseSurface",
         "Close remaining planar openings with flat faces", True),
    )

    def build(self, obj):
        faces = []
        for shape in resolve_linksublist(obj.Elements):
            if shape.Faces:
                faces.extend(f.copy() for f in shape.Faces)
        if not faces:
            raise GSFeatureError("the selection contains no surface")

        comp = Part.makeCompound(faces)
        comp.sewShape()
        if not comp.Shells:
            raise GSFeatureError(
                "the surfaces do not connect into a shell — their "
                "boundaries must touch exactly (Join them first)")
        shell = max(comp.Shells, key=lambda s: len(s.Faces))

        if not shell.isClosed():
            free = free_boundary_edges(shell)
            if not (free and obj.CapPlanarHoles):
                raise GSFeatureError(
                    "the surfaces do not enclose a volume — there are "
                    "open boundaries")
            sorter = getattr(Part, "sortEdges", None) or \
                Part.__sortEdges__
            caps = []
            for group in sorter(free):
                try:
                    wire = Part.Wire(group)
                except Part.OCCError:
                    raise GSFeatureError(
                        "an open boundary does not form a closed loop")
                if not wire.isClosed():
                    raise GSFeatureError(
                        "an open boundary does not form a closed loop")
                if Part.makeCompound(wire.Edges).findPlane() is None:
                    raise GSFeatureError(
                        "a non-planar opening cannot be capped — close "
                        "it with a Fill surface and include it")
                caps.append(Part.Face(wire))
            comp = Part.makeCompound(
                [f.copy() for f in shell.Faces] + caps)
            comp.sewShape()
            closed = [s for s in comp.Shells if s.isClosed()]
            if not closed:
                raise GSFeatureError(
                    "capping did not close the volume — check for gaps "
                    "between the surfaces")
            shell = closed[0]

        try:
            solid = Part.makeSolid(shell)
        except Part.OCCError as err:
            raise GSFeatureError(f"solidification failed ({err})")
        if solid.isNull() or not solid.Solids:
            raise GSFeatureError("no solid could be built")
        if solid.Volume < 0:
            solid = solid.reversed()
        return solid


def make_close_surface(doc, name="CloseSurface"):
    return make_feature(doc, CloseSurface, name)


register(CloseSurface, make_close_surface)
