"""Multiple Extract — GSD 'Multiple Extract' feature: several elements
extracted in one feature, each row with its own propagation type and
angular threshold, plus CATIA's Complementary mode.

Rows reference faces or edges (mixing is allowed). Per row:
  * Propagation: No propagation (default) / Point / Tangent continuity;
  * Threshold: smoothness angle for tangent propagation.

Complementary mode inverts the result within each source object: the
output becomes every face (resp. edge) of the source NOT captured by
the rows.
"""

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, make_feature
from .registry import register
from .extract import (_propagate, _faces_adjacent, _faces_smooth,
                      _edges_shared_vertex, _edges_smooth)

_PROP = ("No propagation", "Point continuity", "Tangent continuity")


class MultiExtract(GSFeature):
    TYPE_ID = "GenSurf::MultiExtract"
    CUSTOM_PANEL = "multiextract"
    REQUIRED_LINKS = ("Elements",)
    INPUT_SLOTS = (
        ("Elements", "Faces / edges to extract", ("Face", "Edge"),
         False, True),
    )
    PROPERTIES = (
        ("App::PropertyLinkSubList", "Elements", "MultiExtract",
         "Sub-elements to extract, in row order", None),
        ("App::PropertyIntegerList", "Propagations", "MultiExtract",
         "Per-row propagation: 0=No 1=Point 2=Tangent", None),
        ("App::PropertyFloatList", "Thresholds", "MultiExtract",
         "Per-row smoothness threshold in degrees (tangent mode)", None),
        ("App::PropertyBool", "Complementary", "MultiExtract",
         "Keep everything EXCEPT the captured elements", False),
    )

    @staticmethod
    def _rows(obj):
        out = []
        for linked, subs in (obj.Elements or []):
            for sub in (subs if subs else ("",)):
                out.append((linked, sub))
        return out

    def build(self, obj):
        import math
        rows = self._rows(obj)
        if not rows:
            raise GSFeatureError("pick at least one face or edge")
        props = list(obj.Propagations or [])
        thresholds = list(obj.Thresholds or [])

        captured = []          # (source_obj, shape) pairs
        sources = {}           # name -> (source_obj, has_faces, has_edges)
        for r, (linked, sub) in enumerate(rows):
            if not sub:
                raise GSFeatureError(
                    f"row {r + 1}: pick a sub-element (face or edge), "
                    "not a whole object")
            picked = linked.Shape.getElement(sub)
            mode = _PROP[props[r]] if r < len(props) and \
                0 <= props[r] < 3 else _PROP[0]
            tol = math.radians(thresholds[r] if r < len(thresholds)
                               and thresholds[r] > 0 else 0.5) + 1e-9

            if picked.ShapeType == "Face":
                found = _propagate([picked], linked.Shape.Faces,
                                   _faces_adjacent, _faces_smooth,
                                   mode, tol)
                flags = (True, False)
            elif picked.ShapeType == "Edge":
                found = _propagate([picked], linked.Shape.Edges,
                                   _edges_shared_vertex, _edges_smooth,
                                   mode, tol)
                flags = (False, True)
            else:
                raise GSFeatureError(
                    f"row {r + 1}: cannot extract a {picked.ShapeType}")

            prev = sources.get(linked.Name, (linked, False, False))
            sources[linked.Name] = (linked, prev[1] or flags[0],
                                    prev[2] or flags[1])
            for shp in found:
                if not any(shp.isSame(c) for _s, c in captured):
                    captured.append((linked, shp))

        if obj.Complementary:
            result = []
            for _name, (src, has_f, has_e) in sources.items():
                pool = (src.Shape.Faces if has_f else []) + \
                       (src.Shape.Edges if has_e else [])
                for shp in pool:
                    taken = any(shp.isSame(c) for s, c in captured
                                if s is src)
                    if not taken:
                        result.append(shp)
            if not result:
                raise GSFeatureError(
                    "complementary mode captured everything — nothing "
                    "remains")
        else:
            result = [c for _s, c in captured]

        faces = [s for s in result if s.ShapeType == "Face"]
        edges = [s for s in result if s.ShapeType == "Edge"]
        parts = []
        if faces:
            if len(faces) == 1:
                parts.append(faces[0])
            else:
                try:
                    shell = Part.makeShell(faces)
                    if not shell.isNull() and \
                            len(shell.Faces) == len(faces):
                        parts.append(shell)
                    else:
                        parts.extend(faces)
                except Part.OCCError:
                    parts.extend(faces)
        if edges:
            sorter = getattr(Part, "sortEdges", None) or Part.__sortEdges__
            parts.extend(Part.Wire(g) for g in sorter(edges))
        if not parts:
            raise GSFeatureError("nothing captured")
        return parts[0] if len(parts) == 1 else Part.makeCompound(parts)


def make_multi_extract(doc, name="MultiExtract"):
    return make_feature(doc, MultiExtract, name)


register(MultiExtract, make_multi_extract)
