"""Projected curve — GSD 'Projection' feature (curve onto support surface).

OCC entry point: TopoShape::project (BRepProj) via ``face.project([curve])``
for normal projection; ``Part.Shape.makeParallelProjection`` when an
explicit direction is given.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub, make_feature,
                   curve_wires)
from .registry import register


class ProjectedCurve(GSFeature):
    TYPE_ID = "GenSurf::ProjectedCurve"
    REQUIRED_LINKS = ("Base", "Support")
    INPUT_SLOTS = (
        ("Base", "Curve / sketch to project", ("Edge", "Wire"), False),
        ("Support", "Support face", ("Face",), False),
    )
    ENUMS = {
        "Mode": ("Normal", "Direction"),
    }
    PROPERTIES = (
        ("App::PropertyLinkSub", "Base", "Projection",
         "Edge or wire to project", None),
        ("App::PropertyLinkSub", "Support", "Projection",
         "Face to project onto", None),
        ("App::PropertyEnumeration", "Mode", "Projection",
         "Normal: along support normals; Direction: along a fixed vector",
         None),
        ("App::PropertyVector", "Direction", "Projection",
         "Projection direction (Mode = Direction)", App.Vector(0, 0, 1)),
    )

    def build(self, obj):
        wires = curve_wires(resolve_linksub(obj.Base))
        support = resolve_linksub(obj.Support, expect="Face")

        results = []
        for wire in wires:
            if obj.Mode == "Direction":
                d = obj.Direction
                if d.Length < 1e-12:
                    raise GSFeatureError("Direction vector is null")
                projected = support.makeParallelProjection(wire, d)
            else:
                projected = support.project([wire])
            if not projected.isNull() and projected.Edges:
                results.append(projected)

        if not results:
            raise GSFeatureError("projection produced no result on support")
        return results[0] if len(results) == 1 else Part.makeCompound(results)


def make_projected_curve(doc, name="Project"):
    return make_feature(doc, ProjectedCurve, name)


register(ProjectedCurve, make_projected_curve)
