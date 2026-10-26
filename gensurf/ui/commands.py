"""GUI command registration.

Every operator gets a command (created from the feature registry by type
identifier): Activated() creates the object in the active construction
set, seeds its inputs from the current selection and opens its task
panel. Toolbars and fly-out groups are organised by task: Sets, Curves,
Surfaces, Edit and Inspect.
"""

import os

import FreeCAD as App
import FreeCADGui as Gui

import gensurf
from gensurf.containers import make_construction_set, is_set

ICON_DIR = os.path.join(gensurf.ADDON_DIR, "resources", "icons")


def _icon(command_name):
    return os.path.join(ICON_DIR, f"{command_name}.svg")


class _InsertConstructionSet:
    def GetResources(self):
        return {
            "MenuText": "Construction Set",
            "ToolTip": "Insert a construction set and make it active",
            "Pixmap": _icon("GenSurf_ConstructionSet"),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        doc = App.ActiveDocument
        doc.openTransaction("Insert construction set")
        make_construction_set(doc)
        doc.commitTransaction()


class _SetActive:
    def GetResources(self):
        return {
            "MenuText": "Set Active / Inactive",
            "ToolTip": "Make the selected construction set active (new "
                       "features go into it), or inactive if it already "
                       "is (new features go to the top level)",
            "Pixmap": _icon("GenSurf_SetActive"),
        }

    @staticmethod
    def _selected_set():
        sel = Gui.Selection.getSelection()
        return sel[0] if len(sel) == 1 and is_set(sel[0]) else None

    def IsActive(self):
        return self._selected_set() is not None

    def Activated(self):
        from gensurf.ui.view_provider import toggle_active_set
        target = self._selected_set()
        if target is not None:
            toggle_active_set(target)


class _FeatureCommand:
    def __init__(self, type_id, menu_text, tooltip, icon):
        self.type_id = type_id
        self.menu_text = menu_text
        self.tooltip = tooltip
        self.icon = icon

    def GetResources(self):
        return {
            "MenuText": self.menu_text,
            "ToolTip": self.tooltip,
            "Pixmap": os.path.join(ICON_DIR, self.icon),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        from gensurf.features import factory
        from gensurf.ui.view_provider import open_feature_dialog

        if Gui.Control.activeDialog():
            App.Console.PrintWarning(
                "[GenSurf] close the active task dialog first\n")
            return
        doc = App.ActiveDocument
        # the dialog owns this transaction: OK commits, Cancel aborts
        # (which removes the freshly created feature in one step)
        doc.openTransaction(self.menu_text)
        obj = factory(self.type_id)(doc)
        self._prefill_from_selection(obj)
        doc.recompute()
        open_feature_dialog(obj, created=True)

    @staticmethod
    def _prefill_from_selection(obj):
        """Seed input slots from whatever was selected before the command.
        A multi slot consumes all remaining matching picks in order."""
        slots = [(s[0], s[2], s[4] if len(s) > 4 else False)
                 for s in getattr(obj.Proxy, "INPUT_SLOTS", ())]
        if not slots:
            return
        picks = []
        for sel in Gui.Selection.getSelectionEx():
            if sel.Object is obj:
                continue
            subs = sel.SubElementNames or ("",)
            for sub in subs:
                picks.append((sel.Object, sub))

        def matches(expect, picked, sub):
            if not (sub and expect):
                return True
            return picked.Shape.getElement(sub).ShapeType in expect

        i = 0
        for prop, expect, multiple in slots:
            if i >= len(picks):
                break
            if multiple:
                taken = [(p, [s] if s else [""])
                         for p, s in picks[i:] if matches(expect, p, s)]
                if taken:
                    setattr(obj, prop, taken)
                i = len(picks)
            else:
                picked, sub = picks[i]
                if matches(expect, picked, sub):
                    setattr(obj, prop, (picked, [sub] if sub else []))
                i += 1


class _ReloadWorkbench:
    """Developer hot-reload: re-imports all gensurf modules so command and
    panel changes apply without restarting FreeCAD. Feature *geometry*
    changes on already-open documents still need the document reopened."""

    #: reload order: dependencies first
    MODULES = (
        "gensurf",
        "gensurf.migrations",
        "gensurf.containers.construction_set",
        "gensurf.containers",
        "gensurf.features.registry",
        "gensurf.features.base",
        "gensurf.features.datum_plane",
        "gensurf.features.projected_curve",
        "gensurf.features.extruded_surface",
        "gensurf.features.offset_surface",
        "gensurf.features.blend_surface",
        "gensurf.features.revolved_surface",
        "gensurf.features.split",
        "gensurf.features.trim",
        "gensurf.features.translate",
        "gensurf.features.rotate",
        "gensurf.features.scale",
        "gensurf.features.extend",
        "gensurf.features.loft",
        "gensurf.features.fill",
        "gensurf.features.bridge_curve",
        "gensurf.features.boundary_curves",
        "gensurf.features.extract",
        "gensurf.features.join",
        "gensurf.features.point",
        "gensurf.features.line",
        "gensurf.features.intersection",
        "gensurf.features.offset_curve_on_surface",
        "gensurf.features.offset_curve_3d",
        "gensurf.features.circle",
        "gensurf.features.curve_fillet",
        "gensurf.features.spline",
        "gensurf.features.helix",
        "gensurf.features.surface_fillet",
        "gensurf.features.edge_fillet",
        "gensurf.features.chamfer",
        "gensurf.features.spine_curve",
        "gensurf.features.symmetry",
        "gensurf.features.sphere",
        "gensurf.features.sweep_common",
        "gensurf.features.sweep_explicit",
        "gensurf.features.sweep_line",
        "gensurf.features.sweep_circle",
        "gensurf.features.sweep_conic",
        "gensurf.features.make_solid",
        "gensurf.features.heal",
        "gensurf.features.curvature_comb",
        "gensurf.features",
        "gensurf.ui.view_provider",
        "gensurf.ui.task_panels",
        "gensurf.ui.loft_panel",
        "gensurf.ui.extract_panel",
        "gensurf.ui.selection_manager",
    )

    def GetResources(self):
        return {
            "MenuText": "Reload workbench code",
            "ToolTip": "Hot-reload GenSurf (development)",
            "Pixmap": _icon("GenSurf_DevReload"),
        }

    def IsActive(self):
        return True

    def Activated(self):
        import importlib
        for name in self.MODULES:
            importlib.reload(importlib.import_module(name))

        # re-register commands from the reloaded module
        import gensurf.ui.commands as cmds
        importlib.reload(cmds)
        cmds.register_all()
        App.Console.PrintMessage(
            "[GenSurf] workbench code reloaded. Reopen the document to "
            "refresh feature behavior on existing objects.\n")


#: (command name, type identifier, menu text, tooltip); the icon is
#: resources/icons/<command name>.svg
_FEATURES = (
    # -- curves
    ("GenSurf_Point", "GenSurf::Point", "Point",
     "Point: coordinates, on curve/plane/surface, center, between"),
    ("GenSurf_Line", "GenSurf::Line", "Line",
     "Line: point-point, point-direction, tangent, surface normal"),
    ("GenSurf_Plane", "GenSurf::DatumPlane", "Plane",
     "Offset datum plane from a planar support"),
    ("GenSurf_Circle", "GenSurf::Circle", "Circle",
     "Circle or arc: center/radius, points, axis definitions"),
    ("GenSurf_Spline", "GenSurf::Spline", "Spline",
     "Spline through ordered points with optional tangents"),
    ("GenSurf_Helix", "GenSurf::Helix", "Helix",
     "Helix around an axis from a starting point"),
    ("GenSurf_Spine", "GenSurf::SpineCurve", "Spine",
     "Curve crossing ordered section planes at right angles"),
    ("GenSurf_CurveFillet", "GenSurf::CurveFillet", "Curve Fillet",
     "Fillet arc between two curves, with optional trimming"),
    ("GenSurf_BridgeCurve", "GenSurf::BridgeCurve", "Bridge Curve",
     "Curve joining two curve ends with G0/G1/G2 continuity and tension"),
    ("GenSurf_OffsetCurveOnSurface", "GenSurf::OffsetCurveOnSurface",
     "Offset Curve on Surface",
     "Offset a curve on its support at a constant distance"),
    ("GenSurf_OffsetCurve3D", "GenSurf::OffsetCurve3D", "Offset Curve 3D",
     "Offset a 3D curve perpendicular to a direction"),
    ("GenSurf_Extract", "GenSurf::Extract", "Extract",
     "Extract faces or edges, each with its own propagation"),
    ("GenSurf_BoundaryCurves", "GenSurf::BoundaryCurves", "Boundary Curves",
     "Free boundary of a surface, with propagation and limits"),
    ("GenSurf_Intersection", "GenSurf::Intersection", "Intersection",
     "Intersect two elements: points, curves or surface pieces"),
    ("GenSurf_Projection", "GenSurf::ProjectedCurve", "Projection",
     "Project a curve onto a support surface"),
    # -- surfaces
    ("GenSurf_Extrude", "GenSurf::ExtrudedSurface", "Extrude",
     "Extrude a profile into a surface"),
    ("GenSurf_Revolve", "GenSurf::RevolvedSurface", "Revolve",
     "Revolve a profile around an axis into a surface"),
    ("GenSurf_Sphere", "GenSurf::Sphere", "Sphere",
     "Spherical surface, whole or bounded by latitude/longitude angles"),
    ("GenSurf_Offset", "GenSurf::OffsetSurface", "Offset Surface",
     "Offset a surface along its normals"),
    ("GenSurf_SweepCurve", "GenSurf::SweepExplicit", "Sweep Curve",
     "Sweep a profile curve along one or two rails, or a rail and a "
     "direction"),
    ("GenSurf_SweepRuled", "GenSurf::SweepLine", "Sweep Ruled",
     "Ruled sweep: between rails, about a middle rail, at an angle to a "
     "surface, or drafted from a direction"),
    ("GenSurf_SweepArc", "GenSurf::SweepCircle", "Sweep Arc",
     "Circular sweep: through three rails, two rails and a radius, or "
     "around a center rail"),
    ("GenSurf_SweepConic", "GenSurf::SweepConic", "Sweep Conic",
     "Conic sweep: tangent to two surfaces, or through five rails"),
    ("GenSurf_Loft", "GenSurf::Loft", "Loft",
     "Surface through ordered sections, optionally following rails"),
    ("GenSurf_Fill", "GenSurf::Fill", "Fill",
     "N-sided patch bounded by a closed loop of curves"),
    ("GenSurf_Blend", "GenSurf::BlendSurface", "Blend",
     "Surface between two curves with G0/G1/G2 continuity"),
    # -- edit
    ("GenSurf_Split", "GenSurf::Split", "Split",
     "Split an element by a cutter, keeping one side"),
    ("GenSurf_Trim", "GenSurf::Trim", "Trim",
     "Mutually trim two elements into one"),
    ("GenSurf_Join", "GenSurf::Join", "Join",
     "Assemble surfaces or curves into one element"),
    ("GenSurf_MakeSolid", "GenSurf::MakeSolid", "Make Solid",
     "Turn a closed set of surfaces into a solid"),
    ("GenSurf_SurfaceFillet", "GenSurf::SurfaceFillet", "Surface Fillet",
     "Rolling-ball fillet between two support surfaces"),
    ("GenSurf_EdgeFillet", "GenSurf::EdgeFillet", "Edge Fillet",
     "Round edges of a surface at a constant radius"),
    ("GenSurf_Chamfer", "GenSurf::Chamfer", "Chamfer",
     "Bevel edges of a surface"),
    ("GenSurf_Extend", "GenSurf::Extend", "Extend",
     "Naturally extrapolate a curve or surface past a picked extremity"),
    ("GenSurf_Translate", "GenSurf::Translate", "Translate",
     "Translated copy along a picked direction"),
    ("GenSurf_Rotate", "GenSurf::Rotate", "Rotate",
     "Rotated copy around a picked axis"),
    ("GenSurf_Scale", "GenSurf::Scale", "Scale",
     "Scaled copy about a point, plane or line reference"),
    ("GenSurf_Symmetry", "GenSurf::Symmetry", "Symmetry",
     "Mirror an element about a point, line or plane"),
    ("GenSurf_Heal", "GenSurf::Heal", "Heal",
     "Repair surfaces: geometry fixes, small edges, simplification"),
    # -- inspect
    ("GenSurf_CurvatureComb", "GenSurf::CurvatureComb", "Curvature Comb",
     "Curvature comb (porcupine) analysis of a curve"),
)

_COMMANDS = {
    "GenSurf_ConstructionSet": _InsertConstructionSet(),
    "GenSurf_SetActive": _SetActive(),
}
_COMMANDS.update({
    name: _FeatureCommand(type_id, text, tip, f"{name}.svg")
    for name, type_id, text, tip in _FEATURES})
_COMMANDS["GenSurf_DevReload"] = _ReloadWorkbench()


class _CommandGroup:
    """Fly-out button: one toolbar slot, a drop-down with the related
    commands (FreeCAD Python group-command protocol)."""

    def __init__(self, menu_text, tooltip, commands):
        self.menu_text = menu_text
        self.tooltip = tooltip
        self.commands = tuple(commands)

    def GetCommands(self):
        return self.commands

    def GetDefaultCommand(self):
        return 0

    def GetResources(self):
        return {"MenuText": self.menu_text, "ToolTip": self.tooltip}

    def IsActive(self):
        return App.ActiveDocument is not None


# fly-out groups, by what the user wants to do
_GROUPS = {
    "GenSurf_Group_CurveShapes": _CommandGroup(
        "Curve shapes", "Circle, Spline, Helix and Spine",
        ["GenSurf_Circle", "GenSurf_Spline", "GenSurf_Helix",
         "GenSurf_Spine"]),
    "GenSurf_Group_CurveFilletBridge": _CommandGroup(
        "Curve fillet & bridge", "Curve Fillet and Bridge Curve",
        ["GenSurf_CurveFillet", "GenSurf_BridgeCurve"]),
    "GenSurf_Group_OffsetCurves": _CommandGroup(
        "Offset curves", "Offset Curve on Surface and Offset Curve 3D",
        ["GenSurf_OffsetCurveOnSurface", "GenSurf_OffsetCurve3D"]),
    "GenSurf_Group_DeriveCurves": _CommandGroup(
        "Derive curves",
        "Extract, Boundary Curves, Intersection and Projection",
        ["GenSurf_Extract", "GenSurf_BoundaryCurves",
         "GenSurf_Intersection", "GenSurf_Projection"]),
    "GenSurf_Group_BasicSurfaces": _CommandGroup(
        "Basic surfaces", "Extrude, Revolve, Sphere and Offset Surface",
        ["GenSurf_Extrude", "GenSurf_Revolve", "GenSurf_Sphere",
         "GenSurf_Offset"]),
    "GenSurf_Group_SurfacesFromCurves": _CommandGroup(
        "Surfaces from curves", "Sweeps, Loft, Fill and Blend",
        ["GenSurf_SweepCurve", "GenSurf_SweepRuled", "GenSurf_SweepArc",
         "GenSurf_SweepConic", "GenSurf_Loft", "GenSurf_Fill",
         "GenSurf_Blend"]),
    "GenSurf_Group_CutCombine": _CommandGroup(
        "Cut & combine", "Split, Trim, Join and Make Solid",
        ["GenSurf_Split", "GenSurf_Trim", "GenSurf_Join",
         "GenSurf_MakeSolid"]),
    "GenSurf_Group_EdgesFillets": _CommandGroup(
        "Edges & fillets", "Surface Fillet, Edge Fillet and Chamfer",
        ["GenSurf_SurfaceFillet", "GenSurf_EdgeFillet",
         "GenSurf_Chamfer"]),
    "GenSurf_Group_Transform": _CommandGroup(
        "Transform", "Translate, Rotate, Scale and Symmetry",
        ["GenSurf_Translate", "GenSurf_Rotate", "GenSurf_Scale",
         "GenSurf_Symmetry"]),
}

#: toolbar layout: fly-out groups + single buttons, by task
TOOLBARS = (
    ("Sets", ["GenSurf_ConstructionSet", "GenSurf_SetActive"]),
    ("Curves", [
        "GenSurf_Point", "GenSurf_Line", "GenSurf_Plane",
        "GenSurf_Group_CurveShapes", "GenSurf_Group_CurveFilletBridge",
        "GenSurf_Group_OffsetCurves", "GenSurf_Group_DeriveCurves"]),
    ("Surfaces", [
        "GenSurf_Group_BasicSurfaces",
        "GenSurf_Group_SurfacesFromCurves"]),
    ("Edit", [
        "GenSurf_Group_CutCombine", "GenSurf_Group_EdgesFillets",
        "GenSurf_Extend", "GenSurf_Group_Transform", "GenSurf_Heal"]),
    ("Inspect", ["GenSurf_CurvatureComb"]),
    ("GenSurf development", ["GenSurf_DevReload"]),
)


def _expand(items):
    out = []
    for name in items:
        group = _GROUPS.get(name)
        out.extend(group.GetCommands() if group else [name])
    return out


#: menu layout: one submenu per toolbar, groups expanded
MENUS = tuple((title, _expand(items)) for title, items in TOOLBARS)


def register_all():
    for name, cmd in _COMMANDS.items():
        Gui.addCommand(name, cmd)
    for name, grp in _GROUPS.items():
        Gui.addCommand(name, grp)
    return list(_COMMANDS) + list(_GROUPS)
