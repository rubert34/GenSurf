"""Document migrations: old names → current names, applied on restore.

Documents saved by earlier GenSurf versions must keep opening and
recomputing identically. Whenever a type, property or enumeration value
is renamed, or a property is added whose default would change the
geometry of an older document, the change is recorded here — never by
editing the old document format elsewhere.

Tables (all keyed by the *current* type identifier unless noted):

* ``LEGACY_PROXIES`` — proxy classes as stored in old documents:
  ``{old_module: {old_class: "new.module:NewClass"}}``. FreeCAD restores
  a Python proxy by importing ``module`` and reading ``class``; the
  parent packages install lightweight alias modules so those imports
  resolve to the current classes (see ``install_legacy_modules``).
* ``TYPE_RENAMES`` — ``{old GSType: new GSType}`` (chains are followed).
* ``PROPERTY_RENAMES`` — ``{type: {old property: new property}}``.
* ``ENUM_RENAMES`` — ``{type: {property: {old value: new value}}}``.
* ``LEGACY_DEFAULTS`` — ``{type: {property: value}}``: the value a
  *restored* object receives when the property did not exist yet, so the
  old document keeps its old behaviour (new objects use the declared
  default).
* ``CUSTOM_STEPS`` — ``{type: [fn(obj, old_type)]}`` for migrations that
  are more than a rename (e.g. merging two operators).

``migrate(obj)`` runs the renames and custom steps; ``GSFeature`` and
the set container call it from ``onDocumentRestored`` before adding any
missing properties.
"""

import sys
import types

# -- 0.29: GenSurf's own vocabulary --------------------------------------

LEGACY_PROXIES = {
    "gensurf.containers.geometrical_set": {
        "GeometricalSet": "gensurf.containers.construction_set:"
                          "ConstructionSet"},
    "gensurf.features.multisection": {
        "MultiSection": "gensurf.features.loft:Loft"},
    "gensurf.features.connect_curve": {
        "ConnectCurve": "gensurf.features.bridge_curve:BridgeCurve"},
    "gensurf.features.corner": {
        "Corner": "gensurf.features.curve_fillet:CurveFillet"},
    "gensurf.features.parallel_curve": {
        "ParallelCurve": "gensurf.features.offset_curve_on_surface:"
                         "OffsetCurveOnSurface"},
    "gensurf.features.curve_offset_3d": {
        "CurveOffset3D": "gensurf.features.offset_curve_3d:OffsetCurve3D"},
    "gensurf.features.shape_fillet": {
        "ShapeFillet": "gensurf.features.surface_fillet:SurfaceFillet"},
    "gensurf.features.multi_extract": {
        "MultiExtract": "gensurf.features.extract:Extract"},
    "gensurf.features.boundary": {
        "Boundary": "gensurf.features.boundary_curves:BoundaryCurves"},
    "gensurf.features.healing": {
        "Healing": "gensurf.features.heal:Heal"},
    "gensurf.features.close_surface": {
        "CloseSurface": "gensurf.features.make_solid:MakeSolid"},
}

TYPE_RENAMES = {
    "GenSurf::GeometricalSet": "GenSurf::ConstructionSet",
    "GenSurf::MultiSection": "GenSurf::Loft",
    "GenSurf::ConnectCurve": "GenSurf::BridgeCurve",
    "GenSurf::Corner": "GenSurf::CurveFillet",
    "GenSurf::ParallelCurve": "GenSurf::OffsetCurveOnSurface",
    "GenSurf::CurveOffset3D": "GenSurf::OffsetCurve3D",
    "GenSurf::ShapeFillet": "GenSurf::SurfaceFillet",
    "GenSurf::MultiExtract": "GenSurf::Extract",
    "GenSurf::Boundary": "GenSurf::BoundaryCurves",
    "GenSurf::Healing": "GenSurf::Heal",
    "GenSurf::CloseSurface": "GenSurf::MakeSolid",
}

_RAILS = {f"Guide{i}": f"Rail{i}" for i in range(1, 6)}

PROPERTY_RENAMES = {
    "GenSurf::Loft": {
        "Guides": "Rails",
        "GuideSupports": "RailSupports",
        "GuideSupportRows": "RailSupportRows",
        "GuideContinuities": "RailContinuities",
    },
    "GenSurf::SweepExplicit": dict(_RAILS, Subtype="Mode"),
    "GenSurf::SweepLine": dict(_RAILS, Subtype="Mode"),
    "GenSurf::SweepCircle": dict(_RAILS, Subtype="Mode"),
    "GenSurf::SweepConic": dict(_RAILS, Subtype="Mode",
                                Tangency1="TangentSurface1",
                                Tangency2="TangentSurface2"),
    "GenSurf::CurveFillet": {"CornerType": "FilletPlane"},
    "GenSurf::OffsetCurveOnSurface": {"Constant": "Distance",
                                      "ParallelMode": "DistanceMode"},
    "GenSurf::OffsetCurve3D": {"PullingDirection": "DirectionRef"},
}

_G = {"Position": "G0 Position", "Tangency": "G1 Tangent",
      "Tangent": "G1 Tangent", "Curvature": "G2 Curvature"}

ENUM_RENAMES = {
    "GenSurf::BlendSurface": {"Continuity1": _G, "Continuity2": _G},
    "GenSurf::BridgeCurve": {"Continuity1": _G, "Continuity2": _G},
    "GenSurf::CurveFillet": {"FilletPlane": {
        "Corner On Support": "Support plane",
        "3D Corner": "Curves' plane"}},
    "GenSurf::BoundaryCurves": {"Propagation": {
        "Point continuity": "Connected",
        "Complete boundary": "Whole boundary",
        "Tangent continuity": "Tangent",
        "No propagation": "None"}},
    "GenSurf::SweepExplicit": {"Mode": {
        "With reference surface": "1 rail",
        "With two guide curves": "2 rails",
        "With pulling direction": "Rail + direction"}},
    "GenSurf::SweepLine": {"Mode": {
        "Two limits": "Between rails",
        "Limit and middle": "Rail 2 as middle",
        "With reference surface": "Angle to surface",
        "With draft direction": "Draft from direction"}},
    "GenSurf::SweepCircle": {"Mode": {
        "Three guides": "Through 3 rails",
        "Two guides and radius": "2 rails + radius",
        "Center and radius": "Center rail + radius",
        "Center and two angles": "Center rail + angles"}},
    "GenSurf::SweepConic": {"Mode": {
        "Two guide curves": "Tangent to 2 surfaces",
        "Five guide curves": "Through 5 rails"}},
}

LEGACY_DEFAULTS = {
    # 0.25 added Borders with "Align to supports" as the default; blends
    # saved before then were built with natural side edges.
    "GenSurf::BlendSurface": {"Borders": "Natural"},
}


def _set_algo(obj, version):
    from gensurf.features.base import ALGO_PROPERTY
    if not hasattr(obj, ALGO_PROPERTY):
        obj.addProperty("App::PropertyInteger", ALGO_PROPERTY,
                        "GenerativeSurfaces",
                        "Version of the geometry algorithm this feature "
                        "uses")
        obj.setEditorMode(ALGO_PROPERTY, 2)
    setattr(obj, ALGO_PROPERTY, version)


def _extract_rows(obj, saved_type):
    """Single-pick extract (Element / Propagation / SmoothAngle) and the
    multi-pick extract became one operator with per-row lists."""
    if saved_type == "GenSurf::MultiExtract":
        _set_algo(obj, 2)  # edges as wires, as it always built them
        return
    if not hasattr(obj, "Element") or hasattr(obj, "Elements"):
        return
    link = obj.Element
    mode = {"No propagation": 0, "Point continuity": 1,
            "Tangent continuity": 2}.get(obj.Propagation, 0)
    threshold = obj.SmoothAngle.getValueAs("deg").Value
    obj.addProperty("App::PropertyLinkSubList", "Elements", "Extract", "")
    obj.addProperty("App::PropertyIntegerList", "Propagations", "Extract",
                    "")
    obj.addProperty("App::PropertyFloatList", "Thresholds", "Extract", "")
    if link:
        linked, subs = link
        obj.Elements = [(linked, list(subs) if subs else [""])]
    obj.Propagations = [mode]
    obj.Thresholds = [threshold]
    for name in ("Element", "Propagation", "SmoothAngle"):
        obj.removeProperty(name)


CUSTOM_STEPS = {
    "GenSurf::Extract": [_extract_rows],
}


# -- type identifiers ------------------------------------------------------


def current_type(type_id):
    """The current type identifier for a possibly old one."""
    seen = set()
    while type_id in TYPE_RENAMES and type_id not in seen:
        seen.add(type_id)
        type_id = TYPE_RENAMES[type_id]
    return type_id


def legacy_defaults(type_id):
    return LEGACY_DEFAULTS.get(type_id, {})


# -- legacy proxy modules --------------------------------------------------


def _resolve(target):
    module_name, class_name = target.split(":")
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)


def _alias_module(old_module, classes):
    mod = types.ModuleType(old_module)
    mod.__doc__ = "Alias of a renamed GenSurf module, for old documents."

    def __getattr__(name):
        if name in classes:
            return _resolve(classes[name])
        raise AttributeError(f"module {old_module!r} has no attribute "
                             f"{name!r}")

    mod.__getattr__ = __getattr__
    return mod


def install_legacy_modules(prefix=""):
    """Register alias modules for every old proxy module path starting
    with ``prefix``. Idempotent; never shadows a real module."""
    for old_module, classes in LEGACY_PROXIES.items():
        if not old_module.startswith(prefix) or old_module in sys.modules:
            continue
        sys.modules[old_module] = _alias_module(old_module, classes)


# -- object migration ------------------------------------------------------


def _rename_property(obj, old, new):
    """Move ``old`` to ``new`` (same type, group and documentation),
    carrying the value and any expression bound to it."""
    if not hasattr(obj, old) or hasattr(obj, new):
        return False
    ptype = obj.getTypeIdOfProperty(old)
    group = obj.getGroupOfProperty(old)
    doc = obj.getDocumentationOfProperty(old)
    expression = None
    for path, expr in list(getattr(obj, "ExpressionEngine", []) or []):
        if path == old:
            expression = expr
    obj.addProperty(ptype, new, group, doc)
    if ptype == "App::PropertyEnumeration":
        setattr(obj, new, list(obj.getEnumerationsOfProperty(old) or []))
    setattr(obj, new, getattr(obj, old))
    if expression is not None:
        obj.setExpression(old, None)
        obj.setExpression(new, expression)
    obj.setEditorMode(new, obj.getEditorMode(old))
    obj.removeProperty(old)
    return True


def _rename_enum_values(obj, prop, mapping):
    if not hasattr(obj, prop):
        return
    values = list(obj.getEnumerationsOfProperty(prop) or [])
    current = getattr(obj, prop)
    if not any(v in mapping for v in values):
        return
    setattr(obj, prop, [mapping.get(v, v) for v in values])
    setattr(obj, prop, mapping.get(current, current))


def migrate(obj, proxy=None):
    """Bring a restored object up to the current names. Returns the type
    identifier the object was saved with (useful to custom steps)."""
    saved_type = getattr(obj, "GSType", "") or \
        getattr(proxy, "Type", "") or ""
    new_type = current_type(saved_type)
    if hasattr(obj, "GSType") and obj.GSType != new_type:
        obj.GSType = new_type
    if proxy is not None:
        proxy.Type = new_type

    for old, new in PROPERTY_RENAMES.get(new_type, {}).items():
        _rename_property(obj, old, new)
    for prop, mapping in ENUM_RENAMES.get(new_type, {}).items():
        _rename_enum_values(obj, prop, mapping)
    for step in CUSTOM_STEPS.get(new_type, ()):
        step(obj, saved_type)
    return saved_type
