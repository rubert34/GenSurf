"""Multiple Extract table panel — CATIA-style dialog.

One table: No | Element | Propagation | Threshold. "Add" arms picking:
every 3D click appends a row — and because FreeCAD's native box element
selection (Edit > Box element selection) emits one selection event per
captured element, sweeping a box while Add is armed bulk-fills the
table (the rectangle "selection trap"). Polygon / freehand traps need a
dedicated viewport event layer and are not implemented yet.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

from gensurf.ui.task_panels import build_params_box

_PROP_NAMES = ("No propagation", "Point continuity",
               "Tangent continuity")


def _pick_label(linked, sub):
    return f"{linked.Label}.{sub}" if sub else linked.Label


class MultiExtractTaskPanel:
    def __init__(self, obj, created=False):
        self.obj = obj
        self.created = created
        if not created:  # dialog session = one transaction (see task_panels)
            obj.Document.openTransaction(f"Edit {obj.Label}")
        self.adding = False

        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(obj.Label or obj.Name)
        layout = QtWidgets.QVBoxLayout(self.form)

        box = QtWidgets.QGroupBox("Elements to extract")
        v = QtWidgets.QVBoxLayout(box)
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(
            ["Element", "Propagation", "Threshold"])
        self.table.horizontalHeader().setStyleSheet(
            "QHeaderView::section { background: palette(button); "
            "color: palette(button-text); padding: 2px; }")
        self.table.verticalHeader().setStyleSheet(
            "QHeaderView::section { background: palette(button); "
            "color: palette(button-text); }")
        self.table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch)
        self.table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        self.table.setSelectionMode(QtWidgets.QTableWidget.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QTableWidget.NoEditTriggers)
        self.table.setMinimumHeight(140)
        v.addWidget(self.table)

        row = QtWidgets.QHBoxLayout()
        for label, cb in (("Add", self._arm),
                          ("Remove", self._remove),
                          ("Box select", self._box_select)):
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(cb)
            row.addWidget(b)
        v.addLayout(row)
        layout.addWidget(box)

        self.hint = QtWidgets.QLabel("")
        self.hint.setWordWrap(True)

        params = build_params_box(obj, set(),
                                  lambda m: self.hint.setText(m))
        if params is not None:
            layout.addWidget(params)
        layout.addWidget(self.hint)
        layout.addStretch()

        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self)
        self.refresh()
        self._arm()

    # -- actions -----------------------------------------------------------

    def _arm(self):
        self.adding = True
        self.hint.setText(
            "Click faces/edges to add rows — or sweep a box with "
            "'Box select' to trap many at once.")

    def _box_select(self):
        self._arm()
        try:
            Gui.runCommand("Std_BoxElementSelection")
        except Exception:
            self.hint.setText(
                "Box element selection unavailable — use Edit menu > "
                "Box element selection.")

    def _remove(self):
        r = self.table.currentRow()
        rows = self._rows()
        if 0 <= r < len(rows):
            del rows[r]
            self._write_rows(rows)
            for prop in ("Propagations", "Thresholds"):
                vals = list(getattr(self.obj, prop) or [])
                if r < len(vals):
                    del vals[r]
                setattr(self.obj, prop, vals)
            self._recompute()
            self.refresh()

    # -- model -------------------------------------------------------------

    def _rows(self):
        out = []
        for linked, subs in (self.obj.Elements or []):
            for sub in (subs if subs else ("",)):
                out.append((linked, sub))
        return out

    def _write_rows(self, rows):
        self.obj.Elements = [(o, [s] if s else [""]) for o, s in rows]

    def _recompute(self):
        try:
            self.obj.Document.recompute()
        except Exception as err:
            self.hint.setText(str(err))

    def _set_row_int(self, prop, row, value, default):
        vals = list(getattr(self.obj, prop) or [])
        n = self.table.rowCount()
        vals = (vals + [default] * n)[:n]
        vals[row] = value
        setattr(self.obj, prop, vals)
        self._recompute()

    def refresh(self):
        rows = self._rows()
        props = list(self.obj.Propagations or [])
        thrs = list(self.obj.Thresholds or [])
        self.table.setRowCount(len(rows))
        for r, (linked, sub) in enumerate(rows):
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(
                _pick_label(linked, sub)))
            combo = QtWidgets.QComboBox()
            combo.addItems(list(_PROP_NAMES))
            combo.setCurrentIndex(props[r] if r < len(props) else 0)
            combo.currentIndexChanged.connect(
                lambda v, row=r: self._set_row_int(
                    "Propagations", row, int(v), 0))
            self.table.setCellWidget(r, 1, combo)
            spin = QtWidgets.QDoubleSpinBox()
            spin.setSuffix(" °")
            spin.setDecimals(2)
            spin.setRange(0.01, 90.0)
            spin.setValue(thrs[r] if r < len(thrs) and thrs[r] > 0
                          else 0.5)
            spin.valueChanged.connect(
                lambda v, row=r: self._set_row_float(row, float(v)))
            self.table.setCellWidget(r, 2, spin)

    def _set_row_float(self, row, value):
        vals = list(self.obj.Thresholds or [])
        n = self.table.rowCount()
        vals = (vals + [0.5] * n)[:n]
        vals[row] = value
        self.obj.Thresholds = vals
        self._recompute()

    # -- selection observer ------------------------------------------------

    def addSelection(self, doc_name, obj_name, sub, _pos):
        if not self.adding or not sub:
            return
        picked = App.getDocument(doc_name).getObject(obj_name)
        if picked is None or picked is self.obj:
            return
        try:
            shape = picked.Shape.getElement(sub)
        except Exception:
            return
        if shape.ShapeType not in ("Face", "Edge"):
            self.hint.setText("pick faces or edges")
            return
        rows = self._rows()
        if any(o is picked and s == sub for o, s in rows):
            return  # already listed
        rows.append((picked, sub))
        self._write_rows(rows)
        self._recompute()
        self.refresh()

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
        self.obj.Document.commitTransaction()
        Gui.Control.closeDialog()
        return True

    def reject(self):
        self._cleanup()
        doc = self.obj.Document
        doc.abortTransaction()  # removes created / reverts edited
        doc.recompute()
        Gui.Control.closeDialog()
        return True
