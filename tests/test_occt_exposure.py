"""Facts recorded in docs/occt_python_exposure.md, re-checked against the
FreeCAD build the tests run on. A failure means the document needs an
update (a FreeCAD upgrade changed what Python can reach)."""

import FreeCAD as App
import Part
import pytest


def test_filling_reports_its_errors():
    mf = Part.BRepOffsetAPI.MakeFilling()
    for name in ("G0Error", "G1Error", "G2Error"):
        assert hasattr(mf, name)


def test_pipe_shell_has_no_law_in_freecad_api():
    ps = Part.BRepOffsetAPI.MakePipeShell(
        Part.Wire([Part.makeLine(App.Vector(), App.Vector(0, 0, 1))]))
    assert not hasattr(ps, "setLaw")


def test_loft_has_no_parametrization_choice():
    doc = Part.makeLoft.__doc__ or ""
    assert "maxDegree" in doc and "par" not in doc.split("--")[0].lower()


def test_surface_differential_geometry_is_available():
    s = Part.BSplineSurface()
    for name in ("normal", "curvature", "curvatureDirections"):
        assert hasattr(s, name)


def test_surface_module_offers_blend_curve_and_geomfill(doc):
    import Surface
    assert hasattr(Surface, "BlendCurve") and hasattr(Surface, "BlendPoint")
    gf = doc.addObject("Surface::GeomFillSurface", "GF")
    assert gf.getEnumerationsOfProperty("FillType") == [
        "Stretched", "Coons", "Curved"]


def test_pythonocc_classes_when_bundled():
    occ = pytest.importorskip("OCC.Core.LocalAnalysis")
    assert hasattr(occ, "LocalAnalysis_SurfaceContinuity")
    from OCC.Core.BRepOffsetAPI import (BRepOffsetAPI_ThruSections,
                                        BRepOffsetAPI_MakePipeShell)
    assert hasattr(BRepOffsetAPI_ThruSections, "SetParType")
    assert hasattr(BRepOffsetAPI_MakePipeShell, "SetLaw")
