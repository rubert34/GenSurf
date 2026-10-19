# GenSurf workbench — GUI initialization.
# Only imported by the FreeCAD GUI; never runs under freecadcmd.

import FreeCADGui


class GenerativeSurfacesWorkbench(FreeCADGui.Workbench):
    """Generative surfacing workbench."""

    MenuText = "GenSurf"
    ToolTip = "Generative wireframe and surface modeling"

    def __init__(self):
        import os
        import gensurf
        self.Icon = os.path.join(
            gensurf.ADDON_DIR, "resources", "icons", "GenSurf_Workbench.svg"
        )

    def Initialize(self):
        # Import here (not module top level) per FreeCAD workbench rules.
        from gensurf.ui import commands, observers
        self.__class__._commands = commands.register_all()
        observers.install()  # new sketches land in the active set

        # fly-out groups + single buttons, by task
        for title, items in commands.TOOLBARS:
            self.appendToolbar(title, items)
        for title, items in commands.MENUS:
            self.appendMenu(["&GenSurf", title], items)

    def Activated(self):
        # Give GenSurf features in already open documents their view
        # providers (files saved without GUI data restore without them).
        import FreeCAD as App
        from gensurf.ui.view_provider import ensure_view_providers
        for name in App.listDocuments():
            ensure_view_providers(App.getDocument(name))

    def GetClassName(self):
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(GenerativeSurfacesWorkbench())

# documents opened later, whichever workbench is active, get GenSurf's
# view providers for their GenSurf features (lightweight observer)
from gensurf.ui import observers as _observers  # noqa: E402
_observers.install_restore_repair()
