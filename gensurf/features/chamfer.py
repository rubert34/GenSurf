"""Chamfer — GSD 'Chamfer' feature: bevels picked edges of a surface
or shell.

Modes: Length1/Angle (second distance derived as L1·tan(angle)) and
Length1/Length2. Reverse swaps which side gets which length.
Propagation Tangency/Minimal as in Edge Fillet.

Not implemented: Chordal length/Angle, Height/Angle and the Hold curve
modes, Corner Cap, and the More>> page.
"""

import math

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, make_feature
from .registry import register
from .edge_fillet import edges_on_one_object, propagate_tangent


class Chamfer(GSFeature):
    TYPE_ID = "GenSurf::Chamfer"
    REQUIRED_LINKS = ("Edges",)
    INPUT_SLOTS = (
        ("Edges", "Edge(s) to chamfer", ("Edge",), False, True),
    )
    ENUMS = {
        "Mode": ("Length1/Angle", "Length1/Length2"),
        "Propagation": ("Tangency", "Minimal"),
    }
    PROPERTIES = (
        ("App::PropertyLinkSubList", "Edges", "Chamfer",
         "Edges to bevel (on one surface object)", None),
        ("App::PropertyEnumeration", "Mode", "Chamfer",
         "How the chamfer is dimensioned", None),
        ("App::PropertyDistance", "Length1", "Chamfer",
         "First chamfer length", "1 mm"),
        ("App::PropertyDistance", "Length2", "Chamfer",
         "Second chamfer length (Length1/Length2 mode)", "1 mm"),
        ("App::PropertyAngle", "Angle", "Chamfer",
         "Chamfer angle (Length1/Angle mode)", "45 deg"),
        ("App::PropertyBool", "Reverse", "Chamfer",
         "Swap which side gets which length", False),
        ("App::PropertyEnumeration", "Propagation", "Chamfer",
         "Tangency follows smooth edge chains; Minimal only the picks",
         None),
    )

    def build(self, obj):
        shape, picked = edges_on_one_object(obj.Edges, "edges to chamfer")
        d1 = obj.Length1.getValueAs("mm").Value
        if d1 < 1e-9:
            raise GSFeatureError("length 1 is zero")
        if obj.Mode == "Length1/Angle":
            ang = obj.Angle.getValueAs("deg").Value
            if not 0 < ang < 90:
                raise GSFeatureError(
                    "the chamfer angle must be between 0 and 90 degrees")
            d2 = d1 * math.tan(math.radians(ang))
        else:
            d2 = obj.Length2.getValueAs("mm").Value
            if d2 < 1e-9:
                raise GSFeatureError("length 2 is zero")
        if obj.Reverse:
            d1, d2 = d2, d1

        if obj.Propagation == "Tangency":
            picked = propagate_tangent(shape, picked)
        try:
            result = shape.makeChamfer(d1, d2, picked)
        except Part.OCCError as err:
            raise GSFeatureError(
                f"chamfer {d1} x {d2} mm failed — it may be too large "
                f"for this geometry ({err})")
        if result.isNull() or not result.Faces:
            raise GSFeatureError("chamfer produced no surface")
        return result


def make_chamfer(doc, name="Chamfer"):
    return make_feature(doc, Chamfer, name)


register(Chamfer, make_chamfer)
