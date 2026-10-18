"""ConstructionSet — the container that organises a GenSurf model.

Construction geometry (points, curves, planes) and the surfaces built
from it are kept in sets, so helpers stay apart from the result
surfaces. A set may be unordered (a plain collection) or ordered (its
children form a linear history), and sets may be nested. New features
are inserted into the *active* set.

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


def get_active_set(doc, create=False):
    """Return the active set, or None. With create=True, make one if absent."""
    for obj in _iter_sets(doc):
        if obj.ActiveSet:
            return obj
    if create:
        return make_construction_set(doc, activate=True)
    return None


def insert_into_active_set(feature_obj, doc=None):
    """Insert a document object into the active set (creating one if needed)."""
    doc = doc or feature_obj.Document
    active = get_active_set(doc, create=True)
    active.addObject(feature_obj)
    return active
