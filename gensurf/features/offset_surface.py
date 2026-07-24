"""Offset surface — GSD 'Offset' feature.

OCC entry point: BRepOffsetAPI_MakeOffsetShape via
``shape.makeOffsetShape(offset, tolerance)`` on a face or shell. The
result is an open surface offset along the source's normals; Reverse
flips the side.
"""

from .base import GSFeature, GSFeatureError, resolve_linksub, make_feature
from .registry import register


class OffsetSurface(GSFeature):
    TYPE_ID = "GenSurf::OffsetSurface"
    REQUIRED_LINKS = ("Source",)
    INPUT_SLOTS = (
        ("Source", "Surface to offset", ("Face", "Shell"), False),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Source", "Offset",
         "Face or shell to offset", None),
        ("App::PropertyDistance", "Offset", "Offset",
         "Offset distance along the surface normal", "1 mm"),
        ("App::PropertyBool", "Reverse", "Offset",
         "Offset to the other side", False),
    )

    def build(self, obj):
        import Part
        src = resolve_linksub(obj.Source)
        if src.ShapeType not in ("Face", "Shell"):
            faces = src.Faces
            if not faces:
                raise GSFeatureError(
                    f"source contains no surface (got {src.ShapeType})")
            src = faces[0] if len(faces) == 1 else Part.makeShell(faces)

        offset = obj.Offset.getValueAs("mm").Value
        if obj.Reverse:
            offset = -offset
        if abs(offset) < 1e-9:
            return src.copy()

        try:
            result = src.makeOffsetShape(offset, 1e-6)
        except Part.OCCError as err:
            raise GSFeatureError(
                f"offset failed at {offset} mm — surface may self-intersect "
                f"at this distance ({err})")
        if result.isNull() or not result.Faces:
            raise GSFeatureError("offset produced no surface")
        return result


def make_offset_surface(doc, name="Offset"):
    return make_feature(doc, OffsetSurface, name)


register(OffsetSurface, make_offset_surface)
