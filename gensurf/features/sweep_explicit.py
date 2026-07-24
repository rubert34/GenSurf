"""Sweep Explicit — GSD 'Swept Surface', Explicit profile type: an
actual profile curve swept along a guide.

Subtypes, as in the dialog:
  * With reference surface — the profile keeps its orientation relative
    to the guide (mean-plane behavior); with a surface picked, the
    sweeping frame follows that surface's normal (the guide must lie on
    it); Angle pre-rotates the profile about the guide tangent;
  * With two guide curves — the profile follows guide 1 while guide 2
    drives its stretch/orientation (anchor points as in the schematic);
  * With pulling direction — the profile keeps a fixed orientation
    relative to the picked direction; Angle pre-rotates likewise.

OCC entry point: BRepOffsetAPI_MakePipeShell (default corrected-frenet
frame, spine-support mode, binormal mode, auxiliary spine).
Not implemented: the angle Law, relimiters, smooth-sweeping tolerances,
twisted-area management, profile positioning parameters.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   direction_from_ref, make_feature)
from .registry import register
from .sweep_common import guide_wire, stations, tangents, support_face


class SweepExplicit(GSFeature):
    TYPE_ID = "GenSurf::SweepExplicit"
    REQUIRED_LINKS = ("Profile", "Guide1")
    INPUT_SLOTS = (
        ("Profile", "Profile to sweep", ("Edge", "Wire"), False),
        ("Guide1", "Guide curve", ("Edge", "Wire"), False),
        ("Guide2", "Guide curve 2 (two-guides subtype)",
         ("Edge", "Wire"), True),
        ("ReferenceSurface", "Reference surface (guide must lie on it)",
         ("Face",), True),
        ("Direction", "Pulling direction (edge / planar face)",
         ("Edge", "Face"), True),
        ("Spine", "Spine (blank: guide 1)", ("Edge", "Wire"), True),
    )
    ENUMS = {
        "Subtype": ("With reference surface", "With two guide curves",
                    "With pulling direction"),
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "Subtype", "Sweep",
         "How the profile is carried along the guide", None),
        ("App::PropertyLinkSub", "Profile", "Sweep",
         "Profile curve", None),
        ("App::PropertyLinkSub", "Guide1", "Sweep",
         "Guide curve", None),
        ("App::PropertyLinkSub", "Guide2", "Sweep",
         "Second guide (two-guides subtype)", None),
        ("App::PropertyLinkSub", "ReferenceSurface", "Sweep",
         "Reference surface the sweeping frame follows", None),
        ("App::PropertyLinkSub", "Direction", "Sweep",
         "Pulling direction reference", None),
        ("App::PropertyVector", "DirectionVector", "Sweep",
         "Explicit pulling direction (no reference picked)",
         App.Vector(0, 0, 1)),
        ("App::PropertyLinkSub", "Spine", "Sweep",
         "Optional spine (defaults to guide 1)", None),
        ("App::PropertyAngle", "Angle", "Sweep",
         "Rotation of the profile about the guide tangent", "0 deg"),
    )

    @staticmethod
    def _two_guides_morph(profile, g1, g2):
        from .sweep_common import loft_sections, STATIONS
        p_pts = stations(g1)
        q_pts = stations(g2)
        prof_pts = [App.Vector(v) for v in profile.discretize(STATIONS)]
        e1, e2 = prof_pts[0], prof_pts[-1]
        # anchor the profile end nearest to guide 1
        if (e1 - p_pts[0]).Length > (e2 - p_pts[0]).Length:
            prof_pts.reverse()
            e1, e2 = e2, e1
        base = e2 - e1
        if base.Length < 1e-9:
            raise GSFeatureError("the profile is closed — the "
                                 "two-guides subtype needs an open one")
        sections = []
        for p, q in zip(p_pts, q_pts):
            target = q - p
            if target.Length < 1e-9:
                raise GSFeatureError("the guides touch")
            scale = target.Length / base.Length
            rot = App.Rotation(base, target)
            pts = [p + rot.multVec(v - e1) * scale for v in prof_pts]
            bs = Part.BSplineCurve()
            try:
                bs.interpolate(pts)
            except Part.OCCError as err:
                raise GSFeatureError(f"section morph failed ({err})")
            sections.append(Part.Wire([bs.toShape()]))
        return loft_sections(sections)

    def build(self, obj):
        profile = guide_wire(obj.Profile, "profile")
        guide = guide_wire(obj.Guide1, "guide curve")
        subtype = obj.Subtype

        spine = guide
        if obj.Spine and subtype != "With two guide curves":
            spine = guide_wire(obj.Spine, "spine")

        angle = obj.Angle.getValueAs("deg").Value
        if abs(angle) > 1e-9:
            pts = stations(guide, 9)
            tg = tangents(pts)[0]
            profile = profile.copy()
            profile.rotate(pts[0], tg, angle)

        ps = Part.BRepOffsetAPI.MakePipeShell(spine)
        with_contact = False
        if subtype == "With pulling direction":
            if obj.Direction:
                d = App.Vector(direction_from_ref(
                    resolve_linksub(obj.Direction)))
            else:
                d = App.Vector(obj.DirectionVector)
            if d.Length < 1e-12:
                raise GSFeatureError("pulling direction is null")
            d.normalize()
            ps.setBiNormalMode(d)
        elif subtype == "With two guide curves":
            # OCC's auxiliary spine only twists the profile, it never
            # stretches it to the second guide — station-morph instead:
            # a similarity transform anchors the profile's ends to the
            # two guides at every station (CATIA's G1/G2 anchoring).
            if not obj.Guide2:
                raise GSFeatureError(
                    "the two-guides subtype needs Guide curve 2")
            return self._two_guides_morph(profile, guide,
                                          guide_wire(obj.Guide2,
                                                     "guide curve 2"))
        else:  # With reference surface
            if obj.ReferenceSurface:
                face = support_face(obj.ReferenceSurface,
                                    "reference surface")
                if guide.distToShape(face)[0] > 1e-4:
                    raise GSFeatureError(
                        "the guide curve must lie on the reference "
                        "surface")
                ps.setSpineSupport(face)

        ps.add(profile, with_contact, False)
        if not ps.isReady():
            raise GSFeatureError("the sweep could not be prepared — "
                                 "check profile and guide positions")
        try:
            ps.build()
            result = ps.shape()
        except Part.OCCError as err:
            raise GSFeatureError(f"sweep failed ({err})")
        if result.isNull() or not result.Faces:
            raise GSFeatureError("sweep produced no surface")
        return result


def make_sweep_explicit(doc, name="SweepExplicit"):
    return make_feature(doc, SweepExplicit, name)


register(SweepExplicit, make_sweep_explicit)
