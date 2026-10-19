"""GenSurfError: keyed, attributable issues routed by GSFeature.execute."""

import Part
import pytest

from conftest import assert_recomputes
from gensurf.features import (GenSurfError, GSFeatureError, GSFeature,
                              ERROR, WARNING, INFO, make_feature)


def test_former_name_is_the_same_class_and_one_argument_form_works():
    assert GSFeatureError is GenSurfError
    err = GSFeatureError("the rails do not touch")
    assert (err.key, err.message, err.severity) == (
        "generic", "the rails do not touch", ERROR)
    assert str(err) == "the rails do not touch"
    assert err.faulty_properties == () and err.sub_elements == ()


def test_full_form_carries_its_context():
    err = GenSurfError("rails-do-not-touch", "rail 2 misses section 3",
                       ["Rails", "Sections"], [("Line001", "Edge1")],
                       WARNING)
    assert err.key == "rails-do-not-touch"
    assert err.faulty_properties == ("Rails", "Sections")
    assert err.sub_elements == (("Line001", "Edge1"),)
    assert err.severity == WARNING
    assert err.describe() == "rail 2 misses section 3 [Rails, Sections]"


class _Probe(GSFeature):
    """Test-only feature whose build behaviour is set per test."""
    TYPE_ID = "GenSurf::TestProbe"
    PROPERTIES = (("App::PropertyInteger", "Mode", "Probe", "", 0),)

    def build(self, obj):
        if obj.Mode == 1:
            raise GenSurfError("probe-failed", "no geometry", ["Mode"])
        if obj.Mode == 2:
            self.report(obj, GenSurfError("probe-loose", "out of tolerance",
                                          ["Mode"], severity=WARNING))
        return Part.makeBox(1, 1, 1)


def test_execute_records_a_raised_issue(doc):
    obj = make_feature(doc, _Probe, "Probe")
    obj.Mode = 1
    doc.recompute()
    assert "Invalid" in obj.State
    issues = obj.Proxy.issues()
    assert [(i.key, i.severity) for i in issues] == [("probe-failed", ERROR)]
    assert issues[0].faulty_properties == ("Mode",)


def test_execute_keeps_geometry_and_reports_warnings(doc):
    obj = make_feature(doc, _Probe, "Probe")
    obj.Mode = 2
    assert_recomputes(doc)
    assert obj.Shape.Volume == pytest.approx(1.0)
    assert [(i.key, i.severity) for i in obj.Proxy.issues()] == [
        ("probe-loose", WARNING)]

    obj.Mode = 0  # issues belong to the last recompute only
    assert_recomputes(doc)
    assert obj.Proxy.issues() == []


def test_missing_inputs_are_an_info_issue_naming_them(doc):
    from gensurf.features import make_loft
    loft = make_loft(doc)
    assert_recomputes(doc)  # incomplete, not broken
    issue, = loft.Proxy.issues()
    assert (issue.key, issue.severity) == ("input-missing", INFO)
    assert issue.faulty_properties == ("Sections",)


def test_existing_errors_are_routed_too(doc):
    from gensurf.features import make_extruded_surface
    import FreeCAD as App
    prof = doc.addObject("Part::Feature", "Prof")
    prof.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0))
    ex = make_extruded_surface(doc)
    ex.Profile = (prof, [])
    ex.DirectionMode = "Vector"
    ex.Direction = App.Vector(0, 0, 0)
    doc.recompute()
    issue, = ex.Proxy.issues()
    assert issue.severity == ERROR and issue.key == "generic"
