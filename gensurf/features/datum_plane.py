"""Offset datum plane — GSD 'Plane' (offset from plane) feature.

OCC entry point: pure Geom — Part.Plane translated along its normal; the
visible face is a bounded patch (datum planes are conceptually infinite;
Size only affects display, never downstream geometry, because dependents
should reference the plane's Surface, not its trimmed boundary).
"""

import Part
from FreeCAD import Units

from .base import GSFeature, GSFeatureError, resolve_linksub, make_feature
from .registry import register


class DatumPlane(GSFeature):
    TYPE_ID = "GenSurf::DatumPlane"
    REQUIRED_LINKS = ("Support",)
    INPUT_SLOTS = (
        ("Support", "Planar support face", ("Face",), False),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Support", "Plane",
         "Planar face or datum plane to offset from", None),
        ("App::PropertyDistance", "Offset", "Plane",
         "Offset distance along the support normal", "0 mm"),
        ("App::PropertyBool", "Reverse", "Plane",
         "Flip the offset direction", False),
        ("App::PropertyLength", "Size", "Display",
         "Half-size of the displayed patch", "50 mm"),
    )

    @staticmethod
    def _support_plane(obj):
        """(position, normal, center_hint) from the support link.

        Accepts a planar face, an object with exactly one planar face
        (e.g. another datum plane), or an origin/datum App::Plane object,
        which has no geometric shape — only a Placement.
        """
        import FreeCAD as App
        linked, _subs = obj.Support
        if getattr(linked, "TypeId", "") == "App::Plane":
            pl = linked.Placement
            normal = pl.Rotation.multVec(App.Vector(0, 0, 1))
            return pl.Base, normal, pl.Base

        shape = resolve_linksub(obj.Support)
        if shape.ShapeType != "Face":
            faces = shape.Faces
            if len(faces) != 1:
                raise GSFeatureError(
                    "support must be a single planar face or a datum plane")
            shape = faces[0]
        surf = shape.Surface
        if not isinstance(surf, Part.Plane):
            raise GSFeatureError("support face is not planar")
        return surf.Position, surf.Axis, shape.CenterOfMass

    def build(self, obj):
        position, normal, center_hint = self._support_plane(obj)

        offset = obj.Offset.getValueAs("mm").Value
        if obj.Reverse:
            offset = -offset
        base = position + normal * offset

        # center the display patch under the support's centroid projection
        center = center_hint - normal * (center_hint - base).dot(normal)
        plane = Part.Plane(center, normal)
        s = obj.Size.getValueAs("mm").Value
        return plane.toShape(-s, s, -s, s)


def make_datum_plane(doc, name="Plane"):
    return make_feature(doc, DatumPlane, name)


register(DatumPlane, make_datum_plane)
