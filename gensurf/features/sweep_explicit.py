"""Sweep Curve — a profile curve swept along a rail (the curve-profile
sweep; the unified Sweep operator replaces the four sweeps later).

Modes:
  * 1 rail — the profile keeps its orientation relative to the rail
    (mean-plane frame); with a reference surface picked, the frame
    follows that surface's normal (the rail must lie on it); Angle
    pre-rotates the profile about the rail tangent;
  * 2 rails — the profile follows rail 1 while rail 2 drives its
    stretch and orientation: at every station a similarity transform
    pins the profile's two ends onto the rails;
  * Rail + direction — the profile keeps a fixed orientation relative
    to the picked direction; Angle pre-rotates likewise.

OCC entry point: BRepOffsetAPI_MakePipeShell (corrected-Frenet frame,
spine support, binormal mode).
Not implemented: an angle law, limiting the sweep by end elements,
smoothing, twist repair and profile positioning.
"""


import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   direction_from_ref, make_feature)
from .registry import register
from .sweep_common import rail_wire, stations, tangents, support_face


class SweepExplicit(GSFeature):
    TYPE_ID = "GenSurf::SweepExplicit"
    REQUIRED_LINKS = ("Profile", "Rail1")
    INPUT_SLOTS = (
        ("Profile", "Profile to sweep", ("Edge", "Wire"), False),
        ("Rail1", "Rail curve", ("Edge", "Wire"), False),
        ("Rail2", "Rail curve 2 (2 rails mode)",
         ("Edge", "Wire"), True),
        ("ReferenceSurface", "Reference surface (rail must lie on it)",
         ("Face",), True),
        ("Direction", "Direction (edge / planar face)",
         ("Edge", "Face"), True),
        ("Spine", "Spine (blank: rail 1)", ("Edge", "Wire"), True),
    )
    ENUMS = {
        "Mode": ("1 rail", "2 rails",
                 "Rail + direction"),
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "Mode", "Sweep",
         "How the profile is carried along the rail", None),
        ("App::PropertyLinkSub", "Profile", "Sweep",
         "Profile curve", None),
        ("App::PropertyLinkSub", "Rail1", "Sweep",
         "Rail curve", None),
        ("App::PropertyLinkSub", "Rail2", "Sweep",
         "Second rail (2 rails mode)", None),
        ("App::PropertyLinkSub", "ReferenceSurface", "Sweep",
         "Reference surface the sweeping frame follows", None),
        ("App::PropertyLinkSub", "Direction", "Sweep",
         "Direction reference (Rail + direction mode)", None),
        ("App::PropertyVector", "DirectionVector", "Sweep",
         "Explicit direction (no reference picked)",
         App.Vector(0, 0, 1)),
        ("App::PropertyLinkSub", "Spine", "Sweep",
         "Optional spine (defaults to rail 1)", None),
        ("App::PropertyAngle", "Angle", "Sweep",
         "Rotation of the profile about the rail tangent", "0 deg"),
    )

    @staticmethod
    def _two_rails_morph(profile, g1, g2):
        from .sweep_common import loft_sections, rotation_between, STATIONS
        p_pts = stations(g1)
        q_pts = stations(g2)
        prof_pts = [App.Vector(v) for v in profile.discretize(STATIONS)]
        e1, e2 = prof_pts[0], prof_pts[-1]
        # anchor the profile end nearest to rail 1
        if (e1 - p_pts[0]).Length > (e2 - p_pts[0]).Length:
            prof_pts.reverse()
            e1, e2 = e2, e1
        base = e2 - e1
        if base.Length < 1e-9:
            raise GSFeatureError("the profile is closed — the "
                                 "2 rails mode needs an open one")
        sections = []
        for p, q in zip(p_pts, q_pts):
            target = q - p
            if target.Length < 1e-9:
                raise GSFeatureError("the rails touch")
            scale = target.Length / base.Length
            rot = rotation_between(base, target)
            pts = [p + rot.multVec(v - e1) * scale for v in prof_pts]
            bs = Part.BSplineCurve()
            try:
                bs.interpolate(pts)
            except Part.OCCError as err:
                raise GSFeatureError(f"section morph failed ({err})")
            sections.append(Part.Wire([bs.toShape()]))
        return loft_sections(sections)

    def build(self, obj):
        profile = rail_wire(obj.Profile, "profile")
        rail = rail_wire(obj.Rail1, "rail curve")
        mode = obj.Mode

        spine = rail
        if obj.Spine and mode != "2 rails":
            spine = rail_wire(obj.Spine, "spine")

        angle = obj.Angle.getValueAs("deg").Value
        if abs(angle) > 1e-9:
            pts = stations(rail, 9)
            tg = tangents(pts)[0]
            profile = profile.copy()
            profile.rotate(pts[0], tg, angle)

        ps = Part.BRepOffsetAPI.MakePipeShell(spine)
        with_contact = False
        if mode == "Rail + direction":
            if obj.Direction:
                d = App.Vector(direction_from_ref(
                    resolve_linksub(obj.Direction)))
            else:
                d = App.Vector(obj.DirectionVector)
            if d.Length < 1e-12:
                raise GSFeatureError("the direction is null")
            d.normalize()
            ps.setBiNormalMode(d)
        elif mode == "2 rails":
            # OCC's auxiliary spine only twists the profile, it never
            # stretches it to the second rail — station-morph instead:
            # a similarity transform anchors the profile's ends to the
            # two rails at every station.
            if not obj.Rail2:
                raise GSFeatureError(
                    "the 2 rails mode needs rail curve 2")
            return self._two_rails_morph(profile, rail,
                                          rail_wire(obj.Rail2,
                                                     "rail curve 2"))
        else:  # 1 rail
            if obj.ReferenceSurface:
                face = support_face(obj.ReferenceSurface,
                                    "reference surface")
                # validate the curve the pipe shell actually follows
                if spine.distToShape(face)[0] > 1e-4:
                    raise GSFeatureError(
                        "the spine curve must lie on the reference "
                        "surface")
                ps.setSpineSupport(face)

        ps.add(profile, with_contact, False)
        if not ps.isReady():
            raise GSFeatureError("the sweep could not be prepared — "
                                 "check profile and rail positions")
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
