"""Old documents keep opening and recomputing identically.

* ``data/GenSurf_Demo.FCStd`` — the demo document, saved before 0.25.
* ``data/gensurf_v028_legacy.FCStd`` — saved by 0.28.0: one object of
  every operator and mode that has since been renamed or merged.

Both are compared against the geometry stored in the file itself: the
document is opened, every object is recomputed with the current code,
and the result must match what was saved.
"""

import os
import shutil
import zipfile

import FreeCAD as App
import pytest

import gensurf.features  # noqa: F401  (registers types, installs aliases)
from gensurf import migrations
from gensurf.containers import SET_TYPE_ID
from gensurf.features import FEATURES
from helpers.shape_fingerprint import fingerprint, differences

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _open_copy(name, tmp_path):
    path = str(tmp_path / name)
    shutil.copyfile(os.path.join(DATA, name), path)
    return App.openDocument(path)


def _features(doc):
    return [o for o in doc.Objects if o.TypeId == "Part::FeaturePython"
            and getattr(o, "GSType", "").startswith("GenSurf::")]


def _recompute_matches_stored(doc):
    stored = {o.Name: fingerprint(o.Shape) for o in _features(doc)}
    assert stored, "fixture contains no GenSurf features"
    for obj in doc.Objects:
        obj.touch()
    doc.recompute()
    invalid = [o.Name for o in doc.Objects if "Invalid" in o.State]
    assert not invalid, f"recompute failed for {invalid}"
    mismatches = {}
    for obj in _features(doc):
        diff = differences(fingerprint(obj.Shape), stored[obj.Name])
        if diff:
            mismatches[obj.Name] = diff
    assert not mismatches, mismatches


@pytest.mark.parametrize("name", ["GenSurf_Demo.FCStd",
                                  "gensurf_v028_legacy.FCStd"])
def test_old_document_recomputes_identically(name, tmp_path):
    doc = _open_copy(name, tmp_path)
    try:
        for obj in doc.Objects:
            gstype = getattr(obj, "GSType", "")
            if not gstype:
                continue
            assert obj.Proxy is not None, f"{obj.Name}: proxy not restored"
            assert gstype in FEATURES or gstype == SET_TYPE_ID, \
                f"{obj.Name}: unmigrated type {gstype}"
        _recompute_matches_stored(doc)
    finally:
        App.closeDocument(doc.Name)


def test_restored_features_are_algorithm_version_1(tmp_path):
    doc = _open_copy("GenSurf_Demo.FCStd", tmp_path)
    try:
        feats = _features(doc)
        assert feats and all(o.GenSurfAlgo == 1 for o in feats)
        assert all(o.getEditorMode("GenSurfAlgo") == ["Hidden"]
                   for o in feats)
    finally:
        App.closeDocument(doc.Name)


def test_new_feature_gets_current_algorithm_version(doc, monkeypatch):
    from gensurf.features.offset_surface import OffsetSurface
    from gensurf.features import make_offset_surface
    monkeypatch.setattr(OffsetSurface, "ALGO_VERSION", 3)
    obj = make_offset_surface(doc)
    assert obj.GenSurfAlgo == 3

    obj.GenSurfAlgo = 1
    assert obj.Proxy.algo_version(obj) == 1
    assert obj.Proxy.upgrade_algorithm(obj)
    assert obj.GenSurfAlgo == 3
    assert not obj.Proxy.upgrade_algorithm(obj)  # already current


def test_blend_saved_before_borders_keeps_natural_sides(tmp_path):
    doc = _open_copy("GenSurf_Demo.FCStd", tmp_path)
    try:
        assert doc.getObject("Blend").Borders == "Natural"
    finally:
        App.closeDocument(doc.Name)


# -- migration mechanisms (synthetic tables) --------------------------------


def test_property_rename_carries_value_and_expression(doc, monkeypatch):
    from gensurf.features import make_offset_surface
    obj = make_offset_surface(doc)
    # fake an object saved when "Offset" was called "Gap"
    obj.removeProperty("Offset")
    obj.addProperty("App::PropertyDistance", "Gap", "Old", "old doc")
    obj.setExpression("Gap", "2 mm + 1 mm")
    doc.recompute()
    monkeypatch.setitem(migrations.PROPERTY_RENAMES,
                        "GenSurf::OffsetSurface", {"Gap": "Offset"})

    obj.Proxy.onDocumentRestored(obj)

    assert not hasattr(obj, "Gap")
    assert dict(obj.ExpressionEngine) == {"Offset": "2 mm + 1 mm"}
    doc.recompute()
    assert obj.Offset.getValueAs("mm").Value == pytest.approx(3.0)
    # presentation follows the current declaration
    assert obj.getGroupOfProperty("Offset") == "Offset"


def test_enum_value_rename_and_list_sync(doc, monkeypatch):
    from gensurf.features import make_blend_surface
    obj = make_blend_surface(doc)
    obj.Continuity1 = ["Old A", "Old B", "G2 Curvature"]
    obj.Continuity1 = "Old B"
    monkeypatch.setitem(migrations.ENUM_RENAMES, "GenSurf::BlendSurface",
                        {"Continuity1": {"Old B": "G1 Tangent",
                                         "Old A": "G0 Position"}})

    obj.Proxy.onDocumentRestored(obj)

    assert obj.Continuity1 == "G1 Tangent"
    assert obj.getEnumerationsOfProperty("Continuity1") == \
        list(obj.Proxy.ENUMS["Continuity1"])


def test_type_rename_updates_gstype_and_proxy(doc, monkeypatch):
    from gensurf.features import make_offset_surface
    obj = make_offset_surface(doc)
    obj.GSType = "GenSurf::OldOffset"
    obj.Proxy.Type = "GenSurf::OldOffset"
    monkeypatch.setitem(migrations.TYPE_RENAMES, "GenSurf::OldOffset",
                        "GenSurf::OffsetSurface")

    obj.Proxy.onDocumentRestored(obj)

    assert obj.GSType == "GenSurf::OffsetSurface"
    assert obj.Proxy.Type == "GenSurf::OffsetSurface"


def test_old_proxy_module_path_resolves(doc, tmp_path, monkeypatch):
    """A document whose proxy names a module that no longer exists opens
    through the alias module registered for it."""
    import sys
    from gensurf.features import make_offset_surface
    from gensurf.features.offset_surface import OffsetSurface
    name = make_offset_surface(doc).Name
    path = str(tmp_path / "old.FCStd")
    doc.saveAs(path)

    patched = str(tmp_path / "patched.FCStd")
    with zipfile.ZipFile(path) as src, \
            zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "Document.xml":
                data = data.replace(
                    b'module="gensurf.features.offset_surface" '
                    b'class="OffsetSurface"',
                    b'module="gensurf.features.gone_offset" '
                    b'class="GoneOffset"')
                assert b"gone_offset" in data
            dst.writestr(item, data)

    monkeypatch.setitem(
        migrations.LEGACY_PROXIES, "gensurf.features.gone_offset",
        {"GoneOffset": "gensurf.features.offset_surface:OffsetSurface"})
    monkeypatch.delitem(sys.modules, "gensurf.features.gone_offset",
                        raising=False)
    migrations.install_legacy_modules("gensurf.features.")
    try:
        reopened = App.openDocument(patched)
        try:
            obj = reopened.getObject(name)
            assert isinstance(obj.Proxy, OffsetSurface)
        finally:
            App.closeDocument(reopened.Name)
    finally:
        sys.modules.pop("gensurf.features.gone_offset", None)
