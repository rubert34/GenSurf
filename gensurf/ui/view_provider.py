"""Generic view provider for all GS features.

Owns the tree icon and the double-click behavior (open the feature's task
panel instead of FreeCAD's default Transform dragger).
"""

import os

import FreeCAD as App
import FreeCADGui as Gui

import gensurf

ICON_DIR = os.path.join(gensurf.ADDON_DIR, "resources", "icons")

_ICON_BY_TYPE = {
    "GenSurf::DatumPlane": "GenSurf_Plane.svg",
    "GenSurf::ProjectedCurve": "GenSurf_Project.svg",
    "GenSurf::ExtrudedSurface": "GenSurf_Extrude.svg",
    "GenSurf::OffsetSurface": "GenSurf_Offset.svg",
    "GenSurf::BlendSurface": "GenSurf_Blend.svg",
    "GenSurf::RevolvedSurface": "GenSurf_Revolve.svg",
    "GenSurf::Split": "GenSurf_Split.svg",
    "GenSurf::Trim": "GenSurf_Trim.svg",
    "GenSurf::Translate": "GenSurf_Translate.svg",
    "GenSurf::Rotate": "GenSurf_Rotate.svg",
    "GenSurf::Scale": "GenSurf_Scale.svg",
    "GenSurf::Extend": "GenSurf_Extend.svg",
    "GenSurf::MultiSection": "GenSurf_MultiSection.svg",
    "GenSurf::Fill": "GenSurf_Fill.svg",
    "GenSurf::ConnectCurve": "GenSurf_Connect.svg",
    "GenSurf::Boundary": "GenSurf_Boundary.svg",
    "GenSurf::Extract": "GenSurf_Extract.svg",
    "GenSurf::MultiExtract": "GenSurf_MultiExtract.svg",
    "GenSurf::Join": "GenSurf_Join.svg",
    "GenSurf::Point": "GenSurf_Point.svg",
    "GenSurf::Line": "GenSurf_Line.svg",
    "GenSurf::Intersection": "GenSurf_Intersect.svg",
    "GenSurf::ParallelCurve": "GenSurf_Parallel.svg",
    "GenSurf::CurveOffset3D": "GenSurf_CurveOffset.svg",
    "GenSurf::Circle": "GenSurf_Circle.svg",
    "GenSurf::Corner": "GenSurf_Corner.svg",
    "GenSurf::Spline": "GenSurf_Spline.svg",
    "GenSurf::Helix": "GenSurf_Helix.svg",
    "GenSurf::ShapeFillet": "GenSurf_ShapeFillet.svg",
    "GenSurf::EdgeFillet": "GenSurf_EdgeFillet.svg",
    "GenSurf::Chamfer": "GenSurf_Chamfer.svg",
    "GenSurf::SpineCurve": "GenSurf_Spine.svg",
    "GenSurf::Symmetry": "GenSurf_Symmetry.svg",
    "GenSurf::Sphere": "GenSurf_Sphere.svg",
    "GenSurf::SweepExplicit": "GenSurf_SweepExplicit.svg",
    "GenSurf::SweepLine": "GenSurf_SweepLine.svg",
    "GenSurf::SweepCircle": "GenSurf_SweepCircle.svg",
    "GenSurf::SweepConic": "GenSurf_SweepConic.svg",
    "GenSurf::CloseSurface": "GenSurf_CloseSurface.svg",
}


class GSViewProvider:
    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.vobj = vobj

    def getIcon(self):
        gstype = getattr(self.vobj.Object, "GSType", "")
        icon = _ICON_BY_TYPE.get(gstype)
        return os.path.join(ICON_DIR, icon) if icon else None

    def doubleClicked(self, vobj):
        open_feature_dialog(vobj.Object, created=False)
        return True  # swallow the default Transform action

    def claimChildren(self):
        return []

    def dumps(self):
        return None

    def loads(self, state):
        return None


def open_feature_dialog(obj, created=False):
    """Show the task panel for a GS feature (if it declares input slots)."""
    if Gui.Control.activeDialog():
        App.Console.PrintWarning(
            "[GenSurf] close the active task dialog first\n")
        return
    custom = getattr(obj.Proxy, "CUSTOM_PANEL", None)
    if custom == "multisection":
        from gensurf.ui.mss_panel import MultiSectionTaskPanel
        Gui.Control.showDialog(MultiSectionTaskPanel(obj, created=created))
        return
    if custom == "multiextract":
        from gensurf.ui.multi_extract_panel import MultiExtractTaskPanel
        Gui.Control.showDialog(MultiExtractTaskPanel(obj, created=created))
        return
    from gensurf.ui.task_panels import FeatureTaskPanel
    Gui.Control.showDialog(FeatureTaskPanel(obj, created=created))


def ensure_view_providers(doc):
    """Attach GSViewProvider to GS features that lack one (e.g. objects
    created before the view-provider layer existed)."""
    if not App.GuiUp or doc is None:
        return
    for obj in doc.Objects:
        gstype = getattr(obj, "GSType", "")
        if gstype.startswith("GenSurf::") and gstype in _ICON_BY_TYPE:
            vo = getattr(obj, "ViewObject", None)
            if vo is not None and getattr(vo, "Proxy", None) is None:
                GSViewProvider(vo)
