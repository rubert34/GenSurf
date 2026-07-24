"""Translate — GSD 'Translate' feature: a moved copy of any element.

Direction is picked CATIA-style from a reference (straight edge gives
its direction, planar face gives its normal) or entered as a vector.
Rigid motion — geometry types are preserved (no BSpline conversion).
"""

import FreeCAD as App

from .base import (GSFeature, GSFeatureError, resolve_linksub, make_feature,
                   direction_from_ref)
from .registry import register


class Translate(GSFeature):
    TYPE_ID = "GenSurf::Translate"
    REQUIRED_LINKS = ("Source",)
    INPUT_SLOTS = (
        ("Source", "Element to translate", None, False),
        ("DirectionRef", "Direction: straight edge / planar face (optional)",
         ("Edge", "Face"), True),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Source", "Translate",
         "Element to translate (a copy is created)", None),
        ("App::PropertyLinkSub", "DirectionRef", "Translate",
         "Straight edge or planar face defining the direction", None),
        ("App::PropertyVector", "Direction", "Translate",
         "Translation direction (when no reference is set)",
         App.Vector(0, 0, 1)),
        ("App::PropertyDistance", "Distance", "Translate",
         "Translation distance", "10 mm"),
    )

    def build(self, obj):
        src = resolve_linksub(obj.Source)
        if obj.DirectionRef:
            d = App.Vector(direction_from_ref(
                resolve_linksub(obj.DirectionRef)))
        else:
            d = App.Vector(obj.Direction)
        if d.Length < 1e-12:
            raise GSFeatureError("direction is null")
        d.normalize()
        dist = obj.Distance.getValueAs("mm").Value

        # Rigid moves must go through obj.Placement: Part::FeaturePython
        # re-syncs the stored shape's top-level location to obj.Placement
        # on every recompute, which would silently undo shape.translated().
        out = src.copy()
        move = App.Placement(d * dist, App.Rotation())
        obj.Placement = move.multiply(out.Placement)
        return out


def make_translate(doc, name="Translate"):
    return make_feature(doc, Translate, name)


register(Translate, make_translate)
