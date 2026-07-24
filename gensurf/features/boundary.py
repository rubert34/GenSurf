"""Boundary — GSD 'Boundary' feature: free boundary of a surface as a
parametric curve, with CATIA's propagation types and limits.

Propagation from the picked surface edge:
  * Complete boundary — the whole free-boundary loop containing the
    picked edge (limits ignored, as in CATIA);
  * Point continuity  — the connected boundary chain, relimitable;
  * Tangent continuity — the chain, stopping at sharp corners;
  * No propagation    — just the picked edge, relimitable.

Limits (optional vertex picks) cut the chain; the kept portion is the
one containing the picked edge.
"""

import math

import FreeCAD as App
import Part

from .base import GSFeature, GSFeatureError, make_feature
from .registry import register

_PROP = ("Point continuity", "Complete boundary", "Tangent continuity",
         "No propagation")
_TOL = 1e-7


def _sorter():
    return getattr(Part, "sortEdges", None) or Part.__sortEdges__


def free_boundary_edges(shape):
    """Original edge objects that belong to exactly one face."""
    faces = shape.Faces
    if not faces:
        raise GSFeatureError("the picked object has no surface")
    tallied = []
    for f in faces:
        for e in f.Edges:
            for i, (e2, c) in enumerate(tallied):
                if e.isSame(e2):
                    tallied[i] = (e2, c + 1)
                    break
            else:
                tallied.append((e, 1))
    free = [e for e, c in tallied if c == 1]
    if not free:
        raise GSFeatureError("the surface has no free boundary (closed)")
    return free


def free_boundary_chains(shape):
    """Free boundary as wires (convenience for tests/inspection)."""
    return [Part.Wire(g) for g in _sorter()(free_boundary_edges(shape))]


def _order_group(edges):
    """Order one connected set of edges into a travel chain:
    [(edge, start_point, end_point), ...]."""
    remaining = list(edges)
    e0 = remaining.pop(0)
    chain = [(e0, e0.valueAt(e0.FirstParameter),
              e0.valueAt(e0.LastParameter))]
    grew = True
    while remaining and grew:
        grew = False
        for i, e in enumerate(remaining):
            a = e.valueAt(e.FirstParameter)
            b = e.valueAt(e.LastParameter)
            if (chain[-1][2] - a).Length < _TOL:
                chain.append((e, a, b))
            elif (chain[-1][2] - b).Length < _TOL:
                chain.append((e, b, a))
            elif (chain[0][1] - b).Length < _TOL:
                chain.insert(0, (e, a, b))
            elif (chain[0][1] - a).Length < _TOL:
                chain.insert(0, (e, b, a))
            else:
                continue
            remaining.pop(i)
            grew = True
            break
    return chain, remaining


def _group_containing(edges, picked):
    """Ordered chain of the connected group containing the picked edge."""
    pool = list(edges)
    while pool:
        chain, pool_rest = _order_group(pool)
        if any(picked.isSame(e) for e, _a, _b in chain):
            return chain
        if len(pool_rest) == len(pool):
            break
        pool = pool_rest
    raise GSFeatureError("the picked edge is not a free boundary edge")


def _is_closed(chain):
    return (chain[0][1] - chain[-1][2]).Length < _TOL


def _junction_smooth(entry1, entry2, tol_rad):
    """Tangent continuity across the junction between two chain entries
    (entry1 ends where entry2 starts)."""
    def travel_tangent(entry, at_end):
        e, a, b = entry
        pt = b if at_end else a
        try:
            param = e.Curve.parameter(pt)
        except Part.OCCError:
            param = e.FirstParameter \
                if (e.valueAt(e.FirstParameter) - pt).Length < \
                   (e.valueAt(e.LastParameter) - pt).Length \
                else e.LastParameter
        t = App.Vector(e.tangentAt(param))
        t.normalize()
        # orient along travel direction a -> b
        if (e.valueAt(e.LastParameter) - b).Length > _TOL:
            t = t.negative()
        return t
    t1 = travel_tangent(entry1, True)
    t2 = travel_tangent(entry2, False)
    return t1.getAngle(t2) < tol_rad


def _tangent_prune(chain, picked_idx, tol_rad):
    """Sub-chain around picked_idx bounded by sharp corners."""
    n = len(chain)
    closed = _is_closed(chain)

    lo = picked_idx
    for _ in range(n - 1):
        prev = (lo - 1) % n
        if (lo == 0 and not closed) or \
                not _junction_smooth(chain[prev], chain[lo], tol_rad):
            break
        if prev == picked_idx:
            break
        lo = prev
    hi = picked_idx
    for _ in range(n - 1):
        nxt = (hi + 1) % n
        if (hi == n - 1 and not closed) or \
                not _junction_smooth(chain[hi], chain[nxt], tol_rad):
            break
        if nxt == lo:
            break
        hi = nxt

    idxs = []
    i = lo
    while True:
        idxs.append(i)
        if i == hi:
            break
        i = (i + 1) % n
        if len(idxs) > n:
            break
    return [chain[i] for i in idxs]


class Boundary(GSFeature):
    TYPE_ID = "GenSurf::Boundary"
    REQUIRED_LINKS = ("Edge",)
    INPUT_SLOTS = (
        ("Edge", "Surface edge", ("Edge",), False),
        ("Limit1", "Limit 1 (optional point)", ("Vertex",), True),
        ("Limit2", "Limit 2 (optional point)", ("Vertex",), True),
    )
    ENUMS = {
        "Propagation": _PROP,
    }
    PROPERTIES = (
        ("App::PropertyLinkSub", "Edge", "Boundary",
         "A free boundary edge of the surface", None),
        ("App::PropertyLinkSub", "Limit1", "Boundary",
         "First relimiting point", None),
        ("App::PropertyLinkSub", "Limit2", "Boundary",
         "Second relimiting point", None),
        ("App::PropertyEnumeration", "Propagation", "Boundary",
         "How far the boundary propagates from the picked edge", None),
        ("App::PropertyAngle", "CornerAngle", "Boundary",
         "Corner threshold for tangent propagation", "0.5 deg"),
    )

    @staticmethod
    def _limit_point(link):
        if not link:
            return None
        linked, subs = link
        if not subs or not subs[0]:
            raise GSFeatureError("limits must be vertex picks")
        v = linked.Shape.getElement(subs[0])
        if v.ShapeType != "Vertex":
            raise GSFeatureError("limits must be vertex picks")
        return App.Vector(v.Point)

    @staticmethod
    def _sub_edge(entry, f0, f1):
        """Portion of a chain entry between travel-fractions f0 < f1."""
        e, a, _b = entry
        forward = (e.valueAt(e.FirstParameter) - a).Length < _TOL
        p_lo, p_hi = e.FirstParameter, e.LastParameter
        if forward:
            q0 = p_lo + (p_hi - p_lo) * f0
            q1 = p_lo + (p_hi - p_lo) * f1
        else:
            q0 = p_hi - (p_hi - p_lo) * f1
            q1 = p_hi - (p_hi - p_lo) * f0
        try:
            return e.Curve.toShape(q0, q1)
        except Part.OCCError:
            return e

    @classmethod
    def _relimit(cls, chain, picked_idx, l1, l2):
        lengths = [c[0].Length for c in chain]
        starts = [0.0]
        for ln in lengths[:-1]:
            starts.append(starts[-1] + ln)
        total = starts[-1] + lengths[-1]
        closed = _is_closed(chain)

        def position(pt):
            best = (1e18, 0.0)
            for i, (e, a, _b) in enumerate(chain):
                d, pairs, _ = e.distToShape(Part.Vertex(pt))
                if d < best[0]:
                    on_e = pairs[0][0]
                    frac = (on_e - a).Length / max(lengths[i], 1e-12)
                    best = (d, starts[i] + min(max(frac, 0), 1) * lengths[i])
            return best[1]

        s1, s2 = sorted((position(l1), position(l2)))
        mid = starts[picked_idx] + lengths[picked_idx] * 0.5
        if s1 <= mid <= s2:
            intervals = [(s1, s2)]
        elif closed:
            intervals = [(s2, total), (0.0, s1)]
        else:
            intervals = [(0.0, s1)] if mid < s1 else [(s2, total)]

        segments = []
        for i, entry in enumerate(chain):
            e0, e1 = starts[i], starts[i] + lengths[i]
            for lo, hi in intervals:
                a = max(e0, lo)
                b = min(e1, hi)
                if b - a < 1e-9:
                    continue
                segments.append(cls._sub_edge(
                    entry, (a - e0) / lengths[i], (b - e0) / lengths[i]))
        if not segments:
            raise GSFeatureError("limits removed the whole boundary")
        groups = _sorter()(segments)
        wires = [Part.Wire(g) for g in groups]
        return wires[0] if len(wires) == 1 else Part.makeCompound(wires)

    def build(self, obj):
        linked, subs = obj.Edge
        if not subs or not subs[0]:
            raise GSFeatureError("pick an EDGE of the surface")
        picked = linked.Shape.getElement(subs[0])
        if picked.ShapeType != "Edge":
            raise GSFeatureError(f"pick an edge, not a {picked.ShapeType}")

        mode = obj.Propagation
        if mode == "No propagation":
            chain = [(picked, picked.valueAt(picked.FirstParameter),
                      picked.valueAt(picked.LastParameter))]
            picked_idx = 0
        else:
            free = free_boundary_edges(linked.Shape)
            chain = _group_containing(free, picked)
            picked_idx = next(i for i, (e, _a, _b) in enumerate(chain)
                              if picked.isSame(e))
            if mode == "Tangent continuity":
                chain = _tangent_prune(
                    chain, picked_idx,
                    obj.CornerAngle.getValueAs("rad").Value + 1e-9)
                picked_idx = next(
                    i for i, (e, _a, _b) in enumerate(chain)
                    if picked.isSame(e))

        l1 = self._limit_point(obj.Limit1)
        l2 = self._limit_point(obj.Limit2)
        if mode != "Complete boundary" and l1 is not None \
                and l2 is not None:
            return self._relimit(chain, picked_idx, l1, l2)

        edges = [c[0] for c in chain]
        groups = _sorter()(edges)
        wires = [Part.Wire(g) for g in groups]
        return wires[0] if len(wires) == 1 else Part.makeCompound(wires)


def make_boundary(doc, name="Boundary"):
    return make_feature(doc, Boundary, name)


register(Boundary, make_boundary)
