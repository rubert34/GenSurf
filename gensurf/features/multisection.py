"""Multi-section surface — GSD 'Multi-Sections Surface' (loft).

Sections are picked in order (2+). Without guides the surface is a
direct BRepOffsetAPI_ThruSections loft (Part.makeLoft), optionally
ruled. With guides (up to two in this version) the surface is skinned
CATIA-style:

  * every consecutive pair of sections is bridged by intermediate
    stations (Stations per span);
  * each station starts as the pointwise blend of its two sections and
    is then warped by the similarity transform (translate + rotate +
    scale) that pins its anchor points onto the guides at the matching
    guide fraction;
  * the dense station family is lofted.

Guides must touch every section (within tolerance). Coupling chooses
how section points correspond: ArcLength (equal length fractions) or
Ratio (equal parameter fractions).
"""

import FreeCAD as App
import Part

from .base import (GSFeature, GSFeatureError, resolve_linksublist,
                   make_feature, curve_wires)
from .registry import register

_TOUCH_TOL = 1e-4


class MultiSection(GSFeature):
    TYPE_ID = "GenSurf::MultiSection"
    CUSTOM_PANEL = "multisection"
    REQUIRED_LINKS = ("Sections",)
    INPUT_SLOTS = (
        ("Sections", "Section curves (2 or more, in order)",
         ("Edge", "Wire"), False, True),
        ("Guides", "Guide curves (up to two, optional)",
         ("Edge", "Wire"), True, True),
    )
    ENUMS = {
        "Coupling": ("ArcLength", "Ratio"),
    }
    PROPERTIES = (
        ("App::PropertyLinkSubList", "Sections", "MultiSection",
         "Ordered section curves", None),
        ("App::PropertyLinkSubList", "Guides", "MultiSection",
         "Guide curves the surface must follow (0-2)", None),
        ("App::PropertyLinkSubList", "GuideSupports", "MultiSection",
         "Support surfaces for guides (see GuideSupportRows)", None),
        ("App::PropertyIntegerList", "GuideSupportRows", "MultiSection",
         "Guide index for each GuideSupports entry", None),
        ("App::PropertyIntegerList", "GuideContinuities", "MultiSection",
         "Per-guide continuity: 0=Position 1=Tangent 2=Curvature", None),
        ("App::PropertyLinkSubList", "SectionSupports", "MultiSection",
         "Support surfaces for sections (see SectionSupportRows)", None),
        ("App::PropertyIntegerList", "SectionSupportRows", "MultiSection",
         "Section index for each SectionSupports entry", None),
        ("App::PropertyIntegerList", "SectionContinuities", "MultiSection",
         "Per-section continuity: 0=Position 1=Tangent 2=Curvature "
         "(only the first and last sections take effect)", None),
        ("App::PropertyEnumeration", "Coupling", "MultiSection",
         "Point correspondence between sections", None),
        ("App::PropertyBool", "Ruled", "MultiSection",
         "Straight (ruled) transitions between sections", False),
        ("App::PropertyBool", "AutoOrient", "MultiSection",
         "Align section directions automatically", True),
        ("App::PropertyInteger", "Samples", "MultiSection",
         "Section sampling density (guided/constrained modes)", 24),
        ("App::PropertyInteger", "Stations", "MultiSection",
         "Intermediate stations per span (guided/constrained modes)", 8),
    )

    # -- shared sampling helpers ------------------------------------------

    @staticmethod
    def _entries_flat(links):
        out = []
        for linked, subs in (links or []):
            for sub in (subs if subs else ("",)):
                out.append((linked, sub))
        return out

    @staticmethod
    def _as_wires(shapes, what):
        wires = []
        for shape in shapes:
            ws = curve_wires(shape)
            if len(ws) > 1:
                App.Console.PrintWarning(
                    f"[GenSurf] {what}: multiple curves in one pick, "
                    "using the first\n")
            wires.append(ws[0])
        return wires

    @staticmethod
    def _sample(wire, n, coupling):
        if coupling == "Ratio" and len(wire.Edges) == 1:
            edge = wire.Edges[0]
            f, l = edge.FirstParameter, edge.LastParameter
            return [edge.valueAt(f + (l - f) * i / (n - 1))
                    for i in range(n)]
        return wire.discretize(Number=n)

    @staticmethod
    def _orient(sampled):
        """Sequentially flip each sampled section to match the previous."""
        out = [sampled[0]]
        for pts in sampled[1:]:
            prev = out[-1]
            straight = (prev[0] - pts[0]).Length + (prev[-1] - pts[-1]).Length
            flipped = (prev[0] - pts[-1]).Length + (prev[-1] - pts[0]).Length
            out.append(list(reversed(pts)) if flipped < straight else pts)
        return out

    # -- guided skinning ---------------------------------------------------

    @staticmethod
    def _guide_polyline(wire, n=400):
        pts = wire.discretize(Number=n)
        acc = [0.0]
        for a, b in zip(pts, pts[1:]):
            acc.append(acc[-1] + (b - a).Length)
        total = acc[-1] or 1.0
        return pts, [a / total for a in acc]

    @classmethod
    def _guide_hits(cls, guide_wire, section_wires):
        """Arc-length fraction and point where the guide meets each
        section (monotonic along the guide)."""
        pts, fracs = cls._guide_polyline(guide_wire)
        hits = []
        for sw in section_wires:
            best_i, best_d = 0, 1e18
            for i, p in enumerate(pts):
                d = sw.distToShape(Part.Vertex(p))[0]
                if d < best_d:
                    best_i, best_d = i, d
            if best_d > _TOUCH_TOL:
                raise GSFeatureError(
                    f"a guide does not touch every section "
                    f"(gap {best_d:.4f} mm)")
            hits.append((fracs[best_i], pts[best_i]))
        f = [h[0] for h in hits]
        if any(b <= a for a, b in zip(f, f[1:])):
            raise GSFeatureError(
                "guide meets the sections out of order — check the "
                "section picking order")
        return hits

    @staticmethod
    def _guide_point(pts, fracs, f):
        """Point at arc-length fraction f along the guide polyline."""
        if f <= fracs[0]:
            return pts[0]
        for i in range(1, len(fracs)):
            if fracs[i] >= f:
                span = fracs[i] - fracs[i - 1] or 1.0
                w = (f - fracs[i - 1]) / span
                return pts[i - 1] * (1 - w) + pts[i] * w
        return pts[-1]

    @staticmethod
    def _similarity(a1, a2, b1, b2):
        """Transform mapping segment (a1,a2) onto (b1,b2):
        returns point-mapper. Falls back to translation when degenerate."""
        v0, v1 = a2 - a1, b2 - b1
        if v0.Length < 1e-9 or v1.Length < 1e-9:
            t = b1 - a1
            return lambda p: p + t
        scale = v1.Length / v0.Length
        axis = v0.cross(v1)
        if axis.Length < 1e-12:
            rot = App.Rotation()
            if v0.dot(v1) < 0:  # opposite: rotate 180 about any normal
                normal = v0.cross(App.Vector(0, 0, 1))
                if normal.Length < 1e-9:
                    normal = v0.cross(App.Vector(0, 1, 0))
                rot = App.Rotation(normal, 180)
        else:
            import math
            ang = math.degrees(v0.getAngle(v1))
            rot = App.Rotation(axis, ang)
        return lambda p: b1 + rot.multVec(p - a1) * scale

    @staticmethod
    def _row_support(entries, rows, conts, k, what):
        """(face, continuity) for row k of a (supports, rows, conts)
        triple, or (None, 0)."""
        cont = conts[k] if k < len(conts) else 0
        if cont <= 0:
            return None, 0
        flat = []
        for linked, subs in (entries or []):
            for sub in (subs if subs else ("",)):
                flat.append((linked, sub))
        for (linked, sub), row in zip(flat, rows or []):
            if row == k:
                shape = linked.Shape.getElement(sub) if sub \
                    else linked.Shape
                if shape.ShapeType != "Face":
                    faces = shape.Faces
                    if len(faces) != 1:
                        raise GSFeatureError(
                            f"{what} {k + 1} support must be a single "
                            "face")
                    shape = faces[0]
                return shape, cont
        raise GSFeatureError(
            f"{what} {k + 1} has "
            f"{('Tangent', 'Curvature')[cont - 1]} continuity but no "
            "support surface")

    @classmethod
    def _guide_support_of(cls, obj, k):
        """(face, continuity) for guide row k, or (None, 0)."""
        return cls._row_support(
            obj.GuideSupports, obj.GuideSupportRows,
            list(obj.GuideContinuities or []), k, "guide")

    @staticmethod
    def _guide_cross(support, point, guide_dir):
        """Support cross-boundary direction at a guide point, oriented
        away from the support's interior."""
        surf = support.Surface
        u, v = surf.parameter(point)
        normal = support.normalAt(u, v)
        cross = normal.cross(guide_dir)
        if cross.Length < 1e-9:
            return None
        cross.normalize()
        eps = 0.5
        if support.distToShape(Part.Vertex(point + cross * eps))[0] \
                < eps * 0.5:
            cross = cross.negative()
        return cross

    def _guided_loft(self, obj, section_pts, section_wires, guide_wires):
        from .extend import _osculating_continue
        n_sec = len(section_pts)
        guides = [self._guide_polyline(g) for g in guide_wires]
        hit_sets = [self._guide_hits(g, section_wires)
                    for g in guide_wires]
        g_supports = [self._guide_support_of(obj, k)
                      for k in range(len(guide_wires))]

        stations = []
        k = min(max(int(obj.Stations), 1), 64)
        for i in range(n_sec - 1):
            p_a, p_b = section_pts[i], section_pts[i + 1]
            # w = 0 .. 1 across the span; skip w=0 after the first span
            # so shared sections appear exactly once
            for j in range(0 if i == 0 else 1, k + 2):
                w = j / (k + 1)
                base = [pa * (1 - w) + pb * w for pa, pb in zip(p_a, p_b)]
                anchors = []  # (guide_index, point_on_guide, guide_dir)

                if len(guide_wires) == 1:
                    (pts, fracs), hits = guides[0], hit_sets[0]
                    a = hits[i][1] * (1 - w) + hits[i + 1][1] * w
                    f = hits[i][0] * (1 - w) + hits[i + 1][0] * w
                    gp = self._guide_point(pts, fracs, f)
                    base = [p + (gp - a) for p in base]
                    anchors.append((0, gp, self._guide_dir(pts, fracs, f)))
                else:
                    (p1s, f1s), h1 = guides[0], hit_sets[0]
                    (p2s, f2s), h2 = guides[1], hit_sets[1]
                    a1 = h1[i][1] * (1 - w) + h1[i + 1][1] * w
                    a2 = h2[i][1] * (1 - w) + h2[i + 1][1] * w
                    fr1 = h1[i][0] * (1 - w) + h1[i + 1][0] * w
                    fr2 = h2[i][0] * (1 - w) + h2[i + 1][0] * w
                    g1 = self._guide_point(p1s, f1s, fr1)
                    g2 = self._guide_point(p2s, f2s, fr2)
                    mapper = self._similarity(a1, a2, g1, g2)
                    base = [mapper(p) for p in base]
                    anchors.append((0, g1, self._guide_dir(p1s, f1s, fr1)))
                    anchors.append((1, g2, self._guide_dir(p2s, f2s, fr2)))

                stations.append(self._station_wire(
                    base, anchors, g_supports))

        return Part.makeLoft(stations, False, obj.Ruled)

    @staticmethod
    def _guide_dir(pts, fracs, f):
        """Guide polyline direction at arc-length fraction f."""
        for i in range(1, len(fracs)):
            if fracs[i] >= f:
                d = pts[i] - pts[i - 1]
                if d.Length > 1e-12:
                    d.normalize()
                    return d
        d = pts[-1] - pts[-2]
        d.normalize()
        return d

    def _station_wire(self, base, anchors, g_supports):
        """Station curve; ends gain support tangency/curvature when the
        matching guide carries a support.

        A constrained end needs room to curve: interpolation samples
        inside the constraint's influence zone are dropped, and the
        tangent magnitude (Scale=False) spans that zone.
        """
        from .extend import _osculating_continue

        total = sum((b - a).Length for a, b in zip(base, base[1:]))
        influence = total * 0.30

        conditions = []  # (at_start, tangent_vec, phantom_or_None)
        for k, gp, gdir in anchors:
            sup, cont = g_supports[k] if k < len(g_supports) else (None, 0)
            if sup is None:
                continue
            cross = self._guide_cross(sup, gp, gdir)
            if cross is None:
                continue
            at_start = (base[0] - gp).Length <= (base[-1] - gp).Length
            phantom = None
            if cont >= 2:
                surf = sup.Surface
                h = max(influence * 0.1, 1e-3)

                def spt(p):
                    u, v = surf.parameter(p)
                    return surf.value(u, v)
                q1 = spt(gp - cross * h)
                q2 = spt(gp - cross * (2 * h))
                phantom = _osculating_continue(
                    [q2, q1, gp], influence * 0.25)
            conditions.append((at_start, cross * influence, phantom))

        if not conditions:
            bs = Part.BSplineCurve()
            bs.interpolate(base)
            return Part.Wire([bs.toShape()])

        # clear the influence zones (keep the endpoints themselves)
        start_c = next((c for c in conditions if c[0]), None)
        end_c = next((c for c in conditions if not c[0]), None)

        acc = [0.0]
        for a, b in zip(base, base[1:]):
            acc.append(acc[-1] + (b - a).Length)

        kept = []
        for i, p in enumerate(base):
            a = acc[i]
            if start_c and 0 < a < influence and i != len(base) - 1:
                continue
            if end_c and 0 < (total - a) < influence and i != 0:
                continue
            kept.append(p)
        if len(kept) < 4:  # keep it interpolable
            kept = [base[0], base[len(base) // 2], base[-1]]

        pts = list(kept)
        tangents = [App.Vector(0, 0, 0)] * len(pts)
        flags = [False] * len(pts)
        if start_c:
            tangents[0], flags[0] = start_c[1], True
            if start_c[2] is not None:
                pts.insert(1, start_c[2])
                tangents.insert(1, App.Vector(0, 0, 0))
                flags.insert(1, False)
        if end_c:
            tangents[-1], flags[-1] = end_c[1].negative(), True
            if end_c[2] is not None:
                pts.insert(len(pts) - 1, end_c[2])
                tangents.insert(len(tangents) - 1, App.Vector(0, 0, 0))
                flags.insert(len(flags) - 1, False)

        bs = Part.BSplineCurve()
        bs.interpolate(Points=pts, Tangents=tangents, TangentFlags=flags,
                       Scale=False)
        return Part.Wire([bs.toShape()])

    # -- end-continuity constrained loft -----------------------------------

    @staticmethod
    def _end_condition(support, point, section_tangent, away_hint, m,
                       order):
        """(tangent_vector, phantom_point_or_None) at one extreme
        section: the cross-boundary direction of the support (scaled to
        m), and for Curvature an extra point on the support's osculating
        continuation to shape the initial curvature."""
        from .extend import _osculating_continue

        surf = support.Surface
        u, v = surf.parameter(point)
        normal = support.normalAt(u, v)
        cross = normal.cross(section_tangent)
        if cross.Length < 1e-9:
            return None, None
        cross.normalize()
        eps = max(m * 0.05, 0.05)
        probe = point + cross * eps
        if support.distToShape(Part.Vertex(probe))[0] < eps * 0.5:
            cross = cross.negative()
        # prefer leaving toward the rest of the surface when possible
        if away_hint is not None and cross.dot(away_hint) < 0 \
                and abs(cross.dot(away_hint)) > 0.5 * away_hint.Length:
            pass  # keep support-side logic authoritative

        phantom = None
        if order == 2:
            q1p = surf.parameter(point - cross * eps)
            q1 = surf.value(*q1p)
            q2p = surf.parameter(point - cross * (2 * eps))
            q2 = surf.value(*q2p)
            phantom = _osculating_continue([q2, q1, point], m * 0.08)
        return cross * m, phantom

    def _constrained_loft(self, obj, sampled, sup_first, c_first,
                          sup_last, c_last):
        n_sec = len(sampled)
        nu = len(sampled[0])

        def section_tangent(pts, u):
            a = pts[max(u - 1, 0)]
            b = pts[min(u + 1, nu - 1)]
            t = b - a
            if t.Length < 1e-12:
                t = App.Vector(1, 0, 0)
            t.normalize()
            return t

        longitudinals = []
        for u in range(nu):
            pts = [sampled[i][u] for i in range(n_sec)]
            params = [0.0]
            for a, b in zip(pts, pts[1:]):
                params.append(params[-1] + max((b - a).Length, 1e-9))
            total = params[-1]
            params = [p / total for p in params]

            tangents = [App.Vector(0, 0, 0)] * len(pts)
            flags = [False] * len(pts)
            extra_pts, extra_params = [], []

            if sup_first is not None and c_first > 0:
                m = max((pts[1] - pts[0]).Length, 1e-6)
                t0 = section_tangent(sampled[0], u)
                vec, phantom = self._end_condition(
                    sup_first, pts[0], t0, pts[1] - pts[0], m, c_first)
                if vec is not None:
                    tangents[0], flags[0] = vec, True
                    if phantom is not None:
                        extra_pts.append((1, phantom))
                        extra_params.append(0.08 * params[1])
            if sup_last is not None and c_last > 0:
                m = max((pts[-1] - pts[-2]).Length, 1e-6)
                t1 = section_tangent(sampled[-1], u)
                vec, phantom = self._end_condition(
                    sup_last, pts[-1], t1, pts[-2] - pts[-1], m, c_last)
                if vec is not None:
                    # curve runs toward the last point: exit derivative
                    tangents[-1], flags[-1] = vec.negative(), True
                    if phantom is not None:
                        extra_pts.append((len(pts) - 1, phantom))
                        extra_params.append(
                            1.0 - 0.08 * (1.0 - params[-2]))

            # merge phantoms by PARAMETER: sequential index-based inserts
            # desynchronize when both extremes carry a phantom (the
            # second index was computed against the un-grown list)
            entries = list(zip(params, pts, tangents, flags))
            entries += [(par, p, App.Vector(0, 0, 0), False)
                        for (_idx, p), par in zip(extra_pts, extra_params)]
            entries.sort(key=lambda z: z[0])
            all_params = [z[0] for z in entries]
            all_pts = [z[1] for z in entries]
            all_tans = [z[2] for z in entries]
            all_flags = [z[3] for z in entries]

            bs = Part.BSplineCurve()
            bs.interpolate(Points=all_pts, Parameters=all_params,
                           Tangents=all_tans, TangentFlags=all_flags)
            longitudinals.append((bs, all_params[0], all_params[-1]))

        # stations: evaluate every longitudinal at a shared t grid
        k = min(max(int(obj.Stations), 2), 64)
        n_st = (n_sec - 1) * (k + 1) + 1
        stations = []
        for s in range(n_st):
            t = s / (n_st - 1)
            row = []
            for bs, t0, t1 in longitudinals:
                row.append(bs.value(t0 + t * (t1 - t0)))
            st = Part.BSplineCurve()
            st.interpolate(row)
            stations.append(Part.Wire([st.toShape()]))
        return Part.makeLoft(stations, False, False)

    # -- build -------------------------------------------------------------

    def build(self, obj):
        sections = resolve_linksublist(obj.Sections)
        if len(sections) < 2:
            raise GSFeatureError("pick at least two section curves")
        wires = self._as_wires(sections, "sections")

        guides_raw = resolve_linksublist(obj.Guides) if obj.Guides else []
        if len(guides_raw) > 2:
            raise GSFeatureError(
                "up to two guides are supported for now")
        guide_wires = self._as_wires(guides_raw, "guides") \
            if guides_raw else []

        # end-continuity constraints (CATIA: extreme sections only)
        sec_conts = list(obj.SectionContinuities or [])
        n_rows = len(self._entries_flat(obj.Sections))
        for mid in range(1, max(n_rows - 1, 1)):
            if mid < len(sec_conts) and sec_conts[mid] > 0:
                App.Console.PrintWarning(
                    "[GenSurf] MultiSection: continuity on a MIDDLE "
                    f"section (row {mid + 1}) has no effect — only the "
                    "first and last sections take supports (as in "
                    "CATIA)\n")
        sup_first, c_first = self._row_support(
            obj.SectionSupports, obj.SectionSupportRows, sec_conts,
            0, "section")
        sup_last, c_last = self._row_support(
            obj.SectionSupports, obj.SectionSupportRows, sec_conts,
            n_rows - 1, "section") if n_rows > 1 else (None, 0)
        constrained = (c_first > 0) or (c_last > 0)
        if constrained and guide_wires:
            raise GSFeatureError(
                "support continuity combined with guides is not "
                "supported yet — use one or the other")

        if constrained:
            n = min(max(int(obj.Samples), 8), 200)
            sampled = [self._sample(w, n, obj.Coupling) for w in wires]
            if obj.AutoOrient:
                sampled = self._orient(sampled)
            try:
                return self._constrained_loft(
                    obj, sampled, sup_first, c_first, sup_last, c_last)
            except Part.OCCError as err:
                raise GSFeatureError(f"constrained loft failed: {err}")

        if not guide_wires:
            loft_wires = wires
            if obj.AutoOrient:
                n = min(max(int(obj.Samples), 8), 200)
                sampled = self._orient(
                    [self._sample(w, n, obj.Coupling) for w in wires])
                # rebuild only the wires that need flipping
                loft_wires = []
                for w, pts in zip(wires, sampled):
                    if (w.Vertexes[0].Point - pts[0]).Length > 1e-9 \
                            and len(w.Vertexes) > 1:
                        rev = w.copy()
                        rev.reverse()
                        loft_wires.append(rev)
                    else:
                        loft_wires.append(w)
            try:
                return Part.makeLoft(loft_wires, False, obj.Ruled)
            except Part.OCCError as err:
                raise GSFeatureError(f"loft failed: {err}")

        n = min(max(int(obj.Samples), 8), 200)
        sampled = [self._sample(w, n, obj.Coupling) for w in wires]
        if obj.AutoOrient:
            sampled = self._orient(sampled)
        try:
            return self._guided_loft(obj, sampled, wires, guide_wires)
        except Part.OCCError as err:
            raise GSFeatureError(f"guided loft failed: {err}")


def make_multisection(doc, name="MultiSection"):
    return make_feature(doc, MultiSection, name)


register(MultiSection, make_multisection)
