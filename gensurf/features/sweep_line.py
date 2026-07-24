"""Sweep Line — GSD 'Swept Surface', Line profile type: a ruled surface
whose rule line is constructed at every station along the guide(s).

Subtypes (per the dialog schematics):
  * Two limits          — rule between guide 1 and guide 2; Length 1/2
    extend the line beyond each guide (outward);
  * Limit and middle    — guide 2 is the middle: the rule runs from
    guide 1 through the middle to the symmetric point;
  * With reference surface — the rule leaves guide 1 at Angle from the
    reference surface's tangent plane, over Length 1 (Length 2 extends
    backwards);
  * With draft direction — the rule makes Angle with the draft
    direction (Square computation mode).

Not implemented: 'With reference curve', 'With tangency surface',
'With two tangency surfaces' (tangency solving), the Cone draft mode,
length Laws, relimiters and smooth-sweeping options.
"""

import math

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   direction_from_ref, make_feature)
from .registry import register
from .sweep_common import (guide_wire, stations, tangents, support_face,
                           face_normal_at, ruled_between)


class SweepLine(GSFeature):
    TYPE_ID = "GenSurf::SweepLine"
    REQUIRED_LINKS = ("Guide1",)
    INPUT_SLOTS = (
        ("Guide1", "Guide curve 1", ("Edge", "Wire"), False),
        ("Guide2", "Guide curve 2 / middle curve", ("Edge", "Wire"),
         True),
        ("ReferenceSurface", "Reference surface", ("Face",), True),
        ("Direction", "Draft direction (edge / planar face)",
         ("Edge", "Face"), True),
    )
    ENUMS = {
        "Subtype": ("Two limits", "Limit and middle",
                    "With reference surface", "With draft direction"),
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "Subtype", "Sweep",
         "How the rule line is constructed", None),
        ("App::PropertyLinkSub", "Guide1", "Sweep",
         "First guide curve", None),
        ("App::PropertyLinkSub", "Guide2", "Sweep",
         "Second guide / middle curve", None),
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
         "Rule length (forward / beyond guide 1)", "20 mm"),
        ("App::PropertyDistance", "Length2", "Sweep",
         "Rule length (backward / beyond guide 2)", "0 mm"),
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
        subtype = obj.Subtype
        g1 = guide_wire(obj.Guide1, "guide curve 1")
        p_pts = stations(g1)
        l1 = obj.Length1.getValueAs("mm").Value
        l2 = obj.Length2.getValueAs("mm").Value

        if subtype in ("Two limits", "Limit and middle"):
            if not obj.Guide2:
                raise GSFeatureError(
                    f"'{subtype}' needs a second guide curve")
            q_pts = stations(guide_wire(obj.Guide2, "guide curve 2"))
            a_pts, b_pts = [], []
            for p, q in zip(p_pts, q_pts):
                u = q - p
                if u.Length < 1e-9:
                    raise GSFeatureError(
                        "the guides touch — the rule line vanishes")
                if subtype == "Limit and middle":
                    a_pts.append(p)
                    b_pts.append(q + u)  # mirror of p through the middle
                else:
                    un = App.Vector(u)
                    un.normalize()
                    a_pts.append(p - un * l1)
                    b_pts.append(q + un * l2)
            return ruled_between(a_pts, b_pts)

        # angle-driven subtypes need a length
        if l1 < 1e-9 and l2 < 1e-9:
            raise GSFeatureError("set Length 1 (and/or Length 2)")
        ang = math.radians(obj.Angle.getValueAs("deg").Value)
        tg = tangents(p_pts)

        a_pts, b_pts = [], []
        if subtype == "With reference surface":
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
                        "guide tangent is parallel to the surface normal")
                w.normalize()
                d = w * math.cos(ang) + n * math.sin(ang)
                a_pts.append(p - d * l2)
                b_pts.append(p + d * l1)
            return ruled_between(a_pts, b_pts)

        # With draft direction (Square mode)
        dd = self._direction(obj)
        for p, t in zip(p_pts, tg):
            d_p = dd - t * dd.dot(t)
            if d_p.Length < 1e-9:
                raise GSFeatureError(
                    "guide tangent is parallel to the draft direction")
            d_p.normalize()
            e = t.cross(d_p)
            d = d_p * math.cos(ang) + e * math.sin(ang)
            a_pts.append(p - d * l2)
            b_pts.append(p + d * l1)
        return ruled_between(a_pts, b_pts)


def make_sweep_line(doc, name="SweepLine"):
    return make_feature(doc, SweepLine, name)


register(SweepLine, make_sweep_line)
