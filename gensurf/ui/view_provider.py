"""Generic view provider for all GS features.

Owns the tree icon and the double-click behavior (open the feature's task
panel instead of FreeCAD's default Transform dragger).
"""

import os

import FreeCAD as App
import FreeCADGui as Gui

import gensurf

ICON_DIR = os.path.join(gensurf.ADDON_DIR, "resources", "icons")


def _icon_by_type():
    """Tree icon per feature type: the icon of the command that creates
    it (resources/icons/<command name>.svg)."""
    from gensurf.ui.commands import _FEATURES
    return {type_id: f"{name}.svg" for name, type_id, _t, _tip in _FEATURES}


_ICON_BY_TYPE = {}


class GSViewProvider:
    def __init__(self, vobj):
        # attach() is not called when the proxy is set on an existing view
        # object (repair of files saved without GUI data): keep it here too
        self.vobj = vobj
        vobj.Proxy = self

    def attach(self, vobj):
        self.vobj = vobj

    def getIcon(self):
        if not _ICON_BY_TYPE:
            _ICON_BY_TYPE.update(_icon_by_type())
        gstype = getattr(self.vobj.Object, "GSType", "")
        icon = _ICON_BY_TYPE.get(gstype)
        return os.path.join(ICON_DIR, icon) if icon else None

    def doubleClicked(self, vobj):
        open_feature_dialog(vobj.Object, created=False)
        return True  # swallow the default Transform action

    def setupContextMenu(self, vobj, menu):
        obj = vobj.Object
        proxy = getattr(obj, "Proxy", None)
        current = getattr(proxy, "ALGO_VERSION", 1)
        if getattr(obj, "GenSurfAlgo", current) < current:
            action = menu.addAction("Upgrade to current algorithm")
            action.triggered.connect(lambda: upgrade_algorithm(obj))

    def claimChildren(self):
        return []

    def dumps(self):
        return None

    def loads(self, state):
        return None


class SetViewProvider:
    """View provider of a construction set: its tree icon shows whether it
    is the active set (where new features go), and its context menu
    offers Set Active. Children are shown by FreeCAD's group handling."""

    def __init__(self, vobj):
        self.vobj = vobj  # see GSViewProvider.__init__
        vobj.Proxy = self

    def attach(self, vobj):
        self.vobj = vobj

    def getIcon(self):
        active = getattr(self.vobj.Object, "ActiveSet", False)
        name = "GenSurf_SetActive.svg" if active else \
            "GenSurf_ConstructionSet.svg"
        return os.path.join(ICON_DIR, name)

    def updateData(self, obj, prop):
        if prop == "ActiveSet":
            refresh = getattr(self.vobj, "signalChangeIcon", None)
            if refresh:
                refresh()

    def setupContextMenu(self, vobj, menu):
        obj = vobj.Object
        if getattr(obj, "ActiveSet", False):
            action = menu.addAction("Set Inactive")
            action.setToolTip("New features will go to the top level of "
                              "the document")
        else:
            action = menu.addAction("Set Active")
            action.setToolTip("New features will be inserted into this set")
        action.triggered.connect(lambda: toggle_active_set(obj))

    def dumps(self):
        return None

    def loads(self, state):
        return None


def toggle_active_set(obj):
    """Set Active / Set Inactive: make a construction set the active one,
    or switch it off if it already is (one undoable step)."""
    from gensurf.containers import set_active_set, set_inactive
    doc = obj.Document
    doc.openTransaction("Set active construction set")
    if obj.ActiveSet:
        set_inactive(obj)
        message = (f"{obj.Label} is inactive: new features go to the top "
                   "level of the document")
    else:
        set_active_set(obj)
        message = f"{obj.Label} is now the active set: new features go into it"
    doc.commitTransaction()
    App.Console.PrintMessage(f"[GenSurf] {message}\n")


def upgrade_algorithm(obj):
    """Move a feature built with an older algorithm to the current one
    (one undoable step; the geometry may change)."""
    doc = obj.Document
    doc.openTransaction(f"Upgrade {obj.Label} to current algorithm")
    if obj.Proxy.upgrade_algorithm(obj):
        doc.recompute()
    doc.commitTransaction()


def open_feature_dialog(obj, created=False):
    """Show the task panel for a GS feature (if it declares input slots)."""
    if Gui.Control.activeDialog():
        App.Console.PrintWarning(
            "[GenSurf] close the active task dialog first\n")
        return
    custom = getattr(obj.Proxy, "CUSTOM_PANEL", None)
    if custom == "loft":
        from gensurf.ui.loft_panel import LoftTaskPanel
        Gui.Control.showDialog(LoftTaskPanel(obj, created=created))
        return
    if custom == "extract":
        from gensurf.ui.extract_panel import ExtractTaskPanel
        Gui.Control.showDialog(ExtractTaskPanel(obj, created=created))
        return
    from gensurf.ui.task_panels import FeatureTaskPanel
    Gui.Control.showDialog(FeatureTaskPanel(obj, created=created))


def ensure_view_providers(doc):
    """Attach GenSurf's view providers to features and construction sets
    that lack one: documents saved without GUI data (scripts, tests) or
    by earlier versions restore with an empty proxy (None or 0)."""
    if not App.GuiUp or doc is None:
        return
    from gensurf.containers import is_set
    from gensurf.features import FEATURES
    for obj in doc.Objects:
        vo = getattr(obj, "ViewObject", None)
        if vo is None or hasattr(getattr(vo, "Proxy", None), "getIcon"):
            continue
        if getattr(obj, "GSType", "") in FEATURES:
            GSViewProvider(vo)
        elif is_set(obj):
            SetViewProvider(vo)
