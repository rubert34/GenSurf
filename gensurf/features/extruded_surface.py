"""Extruded surface — GSD 'Extrude' feature (surface mode, open result).

OCC entry point: BRepPrimAPI_MakePrism via ``shape.extrude(vector)`` on an
edge/wire profile, yielding a face/shell (never a solid: profiles are open
curves or unfilled wires by design).

Direction modes (CATIA-style):
  * Auto      — normal of the profile's plane; falls back to Direction if
                the profile is not planar (e.g. a straight line).
  * Reference — direction taken from DirectionRef: any straight edge gives
                its direction, any planar face gives its normal.
  * Vector    — the explicit Direction vector.
"""

import FreeCAD as App

from .base import (GSFeature, GSFeatureError, resolve_linksub, make_feature,
                   curve_wires, direction_from_ref, profile_plane_normal)
from .registry import register


class ExtrudedSurface(GSFeature):
    TYPE_ID = "GenSurf::ExtrudedSurface"
    REQUIRED_LINKS = ("Profile",)
    INPUT_SLOTS = (
        ("Profile", "Profile curve or sketch", ("Edge", "Wire"), False),
        ("DirectionRef", "Direction reference (optional)",
         ("Edge", "Face"), True),
    )
    ENUMS = {
        "DirectionMode": ("Auto", "Reference", "Vector"),
    }
    PROPERTIES = (
        ("App::PropertyLinkSub", "Profile", "Extrude",
         "Edge or wire profile to sweep linearly", None),
        ("App::PropertyEnumeration", "DirectionMode", "Extrude",
         "Auto: profile plane normal; Reference: from DirectionRef; "
         "Vector: explicit Direction", None),
        ("App::PropertyLinkSub", "DirectionRef", "Extrude",
         "Straight edge or planar face defining the direction", None),
        ("App::PropertyVector", "Direction", "Extrude",
         "Extrusion direction (Vector mode)", App.Vector(0, 0, 1)),
        ("App::PropertyDistance", "LengthFwd", "Extrude",
         "Length along Direction (Limit 1)", "10 mm"),
        ("App::PropertyDistance", "LengthRev", "Extrude",
         "Length against Direction (Limit 2)", "0 mm"),
    )

    def onChanged(self, obj, prop):
        # Picking a direction reference implies you want to use it.
        if prop == "DirectionRef" and getattr(obj, "DirectionRef", None) \
                and hasattr(obj, "DirectionMode"):
            obj.DirectionMode = "Reference"

    def _direction(self, obj, wires):
        mode = getattr(obj, "DirectionMode", "Vector")
        if mode == "Reference":
            if not obj.DirectionRef:
                raise GSFeatureError(
                    "DirectionMode is Reference but no DirectionRef is set")
            return App.Vector(direction_from_ref(
                resolve_linksub(obj.DirectionRef)))
        if mode == "Auto":
            normal = profile_plane_normal(wires)
            if normal is not None:
                return App.Vector(normal)
            # non-planar or straight-line profile: fall back to the vector
        return App.Vector(obj.Direction)

    def build(self, obj):
        profile = resolve_linksub(obj.Profile)
        wires = curve_wires(profile)  # accepts edge, wire, sketch, compound

        d = self._direction(obj, wires)
        if d.Length < 1e-12:
            raise GSFeatureError("Direction vector is null")
        d.normalize()

        fwd = obj.LengthFwd.getValueAs("mm").Value
        rev = obj.LengthRev.getValueAs("mm").Value
        total = fwd + rev
        if total < 1e-9:
            raise GSFeatureError("extrusion length is zero")

        import Part
        results = []
        for wire in wires:
            base = wire.translated(d * (-rev)) if rev > 0 else wire
            results.append(base.extrude(d * total))
        return results[0] if len(results) == 1 else Part.makeCompound(results)


def make_extruded_surface(doc, name="Extrude"):
    return make_feature(doc, ExtrudedSurface, name)


register(ExtrudedSurface, make_extruded_surface)
