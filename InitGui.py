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
        # Upgrade objects created before the view-provider layer existed.
        import FreeCAD as App
        from gensurf.ui.view_provider import ensure_view_providers
        ensure_view_providers(App.ActiveDocument)

    def GetClassName(self):
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(GenerativeSurfacesWorkbench())
