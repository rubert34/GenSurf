"""GUI smoke test (run as a macro inside the FreeCAD GUI).

    GENSURF_SMOKE_LOG=/tmp/gensurf-smoke.txt \\
        /path/to/FreeCAD --user-cfg /tmp/gensurf-smoke.cfg \\
        tools/gui_smoke.py

Exercises what the headless tests cannot reach: every toolbar command
(create, open its task panel, Apply, Cancel), the task panel of every
operator in edit mode on the 0.28 legacy document, Set Active, and the
toolbar layout. Writes one line per check ("PASS ..." / "FAIL ...") to
$GENSURF_SMOKE_LOG, then quits without saving anything. Python errors
raised inside FreeCAD callbacks are only printed to the console, so also
check the console output for "Traceback".
"""

import os
import shutil
import tempfile
import traceback

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtWidgets

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.environ.get("GENSURF_SMOKE_LOG",
                     os.path.join(tempfile.gettempdir(), "gensurf-smoke.txt"))
RESULTS = []


class _ControlSpy:
    """Forwards to FreeCADGui.Control and remembers the last panel shown
    (FreeCAD only hands back its own wrapper, not the Python panel)."""

    def __init__(self, real):
        self._real = real
        self.last = None

    def showDialog(self, panel):
        self.last = panel
        return self._real.showDialog(panel)

    def __getattr__(self, name):
        return getattr(self._real, name)


class _GuiSpy:
    def __init__(self, real):
        self._real = real
        self.Control = _ControlSpy(real.Control)

    def __getattr__(self, name):
        return getattr(self._real, name)


SPY = _GuiSpy(Gui)


def _close_leftover_dialog():
    if not Gui.Control.activeDialog():
        return
    panel = SPY.Control.last
    try:
        panel.reject()
    except Exception:  # noqa: BLE001
        Gui.Control.closeDialog()
        if App.ActiveDocument:
            App.ActiveDocument.abortTransaction()


def check(name, fn):
    SPY.Control.last = None
    try:
        detail = fn()
        RESULTS.append(f"PASS {name}" + (f" — {detail}" if detail else ""))
    except Exception as err:  # noqa: BLE001 — report everything
        tb = traceback.format_exc().strip().splitlines()[-3:]
        RESULTS.append(f"FAIL {name}: {err!r} | " + " / ".join(tb))
        _close_leftover_dialog()
    QtWidgets.QApplication.processEvents()


def _active_panel():
    panel = SPY.Control.last
    if panel is None or not Gui.Control.activeDialog():
        raise RuntimeError("no task panel was shown")
    return panel


def _apply_and_cancel(panel):
    from gensurf.ui.qt_compat import enum_value, standard_buttons
    if not standard_buttons() & enum_value(
            QtWidgets.QDialogButtonBox.Apply):
        raise RuntimeError("Apply button missing")
    panel.getStandardButtons()
    panel.clicked(enum_value(QtWidgets.QDialogButtonBox.Apply))
    panel.reject()
    QtWidgets.QApplication.processEvents()
    if Gui.Control.activeDialog():
        raise RuntimeError("dialog still open after Cancel")


def toolbars():
    from gensurf.ui import commands
    mw = Gui.getMainWindow()
    titles = {tb.windowTitle() for tb in mw.findChildren(QtWidgets.QToolBar)
              if tb.isVisible()}
    wanted = [title for title, _items in commands.TOOLBARS]
    missing = [t for t in wanted if t not in titles]
    if missing:
        raise RuntimeError(f"toolbars missing: {missing}")
    return ", ".join(wanted)


def create_with_command(name):
    from gensurf.ui import commands
    doc = App.ActiveDocument
    before = len(doc.Objects)
    commands._COMMANDS[name].Activated()
    QtWidgets.QApplication.processEvents()
    created = len(doc.Objects) - before
    if created < 1:
        raise RuntimeError("no object created")
    _apply_and_cancel(_active_panel())
    if len(doc.Objects) != before:
        raise RuntimeError(
            f"Cancel left {len(doc.Objects) - before} object(s) behind")


def edit_existing(obj):
    from gensurf.ui.view_provider import open_feature_dialog
    open_feature_dialog(obj, created=False)
    QtWidgets.QApplication.processEvents()
    panel = _active_panel()
    _apply_and_cancel(panel)
    return type(panel).__name__


def construction_sets():
    from gensurf.containers import get_active_set, make_construction_set
    from gensurf.ui import commands
    doc = App.ActiveDocument
    commands._COMMANDS["GenSurf_ConstructionSet"].Activated()
    first = get_active_set(doc)
    second = make_construction_set(doc, "SmokeSet")  # becomes active
    on, off = "GenSurf_SetActive.svg", "GenSurf_ConstructionSet.svg"

    def icons():
        return tuple(os.path.basename(o.ViewObject.Proxy.getIcon())
                     for o in (first, second))

    def right_click(obj, label):
        menu = QtWidgets.QMenu()
        obj.ViewObject.Proxy.setupContextMenu(obj.ViewObject, menu)
        actions = {a.text(): a for a in menu.actions()}
        if label not in actions:
            raise RuntimeError(f"{obj.Label}: no {label!r} in {list(actions)}")
        actions[label].trigger()
        QtWidgets.QApplication.processEvents()

    if icons() != (off, on):
        raise RuntimeError(f"icons {icons()}")
    right_click(first, "Set Active")
    if get_active_set(doc) is not first or icons() != (on, off):
        raise RuntimeError(f"Set Active failed, icons {icons()}")
    right_click(first, "Set Inactive")
    if get_active_set(doc) is not None or icons() != (off, off):
        raise RuntimeError(f"Set Inactive failed, icons {icons()}")

    cmd = commands._COMMANDS["GenSurf_SetActive"]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(second)
    if not cmd.IsActive():
        raise RuntimeError("Set Active / Inactive is disabled with a set "
                           "selected")
    cmd.Activated()  # toolbar: inactive -> active
    if get_active_set(doc) is not second:
        raise RuntimeError("toolbar did not make the set active")
    cmd.Activated()  # toolbar again: active -> inactive
    if get_active_set(doc) is not None:
        raise RuntimeError("toolbar did not make the set inactive")
    Gui.Selection.clearSelection()
    return "right-click Set Active / Inactive, toolbar toggle, icons"


def tree_icons(doc):
    missing = [o.Name for o in doc.Objects
               if getattr(o, "GSType", "")
               and not hasattr(o.ViewObject.Proxy, "getIcon")]
    if missing:
        raise RuntimeError(f"no GenSurf view provider for {missing}")
    return f"{len(doc.Objects)} objects, sets included"


def run():
    from gensurf.ui import commands, view_provider
    Gui.activateWorkbench("GenerativeSurfacesWorkbench")
    view_provider.Gui = SPY  # panels are shown through this module
    tmp = tempfile.mkdtemp(prefix="gensurf-smoke-")
    try:
        check("toolbars", toolbars)

        App.newDocument("Smoke")
        check("construction sets", construction_sets)
        for name, _type_id, text, _tip in commands._FEATURES:
            check(f"command {text}",
                  lambda n=name: create_with_command(n))
        App.closeDocument("Smoke")

        path = os.path.join(tmp, "legacy.FCStd")
        shutil.copyfile(os.path.join(REPO, "tests", "data",
                                     "gensurf_v028_legacy.FCStd"), path)
        legacy = App.openDocument(path)
        QtWidgets.QApplication.processEvents()  # deferred repairs run here
        legacy.recompute()
        Gui.SendMsgToActiveView("ViewFit")
        check("tree icons", lambda: tree_icons(legacy))
        seen = set()
        for obj in legacy.Objects:
            gstype = getattr(obj, "GSType", "")
            if obj.TypeId != "Part::FeaturePython" or gstype in seen:
                continue
            seen.add(gstype)
            check(f"edit {gstype} ({obj.Name})",
                  lambda o=obj: edit_existing(o))
        App.closeDocument(legacy.Name)
    except Exception:  # noqa: BLE001
        RESULTS.append("FAIL harness: " + traceback.format_exc())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        with open(LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(RESULTS) + "\n")
        App.Console.PrintMessage(f"[smoke] {len(RESULTS)} checks -> {LOG}\n")
        QtCore.QTimer.singleShot(500, Gui.getMainWindow().close)


QtCore.QTimer.singleShot(2500, run)
