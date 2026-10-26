from gensurf.containers import (
    make_construction_set, get_active_set, set_active_set,
    insert_into_active_set,
)


def test_create_and_activate(doc):
    gs1 = make_construction_set(doc, "SetA")
    assert get_active_set(doc) is gs1

    gs2 = make_construction_set(doc, "SetB")
    # newest activated set wins, exclusivity enforced
    assert get_active_set(doc) is gs2
    assert not gs1.ActiveSet

    set_active_set(gs1)
    assert get_active_set(doc) is gs1
    assert not gs2.ActiveSet


def test_nested_sets(doc):
    parent = make_construction_set(doc, "Parent")
    child = make_construction_set(doc, "Child", parent=parent)
    assert child in parent.Group


def test_insert_into_active_creates_set(doc):
    assert get_active_set(doc) is None
    box = doc.addObject("Part::Box", "Box")
    active = insert_into_active_set(box)
    assert active is not None
    assert box in active.Group


def test_active_set_survives_save_load(doc, tmp_path):
    import FreeCAD as App
    make_construction_set(doc, "SetA")
    gs2 = make_construction_set(doc, "SetB")
    set_active_set(gs2)

    path = str(tmp_path / "roundtrip.FCStd")
    doc.saveAs(path)
    name = doc.Name
    App.closeDocument(name)

    reopened = App.openDocument(path)
    try:
        active = get_active_set(reopened)
        assert active is not None and active.Label == "SetB"
    finally:
        App.closeDocument(reopened.Name)


def _point(doc):
    from gensurf.features import make_point
    return make_point(doc)


def _top_level(obj):
    return not any(p.hasExtension("App::GroupExtension") for p in obj.InList)


def test_first_feature_creates_a_set(doc):
    from gensurf.containers import has_gensurf_features
    assert not has_gensurf_features(doc)
    pt = _point(doc)
    active = get_active_set(doc)
    assert active is not None and pt in active.Group
    assert has_gensurf_features(doc)


def test_set_inactive_sends_new_features_to_the_top_level(doc):
    from gensurf.containers import set_inactive
    first = _point(doc)
    active = get_active_set(doc)
    set_inactive(active)
    assert get_active_set(doc) is None
    second = _point(doc)
    assert _top_level(second) and first in active.Group
    assert len([o for o in doc.Objects if o.TypeId ==
                "App::DocumentObjectGroupPython"]) == 1  # no new set

    set_active_set(active)  # Set Active again: back into the set
    third = _point(doc)
    assert third in active.Group


def test_deleting_every_set_never_brings_one_back(doc, tmp_path):
    import FreeCAD as App
    _point(doc)
    doc.removeObject(get_active_set(doc).Name)
    pt = _point(doc)
    assert get_active_set(doc) is None and _top_level(pt)

    # the remaining GenSurf features say so, also after save and reload
    path = str(tmp_path / "used.FCStd")
    doc.saveAs(path)
    App.closeDocument(doc.Name)
    reopened = App.openDocument(path)
    try:
        from gensurf.features import make_point
        later = make_point(reopened)
        assert get_active_set(reopened) is None and _top_level(later)
    finally:
        App.closeDocument(reopened.Name)


def test_any_gensurf_feature_means_gensurf_is_in_use(doc):
    """A file that already holds GenSurf features (e.g. at the top level)
    never gets a set created behind the user's back."""
    from gensurf.features import make_feature
    from gensurf.features.point import Point
    make_feature(doc, Point, "Existing", into_active=False)
    pt = _point(doc)
    assert get_active_set(doc) is None and _top_level(pt)


def test_a_file_emptied_of_gensurf_starts_afresh(doc):
    """With every GenSurf feature deleted (and no active set), the next
    feature is the document's first again: it gets a new set."""
    pt = _point(doc)
    active = get_active_set(doc)
    doc.removeObject(pt.Name)
    doc.removeObject(active.Name)
    again = _point(doc)
    assert get_active_set(doc) is not None and not _top_level(again)


def test_sets_alone_do_not_count_as_features(doc):
    """Only features count: with sets but no GenSurf feature and no active
    set, the first feature gets a new set; with an active set it simply
    goes into that set."""
    from gensurf.containers import set_inactive
    spare = make_construction_set(doc, "Spare")
    first = _point(doc)
    assert first in spare.Group  # the active set receives it
    doc.removeObject(first.Name)
    set_inactive(spare)
    second = _point(doc)
    holder = get_active_set(doc)
    assert holder is not None and holder is not spare
    assert second in holder.Group
