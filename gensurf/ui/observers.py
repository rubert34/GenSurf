"""Document observers that keep the set workflow tidy.

SketchCapture: while the GenSurf workbench is active, a newly created
sketch is adopted into the active construction set, like every other
new feature.

The adoption is deferred one event-loop turn so other workbenches (e.g.
PartDesign, whose sketches belong to a Body) finish claiming their object
first; anything already parented to a group or Body is left alone.
"""

import FreeCAD as App
import FreeCADGui as Gui

_observer = None
_restore_observer = None


class ViewProviderRepair:
    """When a document becomes active (opening one activates it), give
    its GenSurf features their view providers (tree icon, double-click
    opens the task panel) even if the file was saved without GUI data.
    FreeCAD 1.1 does not call slotFinishRestoreDocument on Python
    observers, hence activation. Deferred one event-loop turn so loading
    has finished; repeated activations are cheap no-ops."""

    def slotActivateDocument(self, doc):
        from PySide import QtCore
        name = doc.Name
        QtCore.QTimer.singleShot(0, lambda: self._repair(name))

    @staticmethod
    def _repair(name):
        if name not in App.listDocuments():
            return
        from gensurf.ui.view_provider import ensure_view_providers
        ensure_view_providers(App.getDocument(name))


def install_restore_repair():
    """Installed when FreeCAD loads the workbench list, so documents
    opened before GenSurf is first activated are repaired too."""
    global _restore_observer
    if _restore_observer is None:
        _restore_observer = ViewProviderRepair()
        App.addDocumentObserver(_restore_observer)


class SketchCapture:
    def slotCreatedObject(self, obj):
        try:
            if obj.TypeId != "Sketcher::SketchObject":
                return
            wb = Gui.activeWorkbench()
            if wb is None or wb.name() != "GenerativeSurfacesWorkbench":
                return
        except Exception:
            return
        from PySide import QtCore
        doc_name, obj_name = obj.Document.Name, obj.Name
        QtCore.QTimer.singleShot(0, lambda: self._adopt(doc_name, obj_name))

    @staticmethod
    def _adopt(doc_name, obj_name):
        doc = App.getDocument(doc_name) if doc_name in App.listDocuments() \
            else None
        obj = doc.getObject(obj_name) if doc else None
        if obj is None:
            return
        # leave it alone if something already claimed it
        for parent in obj.InList:
            if parent.hasExtension("App::GroupExtension") \
                    or parent.TypeId == "PartDesign::Body":
                return
        from gensurf.containers import get_active_set
        active = get_active_set(doc)
        if active is None:
            return  # no set in this document — don't surprise the user
        active.addObject(obj)
        App.Console.PrintMessage(
            f"[GenSurf] {obj.Label} added to {active.Label}\n")


def install():
    global _observer
    if _observer is None:
        _observer = SketchCapture()
        App.addDocumentObserver(_observer)
