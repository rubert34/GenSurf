"""Edge Fillet — GSD 'Edge Fillet' feature: rounds picked edges of a
surface or shell at a constant radius.

Propagation Tangency extends each picked edge along its tangent-
continuous chain (as in CATIA); Minimal fillets exactly the picked
edges. All picked edges must belong to the same surface object.

Not implemented: variable radius (points table), conic parameter,
Edge(s) to keep, limiting elements, blend corners / setback, circle
fillet with spine, trim ribbons — the constant-radius core covers the
overwhelming share of real use.
"""

import math

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, make_feature
from .registry import register
from .extract import _edges_shared_vertex, _edges_smooth, _propagate

_SMOOTH_TOL = math.radians(2.0)


def edges_on_one_object(links, what):
    """(shape, [edges]) for a LinkSubList whose picks must all live on
    the same document object."""
    if not links:
        raise GSFeatureError(f"{what}: pick at least one edge")
    owner = links[0][0]
    edges = []
    for linked, subs in links:
        if linked is not owner:
            raise GSFeatureError(
                f"{what}: all edges must belong to the same surface "
                f"({owner.Label} vs {linked.Label})")
        for sub in (subs if subs else ("",)):
            if not sub:
                raise GSFeatureError(
                    f"{what}: pick individual edges, not whole objects")
            shape = owner.Shape.getElement(sub)
            if shape.ShapeType != "Edge":
                raise GSFeatureError(
                    f"{what}: expected an edge, got {shape.ShapeType}")
            edges.append(shape)
    return owner.Shape, edges


def propagate_tangent(shape, edges):
    """Extend the picked edges along tangent-continuous chains."""
    return _propagate(
        edges, shape.Edges, _edges_shared_vertex, _edges_smooth,
        "Tangent continuity", _SMOOTH_TOL)


class EdgeFillet(GSFeature):
    TYPE_ID = "GenSurf::EdgeFillet"
    REQUIRED_LINKS = ("Edges",)
    INPUT_SLOTS = (
        ("Edges", "Edge(s) to fillet", ("Edge",), False, True),
    )
    ENUMS = {
        "Propagation": ("Tangency", "Minimal"),
    }
    PROPERTIES = (
        ("App::PropertyLinkSubList", "Edges", "Fillet",
         "Edges to round (on one surface object)", None),
        ("App::PropertyDistance", "Radius", "Fillet",
         "Fillet radius", "5 mm"),
        ("App::PropertyEnumeration", "Propagation", "Fillet",
         "Tangency follows smooth edge chains; Minimal only the picks",
         None),
    )

    def build(self, obj):
        shape, picked = edges_on_one_object(obj.Edges, "edges to fillet")
        radius = obj.Radius.getValueAs("mm").Value
        if radius < 1e-9:
            raise GSFeatureError("radius is zero")
        if obj.Propagation == "Tangency":
            picked = propagate_tangent(shape, picked)
        try:
            result = shape.makeFillet(radius, picked)
        except Part.OCCError as err:
            raise GSFeatureError(
                f"fillet of radius {radius} mm failed — it may be too "
                f"large for this geometry ({err})")
        if result.isNull() or not result.Faces:
            raise GSFeatureError("fillet produced no surface")
        return result


def make_edge_fillet(doc, name="EdgeFillet"):
    return make_feature(doc, EdgeFillet, name)


register(EdgeFillet, make_edge_fillet)
