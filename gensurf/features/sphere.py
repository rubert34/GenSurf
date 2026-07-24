"""Sphere — GSD 'Sphere Surface' feature.

Center point + optional axis (straight edge; planar face normal also
accepted) + radius. Sphere Limitations, exactly as the dialog: either
the whole sphere, or a patch bounded by Parallel start/end angles
(latitude, -90..90 measured from the equator) and Meridian start/end
angles (longitude around the axis).
"""

import math

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   axis_from_link, direction_from_ref, make_feature)
from .registry import register
from .point import _vertex_point


class Sphere(GSFeature):
    TYPE_ID = "GenSurf::Sphere"
    REQUIRED_LINKS = ("Center",)
    INPUT_SLOTS = (
        ("Center", "Center point", ("Vertex",), False),
        ("Axis", "Sphere axis (blank: absolute Z)", ("Edge", "Face"),
         True),
    )
    ENUMS = {
        "Limitation": ("Angles", "Whole sphere"),
    }
    PROPERTIES = (
        ("App::PropertyLinkSub", "Center", "Sphere",
         "Center point", None),
        ("App::PropertyLinkSub", "Axis", "Sphere",
         "Axis: straight edge, or planar face normal", None),
        ("App::PropertyDistance", "Radius", "Sphere",
         "Sphere radius", "20 mm"),
        ("App::PropertyEnumeration", "Limitation", "Sphere",
         "Angle-bounded patch or the whole sphere", None),
        ("App::PropertyAngle", "ParallelStart", "Sphere",
         "Parallel (latitude) start angle", "-45 deg"),
        ("App::PropertyAngle", "ParallelEnd", "Sphere",
         "Parallel (latitude) end angle", "45 deg"),
        ("App::PropertyAngle", "MeridianStart", "Sphere",
         "Meridian (longitude) start angle", "0 deg"),
        ("App::PropertyAngle", "MeridianEnd", "Sphere",
         "Meridian (longitude) end angle", "180 deg"),
    )

    def build(self, obj):
        center = _vertex_point(obj.Center, "Center")
        radius = obj.Radius.getValueAs("mm").Value
        if radius < 1e-9:
            raise GSFeatureError("radius is zero")

        d = App.Vector(0, 0, 1)
        if obj.Axis:
            try:
                _base, d = axis_from_link(obj.Axis)
                d = App.Vector(d)
            except GSFeatureError:
                d = App.Vector(direction_from_ref(
                    resolve_linksub(obj.Axis)))
        if d.Length < 1e-12:
            raise GSFeatureError("axis direction is null")
        d.normalize()

        # exact analytic sphere in place — no transform, no approximation
        surf = Part.Sphere()
        surf.Radius = radius
        surf.Center = center
        surf.Axis = d

        if obj.Limitation == "Whole sphere":
            return surf.toShape()

        p0 = obj.ParallelStart.getValueAs("deg").Value
        p1 = obj.ParallelEnd.getValueAs("deg").Value
        if not -90 - 1e-9 <= p0 < p1 <= 90 + 1e-9:
            raise GSFeatureError(
                "parallel angles must satisfy -90 <= start < end <= 90")
        m0 = obj.MeridianStart.getValueAs("deg").Value
        m1 = obj.MeridianEnd.getValueAs("deg").Value
        span = (m1 - m0) % 360.0
        if span < 1e-9:
            span = 360.0

        patch = surf.toShape(
            math.radians(m0), math.radians(m0 + span),
            math.radians(p0), math.radians(p1))
        if patch.isNull() or not patch.Faces:
            raise GSFeatureError("sphere limitation produced no patch")
        return patch


def make_sphere(doc, name="Sphere"):
    return make_feature(doc, Sphere, name)


register(Sphere, make_sphere)
