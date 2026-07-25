"""Healing — GSD 'Healing' feature: repair and sanitize surfaces.

Pipeline (each step optional where noted):
  1. ShapeFix on every input (invalid geometry, missing/broken pcurves,
     same-parameter repair) with the working precision set from
     MergingDistance;
  2. sew exactly-touching boundaries into shells;
  3. remove edges smaller than SmallEdgeThreshold (optional);
  4. merge co-surface faces (UnifySameDomain, optional 'Simplify');
  5. encode G1/G2 regularity flags on the result's edges.

Not implemented: closing real gaps larger than sewing tolerance
(~1e-6 mm) between faces — that needs geometry deformation; use Join /
Fill / Blend to bridge visible gaps. (The OCC FaceConnect gap-stitcher
is exposed but crashes; not used.)
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksublist,
                   make_feature)
from .registry import register


class Healing(GSFeature):
    TYPE_ID = "GenSurf::Healing"
    HIDE_INPUTS = ("Elements",)
    REQUIRED_LINKS = ("Elements",)
    INPUT_SLOTS = (
        ("Elements", "Surfaces to heal", ("Face", "Shell"), False, True),
    )
    PROPERTIES = (
        ("App::PropertyLinkSubList", "Elements", "Healing",
         "Surfaces to repair", None),
        ("App::PropertyDistance", "MergingDistance", "Healing",
         "Working precision for the repairs", "0.001 mm"),
        ("App::PropertyBool", "FixSmallEdges", "Healing",
         "Remove edges shorter than the threshold", False),
        ("App::PropertyDistance", "SmallEdgeThreshold", "Healing",
         "Edges shorter than this are dissolved", "0.1 mm"),
        ("App::PropertyBool", "Simplify", "Healing",
         "Merge adjacent faces lying on the same surface", False),
    )

    def build(self, obj):
        faces = []
        for shape in resolve_linksublist(obj.Elements):
            if shape.Faces:
                faces.extend(f.copy() for f in shape.Faces)
        if not faces:
            raise GSFeatureError("the selection contains no surface")

        prec = max(obj.MergingDistance.getValueAs("mm").Value, 1e-7)

        # 1. per-face geometry repair
        healed = []
        for f in faces:
            try:
                fx = Part.ShapeFix.Shape(f)
                fx.Precision = prec
                fx.MaxTolerance = max(prec, 1e-4)
                fx.perform()
                out = fx.shape()
                healed.extend(out.Faces if out.Faces else [f])
            except Part.OCCError:
                healed.append(f)

        # 2. sew exact-touching boundaries
        comp = Part.makeCompound(healed)
        comp.sewShape()
        result = comp.Shells[0] if len(comp.Shells) == 1 and \
            len(comp.Shells[0].Faces) == len(comp.Faces) else comp

        # 3. small-edge removal
        if obj.FixSmallEdges:
            thr = obj.SmallEdgeThreshold.getValueAs("mm").Value
            try:
                cleaned = Part.ShapeFix.removeSmallEdges(result, thr)
                if cleaned is not None and not cleaned.isNull() \
                        and cleaned.Faces:
                    result = cleaned
            except Part.OCCError:
                App.Console.PrintWarning(
                    "[GenSurf] Healing: small-edge removal failed — "
                    "kept the unmodified result\n")

        # 4. same-surface face merging
        if obj.Simplify:
            try:
                uni = Part.ShapeUpgrade.UnifySameDomain(result)
                uni.build()
                merged = uni.shape()
                if not merged.isNull() and merged.Faces:
                    result = merged
            except Part.OCCError:
                App.Console.PrintWarning(
                    "[GenSurf] Healing: simplification failed — kept "
                    "the unmodified result\n")

        # 5. continuity flags for downstream tangency-aware tools
        try:
            Part.ShapeFix.encodeRegularity(result)
        except Part.OCCError:
            pass

        if result.isNull() or not result.Faces:
            raise GSFeatureError("healing produced no surface")
        return result


def make_healing(doc, name="Healing"):
    return make_feature(doc, Healing, name)


register(Healing, make_healing)
