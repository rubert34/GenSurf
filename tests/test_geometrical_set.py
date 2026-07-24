from gensurf.containers import (
    make_geometrical_set, get_active_set, set_active_set,
    insert_into_active_set,
)


def test_create_and_activate(doc):
    gs1 = make_geometrical_set(doc, "SetA")
    assert get_active_set(doc) is gs1

    gs2 = make_geometrical_set(doc, "SetB")
    # newest activated set wins, exclusivity enforced
    assert get_active_set(doc) is gs2
    assert not gs1.ActiveSet

    set_active_set(gs1)
    assert get_active_set(doc) is gs1
    assert not gs2.ActiveSet


def test_nested_sets(doc):
    parent = make_geometrical_set(doc, "Parent")
    child = make_geometrical_set(doc, "Child", parent=parent)
    assert child in parent.Group


def test_insert_into_active_creates_set(doc):
    assert get_active_set(doc) is None
    box = doc.addObject("Part::Box", "Box")
    active = insert_into_active_set(box)
    assert active is not None
    assert box in active.Group


def test_active_set_survives_save_load(doc, tmp_path):
    import FreeCAD as App
    make_geometrical_set(doc, "SetA")
    gs2 = make_geometrical_set(doc, "SetB")
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
