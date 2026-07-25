"""Symmetry — GSD 'Symmetry' feature: the mirrored copy of an element
about a point, a line, or a plane.

A reflection is an improper transform (determinant -1), which a
Placement cannot represent, so the mirror matrix is baked into the
geometry with transformGeometry (the same route as Scale — engineering
rule 4).

Reference resolution, CATIA-style: a planar face or datum plane mirrors
about that plane, a straight edge or datum axis about that line, a
vertex about that point.
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksub,
                   plane_from_link, axis_from_link, make_feature)
from .registry import register


def _mirror_matrix(link):
    """Reflection matrix for a point / line / plane reference."""
    planar = plane_from_link(link)
    if planar is not None:
        pos, n = planar
        n = App.Vector(n)
        n.normalize()
        k = 2.0 * pos.dot(n)
        return App.Matrix(
            1 - 2 * n.x * n.x, -2 * n.x * n.y, -2 * n.x * n.z, k * n.x,
            -2 * n.y * n.x, 1 - 2 * n.y * n.y, -2 * n.y * n.z, k * n.y,
            -2 * n.z * n.x, -2 * n.z * n.y, 1 - 2 * n.z * n.z, k * n.z,
            0, 0, 0, 1)

    try:
        base, d = axis_from_link(link)
    except GSFeatureError:
        base, d = None, None
    if d is not None:
        d = App.Vector(d)
        d.normalize()
        # A = 2 dd^T - I ; t = 2 (I - dd^T) base
        a = [[2 * d[i] * d[j] - (1.0 if i == j else 0.0)
              for j in range(3)] for i in range(3)]
        t = [2 * (base[i] - d[i] * d.dot(base)) for i in range(3)]
        return App.Matrix(
            a[0][0], a[0][1], a[0][2], t[0],
            a[1][0], a[1][1], a[1][2], t[1],
            a[2][0], a[2][1], a[2][2], t[2],
            0, 0, 0, 1)

    shape = resolve_linksub(link)
    # a closed curved edge (circle) also has a single vertex — its seam
    # — which must NOT silently become a point-symmetry center
    if shape.ShapeType == "Vertex" or \
            (not shape.Edges and len(shape.Vertexes) == 1):
        p = shape.Vertexes[0].Point
        return App.Matrix(
            -1, 0, 0, 2 * p.x,
            0, -1, 0, 2 * p.y,
            0, 0, -1, 2 * p.z,
            0, 0, 0, 1)
    raise GSFeatureError(
        "the symmetry reference must be a point, a straight line, or a "
        "plane")


class Symmetry(GSFeature):
    TYPE_ID = "GenSurf::Symmetry"
    REQUIRED_LINKS = ("Source", "Reference")
    INPUT_SLOTS = (
        ("Source", "Element to mirror", None, False),
        ("Reference", "Point / line / plane reference",
         ("Vertex", "Edge", "Face"), False),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Source", "Symmetry",
         "Element to mirror", None),
        ("App::PropertyLinkSub", "Reference", "Symmetry",
         "Mirror reference: point, line, or plane", None),
    )

    def build(self, obj):
        src = resolve_linksub(obj.Source)
        m = _mirror_matrix(obj.Reference)
        result = src.transformGeometry(m)
        if result.isNull():
            raise GSFeatureError("symmetry produced no geometry")
        return result


def make_symmetry(doc, name="Symmetry"):
    return make_feature(doc, Symmetry, name)


register(Symmetry, make_symmetry)
