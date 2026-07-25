"""Feature framework: the canonical FeaturePython pattern for all GS features.

Every feature declares:
  * TYPE_ID    — "GenSurf::<Name>", persisted for headless reload dispatch
  * PROPERTIES — list of (ptype, name, group, doc, default) tuples
  * build(obj) — returns the Part.Shape for the current property values

The base class owns proxy wiring, property creation, execute() error
handling, and shape validity checking. Subclasses implement geometry only.
"""

import FreeCAD as App


class GSFeatureError(RuntimeError):
    """Raised by build() when inputs are missing or geometry fails."""


class GSFeature:
    TYPE_ID = "GenSurf::Feature"
    PROPERTIES = ()
    #: link properties that must be filled before the feature can build.
    #: While any are empty the feature idles with an empty shape (a feature
    #: freshly inserted from the GUI is incomplete, not broken).
    REQUIRED_LINKS = ()
    #: declarative input slots driving the task panel:
    #: (property_name, user_label, allowed subelement ShapeTypes or None)
    INPUT_SLOTS = ()

    #: enumeration property values: {property_name: (value0, value1, ...)};
    #: the first value is the default.
    ENUMS = {}

    def __init__(self, obj):
        obj.Proxy = self
        self.Type = self.TYPE_ID
        self.ensure_properties(obj)

    def ensure_properties(self, obj):
        """Create any missing declared properties (idempotent). Also runs
        on document restore so old objects gain newly added properties."""
        if not hasattr(obj, "GSType"):
            obj.addProperty(
                "App::PropertyString", "GSType", "GenerativeSurfaces",
                "Internal type identifier")
            obj.GSType = self.TYPE_ID
            obj.setEditorMode("GSType", 2)
        for ptype, name, group, doc, default in self.PROPERTIES:
            if not hasattr(obj, name):
                obj.addProperty(ptype, name, group, doc)
                if name in self.ENUMS:
                    setattr(obj, name, list(self.ENUMS[name]))
                    setattr(obj, name, self.ENUMS[name][0])
                elif default is not None:
                    setattr(obj, name, default)

    def onDocumentRestored(self, obj):
        self.ensure_properties(obj)

    # -- subclass API -----------------------------------------------------

    def build(self, obj):
        raise NotImplementedError

    # -- FreeCAD lifecycle ------------------------------------------------

    def execute(self, obj):
        missing = [n for n in self.REQUIRED_LINKS if not getattr(obj, n, None)]
        if missing:
            App.Console.PrintWarning(
                f"[GenSurf] {obj.Name}: waiting for input(s): "
                f"{', '.join(missing)}\n")
            return  # incomplete, not broken — keep an empty shape quietly

        was_empty = obj.Shape.isNull() if getattr(obj, "Shape", None) else True
        try:
            shape = self.build(obj)
        except GSFeatureError as err:
            App.Console.PrintError(f"[GenSurf] {obj.Name}: {err}\n")
            raise
        if shape is None:
            return  # feature idles (incomplete inputs signalled by build)
        if not shape.isValid():
            shape.fix(1e-7, 1e-7, 1e-7)
            if not shape.isValid():
                raise GSFeatureError(f"{obj.Name}: invalid shape produced")
        obj.Shape = shape
        # First successful build: make sure the result is actually shown,
        # even if the object was toggled invisible while it had no shape.
        if was_empty and App.GuiUp and obj.ViewObject:
            obj.ViewObject.Visibility = True

    def dumps(self):
        return {"Type": self.Type}

    def loads(self, state):
        if state:
            self.Type = state.get("Type", self.TYPE_ID)


# -- helpers shared by features ------------------------------------------


def plane_from_link(link):
    """(position, normal) if the link resolves to something planar:
    an App::Plane datum, a GenSurf datum plane, or a single planar face.
    Returns None otherwise."""
    import FreeCAD as App
    import Part
    if not link:
        return None
    linked, subs = link
    if getattr(linked, "TypeId", "") == "App::Plane":
        pl = linked.Placement
        return pl.Base, pl.Rotation.multVec(App.Vector(0, 0, 1))
    try:
        shape = resolve_linksub(link)
    except GSFeatureError:
        return None
    if shape.ShapeType != "Face":
        if len(shape.Faces) != 1:
            return None
        shape = shape.Faces[0]
    if isinstance(shape.Surface, Part.Plane):
        axis = App.Vector(shape.Surface.Axis)
        if shape.Orientation == "Reversed":
            axis = axis.negative()  # true outward normal of the face
        return shape.Surface.Position, axis
    return None


def axis_from_link(link):
    """(point_on_axis, direction) from a straight edge or App::Line datum."""
    import FreeCAD as App
    import Part
    linked, _subs = link
    if getattr(linked, "TypeId", "") == "App::Line":
        pl = linked.Placement
        return pl.Base, pl.Rotation.multVec(App.Vector(1, 0, 0))
    shape = resolve_linksub(link)
    if shape.ShapeType == "Wire" and len(shape.Edges) == 1:
        shape = shape.Edges[0]
    if shape.ShapeType != "Edge" or not isinstance(shape.Curve, Part.Line):
        raise GSFeatureError(
            "axis reference must be a straight edge or a datum axis")
    return shape.Vertexes[0].Point, App.Vector(shape.Curve.Direction)


def direction_from_ref(shape):
    """CATIA-style direction pick: a straight edge gives its direction, a
    planar face gives its normal."""
    import Part
    if shape.ShapeType == "Edge" and isinstance(shape.Curve, Part.Line):
        return shape.Curve.Direction
    if shape.ShapeType == "Face" and isinstance(shape.Surface, Part.Plane):
        return shape.Surface.Axis
    raise GSFeatureError(
        "direction reference must be a straight edge or a planar face "
        f"(got a {shape.ShapeType})")


def profile_plane_normal(wires):
    """Common plane normal of the profile wires, or None if not planar."""
    import Part
    all_edges = [e for w in wires for e in w.Edges]
    probe = Part.makeCompound(all_edges) if len(all_edges) > 1 else all_edges[0]
    finder = getattr(probe, "findPlane", None)
    plane = finder() if finder else None
    return plane.Axis if plane is not None else None


def curve_wires(shape):
    """Normalize any curve-bearing input to a list of wires.

    Accepts an Edge, a Wire, or anything containing edges (a Sketch shape
    is often a Wire or a Compound of edges). Disconnected edges are sorted
    into as many wires as needed.
    """
    import Part
    if shape.ShapeType == "Wire":
        return [shape]
    if shape.ShapeType == "Edge":
        return [Part.Wire([shape])]
    edges = shape.Edges
    if not edges:
        raise GSFeatureError(
            f"input of type {shape.ShapeType} contains no curves")
    sorter = getattr(Part, "sortEdges", None) or Part.__sortEdges__
    return [Part.Wire(group) for group in sorter(edges)]


def oriented_edge_walk(wire, per_edge):
    """Sample a wire edge-by-edge in TRAVEL order: yields one list of
    (point, unit_tangent) per edge, with reversed-orientation edges
    walked (and their tangents flipped) so the sequence always advances
    along the wire. Guards the classic trap: Part.Wire keeps each
    edge's own curve direction, which may oppose the travel."""
    import Part  # noqa: F401
    edges = list(getattr(wire, "OrderedEdges", None) or wire.Edges)
    out = []
    cur = None
    for k, edge in enumerate(edges):
        a = edge.valueAt(edge.FirstParameter)
        b = edge.valueAt(edge.LastParameter)
        if cur is None:
            if len(edges) > 1:
                nxt = edges[1]
                na = nxt.valueAt(nxt.FirstParameter)
                nb = nxt.valueAt(nxt.LastParameter)
                forward = min((b - na).Length, (b - nb).Length) <= \
                    min((a - na).Length, (a - nb).Length)
            else:
                forward = True
        else:
            forward = (a - cur).Length <= (b - cur).Length
        u0, u1 = edge.FirstParameter, edge.LastParameter
        samples = []
        for i in range(per_edge + 1):
            f = i / per_edge
            t = u0 + (u1 - u0) * (f if forward else 1.0 - f)
            p = App.Vector(edge.valueAt(t))
            tan = App.Vector(edge.tangentAt(t))
            if not forward:
                tan = tan.negative()
            samples.append((p, tan))
        out.append(samples)
        cur = b if forward else a
    return out


def resolve_linksub(link, expect=None):
    """Resolve an App::PropertyLinkSub to a concrete subshape (or whole shape).

    ``link`` is (documentObject, [subnames]). With no subnames, the object's
    whole shape is returned. ``expect`` optionally names a ShapeType to
    enforce ("Face", "Edge", "Wire", ...).
    """
    if not link:
        raise GSFeatureError("required input link is empty")
    obj, subs = link
    if getattr(obj, "Shape", None) is None:
        raise GSFeatureError(f"{obj.Name} carries no geometry")
    try:
        if not subs:
            shape = obj.Shape
        else:
            shape = obj.Shape.getElement(subs[0]) if len(subs) == 1 \
                else None
            if shape is None:
                import Part
                shape = Part.makeCompound(
                    [obj.Shape.getElement(s) for s in subs])
    except Exception:
        raise GSFeatureError(
            f"sub-element {subs} of {obj.Name} no longer exists — "
            "upstream geometry changed; re-pick the input")
    if expect and shape.ShapeType != expect:
        raise GSFeatureError(
            f"expected a {expect}, got {shape.ShapeType} from {obj.Name}")
    return shape


def resolve_linksublist(links, expect=None):
    """Resolve an App::PropertyLinkSubList to a list of shapes, one per
    (object, subelement) pick, in pick order."""
    shapes = []
    for entry in links or []:
        obj, subs = entry
        subs = subs if subs else ("",)
        for sub in subs:
            if sub:
                shape = obj.Shape.getElement(sub)
            else:
                shape = obj.Shape
            if expect and shape.ShapeType not in expect:
                raise GSFeatureError(
                    f"expected {' or '.join(expect)}, got "
                    f"{shape.ShapeType} from {obj.Name}")
            shapes.append(shape)
    return shapes


def make_feature(doc, proxy_cls, name, into_active=True):
    """Factory: create a FeaturePython object with the given proxy class,
    insert it into the active geometrical set, and return it (no recompute)."""
    from gensurf.containers import insert_into_active_set

    obj = doc.addObject("Part::FeaturePython", name)
    proxy_cls(obj)
    if App.GuiUp:
        from gensurf.ui.view_provider import GSViewProvider
        GSViewProvider(obj.ViewObject)
    if into_active:
        insert_into_active_set(obj)
    return obj
