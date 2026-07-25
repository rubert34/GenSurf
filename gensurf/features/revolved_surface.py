"""Revolved surface — GSD 'Revolve' feature (surface mode, open result).

OCC entry point: BRepPrimAPI_MakeRevol via ``shape.revolve(base, axis,
angle)`` on an edge/wire profile.

The axis is picked CATIA-style from a reference: any straight edge, or an
origin/datum axis object (App::Line). AngleFwd/AngleRev sweep either way
around the axis, like Extrude's two limits.
"""

import FreeCAD as App

from .base import (GSFeature, GSFeatureError, resolve_linksub, make_feature,
                   curve_wires, axis_from_link)
from .registry import register


class RevolvedSurface(GSFeature):
    TYPE_ID = "GenSurf::RevolvedSurface"
    REQUIRED_LINKS = ("Profile", "AxisRef")
    INPUT_SLOTS = (
        ("Profile", "Profile curve or sketch", ("Edge", "Wire"), False),
        ("AxisRef", "Revolution axis: straight edge or axis", ("Edge",),
         False),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Profile", "Revolve",
         "Edge or wire profile to revolve", None),
        ("App::PropertyLinkSub", "AxisRef", "Revolve",
         "Straight edge or datum axis to revolve around", None),
        ("App::PropertyAngle", "AngleFwd", "Revolve",
         "Sweep angle (Limit 1)", "360 deg"),
        ("App::PropertyAngle", "AngleRev", "Revolve",
         "Sweep angle the other way (Limit 2)", "0 deg"),
    )


    def build(self, obj):
        profile = resolve_linksub(obj.Profile)
        wires = curve_wires(profile)
        base, direction = axis_from_link(obj.AxisRef)
        if direction.Length < 1e-12:
            raise GSFeatureError("axis direction is null")
        direction.normalize()

        fwd = obj.AngleFwd.getValueAs("deg").Value
        rev = obj.AngleRev.getValueAs("deg").Value
        total = min(fwd + rev, 360.0)
        if total < 1e-9:
            raise GSFeatureError("revolution angle is zero")

        import Part
        results = []
        for wire in wires:
            start = wire
            if abs(rev) > 1e-12:  # any non-zero Limit 2, either sign
                start = wire.copy()
                start.rotate(base, direction, -rev)
            results.append(start.revolve(base, direction, total))
        return results[0] if len(results) == 1 else Part.makeCompound(results)


def make_revolved_surface(doc, name="Revolve"):
    return make_feature(doc, RevolvedSurface, name)


register(RevolvedSurface, make_revolved_surface)
