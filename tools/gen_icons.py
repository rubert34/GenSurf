#!/usr/bin/env python3
"""Generate the Generative Surfaces icon set — FreeCAD-native (Tango) style.

Visual language:
  - blue gradient surfaces  (#71b2f8 -> #16437e, dark navy outline)  = surface geometry
  - gold gradient surfaces  (#fce94f -> #e08e00, chocolate outline)  = secondary/support surfaces
  - red cased curves        (#ef2929 over #7c0000)                    = wireframe results / boundaries
  - sky-blue strokes        (#729fcf / #3465a4), dashed when datum    = construction geometry
  - green solid arrows      (#8ae234 -> #4e9a06, dark green outline)  = actions / directions
Geometry fills the 64px canvas nearly edge-to-edge.
"""
import math, os

# writes straight into the addon's icon folder (the generator is the source
# of truth for every icon it lists; CurvatureComb and Heal are hand-drawn)
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "resources", "icons")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- palette
BLUE_S   = "#0a1c38"   # outline for blue surfaces
GOLD_S   = "#5c3a04"   # outline for gold surfaces
RED      = "#ef2929"; RED_D = "#7c0000"
CON      = "#729fcf"; CON_D = "#3465a4"
GRN      = "#8ae234"; GRN_D = "#4e9a06"; GRN_S = "#1e4506"
HILITE   = "#c3ddfa"   # light rim line on blue surfaces

DEFS = """<defs>
<linearGradient id="bV" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#71b2f8"/><stop offset="1" stop-color="#16437e"/></linearGradient>
<linearGradient id="bV2" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#a8cef8"/><stop offset="1" stop-color="#2f6bb8"/></linearGradient>
<linearGradient id="bD" x1="0" y1="0" x2="1" y2="1">
 <stop offset="0" stop-color="#71b2f8"/><stop offset="1" stop-color="#16437e"/></linearGradient>
<linearGradient id="gV" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#fce94f"/><stop offset="1" stop-color="#e08e00"/></linearGradient>
<linearGradient id="gnV" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#8ae234"/><stop offset="1" stop-color="#4e9a06"/></linearGradient>
<linearGradient id="oV" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#fcaf3e"/><stop offset="1" stop-color="#ce5c00"/></linearGradient>
<radialGradient id="sph" cx="0.35" cy="0.3" r="0.9">
 <stop offset="0" stop-color="#cfe6ff"/><stop offset="0.55" stop-color="#5b9de0"/>
 <stop offset="1" stop-color="#123a70"/></radialGradient>
<radialGradient id="gsph" cx="0.35" cy="0.3" r="0.9">
 <stop offset="0" stop-color="#faff2b"/><stop offset="1" stop-color="#e08e00"/></radialGradient>
</defs>"""

def svg(body):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" '
            'viewBox="0 0 64 64">\n' + DEFS + "\n" + body + "\n</svg>\n")

# ---------------------------------------------------------------- helpers
def rcurve(d, w=4.2, cw=None, dash=None):
    """Red result curve: dark casing + bright core."""
    cw = cw or w + 2.6
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<path d="{d}" fill="none" stroke="{RED_D}" stroke-width="{cw}" '
            f'stroke-linecap="round"{da}/>\n'
            f'<path d="{d}" fill="none" stroke="{RED}" stroke-width="{w}" '
            f'stroke-linecap="round"{da}/>')

def bcurve(d, w=3.6, dash=None, color=CON_D):
    da = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" '
            f'stroke-linecap="round"{da}/>')

def surf(d, grad="bV", sw=2.4, stroke=None, extra=""):
    stroke = stroke or (GOLD_S if grad in ("gV", "oV", "gsph") else BLUE_S)
    return (f'<path d="{d}" fill="url(#{grad})" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linejoin="round" {extra}/>')

def ghost(d, hue="b"):
    fill = "#71b2f8" if hue == "b" else "#fce94f"
    return (f'<path d="{d}" fill="{fill}" fill-opacity="0.30" stroke="{CON_D}" '
            f'stroke-width="2.2" stroke-dasharray="4 3" stroke-linejoin="round"/>')

def rghost(d):
    return (f'<path d="{d}" fill="{RED}" fill-opacity="0.22" stroke="{RED_D}" '
            f'stroke-width="2.2" stroke-dasharray="4 3" stroke-linejoin="round"/>')

def dot(x, y, r=5.5, fill=RED, ring=RED_D):
    return (f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{ring}" '
            f'stroke-width="2"/>')

def gdot(x, y, r=4):
    return dot(x, y, r, GRN, GRN_S)

def _pt(p): return f"{round(p[0],1)} {round(p[1],1)}"

def arrow(x1, y1, x2, y2, w=5.5, hw=13, hl=11):
    """Solid green arrow polygon from (x1,y1) to (x2,y2)."""
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    bx, by = x2 - ux * hl, y2 - uy * hl
    pts = [(x1 + nx*w/2, y1 + ny*w/2), (bx + nx*w/2, by + ny*w/2),
           (bx + nx*hw/2, by + ny*hw/2), (x2, y2),
           (bx - nx*hw/2, by - ny*hw/2), (bx - nx*w/2, by - ny*w/2),
           (x1 - nx*w/2, y1 - ny*w/2)]
    d = "M " + " L ".join(_pt(p) for p in pts) + " Z"
    return (f'<path d="{d}" fill="url(#gnV)" stroke="{GRN_S}" stroke-width="1.8" '
            f'stroke-linejoin="round"/>')

def arrowhead(tip, ang_deg, hw=13, hl=11, fill="url(#gnV)", stroke=GRN_S):
    """Solid triangular head pointing along ang_deg at tip."""
    a = math.radians(ang_deg)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    bx, by = tip[0] - ux*hl, tip[1] - uy*hl
    pts = [(bx + nx*hw/2, by + ny*hw/2), tip, (bx - nx*hw/2, by - ny*hw/2)]
    d = "M " + " L ".join(_pt(p) for p in pts) + " Z"
    return (f'<path d="{d}" fill="{fill}" stroke="{stroke}" stroke-width="1.8" '
            f'stroke-linejoin="round"/>')

ICONS = {}

# ============================================================ wireframe
ICONS["Point"] = (
    bcurve("M3 50 Q 32 12 61 40", dash="7 5") +
    dot(32, 30, 8.5) +
    '<circle cx="29" cy="27" r="2.4" fill="#ffc9c9"/>'
)

ICONS["Line"] = (
    bcurve("M1 60 L 63 4", w=2, dash="5 4", color=CON) +
    rcurve("M7 55 L 57 9", w=5, cw=8) +
    dot(7, 55, 6) + dot(57, 9, 6)
)

ICONS["Plane"] = (
    ghost("M16 38 L 36 20 L 62 20 L 42 38 Z") +
    surf("M2 60 L 22 40 L 60 40 L 40 60 Z") +
    f'<path d="M2 60 L 22 40 L 60 40" fill="none" stroke="{HILITE}" stroke-width="2" stroke-linejoin="round"/>' +
    arrow(28, 36, 28, 6)
)

ICONS["Circle"] = (
    bcurve("M32 34 L 50 16", w=3, dash="6 4") +
    rcurve("M32 8 A 26 26 0 1 0 32.01 8 Z", w=4.6) +
    dot(32, 34, 4.5)
)

ICONS["Spline"] = (
    bcurve("M4 56 L 18 14 L 44 52 L 60 8", w=2.4, dash="5 4", color=CON) +
    rcurve("M4 56 C 14 22 32 62 60 8", w=4.6) +
    '<rect x="14.5" y="10.5" width="7" height="7" fill="#fff" stroke="#3465a4" stroke-width="2.2"/>' +
    '<rect x="40.5" y="48.5" width="7" height="7" fill="#fff" stroke="#3465a4" stroke-width="2.2"/>' +
    dot(4, 56, 5) + dot(60, 8, 5)
)

ICONS["Helix"] = (
    bcurve("M32 2 L 32 62", w=2.6, dash="6 4") +
    bcurve("M55 47 Q 32 58 9 38", w=3.4, color="#e26b6b") +
    bcurve("M55 29 Q 32 40 9 20", w=3.4, color="#e26b6b") +
    rcurve("M9 56 Q 32 46 55 47", w=4.4) +
    rcurve("M9 38 Q 32 28 55 29", w=4.4) +
    rcurve("M9 20 Q 32 10 55 11", w=4.4)
)

ICONS["CurveFillet"] = (
    bcurve("M9 2 L 9 28", w=5) +
    bcurve("M36 55 L 62 55", w=5) +
    rcurve("M9 28 Q 9 55 36 55", w=5) +
    gdot(9, 28) + gdot(36, 55)
)

ICONS["BridgeCurve"] = (
    bcurve("M2 12 Q 12 5 21 14", w=5) +
    bcurve("M43 50 Q 52 59 62 52", w=5) +
    rcurve("M21 14 C 38 30 26 34 43 50", w=4.4) +
    gdot(21, 14, 4.5) + gdot(43, 50, 4.5)
)

ICONS["OffsetCurve3D"] = (
    bcurve("M4 58 Q 18 24 34 42 Q 46 54 60 34", w=4.6) +
    rcurve("M4 36 Q 18 2 34 20 Q 46 32 60 12", w=4.4, dash="9 6") +
    arrow(12, 46, 12, 24, w=4.5, hw=11, hl=9)
)

ICONS["OffsetCurveOnSurface"] = (
    surf("M2 58 L 14 12 L 62 12 L 50 58 Z", "bV2", sw=2.2) +
    bcurve("M12 46 Q 32 32 56 40", w=4.2, color="#16437e") +
    rcurve("M17 28 Q 36 14 60 22", w=4.2) +
    arrow(30, 36, 34, 22, w=4, hw=10, hl=8)
)

ICONS["Intersection"] = (
    surf("M2 36 L 24 14 L 62 24 L 40 46 Z", "gV") +
    surf("M22 2 L 42 8 L 34 62 L 14 56 Z", extra='fill-opacity="0.92"') +
    rcurve("M30 22 L 36 40", w=4.4) +
    dot(33, 31, 4.5)
)

ICONS["Projection"] = (
    rcurve("M8 9 Q 32 -2 56 9", w=4.4) +
    arrow(18, 16, 18, 32, w=4, hw=10, hl=8) +
    arrow(46, 16, 46, 32, w=4, hw=10, hl=8) +
    surf("M2 54 L 20 38 L 62 38 L 44 54 Z") +
    bcurve("M12 50 Q 32 42 52 46", w=3.8, color="#a40000")
)

ICONS["BoundaryCurves"] = (
    f'<path d="M12 12 Q 32 3 52 12 Q 61 32 52 52 Q 32 61 12 52 Q 3 32 12 12 Z" '
    f'fill="#71b2f8" fill-opacity="0.35"/>' +
    rcurve("M12 12 Q 32 3 52 12 Q 61 32 52 52 Q 32 61 12 52 Q 3 32 12 12 Z", w=4.6)
)

ICONS["Spine"] = (
    rcurve("M5 58 Q 26 44 33 31 Q 40 18 59 6", w=4.4) +
    ghost("M2 44 L 15 36 L 28 44 L 15 52 Z") +
    ghost("M20 27 L 33 19 L 46 27 L 33 35 Z") +
    ghost("M38 10 L 51 2 L 64 10 L 51 18 Z")
)

# ============================================================ surfaces
ICONS["Extrude"] = (
    surf("M3 57 Q 32 43 61 57 L 61 21 Q 32 7 3 21 Z") +
    f'<path d="M3 21 Q 32 7 61 21" fill="none" stroke="{HILITE}" stroke-width="2.2"/>' +
    rcurve("M3 57 Q 32 43 61 57", w=4.2) +
    arrow(32, 40, 32, 12)
)

ICONS["Revolve"] = (
    bcurve("M30 4 L 30 62", w=2.6, dash="6 4") +
    surf("M8 24 A 24 9 0 0 0 56 24 L 47 54 A 15 6 0 0 1 17 54 Z") +
    f'<ellipse cx="32" cy="24" rx="24" ry="9" fill="url(#bV2)" stroke="{BLUE_S}" stroke-width="2.2"/>' +
    rcurve("M56 24 Q 54 42 47 54", w=4.2) +
    f'<path d="M12 10 A 25 11 0 0 1 46 7" fill="none" stroke="{GRN_D}" stroke-width="4.6" stroke-linecap="round"/>' +
    arrowhead((50, 9), 35)
)

ICONS["Sphere"] = (
    f'<circle cx="32" cy="32" r="29" fill="url(#sph)" stroke="{BLUE_S}" stroke-width="2.4"/>' +
    f'<ellipse cx="32" cy="32" rx="29" ry="10.5" fill="none" stroke="{HILITE}" stroke-width="2.6"/>' +
    f'<ellipse cx="32" cy="32" rx="10.5" ry="29" fill="none" stroke="{HILITE}" stroke-width="2.6"/>'
)

ICONS["Offset"] = (
    surf("M2 62 Q 32 47 62 58 L 62 45 Q 32 34 2 49 Z") +
    surf("M2 30 Q 32 15 62 26 L 62 13 Q 32 2 2 17 Z", "bV2") +
    arrow(16, 44, 16, 26, w=4.8, hw=11, hl=9) +
    arrow(46, 40, 46, 22, w=4.8, hw=11, hl=9)
)

ICONS["Fill"] = (
    surf("M12 12 Q 32 3 52 12 Q 61 32 52 52 Q 32 61 12 52 Q 3 32 12 12 Z") +
    f'<path d="M16 17 Q 32 10 48 17" fill="none" stroke="{HILITE}" stroke-width="2.4" stroke-linecap="round"/>' +
    rcurve("M12 12 Q 32 3 52 12 Q 61 32 52 52 Q 32 61 12 52 Q 3 32 12 12 Z", w=3.6, cw=5.8)
)

ICONS["Loft"] = (
    surf("M3 53 Q 32 41 61 53 L 61 11 Q 32 23 3 11 Z") +
    rcurve("M3 53 Q 32 41 61 53", w=4) +
    rcurve("M4 32 Q 32 40 60 32", w=3.6) +
    rcurve("M3 11 Q 32 23 61 11", w=4)
)

ICONS["Blend"] = (
    surf("M2 4 L 26 4 L 26 20 L 2 20 Z", "gV") +
    surf("M38 44 L 62 44 L 62 60 L 38 60 Z", "gV") +
    surf("M26 4 Q 48 16 38 44 L 38 60 Q 16 48 26 20 Z") +
    f'<path d="M26 4 Q 48 16 38 44" fill="none" stroke="{HILITE}" stroke-width="2"/>'
)

ICONS["SweepCurve"] = (
    surf("M2 60 Q 26 54 34 32 Q 40 16 62 12 L 62 26 Q 46 28 44 40 Q 36 62 2 60 Z") +
    f'<path d="M2 60 Q 26 54 34 32 Q 40 16 62 12" fill="none" stroke="{HILITE}" stroke-width="2"/>' +
    rcurve("M2 60 Q 1 53 2 46", w=4.4) +
    rcurve("M8 52 Q 24 46 30 28 Q 36 12 58 6", w=3.4, cw=5.6, dash="8 6")
)

ICONS["SweepRuled"] = (
    f'<path d="M4 50 Q 30 36 60 44 L 62 16 Q 32 8 6 22 Z" fill="#71b2f8" fill-opacity="0.45"/>' +
    bcurve("M10 46 L 12 20 M 24 41 L 26 15 M 38 39 L 40 13 M 52 41 L 54 15", w=3.2) +
    rcurve("M4 50 Q 30 36 60 44", w=4.4) +
    rcurve("M6 22 Q 32 8 62 16", w=4.4)
)

ICONS["SweepArc"] = (
    surf("M6 58 Q 32 44 62 52 L 62 30 Q 32 22 6 36 Z") +
    f'<path d="M6 36 Q 32 22 62 30" fill="none" stroke="{HILITE}" stroke-width="2"/>' +
    f'<ellipse cx="10" cy="47" rx="7" ry="11.5" fill="#71b2f8" fill-opacity="0.5" '
    f'stroke="{RED_D}" stroke-width="5.6" transform="rotate(-8 10 47)"/>' +
    f'<ellipse cx="10" cy="47" rx="7" ry="11.5" fill="none" '
    f'stroke="{RED}" stroke-width="3.4" transform="rotate(-8 10 47)"/>' +
    bcurve("M14 8 Q 38 2 60 10", w=3, dash="6 4")
)

ICONS["SweepConic"] = (
    surf("M4 14 Q 32 58 60 14 L 60 28 Q 32 72 4 28 Z") +
    rcurve("M4 14 Q 32 58 60 14", w=4) +
    bcurve("M4 14 L 16 30 M 60 14 L 48 30", w=2.8, dash="5 4")
)

ICONS["Join"] = (
    surf("M2 32 Q 16 20 29 26 L 29 46 Q 16 40 2 52 Z") +
    surf("M62 32 Q 48 20 35 26 L 35 46 Q 48 40 62 52 Z", "gV") +
    arrow(10, 8, 26, 16, w=4.6, hw=11, hl=9) +
    arrow(54, 8, 38, 16, w=4.6, hw=11, hl=9)
)

ICONS["Split"] = (
    ghost("M2 54 Q 18 38 30 44 L 30 22 Q 18 16 2 32 Z") +
    surf("M34 44 Q 46 48 62 40 L 62 18 Q 46 26 34 22 Z") +
    rcurve("M32 3 Q 28 32 32 61", w=4.4)
)

ICONS["Trim"] = (
    ghost("M38 10 L 62 10 L 62 26 L 38 26 Z") +
    rghost("M38 28 L 54 28 L 54 44 L 38 44 Z") +
    surf("M2 10 L 38 10 L 38 26 L 2 26 Z") +
    surf("M38 26 L 54 26 L 54 62 L 38 62 Z", "gV") +
    rcurve("M38 10 L 38 26 L 54 26", w=3.4, cw=5.6)
)

ICONS["Extend"] = (
    surf("M2 52 Q 20 38 34 42 L 34 22 Q 20 18 2 32 Z") +
    rghost("M34 42 Q 48 46 62 42 L 62 22 Q 48 26 34 22 Z") +
    arrow(38, 10, 60, 10, w=4.6, hw=11, hl=9)
)

ICONS["EdgeFillet"] = (
    surf("M4 2 L 22 2 L 22 26 Q 22 42 38 42 L 62 42 L 62 60 L 38 60 Q 4 60 4 26 Z") +
    rcurve("M22 26 Q 22 42 38 42", w=4.6) +
    gdot(22, 26, 3.6) + gdot(38, 42, 3.6)
)

ICONS["SurfaceFillet"] = (
    surf("M4 2 L 20 2 L 20 26 L 4 26 Z", "gV") +
    surf("M38 44 L 62 44 L 62 60 L 38 60 Z") +
    f'<path d="M4 26 Q 4 60 38 60 L 38 44 Q 20 44 20 26 Z" fill="url(#bV2)" '
    f'stroke="{BLUE_S}" stroke-width="2.4" stroke-linejoin="round"/>' +
    rcurve("M20 26 Q 20 44 38 44", w=4.2)
)

ICONS["Chamfer"] = (
    surf("M4 2 L 22 2 L 22 22 L 42 42 L 62 42 L 62 60 L 36 60 L 4 28 Z") +
    rcurve("M22 22 L 42 42", w=4.6) +
    gdot(22, 22, 3.6) + gdot(42, 42, 3.6)
)

ICONS["MakeSolid"] = (
    surf("M8 24 L 32 36 L 32 62 L 8 50 Z") +
    surf("M56 24 L 32 36 L 32 62 L 56 50 Z", "bV2") +
    surf("M8 24 L 32 12 L 56 24 L 32 36 Z", "gV") +
    f'<circle cx="52" cy="11" r="10" fill="url(#gnV)" stroke="{GRN_S}" stroke-width="1.8"/>' +
    '<path d="M47 11 L 51 15 L 58 6" fill="none" stroke="#fff" stroke-width="3" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
)

ICONS["Extract"] = (
    ghost("M2 32 L 20 21 L 38 32 L 20 43 Z") +
    ghost("M2 50 L 20 39 L 38 50 L 20 61 Z") +
    surf("M26 21 L 44 10 L 62 21 L 44 32 Z", "gV") +
    arrow(28, 42, 42, 32, w=4.6, hw=11, hl=9)
)

# ============================================================ operations / transforms
ICONS["Translate"] = (
    ghost("M2 40 Q 14 28 26 34 L 26 52 Q 14 46 2 58 Z") +
    surf("M38 18 Q 50 6 62 12 L 62 30 Q 50 24 38 36 Z") +
    arrow(16, 40, 46, 20)
)

ICONS["Rotate"] = (
    ghost("M4 34 Q 10 20 24 24 L 24 42 Q 10 38 4 52 Z") +
    surf("M40 24 Q 54 28 60 42 L 44 48 Q 40 38 32 34 Z") +
    f'<path d="M14 12 A 26 16 0 0 1 46 12" fill="none" stroke="{GRN_D}" '
    f'stroke-width="4.6" stroke-linecap="round"/>' +
    arrowhead((50, 15), 55) +
    f'<circle cx="30" cy="56" r="4.5" fill="#555" stroke="#1a1a1a" stroke-width="1.8"/>'
)

ICONS["Scale"] = (
    f'<path d="M6 58 L 58 58 L 58 6 L 6 6 Z" fill="#71b2f8" fill-opacity="0.2" '
    f'stroke="{CON_D}" stroke-width="3.4" stroke-linejoin="round"/>' +
    ghost("M6 58 L 28 58 L 28 36 L 6 36 Z") +
    arrow(26, 38, 52, 12) +
    dot(6, 58, 5.5)
)

ICONS["Symmetry"] = (
    rcurve("M32 2 L 32 62", w=3, cw=5.2, dash="7 5") +
    surf("M4 40 Q 12 14 26 34 L 26 50 Q 12 32 4 54 Z") +
    ghost("M60 40 Q 52 14 38 34 L 38 50 Q 52 32 60 54 Z")
)

# ============================================================ misc
ICONS["ConstructionSet"] = (
    surf("M2 18 Q 2 13 7 13 L 22 13 L 28 20 L 57 20 Q 62 20 62 25 L 62 51 "
         "Q 62 56 57 56 L 7 56 Q 2 56 2 51 Z", "oV", sw=2.6, stroke="#8f5902") +
    f'<path d="M2 25 L 62 25" stroke="#8f5902" stroke-width="2" opacity="0.55"/>' +
    bcurve("M12 47 Q 26 30 50 38", w=4, color="#16437e") +
    dot(12, 47, 4.5) + dot(50, 38, 4.5)
)

ICONS["SetActive"] = (
    ICONS["ConstructionSet"] +
    f'<circle cx="52" cy="11" r="10" fill="url(#gnV)" stroke="{GRN_S}" stroke-width="1.8"/>' +
    '<path d="M47 11 L 51 15 L 58 6" fill="none" stroke="#fff" stroke-width="3" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
)

ICONS["DevReload"] = (
    f'<path d="M53 36 A 22 22 0 1 1 46 17" fill="none" stroke="{GRN_S}" '
    f'stroke-width="10" stroke-linecap="round"/>' +
    f'<path d="M53 36 A 22 22 0 1 1 46 17" fill="none" stroke="url(#gnV)" '
    f'stroke-width="7" stroke-linecap="round"/>' +
    arrowhead((51, 13), -18, hw=17, hl=14)
)

ICONS["Workbench"] = (
    surf("M2 46 Q 16 8 32 20 Q 48 32 62 12 L 62 34 Q 48 54 32 42 Q 16 30 2 62 Z") +
    f'<path d="M2 46 Q 16 8 32 20 Q 48 32 62 12" fill="none" stroke="{HILITE}" stroke-width="2.6"/>' +
    f'<circle cx="50" cy="13" r="9.5" fill="url(#gsph)" stroke="{GOLD_S}" stroke-width="2"/>'
)

# ---------------------------------------------------------------- write
for name, body in ICONS.items():
    with open(os.path.join(OUT, f"GenSurf_{name}.svg"), "w") as f:
        f.write(svg(body))
print(f"wrote {len(ICONS)} icons to {OUT}")
