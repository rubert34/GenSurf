# Generative Surfaces workbench — GUI initialization.
# Only imported by the FreeCAD GUI; never runs under freecadcmd.

import FreeCADGui


class GenerativeSurfacesWorkbench(FreeCADGui.Workbench):
    """CATIA GSD-style surfacing workbench."""

    MenuText = "GenSurf"
    ToolTip = "GSD-style wireframe and surface modeling"

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
        observers.install()  # sketches created in GS land in the active set

        # CATIA-style layout: fly-out groups + single buttons
        for title, items in commands.TOOLBARS:
            self.appendToolbar(title, items)
        self.appendMenu("&GenSurf", commands.MENU)

    def Activated(self):
        # Upgrade objects created before the view-provider layer existed.
        import FreeCAD as App
        from gensurf.ui.view_provider import ensure_view_providers
        ensure_view_providers(App.ActiveDocument)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(GenerativeSurfacesWorkbench())
