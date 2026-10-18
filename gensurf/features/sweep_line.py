"""Sweep Ruled — a ruled surface whose straight section is built at every
station along the rail(s).

Modes:
  * Between rails — the line spans rail 1 to rail 2; Length 1/2 extend
    it beyond each rail (outward);
  * Rail 2 as middle — the line runs from rail 1 through rail 2 to the
    point symmetric about it;
  * Angle to surface — the line leaves rail 1 at Angle from the
    reference surface's tangent plane, over Length 1 (Length 2 extends
    backwards);
  * Draft from direction — the line makes Angle with the draft
    direction, measured in the plane normal to the rail.

Not implemented: lines tangent to one or two surfaces, lines ruled from
a reference curve, a conical draft, length laws, end limits and
smoothing.
"""


import math

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   direction_from_ref, make_feature)
from .registry import register
from .sweep_common import (rail_wire, stations, tangents, support_face,
                           face_normal_at, ruled_between)


class SweepLine(GSFeature):
    TYPE_ID = "GenSurf::SweepLine"
    REQUIRED_LINKS = ("Rail1",)
    INPUT_SLOTS = (
        ("Rail1", "Rail curve 1", ("Edge", "Wire"), False),
        ("Rail2", "Rail curve 2 / middle curve", ("Edge", "Wire"),
         True),
        ("ReferenceSurface", "Reference surface", ("Face",), True),
        ("Direction", "Draft direction (edge / planar face)",
         ("Edge", "Face"), True),
    )
    ENUMS = {
        "Mode": ("Between rails", "Rail 2 as middle",
                 "Angle to surface", "Draft from direction"),
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "Mode", "Sweep",
         "How the rule line is constructed", None),
        ("App::PropertyLinkSub", "Rail1", "Sweep",
         "First rail curve", None),
        ("App::PropertyLinkSub", "Rail2", "Sweep",
         "Second rail / middle curve", None),
        ("App::PropertyLinkSub", "ReferenceSurface", "Sweep",
         "Surface the angle is measured from", None),
        ("App::PropertyLinkSub", "Direction", "Sweep",
         "Draft direction reference", None),
        ("App::PropertyVector", "DirectionVector", "Sweep",
         "Explicit draft direction (no reference picked)",
         App.Vector(0, 0, 1)),
        ("App::PropertyAngle", "Angle", "Sweep",
         "Angle from the reference surface / draft direction", "0 deg"),
        ("App::PropertyDistance", "Length1", "Sweep",
         "Rule length (forward / beyond rail 1)", "20 mm"),
        ("App::PropertyDistance", "Length2", "Sweep",
         "Rule length (backward / beyond rail 2)", "0 mm"),
    )

    def _direction(self, obj):
        if obj.Direction:
            d = App.Vector(direction_from_ref(
                resolve_linksub(obj.Direction)))
        else:
            d = App.Vector(obj.DirectionVector)
        if d.Length < 1e-12:
            raise GSFeatureError("draft direction is null")
        d.normalize()
        return d

    def build(self, obj):
        mode = obj.Mode
        g1 = rail_wire(obj.Rail1, "rail curve 1")
        p_pts = stations(g1)
        l1 = obj.Length1.getValueAs("mm").Value
        l2 = obj.Length2.getValueAs("mm").Value

        if mode in ("Between rails", "Rail 2 as middle"):
            if not obj.Rail2:
                raise GSFeatureError(
                    f"'{mode}' needs a second rail curve")
            q_pts = stations(rail_wire(obj.Rail2, "rail curve 2"))
            a_pts, b_pts = [], []
            for p, q in zip(p_pts, q_pts):
                u = q - p
                if u.Length < 1e-9:
                    raise GSFeatureError(
                        "the rails touch — the rule line vanishes")
                if mode == "Rail 2 as middle":
                    a_pts.append(p)
                    b_pts.append(q + u)  # mirror of p through the middle
                else:
                    un = App.Vector(u)
                    un.normalize()
                    a_pts.append(p - un * l1)
                    b_pts.append(q + un * l2)
            return ruled_between(a_pts, b_pts)

        # angle-driven modes need a length
        if l1 < 1e-9 and l2 < 1e-9:
            raise GSFeatureError("set Length 1 (and/or Length 2)")
        ang = math.radians(obj.Angle.getValueAs("deg").Value)
        tg = tangents(p_pts)

        a_pts, b_pts = [], []
        if mode == "Angle to surface":
            if not obj.ReferenceSurface:
                raise GSFeatureError(
                    "pick the reference surface the angle is measured "
                 "from")
            face = support_face(obj.ReferenceSurface, "reference surface")
            for p, t in zip(p_pts, tg):
                n = face_normal_at(face, p)
                w = t.cross(n)
                if w.Length < 1e-9:
                    raise GSFeatureError(
                        "rail tangent is parallel to the surface normal")
                w.normalize()
                d = w * math.cos(ang) + n * math.sin(ang)
                a_pts.append(p - d * l2)
                b_pts.append(p + d * l1)
            return ruled_between(a_pts, b_pts)

        # Draft from direction (Square mode)
        dd = self._direction(obj)
        for p, t in zip(p_pts, tg):
            d_p = dd - t * dd.dot(t)
            if d_p.Length < 1e-9:
                raise GSFeatureError(
                    "rail tangent is parallel to the draft direction")
            d_p.normalize()
            e = t.cross(d_p)
            d = d_p * math.cos(ang) + e * math.sin(ang)
            a_pts.append(p - d * l2)
            b_pts.append(p + d * l1)
        return ruled_between(a_pts, b_pts)


def make_sweep_line(doc, name="SweepLine"):
    return make_feature(doc, SweepLine, name)


register(SweepLine, make_sweep_line)
