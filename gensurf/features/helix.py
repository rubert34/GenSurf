"""Helix — GSD 'Helix Curve' feature.

Axis + starting point define the cylinder: the radius is the point's
distance to the axis and the helix starts exactly at the point (plus
Starting Angle). Helix types combine Pitch / Revolutions / Height;
Orientation sets the winding sense, Taper Angle with Way Inward/Outward
makes it conical. Reverse Direction winds down the axis instead of up.

OCC entry point: Part.makeHelix (exact helix on a cylinder/cone),
relocated onto the axis frame by a rigid transformGeometry.
('Law' pitch variation and the 'Profile' radius law are not
implemented.)
"""

import math

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, axis_from_link,
                   make_feature)
from .registry import register
from .point import _vertex_point

_TYPES = ("Pitch and Revolution", "Height and Pitch",
          "Height and Revolution")


class Helix(GSFeature):
    TYPE_ID = "GenSurf::Helix"
    REQUIRED_LINKS = ("StartPoint", "Axis")
    INPUT_SLOTS = (
        ("StartPoint", "Starting point", ("Vertex",), False),
        ("Axis", "Axis (straight edge)", ("Edge",), False),
    )
    ENUMS = {
        "HelixType": _TYPES,
        "Orientation": ("Counterclockwise", "Clockwise"),
        "Way": ("Inward", "Outward"),
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "HelixType", "Helix",
         "Which two of pitch / revolutions / height define the helix",
         None),
        ("App::PropertyLinkSub", "StartPoint", "Helix",
         "Starting point (sets the radius)", None),
        ("App::PropertyLinkSub", "Axis", "Helix",
         "Helix axis", None),
        ("App::PropertyDistance", "Pitch", "Helix",
         "Height gained per revolution", "5 mm"),
        ("App::PropertyFloat", "Revolutions", "Helix",
         "Number of revolutions", 5.0),
        ("App::PropertyDistance", "Height", "Helix",
         "Total helix height", "25 mm"),
        ("App::PropertyEnumeration", "Orientation", "Helix",
         "Winding sense seen along the axis", None),
        ("App::PropertyAngle", "StartingAngle", "Helix",
         "Angular offset of the start around the axis", "0 deg"),
        ("App::PropertyAngle", "TaperAngle", "Helix",
         "Cone half-angle of the radius variation", "0 deg"),
        ("App::PropertyEnumeration", "Way", "Helix",
         "Taper the radius inward or outward while climbing", None),
        ("App::PropertyBool", "ReverseDirection", "Helix",
         "Wind down the axis instead of up", False),
    )

    def build(self, obj):
        base, d = axis_from_link(obj.Axis)
        p = _vertex_point(obj.StartPoint, "Starting point")
        w = p - base
        foot = base + d * w.dot(d)
        radial = p - foot
        radius = radial.Length
        if radius < 1e-9:
            raise GSFeatureError("the starting point lies on the axis")

        kind = obj.HelixType
        pitch = obj.Pitch.getValueAs("mm").Value
        height = obj.Height.getValueAs("mm").Value
        revs = obj.Revolutions
        if kind == "Pitch and Revolution":
            if pitch < 1e-9 or revs < 1e-9:
                raise GSFeatureError("pitch and revolutions must be > 0")
            height = pitch * revs
        elif kind == "Height and Pitch":
            if pitch < 1e-9 or height < 1e-9:
                raise GSFeatureError("height and pitch must be > 0")
        else:  # Height and Revolution
            if height < 1e-9 or revs < 1e-9:
                raise GSFeatureError("height and revolutions must be > 0")
            pitch = height / revs

        taper = obj.TaperAngle.getValueAs("deg").Value
        if obj.Way == "Inward":
            taper = -taper
        if taper <= -90 + 1e-9 or taper >= 90 - 1e-9:
            raise GSFeatureError("taper angle must be within ±90°")
        # an inward taper must not shrink the radius through zero
        end_radius = radius + height * math.tan(math.radians(taper))
        if end_radius < 1e-6:
            raise GSFeatureError(
                f"taper angle {abs(taper)}° shrinks the radius to zero "
                f"before the helix ends (height {height} mm)")

        lefthand = obj.Orientation == "Clockwise"
        # makeHelix measures height and pitch along the cone slant when
        # tapered — rescale so ours stay axial
        slant = 1.0 / math.cos(math.radians(taper))
        try:
            if taper >= 0:
                helix = Part.makeHelix(pitch * slant, height * slant,
                                       radius, taper, lefthand)
            else:
                # makeHelix ignores negative angles: build the cone
                # outward from the small end and flip it upside down
                # (the flip is a rotation, so winding is preserved)
                helix = Part.makeHelix(pitch * slant, height * slant,
                                       end_radius, -taper, lefthand)
                flip = App.Matrix(1, 0, 0, 0,
                                  0, -1, 0, 0,
                                  0, 0, -1, height,
                                  0, 0, 0, 1)
                helix = helix.transformGeometry(flip)
                # re-zero the start azimuth (offset for non-integer revs)
                s = min((v.Point for v in helix.Vertexes),
                        key=lambda q: q.z)
                phi = math.atan2(s.y, s.x)
                if abs(phi) > 1e-12:
                    c, sn = math.cos(-phi), math.sin(-phi)
                    unspin = App.Matrix(c, -sn, 0, 0,
                                        sn, c, 0, 0,
                                        0, 0, 1, 0,
                                        0, 0, 0, 1)
                    helix = helix.transformGeometry(unspin)
        except Part.OCCError as err:
            raise GSFeatureError(f"helix construction failed ({err})")

        # map the canonical helix (axis +Z, start at (radius, 0, 0))
        # onto the picked axis, starting at the picked point
        axis_dir = App.Vector(d)
        if obj.ReverseDirection:
            axis_dir = axis_dir.negative()
        u = App.Vector(radial)
        u.normalize()
        # re-orthogonalize in case the axis pick is slightly skew
        u = u - axis_dir * u.dot(axis_dir)
        u.normalize()
        v = axis_dir.cross(u)
        start = math.radians(obj.StartingAngle.getValueAs("deg").Value)
        if abs(start) > 1e-12:
            u, v = (u * math.cos(start) + v * math.sin(start),
                    v * math.cos(start) - u * math.sin(start))
        m = App.Matrix(
            u.x, v.x, axis_dir.x, foot.x,
            u.y, v.y, axis_dir.y, foot.y,
            u.z, v.z, axis_dir.z, foot.z,
            0, 0, 0, 1)
        return helix.transformGeometry(m)


def make_helix(doc, name="Helix"):
    return make_feature(doc, Helix, name)


register(Helix, make_helix)
