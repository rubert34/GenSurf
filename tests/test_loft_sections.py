"""Loft algorithm version 2: seam points, section directions, the twist
check and the exact skin through prepared sections."""

import math

import pytest

import FreeCAD as App
import Part

from conftest import assert_recomputes

V = App.Vector
CYLINDER = 2 * math.pi * 10 * 10  # side area: radius 10, height 10


def _square(doc, z, size=10, start=0, name="Sq"):
    pts = [V(-size, -size, z), V(size, -size, z), V(size, size, z),
           V(-size, size, z)]
    pts = pts[start:] + pts[:start]
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = Part.makePolygon(pts + [pts[0]])
    return obj


def _circle(doc, z, seam_deg=0.0, radius=10, name="Ci"):
    u0 = math.radians(seam_deg)
    circle = Part.Circle(V(0, 0, z), V(0, 0, 1), radius)
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = Part.Wire([Part.Edge(circle, u0, u0 + 2 * math.pi)])
    return obj


def _loft(doc, *sections):
    from gensurf.features import make_loft
    loft = make_loft(doc)
    loft.Sections = [(s, "") for s in sections]
    return loft


def _keys(loft):
    return [i.key for i in loft.Proxy.issues()]


def _through(shape, *objs):
    """Largest distance from the section curves to the surface."""
    return max(shape.distToShape(Part.Vertex(p))[0]
               for o in objs for p in o.Shape.discretize(40))


def test_new_lofts_use_version_2(doc):
    loft = _loft(doc, _square(doc, 0), _square(doc, 10))
    assert loft.GenSurfAlgo == 2


def test_shifted_seam_is_matched_automatically(doc):
    loft = _loft(doc, _square(doc, 0), _square(doc, 10, start=1))
    assert_recomputes(doc)
    assert loft.Shape.Area == pytest.approx(800.0, abs=1e-6)  # no twist
    assert len(loft.Shape.Faces) == 4  # one face per edge column
    assert _keys(loft) == []


def test_picked_seam_is_kept_and_twist_warned(doc):
    s0, s1 = _square(doc, 0), _square(doc, 10)
    loft = _loft(doc, s0, s1)
    loft.SeamPoints = [(s1, "Vertex2")]  # a quarter turn round
    loft.SeamPointRows = [1]
    assert_recomputes(doc)
    assert loft.Shape.Area > 850.0  # twisted, as asked
    assert _through(loft.Shape, s0, s1) < 1e-6
    issue, = loft.Proxy.issues()
    assert issue.key == "sections-twist"
    assert "90°" in issue.message
    assert issue.faulty_properties == ("SeamPoints",)


def test_twist_limit_zero_silences_the_warning(doc):
    s0, s1 = _square(doc, 0), _square(doc, 10)
    loft = _loft(doc, s0, s1)
    loft.SeamPoints = [(s1, "Vertex2")]
    loft.SeamPointRows = [1]
    loft.TwistLimit = 0
    assert_recomputes(doc)
    assert _keys(loft) == []


def test_reversed_row_flips_that_section_and_warns(doc):
    loft = _loft(doc, _square(doc, 0), _square(doc, 10))
    loft.SectionDirections = [0, 1]
    assert_recomputes(doc)
    assert loft.Shape.Area > 1000.0  # folds through the middle
    assert _keys(loft) == ["sections-opposite"]


def test_manual_alignment_uses_sections_as_drawn(doc):
    loft = _loft(doc, _square(doc, 0), _square(doc, 10, start=1))
    loft.AutoOrient = False
    assert_recomputes(doc)
    assert loft.Shape.Area > 850.0
    assert _keys(loft) == ["sections-twist"]


def test_smooth_section_seam_matched_anywhere(doc):
    loft = _loft(doc, _circle(doc, 0), _circle(doc, 10, seam_deg=135))
    assert_recomputes(doc)
    assert loft.Shape.Area == pytest.approx(CYLINDER, rel=1e-6)
    assert len(loft.Shape.Faces) == 1  # a periodic curve is not split


def test_square_to_circle_matches_plain_loft(doc):
    sq, ci = _square(doc, 0), _circle(doc, 10)
    loft = _loft(doc, sq, ci)
    assert_recomputes(doc)
    plain = Part.makeLoft([sq.Shape, ci.Shape])
    assert loft.Shape.Area == pytest.approx(plain.Area, rel=1e-6)
    assert _through(loft.Shape, sq, ci) < 1e-6
    assert loft.Shape.isValid()


def test_three_sections_pass_exactly_and_match_plain_loft(doc):
    secs = (_square(doc, 0), _square(doc, 5, size=14), _square(doc, 10))
    loft = _loft(doc, *secs)
    assert_recomputes(doc)
    plain = Part.makeLoft([s.Shape for s in secs])
    assert loft.Shape.Area == pytest.approx(plain.Area, rel=1e-6)
    assert _through(loft.Shape, *secs) < 1e-6
    assert len(loft.Shape.Shells) == 1


def test_ruled_closed_sections(doc):
    secs = (_square(doc, 0), _square(doc, 5, size=14), _square(doc, 10))
    loft = _loft(doc, *secs)
    loft.Ruled = True
    assert_recomputes(doc)
    side = math.hypot(5, 4)  # slant height of each band
    assert loft.Shape.Area == pytest.approx(
        2 * 4 * (20 + 28) / 2 * side, rel=1e-6)
    assert len(loft.Shape.Faces) == 8


def test_open_and_closed_sections_cannot_mix(doc):
    line = doc.addObject("Part::Feature", "L")
    line.Shape = Part.makeLine(V(0, 0, 10), V(10, 0, 10))
    loft = _loft(doc, _square(doc, 0), line)
    doc.recompute()
    assert "Invalid" in str(loft.State)
    assert _keys(loft) == ["sections-mixed"]


def test_seam_must_be_a_point(doc):
    s0, s1 = _square(doc, 0), _square(doc, 10)
    loft = _loft(doc, s0, s1)
    loft.SeamPoints = [(s1, "Edge1")]
    loft.SeamPointRows = [1]
    doc.recompute()
    assert _keys(loft) == ["seam-not-a-point"]


def test_end_support_path_matches_seams_too(doc):
    """Closed sections with a G1 end support (the sampled path): the
    second circle's seam is a third of a turn away, and the surface
    still continues the cylinder instead of twisting."""
    cyl = doc.addObject("Part::Feature", "Cyl")
    cyl.Shape = Part.makeCylinder(10, 10, V(0, 0, -10)).Faces[0]
    loft = _loft(doc, _circle(doc, 0), _circle(doc, 10, seam_deg=120))
    loft.SectionSupports = [(cyl, "Face1")]
    loft.SectionSupportRows = [0]
    loft.SectionContinuities = [1, 0]
    assert_recomputes(doc)
    radii = [math.hypot(p.x, p.y) for w in loft.Shape.slice(V(0, 0, 1), 5)
             for p in w.discretize(24)]
    assert min(radii) > 9.5  # an untwisted mid-section stays round

    loft.GenSurfAlgo = 1  # the old path takes the seams as drawn
    assert_recomputes(doc)
    radii = [math.hypot(p.x, p.y) for w in loft.Shape.slice(V(0, 0, 1), 5)
             for p in w.discretize(24)]
    assert min(radii) < 9.0  # twisted: the waist narrows


def test_version_1_keeps_plain_loft_and_flags_seam_settings(doc):
    from gensurf.features.base import WARNING
    s0, s1 = _square(doc, 0), _square(doc, 10, start=1)
    loft = _loft(doc, s0, s1)
    loft.GenSurfAlgo = 1
    loft.SectionDirections = [0, 1]
    assert_recomputes(doc)
    plain = Part.makeLoft([s0.Shape, s1.Shape])
    assert loft.Shape.Area == pytest.approx(plain.Area, rel=1e-9)
    issue, = loft.Proxy.issues()
    assert (issue.key, issue.severity) == ("loft-upgrade-for-seams",
                                           WARNING)

    loft.Proxy.upgrade_algorithm(loft)
    assert loft.GenSurfAlgo == 2
    assert_recomputes(doc)
    assert _keys(loft) == ["sections-opposite"]
