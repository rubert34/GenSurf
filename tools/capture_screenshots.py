"""Capture the README screenshots (run as a macro inside the FreeCAD GUI).

    GENSURF_SHOTS_OUT=docs/images \\
        /path/to/FreeCAD --user-cfg /tmp/gensurf-shots.cfg \\
        tools/capture_screenshots.py

A separate ``--user-cfg`` keeps your own preferences and window layout
untouched. The script opens a copy of ``tests/data/GenSurf_Demo.FCStd``,
captures the main window only (never the desktop), writes the PNG files
to $GENSURF_SHOTS_OUT and quits without saving anything.
"""

import os
import shutil
import tempfile

import FreeCAD as App
import FreeCADGui as Gui
from PySide import QtCore, QtGui, QtWidgets

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("GENSURF_SHOTS_OUT",
                     os.path.join(REPO, "docs", "images"))
WIDTH = 1600  # output width in pixels


def _main_window():
    return Gui.getMainWindow()


def _tidy_window():
    mw = _main_window()
    mw.showNormal()
    mw.resize(1500, 940)
    for dock in mw.findChildren(QtWidgets.QDockWidget):
        if dock.objectName() in ("Report view", "Python console",
                                 "Selection view"):
            dock.hide()


def _front_document_view(label):
    """A fresh settings file shows FreeCAD's welcome page; bring the
    model's tab to the front (closing the welcome page crashes FreeCAD
    1.1, whose page still has a timer pending)."""
    for area in _main_window().findChildren(QtWidgets.QMdiArea):
        for sub in area.subWindowList():
            if sub.windowTitle().startswith(label):
                area.setActiveSubWindow(sub)


def _gl_widgets():
    try:
        from PySide6.QtOpenGLWidgets import QOpenGLWidget
    except ImportError:
        QOpenGLWidget = QtWidgets.QOpenGLWidget
    return [w for w in _main_window().findChildren(QOpenGLWidget)
            if w.isVisible()]


def _task_dock():
    for dock in _main_window().findChildren(QtWidgets.QDockWidget):
        if dock.windowTitle() == "Tasks" or dock.objectName() == "Tasks":
            return dock
    return None


def _render_view(width, height):
    """The 3D view rendered offscreen by FreeCAD itself (works whether or
    not the window is exposed on screen)."""
    tmp = os.path.join(tempfile.gettempdir(), "gensurf-view.png")
    Gui.ActiveDocument.ActiveView.saveImage(tmp, width, height, "Current")
    return QtGui.QImage(tmp)


def _grab(name):
    """Window image with the 3D view painted in: a plain window grab
    leaves OpenGL viewports blank when the window is not on screen.
    The task panel, shown over the 3D view, is painted back on top."""
    QtWidgets.QApplication.processEvents()
    mw = _main_window()
    pix = mw.grab()
    dpr = pix.devicePixelRatio()
    painter = QtGui.QPainter(pix)
    for glw in _gl_widgets():
        rect = QtCore.QRect(glw.mapTo(mw, QtCore.QPoint(0, 0)), glw.size())
        painter.drawImage(rect, _render_view(int(rect.width() * dpr),
                                             int(rect.height() * dpr)))
    dock = _task_dock()
    if dock is not None and dock.isVisible():
        painter.drawPixmap(dock.mapTo(mw, QtCore.QPoint(0, 0)), dock.grab())
    painter.end()
    if pix.width() > WIDTH:
        pix = pix.scaledToWidth(WIDTH, QtCore.Qt.SmoothTransformation)
    path = os.path.join(OUT, name)
    pix.save(path)
    App.Console.PrintMessage(
        f"[shots] wrote {path} (3D views: {len(_gl_widgets())})\n")


def _report_docks():
    for dock in _main_window().findChildren(QtWidgets.QDockWidget):
        App.Console.PrintMessage(
            f"[shots] dock {dock.objectName()!r} title "
            f"{dock.windowTitle()!r} visible {dock.isVisible()} "
            f"parent {type(dock.parent()).__name__}\n")


def _show_task_dock(visible):
    dock = _task_dock()
    if dock is not None:
        dock.setVisible(visible)


def _expand_tree():
    for tree in _main_window().findChildren(QtWidgets.QTreeWidget):
        tree.expandAll()


def _view(iso=True):
    view = Gui.ActiveDocument.ActiveView
    if iso:
        view.viewIsometric()
    view.fitAll()


class Shots:
    def __init__(self):
        os.makedirs(OUT, exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="gensurf-shots-")
        src = os.path.join(REPO, "tests", "data", "GenSurf_Demo.FCStd")
        path = os.path.join(self.tmp, "GenSurf_Demo.FCStd")
        shutil.copyfile(src, path)
        Gui.activateWorkbench("GenerativeSurfacesWorkbench")
        _tidy_window()
        self.doc = App.openDocument(path)
        for obj in self.doc.Objects:
            obj.touch()
        self.doc.recompute()
        self.panel = None
        self.steps = [self.overview, self.blend_panel, self.close_panel,
                      self.comb, self.finish]

    def run(self):
        if self.steps:
            step = self.steps.pop(0)
            step()
            QtCore.QTimer.singleShot(1500, self.run)

    def overview(self):
        _front_document_view(self.doc.Label)
        _report_docks()
        _show_task_dock(False)
        Gui.Selection.clearSelection()
        _expand_tree()
        _view()
        QtCore.QTimer.singleShot(1000, lambda: _grab("gensurf-overview.png"))

    def blend_panel(self):
        from gensurf.ui.task_panels import FeatureTaskPanel
        _show_task_dock(True)
        self.panel = FeatureTaskPanel(self.doc.getObject("Blend"))
        Gui.Control.showDialog(self.panel)
        QtCore.QTimer.singleShot(1000,
                                 lambda: _grab("gensurf-blend-panel.png"))

    def close_panel(self):
        if self.panel is not None:
            self.panel.reject()  # aborts the edit transaction
            self.panel = None

    def comb(self):
        """Combs on the two character curves, surfaces hidden."""
        from gensurf.features import make_curvature_comb
        for name in ("Extrude", "Extrude001", "Blend"):
            self.doc.getObject(name).ViewObject.Visibility = False
        for name in ("Spline", "Spline001"):
            curve = self.doc.getObject(name)
            curve.ViewObject.LineWidth = 3
            curve.ViewObject.LineColor = (0.85, 0.85, 0.9)
            comb = make_curvature_comb(self.doc)
            comb.Curve = (curve, [])
            comb.Samples = 80
            comb.ViewObject.LineColor = (1.0, 0.55, 0.1)
            comb.ViewObject.LineWidth = 1.5
        self.doc.recompute()
        _show_task_dock(False)
        Gui.Selection.clearSelection()
        _view()
        QtCore.QTimer.singleShot(1000,
                                 lambda: _grab("gensurf-curvature-comb.png"))

    def finish(self):
        App.closeDocument(self.doc.Name)
        shutil.rmtree(self.tmp, ignore_errors=True)
        App.Console.PrintMessage("[shots] done\n")
        QtCore.QTimer.singleShot(500, _main_window().close)


_shots = Shots()
QtCore.QTimer.singleShot(2000, _shots.run)
