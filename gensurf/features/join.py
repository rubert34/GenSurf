"""Join — GSD 'Join' feature: assemble surfaces or curves into one
element, with CATIA's checks.

* Surfaces: sewn into a shell (exactly shared boundaries merge; the
  Python binding exposes no tolerance-driven sewing, so MergingDistance
  is used as the connectivity criterion and for curve welding).
* Curves: welded into wires with MergingDistance as the 3D tolerance.

Checks (as in the CATIA dialog):
  * CheckConnectivity — error when the elements do not form one
    connected set (within MergingDistance);
  * CheckManifold    — error when more than two faces share an edge;
  * CheckTangency    — error when joined faces meet sharper than
    AngularThreshold;
  * Simplify         — remove redundant internal edges (removeSplitter);
  * IgnoreErroneous  — skip inputs that fail to resolve, with a warning.
"""

import math

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksublist,
                   make_feature)
from .registry import register
from .extract import _faces_smooth


class Join(GSFeature):
    TYPE_ID = "GenSurf::Join"
    REQUIRED_LINKS = ("Elements",)
    INPUT_SLOTS = (
        ("Elements", "Surfaces / curves to join (2+)",
         ("Face", "Shell", "Edge", "Wire"), False, True),
    )
    PROPERTIES = (
        ("App::PropertyLinkSubList", "Elements", "Join",
         "Elements to assemble", None),
        ("App::PropertyDistance", "MergingDistance", "Join",
         "Elements closer than this count as connected", "0.001 mm"),
        ("App::PropertyBool", "CheckConnectivity", "Join",
         "Fail when the result is not one connected set", True),
        ("App::PropertyBool", "CheckManifold", "Join",
         "Fail when more than two faces share an edge", True),
        ("App::PropertyBool", "CheckTangency", "Join",
         "Fail when faces meet sharper than AngularThreshold", False),
        ("App::PropertyAngle", "AngularThreshold", "Join",
         "Tangency check threshold", "0.5 deg"),
        ("App::PropertyBool", "Simplify", "Join",
         "Remove redundant internal edges from the result", False),
        ("App::PropertyBool", "IgnoreErroneous", "Join",
         "Skip inputs that fail to resolve", False),
    )

    @staticmethod
    def _components(items, touch):
        """Connected components under the `touch` predicate."""
        comps = []
        for it in items:
            hits = [c for c in comps if any(touch(it, o) for o in c)]
            merged = [it]
            for c in hits:
                merged.extend(c)
                comps.remove(c)
            comps.append(merged)
        return comps

    def build(self, obj):
        faces, edges = [], []
        for entry in (obj.Elements or []):
            linked, subs = entry
            for sub in (subs if subs else ("",)):
                try:
                    shape = linked.Shape.getElement(sub) if sub \
                        else linked.Shape
                    if shape.Faces:
                        faces.extend(shape.Faces)
                    elif shape.Edges:
                        edges.extend(shape.Edges)
                    else:
                        raise GSFeatureError(
                            f"{linked.Label} has no geometry to join")
                except Exception as err:
                    if obj.IgnoreErroneous:
                        App.Console.PrintWarning(
                            f"[GenSurf] Join: skipping {linked.Label} "
                            f"({err})\n")
                    else:
                        raise
        if faces and edges:
            raise GSFeatureError(
                "mixing surfaces and curves in one Join is not supported")
        if not faces and not edges:
            raise GSFeatureError("nothing to join")

        tol = obj.MergingDistance.getValueAs("mm").Value

        if edges:
            # Weld across gaps up to MergingDistance: raise the vertex
            # tolerance on working copies so MakeWire accepts near-touching
            # ends (Part.Wire alone only bridges ~1e-7).
            work = [e.copy() for e in edges]
            if tol > 1e-7:
                for e in work:
                    e.fixTolerance(tol, Part.Vertex)
            sorter = getattr(Part, "sortEdges", None)
            groups = sorter(work, tol) if sorter else \
                Part.__sortEdges__(work)
            if obj.CheckConnectivity and len(groups) > 1:
                raise GSFeatureError(
                    f"curves form {len(groups)} disconnected chains "
                    f"(gaps larger than {tol} mm)")
            wires = [Part.Wire(g) for g in groups]
            return wires[0] if len(wires) == 1 else \
                Part.makeCompound(wires)

        # -- surfaces ------------------------------------------------------
        if obj.CheckConnectivity:
            comps = self._components(
                faces, lambda a, b: a.distToShape(b)[0] <= tol + 1e-9)
            if len(comps) > 1:
                raise GSFeatureError(
                    f"surfaces form {len(comps)} disconnected groups "
                    f"(within merging distance {tol} mm)")

        comp = Part.makeCompound(faces)
        comp.sewShape()
        sewn_faces = comp.Faces

        # manifold check: edges used by more than two faces
        if obj.CheckManifold:
            tally = []
            for f in sewn_faces:
                for e in f.Edges:
                    for i, (e2, c) in enumerate(tally):
                        if e.isSame(e2):
                            tally[i] = (e2, c + 1)
                            break
                    else:
                        tally.append((e, 1))
            worst = max((c for _e, c in tally), default=1)
            if worst > 2:
                raise GSFeatureError(
                    f"non-manifold result: an edge is shared by {worst} "
                    "faces")

        if obj.CheckTangency:
            tol_rad = obj.AngularThreshold.getValueAs("rad").Value + 1e-9
            for i, f1 in enumerate(sewn_faces):
                for f2 in sewn_faces[i + 1:]:
                    shared = None
                    for e1 in f1.Edges:
                        if any(e1.isSame(e2) for e2 in f2.Edges):
                            shared = e1
                            break
                    if shared is not None and \
                            not _faces_smooth(f1, f2, shared, tol_rad):
                        raise GSFeatureError(
                            "tangency check failed: faces meet sharper "
                            f"than {math.degrees(tol_rad):.2f} deg")

        result = None
        if comp.Shells and len(comp.Shells) == 1 and \
                len(comp.Shells[0].Faces) == len(sewn_faces):
            result = comp.Shells[0]
        else:
            try:
                shell = Part.makeShell(sewn_faces)
                if not shell.isNull() and \
                        len(shell.Faces) == len(sewn_faces):
                    result = shell
            except Part.OCCError:
                pass
        if result is None:
            result = Part.makeCompound(sewn_faces)

        if obj.Simplify:
            try:
                simplified = result.removeSplitter()
                if not simplified.isNull() and simplified.Faces:
                    result = simplified
            except Part.OCCError:
                pass
        return result


def make_join(doc, name="Join"):
    return make_feature(doc, Join, name)


register(Join, make_join)
