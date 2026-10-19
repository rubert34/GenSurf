"""Feature framework: the canonical FeaturePython pattern for all GS features.

Every feature declares:
  * TYPE_ID    — "GenSurf::<Name>", persisted for headless reload dispatch
  * PROPERTIES — list of (ptype, name, group, doc, default) tuples
  * build(obj) — returns the Part.Shape for the current property values

The base class owns proxy wiring, property creation, execute() error
handling, and shape validity checking. Subclasses implement geometry only.

Algorithm versioning: every feature carries a hidden ``GenSurfAlgo``
integer. New objects get the class's ``ALGO_VERSION``; objects restored
from a document saved before the property existed get 1. When a
builder's mathematics changes, bump ``ALGO_VERSION`` and keep the old
code path for objects whose ``GenSurfAlgo`` is lower;
``upgrade_algorithm`` moves an object to the current version on request.

Restoring a document runs ``gensurf.migrations.migrate`` first (renamed
types, properties and enumeration values), then adds any property the
saved object lacks.
"""

import FreeCAD as App

from gensurf import migrations

ALGO_PROPERTY = "GenSurfAlgo"

#: continuity orders offered wherever a curve or surface meets another
CONTINUITY = ("G0 Position", "G1 Tangent", "G2 Curvature")


#: issue severities: Error = no geometry; Warning = geometry produced but
#: out of tolerance or with a constraint dropped; Info = for the record
ERROR, WARNING, INFO = "Error", "Warning", "Info"


class GenSurfError(RuntimeError):
    """A problem with a feature that the user can act on.

    ``GenSurfError(key, message, faulty_properties, sub_elements,
    severity)``:

    * key — a stable identifier ("input-missing", "rails-do-not-touch"…)
      for the UI and for tests; messages may be reworded, keys may not;
    * faulty_properties — names of the inputs or fields at fault, which
      the task panel can highlight;
    * sub_elements — ``(object name, sub-element name)`` pairs at fault,
      which can be highlighted in 3D;
    * severity — ERROR, WARNING or INFO.

    The one-argument form ``GenSurfError(message)`` (key "generic") keeps
    every ``GSFeatureError("...")`` call working. Raised from build(), an
    issue always means no geometry; non-fatal issues are passed to
    ``GSFeature.report`` instead.
    """

    def __init__(self, key, message=None, faulty_properties=(),
                 sub_elements=(), severity=ERROR):
        if message is None:
            key, message = "generic", key
        super().__init__(message)
        self.key = key
        self.message = message
        self.faulty_properties = tuple(faulty_properties)
        self.sub_elements = tuple(tuple(s) for s in sub_elements)
        self.severity = severity

    def __str__(self):
        return self.message

    def describe(self):
        """One line for the console and the task panel."""
        text = self.message
        if self.faulty_properties:
            text += f" [{', '.join(self.faulty_properties)}]"
        return text


#: former name, kept so existing code and scripts keep working
GSFeatureError = GenSurfError


class GSFeature:
    TYPE_ID = "GenSurf::Feature"
    #: version of this feature's geometry algorithm (see module docstring)
    ALGO_VERSION = 1
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

    def ensure_properties(self, obj, restored=False):
        """Create any missing declared properties (idempotent). Also runs
        on document restore so old objects gain newly added properties;
        there, a property that did not exist yet takes its legacy value
        (``migrations.LEGACY_DEFAULTS``) and existing properties pick up
        the current group, tooltip and enumeration values."""
        if not hasattr(obj, "GSType"):
            obj.addProperty(
                "App::PropertyString", "GSType", "GenerativeSurfaces",
                "Internal type identifier")
            obj.GSType = self.TYPE_ID
            obj.setEditorMode("GSType", 2)
        if not hasattr(obj, ALGO_PROPERTY):
            obj.addProperty(
                "App::PropertyInteger", ALGO_PROPERTY, "GenerativeSurfaces",
                "Version of the geometry algorithm this feature uses")
            setattr(obj, ALGO_PROPERTY, 1 if restored else self.ALGO_VERSION)
            obj.setEditorMode(ALGO_PROPERTY, 2)
        legacy = migrations.legacy_defaults(self.TYPE_ID) if restored else {}
        for ptype, name, group, doc, default in self.PROPERTIES:
            if not hasattr(obj, name):
                obj.addProperty(ptype, name, group, doc)
                if name in self.ENUMS:
                    setattr(obj, name, list(self.ENUMS[name]))
                    setattr(obj, name, legacy.get(name, self.ENUMS[name][0]))
                elif name in legacy:
                    setattr(obj, name, legacy[name])
                elif default is not None:
                    setattr(obj, name, default)
            elif restored:
                self._sync_property(obj, name, group, doc)

    def _sync_property(self, obj, name, group, doc):
        """Refresh the presentation of a restored property (group,
        tooltip, enumeration list) without touching its value."""
        set_group = getattr(obj, "setGroupOfProperty", None)
        if set_group and obj.getGroupOfProperty(name) != group:
            set_group(name, group)
        set_doc = getattr(obj, "setDocumentationOfProperty", None)
        if set_doc and obj.getDocumentationOfProperty(name) != doc:
            set_doc(name, doc)
        values = self.ENUMS.get(name)
        if values and list(obj.getEnumerationsOfProperty(name) or []) \
                != list(values):
            current = getattr(obj, name)
            setattr(obj, name, list(values))
            setattr(obj, name, current if current in values else values[0])

    def onDocumentRestored(self, obj):
        migrations.migrate(obj, self)
        self.ensure_properties(obj, restored=True)

    def upgrade_algorithm(self, obj):
        """Switch an object to the current algorithm version. Its
        geometry may change; the caller recomputes."""
        if getattr(obj, ALGO_PROPERTY, self.ALGO_VERSION) < self.ALGO_VERSION:
            setattr(obj, ALGO_PROPERTY, self.ALGO_VERSION)
            obj.touch()
            return True
        return False

    @staticmethod
    def algo_version(obj):
        """The algorithm version an object is built with."""
        return getattr(obj, ALGO_PROPERTY, 1)

    # -- subclass API -----------------------------------------------------

    def build(self, obj):
        raise NotImplementedError

    # -- FreeCAD lifecycle ------------------------------------------------

    def report(self, obj, issue):
        """Record a non-fatal issue (a GenSurfError with severity WARNING
        or INFO) while building; execute() reports it afterwards."""
        self._issue_list().append(issue)

    def issues(self):
        """Issues found by the last recompute, most serious first."""
        order = {ERROR: 0, WARNING: 1, INFO: 2}
        return sorted(self._issue_list(), key=lambda i: order[i.severity])

    def _issue_list(self):
        # proxies restored from a document skip __init__: create lazily
        if not hasattr(self, "_issues"):
            self._issues = []
        return self._issues

    @staticmethod
    def _print(obj, issue):
        line = f"[GenSurf] {obj.Name}: {issue.describe()}\n"
        if issue.severity == ERROR:
            App.Console.PrintError(line)
        elif issue.severity == WARNING:
            App.Console.PrintWarning(line)
        else:
            App.Console.PrintMessage(line)

    def execute(self, obj):
        self._issues = []
        missing = [n for n in self.REQUIRED_LINKS if not getattr(obj, n, None)]
        if missing:
            issue = GenSurfError(
                "input-missing",
                f"waiting for input(s): {', '.join(missing)}",
                faulty_properties=missing, severity=INFO)
            self._issues.append(issue)
            self._print(obj, issue)
            return  # incomplete, not broken — keep an empty shape quietly

        was_empty = obj.Shape.isNull() if getattr(obj, "Shape", None) else True
        try:
            shape = self.build(obj)
        except GenSurfError as err:
            err.severity = ERROR  # raised = no geometry
            self._issues.append(err)
            self._print(obj, err)
            raise
        for issue in list(self._issues):
            self._print(obj, issue)
        if shape is None:
            return  # feature idles (incomplete inputs signalled by build)
        if not shape.isValid():
            shape.fix(1e-7, 1e-7, 1e-7)
            if not shape.isValid():
                err = GenSurfError("invalid-shape",
                                   f"{obj.Name}: invalid shape produced")
                self._issues.append(err)
                raise err
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
    """Direction from a picked reference: a straight edge gives its
    direction, a planar face gives its normal."""
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
    def _one(sub):
        """Resolve one subname: Part.getShape follows App::Link chains
        and container placements (TNP-safer); getElement is the
        fallback."""
        import Part
        try:
            s = Part.getShape(obj, sub, needSubElement=True)
            if s is not None and not s.isNull():
                return s
        except Exception:
            pass
        return obj.Shape.getElement(sub)

    try:
        if not subs:
            shape = obj.Shape
        else:
            shape = _one(subs[0]) if len(subs) == 1 else None
            if shape is None:
                import Part
                shape = Part.makeCompound([_one(s) for s in subs])
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
    insert it into the active construction set, and return it (no recompute)."""
    from gensurf.containers import insert_into_active_set

    obj = doc.addObject("Part::FeaturePython", name)
    proxy_cls(obj)
    if App.GuiUp:
        from gensurf.ui.view_provider import GSViewProvider
        GSViewProvider(obj.ViewObject)
    if into_active:
        insert_into_active_set(obj)
    return obj
