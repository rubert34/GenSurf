"""GUI command registration.

Commands are generated from the feature registry: each feature gets an
Activated() that creates the object in the active geometrical set and opens
its task panel (task panels arrive with the interactive-dialog milestone;
for now creation uses current selection directly where possible).
"""

import os

import FreeCAD as App
import FreeCADGui as Gui

import gensurf
from gensurf.containers import make_geometrical_set

ICON_DIR = os.path.join(gensurf.ADDON_DIR, "resources", "icons")


class _InsertGeometricalSet:
    def GetResources(self):
        return {
            "MenuText": "Geometrical Set",
            "ToolTip": "Insert a geometrical set and make it active",
            "Pixmap": os.path.join(ICON_DIR, "GenSurf_Set.svg"),
        }

    def IsActive(self):
        return App.ActiveDocument is not None

    def Activated(self):
        doc = App.ActiveDocument
        doc.openTransaction("Insert geometrical set")
        make_geometrical_set(doc)
        doc.commitTransaction()


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

        doc = App.ActiveDocument
        doc.openTransaction(self.menu_text)
        obj = factory(self.type_id)(doc)
        self._prefill_from_selection(obj)
        doc.commitTransaction()
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
    dialog changes apply without restarting FreeCAD. Feature *geometry*
    changes on already-open documents still need the document reopened."""

    def GetResources(self):
        return {
            "MenuText": "Reload workbench code",
            "ToolTip": "Hot-reload Generative Surfaces (dev)",
            "Pixmap": os.path.join(ICON_DIR, "GenSurf_Reload.svg"),
        }

    def IsActive(self):
        return True

    def Activated(self):
        import importlib
        import gensurf
        import gensurf.containers.geometrical_set
        import gensurf.features.registry
        import gensurf.features.base
        import gensurf.features.datum_plane
        import gensurf.features.projected_curve
        import gensurf.features.extruded_surface
        import gensurf.features.offset_surface
        import gensurf.features.blend_surface
        import gensurf.features.revolved_surface
        import gensurf.features.split
        import gensurf.features.trim
        import gensurf.features.translate
        import gensurf.features.rotate
        import gensurf.features.scale
        import gensurf.features.extend
        import gensurf.features.multisection
        import gensurf.features.fill
        import gensurf.features.connect_curve
        import gensurf.features.boundary
        import gensurf.features.extract
        import gensurf.features.multi_extract
        import gensurf.features.join
        import gensurf.features.point
        import gensurf.features.line
        import gensurf.features.intersection
        import gensurf.features.parallel_curve
        import gensurf.features.curve_offset_3d
        import gensurf.features.circle
        import gensurf.features.corner
        import gensurf.features.spline
        import gensurf.features.helix
        import gensurf.features.shape_fillet
        import gensurf.features.edge_fillet
        import gensurf.features.chamfer
        import gensurf.features.spine_curve
        import gensurf.features.symmetry
        import gensurf.features.sphere
        import gensurf.features.sweep_common
        import gensurf.features.sweep_explicit
        import gensurf.features.sweep_line
        import gensurf.features.sweep_circle
        import gensurf.features.sweep_conic
        import gensurf.features
        import gensurf.containers
        import gensurf.ui.view_provider
        import gensurf.ui.task_panels
        import gensurf.ui.mss_panel
        import gensurf.ui.multi_extract_panel
        import gensurf.ui.selection_manager

        ordered = [
            gensurf,
            gensurf.containers.geometrical_set,
            gensurf.containers,
            gensurf.features.registry,
            gensurf.features.base,
            gensurf.features.datum_plane,
            gensurf.features.projected_curve,
            gensurf.features.extruded_surface,
            gensurf.features.offset_surface,
            gensurf.features.blend_surface,
            gensurf.features.revolved_surface,
            gensurf.features.split,
            gensurf.features.trim,
            gensurf.features.translate,
            gensurf.features.rotate,
            gensurf.features.scale,
            gensurf.features.extend,
            gensurf.features.multisection,
            gensurf.features.fill,
            gensurf.features.connect_curve,
            gensurf.features.boundary,
            gensurf.features.extract,
            gensurf.features.multi_extract,
            gensurf.features.join,
            gensurf.features.point,
            gensurf.features.line,
            gensurf.features.intersection,
            gensurf.features.parallel_curve,
            gensurf.features.curve_offset_3d,
            gensurf.features.circle,
            gensurf.features.corner,
            gensurf.features.spline,
            gensurf.features.helix,
            gensurf.features.shape_fillet,
            gensurf.features.edge_fillet,
            gensurf.features.chamfer,
            gensurf.features.spine_curve,
            gensurf.features.symmetry,
            gensurf.features.sphere,
            gensurf.features.sweep_common,
            gensurf.features.sweep_explicit,
            gensurf.features.sweep_line,
            gensurf.features.sweep_circle,
            gensurf.features.sweep_conic,
            gensurf.features,
            gensurf.ui.view_provider,
            gensurf.ui.task_panels,
            gensurf.ui.mss_panel,
            gensurf.ui.multi_extract_panel,
            gensurf.ui.selection_manager,
        ]
        for mod in ordered:
            importlib.reload(mod)

        # re-register commands from the reloaded module
        import gensurf.ui.commands as cmds
        importlib.reload(cmds)
        cmds.register_all()
        App.Console.PrintMessage(
            "[GenSurf] workbench code reloaded. Reopen the document to "
            "refresh feature behavior on existing objects.\n")


_COMMANDS = {
    "GenSurf_Dev_Reload": _ReloadWorkbench(),
    "GenSurf_Set_Insert": _InsertGeometricalSet(),
    "GenSurf_WF_Plane": _FeatureCommand(
        "GenSurf::DatumPlane", "Plane",
        "Offset datum plane from a planar support", "GenSurf_Plane.svg"),
    "GenSurf_WF_Project": _FeatureCommand(
        "GenSurf::ProjectedCurve", "Projection",
        "Project a curve onto a support surface", "GenSurf_Project.svg"),
    "GenSurf_Surf_Extrude": _FeatureCommand(
        "GenSurf::ExtrudedSurface", "Extrude",
        "Extrude a profile into a surface", "GenSurf_Extrude.svg"),
    "GenSurf_Surf_Offset": _FeatureCommand(
        "GenSurf::OffsetSurface", "Offset",
        "Offset a surface along its normals", "GenSurf_Offset.svg"),
    "GenSurf_Surf_Blend": _FeatureCommand(
        "GenSurf::BlendSurface", "Blend",
        "Blend surface between two curves with continuity control",
        "GenSurf_Blend.svg"),
    "GenSurf_Surf_Revolve": _FeatureCommand(
        "GenSurf::RevolvedSurface", "Revolve",
        "Revolve a profile around an axis into a surface",
        "GenSurf_Revolve.svg"),
    "GenSurf_Op_Split": _FeatureCommand(
        "GenSurf::Split", "Split",
        "Split an element by a cutter, keeping one side",
        "GenSurf_Split.svg"),
    "GenSurf_Op_Trim": _FeatureCommand(
        "GenSurf::Trim", "Trim",
        "Mutually trim two elements into one",
        "GenSurf_Trim.svg"),
    "GenSurf_Op_Translate": _FeatureCommand(
        "GenSurf::Translate", "Translate",
        "Translated copy along a picked direction", "GenSurf_Translate.svg"),
    "GenSurf_Op_Rotate": _FeatureCommand(
        "GenSurf::Rotate", "Rotate",
        "Rotated copy around a picked axis", "GenSurf_Rotate.svg"),
    "GenSurf_Op_Scale": _FeatureCommand(
        "GenSurf::Scale", "Scale",
        "Scaled copy about a point, plane or line reference",
        "GenSurf_Scale.svg"),
    "GenSurf_Op_Extend": _FeatureCommand(
        "GenSurf::Extend", "Extend",
        "Naturally extrapolate a curve or surface past a picked extremity",
        "GenSurf_Extend.svg"),
    "GenSurf_Surf_MultiSection": _FeatureCommand(
        "GenSurf::MultiSection", "Multi-Sections",
        "Loft through ordered sections, optionally following guides",
        "GenSurf_MultiSection.svg"),
    "GenSurf_Surf_Fill": _FeatureCommand(
        "GenSurf::Fill", "Fill",
        "N-sided patch bounded by a closed loop of curves",
        "GenSurf_Fill.svg"),
    "GenSurf_WF_Connect": _FeatureCommand(
        "GenSurf::ConnectCurve", "Connect",
        "Blend curve between two curve ends with continuity control",
        "GenSurf_Connect.svg"),
    "GenSurf_Op_Boundary": _FeatureCommand(
        "GenSurf::Boundary", "Boundary",
        "Free boundary of a surface with propagation and limits",
        "GenSurf_Boundary.svg"),
    "GenSurf_Op_Extract": _FeatureCommand(
        "GenSurf::Extract", "Extract",
        "Extract a face or edge with propagation",
        "GenSurf_Extract.svg"),
    "GenSurf_Op_MultiExtract": _FeatureCommand(
        "GenSurf::MultiExtract", "Multiple Extract",
        "Extract several elements, each with its own propagation",
        "GenSurf_MultiExtract.svg"),
    "GenSurf_Op_Join": _FeatureCommand(
        "GenSurf::Join", "Join",
        "Assemble surfaces or curves into one element",
        "GenSurf_Join.svg"),
    "GenSurf_WF_Point": _FeatureCommand(
        "GenSurf::Point", "Point",
        "Point: coordinates, on curve/plane/surface, center, between",
        "GenSurf_Point.svg"),
    "GenSurf_WF_Line": _FeatureCommand(
        "GenSurf::Line", "Line",
        "Line: point-point, point-direction, tangent, surface normal",
        "GenSurf_Line.svg"),
    "GenSurf_WF_Intersect": _FeatureCommand(
        "GenSurf::Intersection", "Intersection",
        "Intersect two elements: points, curves or surface pieces",
        "GenSurf_Intersect.svg"),
    "GenSurf_WF_Parallel": _FeatureCommand(
        "GenSurf::ParallelCurve", "Parallel Curve",
        "Offset a curve on its support at a constant distance",
        "GenSurf_Parallel.svg"),
    "GenSurf_WF_CurveOffset": _FeatureCommand(
        "GenSurf::CurveOffset3D", "3D Curve Offset",
        "Offset a 3D curve perpendicular to a pulling direction",
        "GenSurf_CurveOffset.svg"),
    "GenSurf_WF_Circle": _FeatureCommand(
        "GenSurf::Circle", "Circle",
        "Circle or arc: center/radius, points, axis definitions",
        "GenSurf_Circle.svg"),
    "GenSurf_WF_Corner": _FeatureCommand(
        "GenSurf::Corner", "Corner",
        "Fillet arc between two curves, with optional trimming",
        "GenSurf_Corner.svg"),
    "GenSurf_WF_Spline": _FeatureCommand(
        "GenSurf::Spline", "Spline",
        "Spline through ordered points with optional tangents",
        "GenSurf_Spline.svg"),
    "GenSurf_WF_Helix": _FeatureCommand(
        "GenSurf::Helix", "Helix",
        "Helix around an axis from a starting point",
        "GenSurf_Helix.svg"),
    "GenSurf_WF_Spine": _FeatureCommand(
        "GenSurf::SpineCurve", "Spine",
        "Curve crossing ordered section planes orthogonally",
        "GenSurf_Spine.svg"),
    "GenSurf_Op_ShapeFillet": _FeatureCommand(
        "GenSurf::ShapeFillet", "Shape Fillet",
        "Rolling-ball fillet between two support surfaces",
        "GenSurf_ShapeFillet.svg"),
    "GenSurf_Op_EdgeFillet": _FeatureCommand(
        "GenSurf::EdgeFillet", "Edge Fillet",
        "Round edges of a surface at a constant radius",
        "GenSurf_EdgeFillet.svg"),
    "GenSurf_Op_Chamfer": _FeatureCommand(
        "GenSurf::Chamfer", "Chamfer",
        "Bevel edges of a surface",
        "GenSurf_Chamfer.svg"),
    "GenSurf_Op_Symmetry": _FeatureCommand(
        "GenSurf::Symmetry", "Symmetry",
        "Mirror an element about a point, line or plane",
        "GenSurf_Symmetry.svg"),
    "GenSurf_Surf_Sphere": _FeatureCommand(
        "GenSurf::Sphere", "Sphere",
        "Spherical surface with parallel/meridian angle limits",
        "GenSurf_Sphere.svg"),
    "GenSurf_Surf_SweepExplicit": _FeatureCommand(
        "GenSurf::SweepExplicit", "Sweep Explicit",
        "Sweep a profile along a guide (reference surface / two "
        "guides / pulling direction)",
        "GenSurf_SweepExplicit.svg"),
    "GenSurf_Surf_SweepLine": _FeatureCommand(
        "GenSurf::SweepLine", "Sweep Line",
        "Ruled sweep: two limits, limit and middle, reference "
        "surface, draft direction",
        "GenSurf_SweepLine.svg"),
    "GenSurf_Surf_SweepCircle": _FeatureCommand(
        "GenSurf::SweepCircle", "Sweep Circle",
        "Circular sweep: three guides, two guides and radius, "
        "center-based",
        "GenSurf_SweepCircle.svg"),
    "GenSurf_Surf_SweepConic": _FeatureCommand(
        "GenSurf::SweepConic", "Sweep Conic",
        "Conic sweep: two guides with tangency surfaces, five guides",
        "GenSurf_SweepConic.svg"),
}


class _CommandGroup:
    """CATIA-style fly-out button: one toolbar slot, a drop-down with
    the related commands (FreeCAD Python group-command protocol)."""

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


# CATIA GSD default fly-out structure, mapped onto our operators
_GROUPS = {
    "GenSurf_Grp_Projections": _CommandGroup(
        "Projections-Intersections",
        "Projection and Intersection",
        ["GenSurf_WF_Project", "GenSurf_WF_Intersect"]),
    "GenSurf_Grp_Circles": _CommandGroup(
        "Circle-Corner-Connect",
        "Circle, Corner and Connect Curve",
        ["GenSurf_WF_Circle", "GenSurf_WF_Corner", "GenSurf_WF_Connect"]),
    "GenSurf_Grp_Curves": _CommandGroup(
        "Curves",
        "Spline, Helix and Spine",
        ["GenSurf_WF_Spline", "GenSurf_WF_Helix", "GenSurf_WF_Spine"]),
    "GenSurf_Grp_CurveOffsets": _CommandGroup(
        "Curve Offsets",
        "Parallel Curve and 3D Curve Offset",
        ["GenSurf_WF_Parallel", "GenSurf_WF_CurveOffset"]),
    "GenSurf_Grp_ExtrudeRevolve": _CommandGroup(
        "Extrude-Revolution",
        "Extrude, Revolve and Sphere",
        ["GenSurf_Surf_Extrude", "GenSurf_Surf_Revolve",
         "GenSurf_Surf_Sphere"]),
    "GenSurf_Grp_Sweeps": _CommandGroup(
        "Sweeps",
        "Swept surface: explicit, line, circle, conic profiles",
        ["GenSurf_Surf_SweepExplicit", "GenSurf_Surf_SweepLine",
         "GenSurf_Surf_SweepCircle", "GenSurf_Surf_SweepConic"]),
    "GenSurf_Grp_SplitTrim": _CommandGroup(
        "Split-Trim",
        "Split and Trim",
        ["GenSurf_Op_Split", "GenSurf_Op_Trim"]),
    "GenSurf_Grp_Extracts": _CommandGroup(
        "Extracts",
        "Boundary, Extract and Multiple Extract",
        ["GenSurf_Op_Boundary", "GenSurf_Op_Extract",
         "GenSurf_Op_MultiExtract"]),
    "GenSurf_Grp_Fillets": _CommandGroup(
        "Fillets",
        "Shape Fillet, Edge Fillet and Chamfer",
        ["GenSurf_Op_ShapeFillet", "GenSurf_Op_EdgeFillet",
         "GenSurf_Op_Chamfer"]),
    "GenSurf_Grp_Transforms": _CommandGroup(
        "Transformations",
        "Translate, Rotate, Scale and Symmetry",
        ["GenSurf_Op_Translate", "GenSurf_Op_Rotate",
         "GenSurf_Op_Scale", "GenSurf_Op_Symmetry"]),
}

#: toolbar layout: fly-out groups + the remaining single buttons,
#: mirroring CATIA GSD's default toolbars
TOOLBARS = (
    ("GS Structure", ["GenSurf_Set_Insert"]),
    ("GS Wireframe", [
        "GenSurf_WF_Point", "GenSurf_WF_Line", "GenSurf_WF_Plane",
        "GenSurf_Grp_Projections", "GenSurf_Grp_Circles",
        "GenSurf_Grp_Curves", "GenSurf_Grp_CurveOffsets"]),
    ("GS Surfaces", [
        "GenSurf_Grp_ExtrudeRevolve", "GenSurf_Surf_Offset",
        "GenSurf_Grp_Sweeps", "GenSurf_Surf_Fill",
        "GenSurf_Surf_MultiSection", "GenSurf_Surf_Blend"]),
    ("GS Operations", [
        "GenSurf_Op_Join", "GenSurf_Grp_SplitTrim",
        "GenSurf_Grp_Extracts", "GenSurf_Grp_Fillets",
        "GenSurf_Grp_Transforms", "GenSurf_Op_Extend"]),
    ("GS Dev", ["GenSurf_Dev_Reload"]),
)

#: flat menu: every real command, grouped roughly by toolbar order
MENU = [n for n in _COMMANDS if n != "GenSurf_Dev_Reload"] + \
    ["GenSurf_Dev_Reload"]


def register_all():
    for name, cmd in _COMMANDS.items():
        Gui.addCommand(name, cmd)
    for name, grp in _GROUPS.items():
        Gui.addCommand(name, grp)
    return list(_COMMANDS) + list(_GROUPS)
