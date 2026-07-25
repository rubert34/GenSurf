"""Declarative task panels — the CATIA-style contextual dialog.

Two sections are generated from the feature class:
  * input slots (INPUT_SLOTS): label + read-only field + armable "Select"
    button; while armed, clicking geometry in the 3D view fills the slot.
    5-tuples (prop, label, expect, optional, multiple) support ordered
    multi-pick slots backed by App::PropertyLinkSubList.
  * parameters (PROPERTIES): spin boxes / checkboxes / combos for every
    non-link property, editing the object live with instant recompute.

``build_params_box`` / ``make_param_widget`` are shared with custom
panels (e.g. the Multi-Sections table panel).

OK keeps the feature, Apply recomputes, Cancel removes it if it was just
created.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtWidgets

_LENGTH_TYPES = ("App::PropertyDistance", "App::PropertyLength")


def _camel_label(name):
    """LengthFwd -> 'Length Fwd'."""
    out = []
    for ch in name:
        if ch.isupper() and out:
            out.append(" ")
        out.append(ch)
    return "".join(out)


def _norm_slots(proxy):
    """Yield (prop, label, expect, optional, multiple) from 3/4/5-tuples."""
    for spec in getattr(proxy, "INPUT_SLOTS", ()):
        prop, label, expect = spec[0], spec[1], spec[2]
        optional = spec[3] if len(spec) > 3 else False
        multiple = spec[4] if len(spec) > 4 else False
        yield prop, label, expect, optional, multiple


def make_param_widget(obj, ptype, name, error_cb):
    """One live-editing widget for a feature property, or None."""

    def commit(setter):
        def _apply(*args):
            try:
                setter(*args)
                obj.Document.recompute()
            except Exception as err:
                error_cb(str(err))
        return _apply

    if ptype in _LENGTH_TYPES:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setSuffix(" mm")
        spin.setDecimals(2)
        spin.setSingleStep(1.0)
        lo = 0.0 if ptype == "App::PropertyLength" else -1e9
        spin.setRange(lo, 1e9)
        spin.setValue(getattr(obj, name).getValueAs("mm").Value)
        spin.valueChanged.connect(
            commit(lambda v: setattr(obj, name, f"{v} mm")))
        spin.setMaximumWidth(120)
        return spin

    if ptype == "App::PropertyAngle":
        spin = QtWidgets.QDoubleSpinBox()
        spin.setSuffix(" °")
        spin.setDecimals(2)
        spin.setSingleStep(5.0)
        spin.setRange(-3600, 3600)
        spin.setValue(getattr(obj, name).getValueAs("deg").Value)
        spin.valueChanged.connect(
            commit(lambda v: setattr(obj, name, f"{v} deg")))
        spin.setMaximumWidth(120)
        return spin

    if ptype == "App::PropertyInteger":
        spin = QtWidgets.QSpinBox()
        spin.setRange(0, 100000)
        spin.setValue(int(getattr(obj, name)))
        spin.valueChanged.connect(
            commit(lambda v: setattr(obj, name, int(v))))
        spin.setMaximumWidth(120)
        return spin

    if ptype == "App::PropertyFloat":
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(-1e9, 1e9)
        spin.setDecimals(2)
        spin.setSingleStep(0.1)
        spin.setValue(float(getattr(obj, name)))
        spin.valueChanged.connect(
            commit(lambda v: setattr(obj, name, float(v))))
        spin.setMaximumWidth(120)
        return spin

    if ptype == "App::PropertyBool":
        cb = QtWidgets.QCheckBox()
        cb.setChecked(bool(getattr(obj, name)))
        cb.toggled.connect(commit(lambda v: setattr(obj, name, v)))
        return cb

    if ptype == "App::PropertyEnumeration":
        combo = QtWidgets.QComboBox()
        values = obj.getEnumerationsOfProperty(name) or []
        combo.addItems(list(values))
        combo.setCurrentText(str(getattr(obj, name)))
        combo.currentTextChanged.connect(
            commit(lambda v: setattr(obj, name, v)))
        return combo

    if ptype == "App::PropertyVector":
        holder = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        spins = []
        current = getattr(obj, name)
        for axis, val in zip("xyz", (current.x, current.y, current.z)):
            row.addWidget(QtWidgets.QLabel(axis))
            s = QtWidgets.QDoubleSpinBox()
            s.setRange(-1e9, 1e9)
            s.setDecimals(2)
            s.setValue(val)
            s.setMaximumWidth(70)
            row.addWidget(s)
            spins.append(s)

        def setter():
            setattr(obj, name, App.Vector(*[s.value() for s in spins]))
        for s in spins:
            s.valueChanged.connect(commit(lambda *_: setter()))
        return holder

    return None  # unsupported types stay in the Property View only


def build_params_box(obj, skip_names, error_cb):
    """Parameter group box for every non-link property of a feature.
    Shared by the declarative panel and custom (table) panels."""
    rows = []
    for ptype, name, _group, doc, _default in \
            getattr(obj.Proxy, "PROPERTIES", ()):
        if name in skip_names or not hasattr(obj, name):
            continue
        if ptype.startswith("App::PropertyLink") or ptype.endswith("List"):
            continue
        w = make_param_widget(obj, ptype, name, error_cb)
        if w is not None:
            rows.append((name, doc, w))
    if not rows:
        return None
    box = QtWidgets.QGroupBox("Parameters")
    form = QtWidgets.QFormLayout(box)
    form.setRowWrapPolicy(QtWidgets.QFormLayout.WrapLongRows)
    form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
    for name, doc, w in rows:
        w.setToolTip(doc)
        form.addRow(_camel_label(name), w)
    return box


class FeatureTaskPanel:
    def __init__(self, obj, created=False):
        self.obj = obj
        self.created = created
        self.slots = list(_norm_slots(obj.Proxy))
        self.armed = None
        self._widgets = {}

        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle(obj.Label or obj.Name)
        layout = QtWidgets.QVBoxLayout(self.form)

        for prop, label, expect, optional, multiple in self.slots:
            box = QtWidgets.QGroupBox(label)
            row = QtWidgets.QHBoxLayout(box)
            field = QtWidgets.QLineEdit(self._describe(prop))
            field.setReadOnly(True)
            btn = QtWidgets.QPushButton("Select")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, p=prop: self._arm(p))
            row.addWidget(field)
            row.addWidget(btn)
            if multiple:
                reset = QtWidgets.QPushButton("Reset")
                reset.clicked.connect(
                    lambda _=False, p=prop: self._reset_multi(p))
                row.addWidget(reset)
            layout.addWidget(box)
            self._widgets[prop] = (field, btn)

        self.hint = QtWidgets.QLabel("")
        self.hint.setWordWrap(True)

        slot_props = {s[0] for s in self.slots}
        params = build_params_box(self.obj, slot_props,
                                  lambda m: self.hint.setText(m))
        if params is not None:
            layout.addWidget(params)

        layout.addWidget(self.hint)
        layout.addStretch()

        # the whole dialog session is ONE document transaction: the
        # creating command opens it for new features; for edits of an
        # existing feature the panel opens its own. OK commits, Cancel
        # aborts — live preview becomes fully undoable / revertible.
        if not created:
            obj.Document.openTransaction(f"Edit {obj.Label}")

        Gui.Selection.clearSelection()
        Gui.Selection.addObserver(self)
        self._arm_first_empty()

    # -- slot management --------------------------------------------------

    def _is_multi(self, prop):
        return next(m for p, _l, _e, _o, m in self.slots if p == prop)

    def _describe(self, prop):
        link = getattr(self.obj, prop, None)
        if not link:
            return ""
        if self._is_multi(prop):
            n = sum(max(len(subs), 1) for _o, subs in link)
            return f"{n} picked"
        linked, subs = link
        return f"{linked.Label}.{subs[0]}" if subs else linked.Label

    def _reset_multi(self, prop):
        setattr(self.obj, prop, [])
        field, _btn = self._widgets[prop]
        field.setText("")
        self.obj.Document.recompute()
        self._arm(prop)

    def _arm(self, prop):
        self.armed = prop
        for p, (field, btn) in self._widgets.items():
            btn.setChecked(p == prop)
        label = next(lbl for pp, lbl, _e, _o, _m in self.slots
                     if pp == prop)
        extra = " (click several, in order)" if self._is_multi(prop) else ""
        self.hint.setText(
            f"Click in the 3D view or the model tree: {label}{extra}")

    def _arm_first_empty(self):
        for prop, _label, _expect, optional, _m in self.slots:
            if not optional and not getattr(self.obj, prop, None):
                self._arm(prop)
                return
        self.armed = None
        for _field, btn in self._widgets.values():
            btn.setChecked(False)
        self.hint.setText("All required inputs set — press OK to finish.")

    def _arm_next_after(self, prop):
        """CATIA-style sequential picking: after filling a slot, arm the
        NEXT empty slot in declaration order — optional ones included,
        so Curve 1 -> Support 1 -> Curve 2 -> Support 2 flows without
        touching the dialog."""
        names = [s[0] for s in self.slots]
        try:
            start = names.index(prop) + 1
        except ValueError:
            start = 0
        for p in names[start:]:
            if not getattr(self.obj, p, None):
                self._arm(p)
                return
        self._arm_first_empty()  # nothing later: fall back to required

    # -- FreeCAD selection observer callback -------------------------------

    def addSelection(self, doc_name, obj_name, sub, _pos):
        if self.armed is None:
            return
        picked = App.getDocument(doc_name).getObject(obj_name)
        if picked is None or picked is self.obj:
            return
        expect = next(e for p, _l, e, _o, _m in self.slots
                      if p == self.armed)
        if sub and expect:
            element = picked.Shape.getElement(sub)
            if element.ShapeType not in expect:
                self.hint.setText(
                    f"That is a {element.ShapeType} — expected: "
                    f"{' or '.join(expect)}")
                return
        try:
            if self._is_multi(self.armed):
                current = [(o, list(ss))
                           for o, ss in (getattr(self.obj, self.armed)
                                         or [])]
                current.append((picked, [sub] if sub else [""]))
                setattr(self.obj, self.armed, current)
            else:
                setattr(self.obj, self.armed,
                        (picked, [sub] if sub else []))
        except Exception as err:
            self.hint.setText(str(err))
            return
        field, _btn = self._widgets[self.armed]
        field.setText(self._describe(self.armed))
        self.obj.Document.recompute()  # live preview
        if not self._is_multi(self.armed):
            self._arm_next_after(self.armed)  # multi slots stay armed

    # -- dialog lifecycle --------------------------------------------------

    def getStandardButtons(self):
        return int(QtWidgets.QDialogButtonBox.Ok
                   | QtWidgets.QDialogButtonBox.Apply
                   | QtWidgets.QDialogButtonBox.Cancel)

    def clicked(self, button):
        if int(button) == int(QtWidgets.QDialogButtonBox.Apply):
            self.obj.Document.recompute()
            self._arm_first_empty()

    def _cleanup(self):
        Gui.Selection.removeObserver(self)

    def _hide_consumed(self):
        """CATIA behavior: inputs consumed by the operator disappear
        when the result is confirmed (declared per feature via
        HIDE_INPUTS; e.g. Split hides the split element, not the
        cutter)."""
        shape = getattr(self.obj, "Shape", None)
        if shape is None or shape.isNull():
            return  # nothing built: leave the scene untouched
        for prop in getattr(self.obj.Proxy, "HIDE_INPUTS", ()):
            link = getattr(self.obj, prop, None)
            if not link:
                continue
            entries = link if isinstance(link, list) else [link]
            for entry in entries:
                linked = entry[0] if isinstance(entry, tuple) else entry
                vo = getattr(linked, "ViewObject", None)
                if vo is not None:
                    vo.Visibility = False

    def accept(self):
        self._cleanup()
        doc = self.obj.Document
        doc.recompute()
        self._hide_consumed()
        doc.commitTransaction()
        Gui.Control.closeDialog()
        return True

    def reject(self):
        self._cleanup()
        doc = self.obj.Document
        # aborting removes a just-created feature AND reverts every
        # live-preview edit of an existing one
        doc.abortTransaction()
        doc.recompute()
        Gui.Control.closeDialog()
        return True
