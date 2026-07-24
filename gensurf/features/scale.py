"""Scale — GSD 'Scaling' feature with the reference deciding the kind:

  * point (vertex / datum point)  — uniform scaling about the point,
  * plane (planar face / datum)   — scaling along the plane normal, the
                                    plane itself is invariant,
  * line (straight edge / axis)   — radial scaling away from the line,
                                    distances along the line preserved.

Implemented as an affine matrix A = a*I + b*(u X u) + translation and
applied with ``transformGeometry`` (scaling is not rigid, so geometry is
converted where needed). Negative ratios mirror through the reference.
"""

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, resolve_linksub, make_feature
from .registry import register


class Scale(GSFeature):
    TYPE_ID = "GenSurf::Scale"
    REQUIRED_LINKS = ("Source", "Reference")
    INPUT_SLOTS = (
        ("Source", "Element to scale", None, False),
        ("Reference", "Reference: point, plane or line",
         ("Vertex", "Face", "Edge"), False),
    )
    PROPERTIES = (
        ("App::PropertyLinkSub", "Source", "Scale",
         "Element to scale (a copy is created)", None),
        ("App::PropertyLinkSub", "Reference", "Scale",
         "Point: uniform; plane: along its normal; line: radially", None),
        ("App::PropertyFloat", "Ratio", "Scale",
         "Scaling ratio (negative mirrors)", 2.0),
    )

    @staticmethod
    def _reference(obj):
        """(mode, origin, unit_vector_or_None) from the reference link."""
        linked, _subs = obj.Reference
        tid = getattr(linked, "TypeId", "")
        if tid == "App::Plane":
            pl = linked.Placement
            return "Plane", pl.Base, pl.Rotation.multVec(App.Vector(0, 0, 1))
        if tid == "App::Line":
            pl = linked.Placement
            return "Line", pl.Base, pl.Rotation.multVec(App.Vector(1, 0, 0))

        shape = resolve_linksub(obj.Reference)
        if shape.ShapeType == "Vertex":
            return "Point", App.Vector(shape.Point), None
        if shape.ShapeType == "Wire" and len(shape.Edges) == 1:
            shape = shape.Edges[0]
        if shape.ShapeType == "Edge":
            if not isinstance(shape.Curve, Part.Line):
                raise GSFeatureError("a line reference must be straight")
            return ("Line", shape.Vertexes[0].Point,
                    App.Vector(shape.Curve.Direction))
        if shape.ShapeType != "Face" and len(shape.Faces) == 1:
            shape = shape.Faces[0]
        if shape.ShapeType == "Face":
            if not isinstance(shape.Surface, Part.Plane):
                raise GSFeatureError("a plane reference must be planar")
            return "Plane", shape.Surface.Position, shape.Surface.Axis
        raise GSFeatureError(
            f"reference must be a point, plane or line "
            f"(got a {shape.ShapeType})")

    @staticmethod
    def _matrix(mode, k, origin, u):
        if mode == "Point":
            a, b = k, 0.0
        elif mode == "Plane":
            a, b = 1.0, k - 1.0
        else:  # Line: scale perpendicular to u, preserve along u
            a, b = k, 1.0 - k

        ux, uy, uz = (u.x, u.y, u.z) if u is not None else (0.0, 0.0, 0.0)
        rows = [
            [a + b * ux * ux, b * ux * uy, b * ux * uz],
            [b * uy * ux, a + b * uy * uy, b * uy * uz],
            [b * uz * ux, b * uz * uy, a + b * uz * uz],
        ]
        ap = App.Vector(  # A * origin
            sum(rows[0][i] * origin[i] for i in range(3)),
            sum(rows[1][i] * origin[i] for i in range(3)),
            sum(rows[2][i] * origin[i] for i in range(3)))
        t = origin - ap
        return App.Matrix(
            rows[0][0], rows[0][1], rows[0][2], t.x,
            rows[1][0], rows[1][1], rows[1][2], t.y,
            rows[2][0], rows[2][1], rows[2][2], t.z,
            0, 0, 0, 1)

    def build(self, obj):
        src = resolve_linksub(obj.Source)
        k = float(obj.Ratio)
        if abs(k) < 1e-9:
            raise GSFeatureError("ratio must not be zero")
        mode, origin, u = self._reference(obj)
        if u is not None:
            u = App.Vector(u)
            u.normalize()
        return src.transformGeometry(self._matrix(mode, k, origin, u))


def make_scale(doc, name="Scale"):
    return make_feature(doc, Scale, name)


register(Scale, make_scale)
