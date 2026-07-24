"""SelectionManager — reusable multi-slot selection routing.

NOTE: FreeCAD selection observers are plain Python objects registered with
``Gui.Selection.addObserver`` (there is no ``Gui.SelectionObserver`` base
class). The FeatureTaskPanel embeds its own observer; this standalone
manager remains for future multi-feature tools (e.g. multi-guide sweeps).
"""

import FreeCAD as App
import FreeCADGui as Gui


class SelectionSlot:
    def __init__(self, name, expect=("Edge", "Wire", "Face"), multiple=False):
        self.name = name
        self.expect = expect
        self.multiple = multiple
        self.picks = []  # list of (obj, subname)


class SelectionManager:
    def __init__(self, slots, on_update=None):
        self.slots = slots
        self.active_index = 0
        self.on_update = on_update or (lambda: None)
        Gui.Selection.addObserver(self)

    def detach(self):
        Gui.Selection.removeObserver(self)

    @property
    def active_slot(self):
        return self.slots[self.active_index]

    def arm(self, index):
        self.active_index = index

    def addSelection(self, doc, obj_name, sub, _pnt):  # FreeCAD callback
        slot = self.active_slot
        obj = App.getDocument(doc).getObject(obj_name)
        if obj is None:
            return
        shape_type = obj.Shape.getElement(sub).ShapeType if sub else None
        if slot.expect and shape_type and shape_type not in slot.expect:
            return
        if not slot.multiple:
            slot.picks.clear()
        slot.picks.append((obj, sub))
        if not slot.multiple and self.active_index < len(self.slots) - 1:
            self.active_index += 1
        self.on_update()
