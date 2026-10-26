"""ConstructionSet — the container that organises a GenSurf model.

Construction geometry (points, curves, planes) and the surfaces built
from it are kept in sets, so helpers stay apart from the result
surfaces. A set may be unordered (a plain collection) or ordered (its
children form a linear history), and sets may be nested. New features
are inserted into the *active* set.

Where new features go: into the active set. With no active set (the
user switched it off with Set Inactive, or deleted it) they go to the top
level of the document. A set is created automatically only when a feature
is inserted into a document that holds no other GenSurf feature and has no
active set; once GenSurf features exist, new ones go into the active set,
or to the top level if none is active, so deleting every set later does
not bring one back.

Implementation notes
--------------------
* A set is an ``App::DocumentObjectGroupPython`` with a
  ``ConstructionSet`` proxy.
* The active set is persisted with a hidden boolean property ``ActiveSet``
  on the group object itself, so it survives save/load and needs no GUI
  state. Exactly one set per document may have it True.
"""

import FreeCAD as App

TYPE_ID = "GenSurf::ConstructionSet"


class ConstructionSet:
    """Proxy for a construction set container."""

    def __init__(self, obj, ordered=False):
        obj.Proxy = self
        self.Type = TYPE_ID
        if not hasattr(obj, "GSType"):
            obj.addProperty(
                "App::PropertyString", "GSType", "GenerativeSurfaces",
                "Internal type identifier")
            obj.GSType = TYPE_ID
            obj.setEditorMode("GSType", 2)  # hidden
        if not hasattr(obj, "Ordered"):
            obj.addProperty(
                "App::PropertyBool", "Ordered", "GenerativeSurfaces",
                "Ordered set: children form a linear history")
            obj.Ordered = ordered
        if not hasattr(obj, "ActiveSet"):
            obj.addProperty(
                "App::PropertyBool", "ActiveSet", "GenerativeSurfaces",
                "This set receives newly inserted features")
            obj.ActiveSet = False
            obj.setEditorMode("ActiveSet", 1)  # read-only in the editor

    def execute(self, obj):
        # Containers produce no geometry.
        pass

    def onDocumentRestored(self, obj):
        from gensurf import migrations
        migrations.migrate(obj, self)

    def dumps(self):
        return {"Type": self.Type}

    def loads(self, state):
        if state:
            self.Type = state.get("Type", TYPE_ID)


def is_set(obj):
    return getattr(obj, "GSType", None) == TYPE_ID


def _iter_sets(doc):
    for obj in doc.Objects:
        if is_set(obj):
            yield obj


def make_construction_set(doc, name="ConstructionSet", ordered=False,
                          parent=None, activate=True):
    """Create a construction set; optionally nest it and make it active."""
    obj = doc.addObject("App::DocumentObjectGroupPython", name)
    ConstructionSet(obj, ordered=ordered)
    if App.GuiUp:
        from gensurf.ui.view_provider import SetViewProvider
        SetViewProvider(obj.ViewObject)
    if parent is not None:
        parent.addObject(obj)
    if activate:
        set_active_set(obj)
    return obj


def set_active_set(obj):
    """Make ``obj`` the document's active construction set (exclusive)."""
    if not is_set(obj):
        raise ValueError(f"{obj.Name} is not a construction set")
    for other in _iter_sets(obj.Document):
        if other.ActiveSet and other is not obj:
            other.ActiveSet = False
    obj.ActiveSet = True
    return obj


def set_inactive(obj):
    """Switch the active set off: new features then go to the top level
    of the document until a set is made active again."""
    if not is_set(obj):
        raise ValueError(f"{obj.Name} is not a construction set")
    obj.ActiveSet = False
    return obj


def get_active_set(doc, create=False):
    """Return the active set, or None. With create=True, make one if absent."""
    for obj in _iter_sets(doc):
        if obj.ActiveSet:
            return obj
    if create:
        return make_construction_set(doc, activate=True)
    return None


def has_gensurf_features(doc, exclude=None):
    """True when the document already contains a GenSurf feature (sets do
    not count) other than ``exclude``, the feature being inserted."""
    return any(getattr(o, "GSType", "") not in ("", TYPE_ID)
               for o in doc.Objects if o is not exclude)


def insert_into_active_set(feature_obj, doc=None):
    """Insert a new feature into the active set and return that set. With
    no active set it stays at the top level (returns None), unless it is
    the document's first GenSurf feature: then a set is created for it."""
    doc = doc or feature_obj.Document
    active = get_active_set(doc)
    if active is None and not has_gensurf_features(doc, exclude=feature_obj):
        active = make_construction_set(doc, activate=True)
        App.Console.PrintMessage(
            f"[GenSurf] created {active.Label}: GenSurf keeps features in "
            "construction sets, and new features go into the active one. "
            "Right-click a set to make it active or inactive; with no "
            "active set, features go to the top level\n")
    if active is not None:
        active.addObject(feature_obj)
    return active
