"""Rotate — GSD 'Rotate' feature: a rotated copy of any element.

Axis is picked CATIA-style: any straight edge, or a datum axis
(App::Line). Rigid motion — geometry types are preserved.
"""

from .base import (GSFeature, GSFeatureError, resolve_linksub, make_feature,
                   axis_from_link)
from .registry import register


class Rotate(GSFeature):
    TYPE_ID = "GenSurf::Rotate"
    HIDE_INPUTS = ("Source",)
    REQUIRED_LINKS = ("Source", "AxisRef")
    INPUT_SLOTS = (
        ("Source", "Element to rotate", None, False),
        ("AxisRef", "Rotation axis: straight edge or datum axis",
         ("Edge",), False),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Source", "Rotate",
         "Element to rotate (a copy is created)", None),
        ("App::PropertyLinkSub", "AxisRef", "Rotate",
         "Straight edge or datum axis to rotate around", None),
        ("App::PropertyAngle", "Angle", "Rotate",
         "Rotation angle", "45 deg"),
    )

    def build(self, obj):
        import FreeCAD as App
        src = resolve_linksub(obj.Source)
        base, direction = axis_from_link(obj.AxisRef)
        if direction.Length < 1e-12:
            raise GSFeatureError("axis direction is null")

        # Rigid moves must go through obj.Placement (see translate.py).
        out = src.copy()
        rot = App.Placement(
            App.Vector(0, 0, 0),
            App.Rotation(direction, obj.Angle.getValueAs("deg").Value),
            base)
        obj.Placement = rot.multiply(out.Placement)
        return out


def make_rotate(doc, name="Rotate"):
    return make_feature(doc, Rotate, name)


register(Rotate, make_rotate)
