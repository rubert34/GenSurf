"""Loft sections: seam points, directions, the twist check and the exact
skin (Loft algorithm version 2).

A Section is a section curve walked in travel order, as a list of pieces
(curve, a, b): the curve from parameter a to parameter b (b < a when the
piece is walked backwards). Its seam is where the walk starts; a closed
section can start anywhere, an open one at one of its two ends.

prepare() gives every section its seam and direction:
  * a picked seam point is used as it is (nearest point on the section);
  * otherwise, with automatic alignment, each section takes the seam and
    direction that best match the section before it (the least sum of
    squared distances between matching points, centroids aligned): a
    vertex for a section with corners, any point for a smooth one;
  * a reversed row flips its section's direction and nothing else.

skin() builds the surface exactly through the prepared sections, as they
are: one B-spline surface, cut into one face per edge column (sections
with the same number of edges are matched edge to edge, others by
length) and sewn into a shell.
"""

import math

import FreeCAD as App
import Part

from .base import GenSurfError, WARNING

_TOL = 1e-7          # coincident points and lengths
_ALIGN_SAMPLES = 48  # points compared per section when aligning
_LOOP_SAMPLES = 96   # coarse seam positions tried on a smooth section


class Section:
    """A section curve walked from its seam in its direction."""

    def __init__(self, pieces, closed, wire_edges):
        self.pieces = [p for p in pieces
                       if abs(p[2] - p[1]) > _TOL]
        self.closed = closed
        self.wire_edges = wire_edges  # edges of the picked curve
        self.lengths = [c.length(min(a, b), max(a, b))
                        for c, a, b in self.pieces]
        self.length = sum(self.lengths) or 1.0

    # -- construction --------------------------------------------------

    @classmethod
    def from_wire(cls, wire):
        edges = list(wire.OrderedEdges)
        pieces = []
        if len(edges) == 1:
            e = edges[0]
            a, b = e.FirstParameter, e.LastParameter
            if e.Orientation == "Reversed":
                a, b = b, a
            pieces.append((e.Curve, a, b))
        else:
            # walk: each edge starts where the previous one ended
            first = edges[0]
            nxt = edges[1]
            a, b = first.FirstParameter, first.LastParameter
            end_b = first.valueAt(b)
            if min((end_b - v.Point).Length for v in nxt.Vertexes) > \
                    min((first.valueAt(a) - v.Point).Length
                        for v in nxt.Vertexes):
                a, b = b, a
            pieces.append((first.Curve, a, b))
            here = first.valueAt(b)
            for e in edges[1:]:
                a, b = e.FirstParameter, e.LastParameter
                if (e.valueAt(b) - here).Length < \
                        (e.valueAt(a) - here).Length:
                    a, b = b, a
                pieces.append((e.Curve, a, b))
                here = e.valueAt(b)
        return cls(pieces, wire.isClosed(), len(edges))

    def reversed(self):
        return Section([(c, b, a) for c, a, b in reversed(self.pieces)],
                       self.closed, self.wire_edges)

    def rotated(self, frac):
        """The same closed section, starting at length fraction frac."""
        frac %= 1.0
        if not self.closed or frac < _TOL or frac > 1.0 - _TOL:
            return self
        k, u = self._locate(frac)
        c, a, b = self.pieces[k]
        if len(self.pieces) == 1 and _period(c) is not None:
            # a periodic curve simply starts at the new seam (a B-spline
            # is cut there: it is only evaluated within its own range)
            end = u + (b - a)
            if isinstance(c, Part.BSplineCurve):
                c = c.copy()
                c.segment(min(u, end), max(u, end))
            return Section([(c, u, end)], True, self.wire_edges)
        before = (c, a, u)
        after = (c, u, b)
        pieces = [after] + self.pieces[k + 1:] + self.pieces[:k] + [before]
        return Section(pieces, True, self.wire_edges)

    # -- evaluation ----------------------------------------------------

    def _locate(self, frac):
        """(piece index, curve parameter) at length fraction frac."""
        target = min(max(frac, 0.0), 1.0) * self.length
        acc = 0.0
        for k, ((c, a, b), length) in enumerate(zip(self.pieces,
                                                    self.lengths)):
            if target <= acc + length or k == len(self.pieces) - 1:
                local = min(max(target - acc, 0.0), length)
                sign = 1.0 if b >= a else -1.0
                return k, c.parameterAtDistance(sign * local, a)
            acc += length
        c, a, b = self.pieces[-1]
        return len(self.pieces) - 1, b

    def point_at(self, frac):
        k, u = self._locate(frac)
        return self.pieces[k][0].value(u)

    def samples(self, n, by_parameter=False):
        """n points from the seam to the end (a closed section repeats
        its seam at the end). by_parameter: equal steps of curve
        parameter instead of length (a single picked edge only)."""
        n = max(n, 2)
        if by_parameter and self.wire_edges == 1:
            spans = [abs(b - a) for _c, a, b in self.pieces]
            total = sum(spans) or 1.0
            out = []
            last = len(self.pieces) - 1
            for i in range(n):
                t = total * i / (n - 1)
                for k, ((c, a, b), span) in enumerate(zip(self.pieces,
                                                          spans)):
                    if t <= span + _TOL or k == last:
                        sign = 1.0 if b >= a else -1.0
                        out.append(c.value(a + sign * min(t, span)))
                        break
                    t -= span
            return out
        return [self.point_at(i / (n - 1)) for i in range(n)]

    def loop_samples(self, n):
        """n points without repeating the seam (for comparisons)."""
        if self.closed:
            return [self.point_at(i / n) for i in range(n)]
        return self.samples(n)

    def start(self):
        c, a, _b = self.pieces[0]
        return c.value(a)

    def end(self):
        c, _a, b = self.pieces[-1]
        return c.value(b)

    def breaks(self):
        """Length fractions of the vertices between pieces."""
        out, acc = [], 0.0
        for length in self.lengths[:-1]:
            acc += length
            out.append(acc / self.length)
        return out

    def nearest_fraction(self, point):
        """Length fraction of the section point nearest to point."""
        best = None
        acc = 0.0
        for (c, a, b), length in zip(self.pieces, self.lengths):
            lo, hi = min(a, b), max(a, b)
            edge = Part.Edge(c, lo, hi)
            dist, pairs, _info = edge.distToShape(Part.Vertex(point))
            near = pairs[0][0]
            u = c.parameter(near)
            u = min(max(u, lo), hi)
            along = c.length(min(a, u), max(a, u))
            if best is None or dist < best[0] - _TOL:
                best = (dist, (acc + along) / self.length)
            acc += length
        return best[1]

    def wire(self):
        edges = []
        for c, a, b in self.pieces:
            e = Part.Edge(c, min(a, b), max(a, b))
            edges.append(e.reversed() if b < a else e)
        return Part.Wire(edges)

    def centroid(self, n=_ALIGN_SAMPLES):
        pts = self.loop_samples(n)
        c = App.Vector()
        for p in pts:
            c += p
        return c * (1.0 / len(pts))

    def winding(self, n=_ALIGN_SAMPLES):
        """Normal of a closed section, oriented by its direction."""
        pts = self.loop_samples(n)
        c = self.centroid(n)
        w = App.Vector()
        for p, q in zip(pts, pts[1:] + pts[:1]):
            w += (p - c).cross(q - c)
        return w

    # -- exact geometry ------------------------------------------------

    def bspline(self, bounds):
        """One B-spline curve through the pieces, piece k mapped onto
        parameters [bounds[k], bounds[k + 1]] (joints stay sharp)."""
        parts = []
        for (c, a, b), lo, hi in zip(self.pieces, bounds, bounds[1:]):
            parts.append(_piece_bspline(c, a, b, lo, hi))
        return _concat(parts)


def _period(curve):
    try:
        return curve.period() if curve.isPeriodic() else None
    except Exception:  # noqa: BLE001
        return None


def _clamped(bs, curve, u0, u1):
    mults = bs.getMultiplicities()
    return (not bs.isPeriodic() and mults[0] == mults[-1] == bs.Degree + 1
            and (bs.value(bs.FirstParameter) - curve.value(u0)).Length
            < 1e-6
            and (bs.value(bs.LastParameter) - curve.value(u1)).Length
            < 1e-6)


def _piece_bspline(curve, a, b, lo, hi):
    """Clamped B-spline of curve between parameters a and b, walked
    from a to b, reparametrized onto [lo, hi]."""
    u0, u1 = min(a, b), max(a, b)
    if isinstance(curve, Part.BSplineCurve):
        bs = curve.copy()
        bs.segment(u0, u1)  # periodic curves: may cross the origin
    else:
        try:
            bs = curve.toBSpline(u0, u1)
        except Exception:  # noqa: BLE001 — no direct conversion
            bs = None
        if bs is None or not _clamped(bs, curve, u0, u1):
            whole = curve.toBSpline()
            whole.segment(u0, u1)
            bs = whole
    if not _clamped(bs, curve, u0, u1):
        raise GenSurfError(
            "section-conversion",
            "a section curve could not be converted exactly",
            ["Sections"])
    if b < a:
        bs.reverse()
    bs.scaleKnotsToBounds(lo, hi)
    return bs


def _concat(parts):
    degree = max(p.Degree for p in parts)
    poles, weights, knots, mults = [], [], [], []
    for p in parts:
        if p.Degree < degree:
            p.increaseDegree(degree)
        pp, ww = p.getPoles(), p.getWeights()
        kk, mm = p.getKnots(), p.getMultiplicities()
        if not poles:
            poles, weights, knots, mults = pp, ww, kk, mm
            continue
        scale = weights[-1] / ww[0]  # same weight at the shared pole
        poles += pp[1:]
        weights += [w * scale for w in ww[1:]]
        mults[-1] = degree  # sharp joint
        knots += kk[1:]
        mults += mm[1:]
    bs = Part.BSplineCurve()
    bs.buildFromPolesMultsKnots(poles, mults, knots, False, degree,
                                weights)
    return bs


# -- alignment ---------------------------------------------------------


def _cost(ref_pts, ref_c, cand_pts, cand_c):
    total = 0.0
    for p, q in zip(ref_pts, cand_pts):
        d = (q - cand_c) - (p - ref_c)
        total += d.x * d.x + d.y * d.y + d.z * d.z
    return total


def _align(prev, sec, seam_frac):
    """sec with the seam and direction that best match prev."""
    n = _ALIGN_SAMPLES
    ref = prev.loop_samples(n)
    ref_c = prev.centroid(n)
    sec_c = sec.centroid(n)

    def score(cand):
        return _cost(ref, ref_c, cand.loop_samples(n), sec_c)

    # closed sections turn the same way round (the distance criterion
    # alone can prefer a mirror image when the seams are far apart)
    flip = None
    if sec.closed and prev.closed:
        wp, ws = prev.winding(), sec.winding()
        if abs(wp.dot(ws)) > 0.1 * wp.Length * ws.Length:
            flip = wp.dot(ws) < 0

    def oriented(cand):
        if flip is None:
            return (cand, cand.reversed())
        return (cand.reversed(),) if flip else (cand,)

    if not sec.closed or seam_frac is not None:
        base = sec.rotated(seam_frac) if seam_frac is not None else sec
        return min(oriented(base), key=score)
    if len(sec.pieces) > 1:  # corners: the seam is a vertex
        cands = [sec] + [sec.rotated(f) for f in sec.breaks()]
        return min((c for s in cands for c in oriented(s)), key=score)

    # smooth closed curve: coarse loop of seam positions, then refine
    m = _LOOP_SAMPLES
    loop = [sec.point_at(i / m) for i in range(m)]
    step = m // n
    best = None
    signs = (1, -1) if flip is None else ((-1,) if flip else (1,))
    for sign in signs:
        for j in range(m):
            pts = [loop[(j + sign * k * step) % m] for k in range(n)]
            cost = _cost(ref, ref_c, pts, sec_c)
            if best is None or cost < best[0]:
                best = (cost, j, sign)
    _cost0, j, sign = best

    def at(shift):
        cand = sec.rotated(shift)
        return cand.reversed() if sign < 0 else cand

    lo, hi = (j - 1) / m, (j + 1) / m
    golden = (math.sqrt(5) - 1) / 2
    for _ in range(30):
        x1 = hi - golden * (hi - lo)
        x2 = lo + golden * (hi - lo)
        if score(at(x1)) <= score(at(x2)):
            hi = x2
        else:
            lo = x1
    return at((lo + hi) / 2)


def prepare(wires, seams, reverse_rows, auto):
    """Sections with their seams and directions.

    seams: {row: point} picked seam points; reverse_rows: per-row 0/1;
    auto: align seams and directions automatically (otherwise every
    section starts where it is drawn and runs as drawn)."""
    out = []
    reference = None  # previous section before its row reversal
    for i, wire in enumerate(wires):
        sec = Section.from_wire(wire)
        seam = seams.get(i)
        seam_frac = sec.nearest_fraction(seam) \
            if (seam is not None and sec.closed) else None
        if reference is None or not auto:
            if seam_frac is not None:
                sec = sec.rotated(seam_frac)
        else:
            sec = _align(reference, sec, seam_frac)
        reference = sec
        if i < len(reverse_rows) and reverse_rows[i]:
            sec = sec.reversed()
        out.append(sec)
    return out


# -- checks ------------------------------------------------------------


def _project(v, axis):
    return v - axis * v.dot(axis)


def check(sections, twist_limit):
    """Non-fatal issues: consecutive sections that run in opposite
    directions, or turn by more than twist_limit degrees."""
    issues = []
    for i, (a, b) in enumerate(zip(sections, sections[1:])):
        ca, cb = a.centroid(), b.centroid()
        axis = cb - ca
        if axis.Length < _TOL:
            axis = a.winding() if a.closed else App.Vector(0, 0, 1)
        if axis.Length < _TOL:
            continue
        axis.normalize()
        rows = f"sections {i + 1} and {i + 2}"
        if a.closed and b.closed:
            opposite = a.winding().dot(b.winding()) < 0
            va, vb = a.start() - ca, b.start() - cb
        else:
            va, vb = a.end() - a.start(), b.end() - b.start()
            opposite = _project(va, axis).dot(_project(vb, axis)) < 0
        if opposite:
            issues.append(GenSurfError(
                "sections-opposite",
                f"{rows} run in opposite directions, so the surface "
                "folds through itself; reverse one of them",
                ["SectionDirections"], severity=WARNING))
            continue
        pa, pb = _project(va, axis), _project(vb, axis)
        if twist_limit <= 0 or pa.Length < _TOL or pb.Length < _TOL:
            continue
        angle = math.degrees(pa.getAngle(pb))
        if angle > twist_limit + 1e-6:
            hint = "check their seam points" if a.closed \
                else "check how the sections are placed"
            issues.append(GenSurfError(
                "sections-twist",
                f"the surface turns by {angle:.0f}° between {rows}; "
                f"{hint}",
                ["SeamPoints"] if a.closed else ["Sections"],
                severity=WARNING))
    return issues


# -- exact skin --------------------------------------------------------


def _merge(values):
    out = []
    for v in sorted(values):
        if not out or v - out[-1] > 1e-9:
            out.append(v)
    return out


def _surface_faces(sections):
    """Faces of the B-spline surface through sections, one per column."""
    counts = {len(s.pieces) for s in sections}
    if len(counts) == 1:
        m = counts.pop()
        bounds = list(range(m + 1))
        curves = [s.bspline(bounds) for s in sections]
        cuts, span = list(range(1, m)), float(m)
    else:
        curves, cuts = [], []
        for s in sections:
            fr = s.breaks()
            cuts += fr
            curves.append(s.bspline([0.0] + fr + [1.0]))
        cuts, span = _merge(cuts), 1.0
    surf = Part.BSplineSurface()
    surf.buildFromNSections(curves, False)
    u0, u1, v0, v1 = surf.bounds()
    us = [u0] + [u0 + (u1 - u0) * c / span for c in cuts] + [u1]
    faces = []
    for ua, ub in zip(us, us[1:]):
        if ub - ua < 1e-9:
            continue
        piece = surf.copy()
        piece.segment(ua, ub, v0, v1)
        faces.append(piece.toShape())
    return faces


def skin(sections, ruled=False):
    """Shell through the prepared sections, exactly as they are."""
    if len({s.closed for s in sections}) > 1:
        raise GenSurfError(
            "sections-mixed",
            "some sections are closed and others open; a loft needs "
            "all closed or all open sections", ["Sections"])
    if ruled:
        faces = []
        for a, b in zip(sections, sections[1:]):
            faces += _surface_faces([a, b])
    else:
        faces = _surface_faces(sections)
    if len(faces) == 1:
        return Part.Shell(faces)
    comp = Part.Compound(faces)
    comp.sewShape()
    shells = comp.Shells
    return shells[0] if len(shells) == 1 else comp
