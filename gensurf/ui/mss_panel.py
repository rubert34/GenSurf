"""Multi-Sections table panel — CATIA-style dialog.

Two tables mirror CATIA's Multi-Sections Surface Definition:
  * Sections: No | Section | Support | Continuity
    (Support/Continuity active on the FIRST and LAST rows only, exactly
    as in CATIA — tangency applies to extreme sections)
  * Guides:   No | Guide | Support | Continuity (every row)

Workflow: press "Add" under a table, then click curves in the 3D view —
each pick appends a row. Select a row and press "Set support", then pick
a face. Continuity combos live inside the table. Everything recomputes
live.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets, QtCore

from gensurf.ui.task_panels import build_params_box

_CONT_NAMES = ("Position", "Tangent", "Curvature")


def _pick_label(linked, subs):
    sub = subs[0] if subs else ""
    return f"{linked.Label}.{sub}" if sub else linked.Label


class MultiSectionTaskPanel:
    def __init__(self, obj, created=False):
        self.obj = obj
        self.created = created
        self.mode = None  # "section" | "guide" | "sup_section" | "sup_guide"

        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(obj.Label or obj.Name)
        layout = QtWidgets.QVBoxLayout(self.form)

        self.sec_table = self._make_table("Sections", layout,
                                          self._sec_buttons)
        self.gui_table = self._make_table("Guides", layout,
                                          self._gui_buttons)

        self.hint = QtWidgets.QLabel("")
        self.hint.setWordWrap(True)

        params = build_params_box(
            obj, set(), lambda m: self.hint.setText(m))
        if params is not None:
            layout.addWidget(params)
        layout.addWidget(self.hint)
        layout.addStretch()

        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self)
        self.refresh()
        if not (obj.Sections or []):
            self._set_mode("section")

    # -- UI scaffolding ----------------------------------------------------

    def _make_table(self, title, layout, buttons_fn):
        box = QtWidgets.QGroupBox(title)
        v = QtWidgets.QVBoxLayout(box)
        table = QtWidgets.QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(
            [title[:-1], "Support", "Continuity"])
        table.horizontalHeader().setStyleSheet(
            "QHeaderView::section { background: palette(button); "
            "color: palette(button-text); padding: 2px; }")
        table.verticalHeader().setStyleSheet(
            "QHeaderView::section { background: palette(button); "
            "color: palette(button-text); }")
        table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch)
        table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        table.setSelectionMode(QtWidgets.QTableWidget.SingleSelection)
        table.setEditTriggers(QtWidgets.QTableWidget.NoEditTriggers)
        table.setMinimumHeight(96)
        table.setMaximumHeight(150)
        v.addWidget(table)
        row = QtWidgets.QHBoxLayout()
        for label, cb in buttons_fn():
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(cb)
            row.addWidget(b)
        v.addLayout(row)
        layout.addWidget(box)
        return table

    def _sec_buttons(self):
        return (("Add", lambda: self._set_mode("section")),
                ("Remove", self._remove_section),
                ("Set support", lambda: self._set_mode("sup_section")))

    def _gui_buttons(self):
        return (("Add", lambda: self._set_mode("guide")),
                ("Remove", self._remove_guide),
                ("Set support", lambda: self._set_mode("sup_guide")))

    def _set_mode(self, mode):
        self.mode = mode
        prompts = {
            "section": "Click a section curve — then its support FACE "
                       "(or the next curve to skip the support).",
            "guide": "Click a guide curve — then its support FACE (or "
                     "the next curve to skip the support).",
            "sup_section": "Pick the support FACE for this section — or "
                           "click the next section curve to skip.",
            "sup_guide": "Pick the support FACE for this guide — or "
                         "click the next guide curve to skip.",
        }
        self.hint.setText(prompts.get(mode, ""))

    # -- model access ------------------------------------------------------

    @staticmethod
    def _entries(links):
        out = []
        for linked, subs in (links or []):
            subs = list(subs) if subs else [""]
            for sub in subs:
                out.append((linked, sub))
        return out

    def refresh(self):
        obj = self.obj
        secs = self._entries(obj.Sections)
        sec_conts = list(obj.SectionContinuities or [])
        sec_sup_map = self._support_map("SectionSupports",
                                        "SectionSupportRows")
        self.sec_table.setRowCount(len(secs))
        for r, (linked, sub) in enumerate(secs):
            self.sec_table.setItem(r, 0, QtWidgets.QTableWidgetItem(
                _pick_label(linked, [sub] if sub else [])))
            text = ""
            if r in sec_sup_map:
                s_linked, s_sub = sec_sup_map[r]
                text = _pick_label(s_linked, [s_sub] if s_sub else [])
            self.sec_table.setItem(r, 1, QtWidgets.QTableWidgetItem(text))
            combo = QtWidgets.QComboBox()
            combo.addItems(list(_CONT_NAMES))
            combo.setCurrentIndex(sec_conts[r] if r < len(sec_conts)
                                  else 0)
            combo.currentIndexChanged.connect(
                lambda v, row=r: self._set_row_cont(
                    "SectionContinuities", self.sec_table, row, v))
            self.sec_table.setCellWidget(r, 2, combo)

        gds = self._entries(obj.Guides)
        conts = list(obj.GuideContinuities or [])
        self.gui_table.setRowCount(len(gds))
        sup_map = self._guide_support_map()
        for r, (linked, sub) in enumerate(gds):
            self.gui_table.setItem(r, 0, QtWidgets.QTableWidgetItem(
                _pick_label(linked, [sub] if sub else [])))
            text = ""
            if r in sup_map:
                s_linked, s_sub = sup_map[r]
                text = _pick_label(s_linked, [s_sub] if s_sub else [])
            self.gui_table.setItem(r, 1, QtWidgets.QTableWidgetItem(text))
            combo = QtWidgets.QComboBox()
            combo.addItems(list(_CONT_NAMES))
            combo.setCurrentIndex(conts[r] if r < len(conts) else 0)
            combo.currentIndexChanged.connect(
                lambda v, row=r: self._set_guide_cont(row, v))
            self.gui_table.setCellWidget(r, 2, combo)

    def _support_map(self, entries_prop, rows_prop):
        rows = list(getattr(self.obj, rows_prop) or [])
        flat = self._entries(getattr(self.obj, entries_prop))
        return {row: pick for pick, row in zip(flat, rows)}

    def _guide_support_map(self):
        return self._support_map("GuideSupports", "GuideSupportRows")

    def _write_supports(self, entries_prop, rows_prop, sup_map):
        entries, rows = [], []
        for row, (linked, sub) in sorted(sup_map.items()):
            entries.append((linked, [sub] if sub else [""]))
            rows.append(row)
        setattr(self.obj, entries_prop, entries)
        setattr(self.obj, rows_prop, rows)

    def _write_guide_supports(self, sup_map):
        self._write_supports("GuideSupports", "GuideSupportRows", sup_map)

    def _recompute(self):
        try:
            self.obj.Document.recompute()
        except Exception as err:
            self.hint.setText(str(err))

    def _set_row_cont(self, prop, table, row, value):
        conts = list(getattr(self.obj, prop) or [])
        n = table.rowCount()
        conts = (conts + [0] * n)[:n]
        conts[row] = int(value)
        setattr(self.obj, prop, conts)
        self._recompute()

    def _set_guide_cont(self, row, value):
        self._set_row_cont("GuideContinuities", self.gui_table, row, value)

    # -- row operations ----------------------------------------------------

    def _remove_section(self):
        r = self.sec_table.currentRow()
        entries = self._entries(self.obj.Sections)
        if 0 <= r < len(entries):
            del entries[r]
            self.obj.Sections = [
                (o, [s] if s else [""]) for o, s in entries]
            sup_map = {row if row < r else row - 1: pick
                       for row, pick in self._support_map(
                           "SectionSupports",
                           "SectionSupportRows").items()
                       if row != r}
            self._write_supports("SectionSupports", "SectionSupportRows",
                                 sup_map)
            conts = list(self.obj.SectionContinuities or [])
            if r < len(conts):
                del conts[r]
            self.obj.SectionContinuities = conts
            self._recompute()
            self.refresh()

    def _remove_guide(self):
        r = self.gui_table.currentRow()
        entries = self._entries(self.obj.Guides)
        if 0 <= r < len(entries):
            del entries[r]
            self.obj.Guides = [
                (o, [s] if s else [""]) for o, s in entries]
            sup_map = {row if row < r else row - 1: pick
                       for row, pick in self._guide_support_map().items()
                       if row != r}
            self._write_guide_supports(sup_map)
            conts = list(self.obj.GuideContinuities or [])
            if r < len(conts):
                del conts[r]
            self.obj.GuideContinuities = conts
            self._recompute()
            self.refresh()

    # -- selection observer ------------------------------------------------

    def addSelection(self, doc_name, obj_name, sub, _pos):
        if self.mode is None:
            return
        picked = App.getDocument(doc_name).getObject(obj_name)
        if picked is None or picked is self.obj:
            return
        try:
            self._handle_pick(picked, sub)
        except Exception as err:
            self.hint.setText(str(err))

    @staticmethod
    def _shape_of(picked, sub):
        return picked.Shape.getElement(sub) if sub else picked.Shape

    def _is_curveish(self, picked, sub):
        shape = self._shape_of(picked, sub)
        return shape.ShapeType in ("Edge", "Wire") or \
            (not shape.Faces and bool(shape.Edges))

    def _is_faceish(self, picked, sub):
        shape = self._shape_of(picked, sub)
        return shape.ShapeType == "Face" or len(shape.Faces) == 1

    def _append_row(self, prop, picked, sub):
        current = [(o, list(ss))
                   for o, ss in (getattr(self.obj, prop) or [])]
        current.append((picked, [sub] if sub else [""]))
        setattr(self.obj, prop, current)

    def _handle_pick(self, picked, sub):
        # Alternating flow: curve -> its support face -> next curve...
        # Clicking a curve while a support is expected skips the support.
        if self.mode in ("section", "guide"):
            prop = "Sections" if self.mode == "section" else "Guides"
            if not self._is_curveish(picked, sub):
                self.hint.setText("pick a CURVE (edge, wire or sketch)")
                return
            self._append_row(prop, picked, sub)
            self._recompute()
            self.refresh()
            table = self.sec_table if self.mode == "section" \
                else self.gui_table
            table.selectRow(table.rowCount() - 1)
            self._set_mode("sup_section" if self.mode == "section"
                           else "sup_guide")
            return

        if self.mode in ("sup_section", "sup_guide"):
            adding = "section" if self.mode == "sup_section" else "guide"
            if self._is_curveish(picked, sub) and \
                    not self._is_faceish(picked, sub):
                # support skipped: this pick is the next curve
                self._set_mode(adding)
                self._handle_pick(picked, sub)
                return
            if not self._is_faceish(picked, sub):
                self.hint.setText(
                    "pick a support FACE, or the next curve to skip")
                return
            shape = self._shape_of(picked, sub)
            if shape.ShapeType != "Face" and len(shape.Faces) == 1:
                sub = sub or ""
            if self.mode == "sup_section":
                r = self.sec_table.currentRow()
                if r < 0:
                    self.hint.setText("select a section row first")
                    return
                sup_map = self._support_map("SectionSupports",
                                            "SectionSupportRows")
                sup_map[r] = (picked, sub)
                self._write_supports("SectionSupports",
                                     "SectionSupportRows", sup_map)
            else:
                r = self.gui_table.currentRow()
                if r < 0:
                    self.hint.setText("select a guide row first")
                    return
                sup_map = self._guide_support_map()
                sup_map[r] = (picked, sub)
                self._write_guide_supports(sup_map)
            self._recompute()
            self.refresh()
            self._set_mode(adding)  # ready for the next curve

    # -- dialog lifecycle --------------------------------------------------

    def getStandardButtons(self):
        return int(QtWidgets.QDialogButtonBox.Ok
                   | QtWidgets.QDialogButtonBox.Apply
                   | QtWidgets.QDialogButtonBox.Cancel)

    def clicked(self, button):
        if int(button) == int(QtWidgets.QDialogButtonBox.Apply):
            self._recompute()

    def _cleanup(self):
        Gui.Selection.removeObserver(self)

    def accept(self):
        self._cleanup()
        self._recompute()
        Gui.Control.closeDialog()
        return True

    def reject(self):
        self._cleanup()
        if self.created:
            name = self.obj.Name
            doc = self.obj.Document
            doc.removeObject(name)
            doc.recompute()
        Gui.Control.closeDialog()
        return True
