"""Corner — GSD 'Corner' feature: a fillet arc of given radius between
two curves, optionally trimming the inputs to the tangency points.

OCC entry point: Part.ChFi2d.FilletAPI (planar fillet solver). The
corner plane is the support (Corner On Support, planar supports only)
or, for '3D Corner', the common plane of the two curves — truly
non-coplanar curves are rejected. A corner between two curves can have
several solutions (one per side pairing); Solution cycles through them
(CATIA's Next Solution).
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   plane_from_link, make_feature)
from .registry import register


def _single_edge(shape, other, what):
    """One edge from a curve pick; for multi-edge wires, the edge nearest
    to the other element."""
    edges = shape.Edges
    if not edges:
        raise GSFeatureError(f"{what} contains no curve")
    if len(edges) == 1:
        return edges[0]
    return min(edges, key=lambda e: e.distToShape(other)[0])


class Corner(GSFeature):
    TYPE_ID = "GenSurf::Corner"
    REQUIRED_LINKS = ("Element1", "Element2")
    INPUT_SLOTS = (
        ("Element1", "First curve", ("Edge", "Wire"), False),
        ("Element2", "Second curve", ("Edge", "Wire"), False),
        ("Support", "Support plane (blank: curves' common plane)",
         ("Face",), True),
    )
    ENUMS = {
        "CornerType": ("Corner On Support", "3D Corner"),
    }
    PROPERTIES = (
        ("App::PropertyEnumeration", "CornerType", "Corner",
         "Corner plane: support plane, or the curves' own plane", None),
        ("App::PropertyLinkSub", "Element1", "Corner",
         "First curve", None),
        ("App::PropertyLinkSub", "Element2", "Corner",
         "Second curve", None),
        ("App::PropertyLinkSub", "Support", "Corner",
         "Planar support (Corner On Support)", None),
        ("App::PropertyDistance", "Radius", "Corner",
         "Corner radius", "1 mm"),
        ("App::PropertyBool", "TrimElement1", "Corner",
         "Trim the first curve to the corner", False),
        ("App::PropertyBool", "TrimElement2", "Corner",
         "Trim the second curve to the corner", False),
        ("App::PropertyInteger", "Solution", "Corner",
         "Cycles through the possible corners (Next Solution)", 0),
    )

    def _plane(self, obj, e1, e2):
        if obj.CornerType == "Corner On Support" and obj.Support:
            planar = plane_from_link(obj.Support)
            if planar is None:
                raise GSFeatureError(
                    "corners on curved supports are not supported yet — "
                    "the support must be planar")
            return Part.Plane(planar[0], planar[1])
        plane = Part.makeCompound([e1, e2]).findPlane()
        if plane is None:
            raise GSFeatureError(
                "the two curves are not coplanar — give a planar support "
                "or use coplanar curves")
        return Part.Plane(plane.Position, plane.Axis)

    @staticmethod
    def _solutions(e1, e2, plane, radius):
        """Distinct (arc, trim1, trim2) solutions, stably ordered."""
        dist, pairs, _info = e1.distToShape(e2)
        near = (pairs[0][0] + pairs[0][1]) * 0.5
        n = plane.Axis
        u = n.cross(App.Vector(0, 0, 1))
        if u.Length < 1e-9:
            u = n.cross(App.Vector(0, 1, 0))
        u.normalize()
        v = n.cross(u)
        r = max(radius * 2.0, dist + radius, 1e-3)

        found = []
        for du, dv in ((1, 1), (1, -1), (-1, 1), (-1, -1), (0, 0)):
            api = Part.ChFi2d.FilletAPI()
            api.init(e1.copy(), e2.copy(), plane)
            try:
                if not api.perform(radius):
                    continue
                res = api.result(near + u * (r * du) + v * (r * dv))
            except (Part.OCCError, TypeError):
                continue
            if not (isinstance(res, (tuple, list)) and len(res) == 3):
                continue
            arc = res[0]
            if arc is None or arc.isNull() or not arc.Edges:
                continue
            center = arc.Edges[0].Curve.Center \
                if hasattr(arc.Edges[0].Curve, "Center") else \
                arc.Edges[0].CenterOfMass
            if all((center - c).Length > 1e-6 for _res, c in found):
                found.append((res, center))
        return [res for res, _c in found]

    def build(self, obj):
        s1 = resolve_linksub(obj.Element1)
        s2 = resolve_linksub(obj.Element2)
        e1 = _single_edge(s1, s2, "element 1")
        e2 = _single_edge(s2, s1, "element 2")
        radius = obj.Radius.getValueAs("mm").Value
        if radius < 1e-9:
            raise GSFeatureError("radius is zero")

        plane = self._plane(obj, e1, e2)
        solutions = self._solutions(e1, e2, plane, radius)
        if not solutions:
            raise GSFeatureError(
                f"no corner of radius {radius} mm fits between the "
                "two curves")
        arc, trim1, trim2 = solutions[obj.Solution % len(solutions)]

        parts = [arc]
        if obj.TrimElement1 and trim1 is not None and not trim1.isNull():
            parts.insert(0, trim1)
        if obj.TrimElement2 and trim2 is not None and not trim2.isNull():
            parts.append(trim2)
        if len(parts) == 1:
            return arc
        edges = [e for p in parts for e in p.Edges]
        try:
            sorter = getattr(Part, "sortEdges", None) or Part.__sortEdges__
            wires = [Part.Wire(g) for g in sorter(edges)]
            return wires[0] if len(wires) == 1 else \
                Part.makeCompound(wires)
        except Part.OCCError:
            return Part.makeCompound(edges)


def make_corner(doc, name="Corner"):
    return make_feature(doc, Corner, name)


register(Corner, make_corner)
