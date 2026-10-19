# OCCT features reachable from Python

What GenSurf can call, checked on **FreeCAD 1.1.2 (macOS bundle),
OCCT 7.8.1**, 19 October 2026. Later work packages cite this page;
`tests/test_occt_exposure.py` re-checks the FreeCAD-side facts on every
test run, so a FreeCAD upgrade that changes them shows up as a failure.

## Two ways in

1. **FreeCAD's own Python API** (`Part`, `Surface`): always present. This
   is what GenSurf uses today.
2. **pythonocc-core** (`import OCC.Core...`): version 7.8.1.1, licensed
   LGPL-3.0-or-later, matching the OCCT of the bundle. It ships inside
   this FreeCAD bundle, but it is **not guaranteed in other FreeCAD
   builds** (not verified on the Linux AppImage, Windows installer or
   distribution packages). Shapes cross between the two worlds as BRep
   files (`Shape.exportBrep` → `breptools.Read`, and back); this works
   (tested) but costs a file write and read per transfer.

Using pythonocc would be a new runtime dependency, which needs the
owner's decision. Until then, anything that relies on it must be
optional, with a fallback.

## Findings

| OCCT feature | FreeCAD API | pythonocc | Verdict |
|---|---|---|---|
| `GeomLib::ExtendSurfByLength` | not exposed | exposed, **unusable**: the wrapper does not hand back the replaced surface handle (surface bounds unchanged after the call) | GenSurf keeps its own extension: analytic continuation, and B-spline surfaces rebuilt on an enlarged parameter range (WP 3.4) |
| `LocalAnalysis_SurfaceContinuity` | not exposed | works (tested on a G1 and a G2 blend) | Its "G2 curvature gap" reported 0.025 where the normal-curvature gap across the edge is 0.05: it appears to compare mean curvature. WP 1.2 builds its own checker on the FreeCAD API and may use this one as a cross-check |
| Surface differential geometry | `Surface.normal`, `Surface.curvature(u, v, "Max"/"Min"/"Mean"/"Gauss")`, `Surface.curvatureDirections`, `Face.derivative1At` / `derivative2At`, `Face.curvatureAt` | also available | Enough for GenSurf's own G0 / G1 / G2 measurement (WP 1.2), tested below |
| `BRepOffsetAPI_MakeFilling` errors | `MakeFilling.G0Error([i])`, `G1Error([i])`, `G2Error([i])` exposed | also available | **Fill does not read them yet** (`fill.py`), so a G2 request can silently come out lower. WP 1.6 |
| `BRepOffsetAPI_ThruSections::SetParType` (and `SetCriteriumWeight`, `SetSmoothing`) | not exposed: `Part.makeLoft(wires, solid, ruled, closed, maxDegree)` only | exposed | Loft parametrization (chord / centripetal / uniform, WP 3.5) needs pythonocc or GenSurf's own fit |
| `Law_*` + `BRepOffsetAPI_MakePipeShell::SetLaw` | `MakePipeShell` exposes no `setLaw` (modes, auxiliary spine, binormal, max degree/segments, tolerance only) | `Law` module and `MakePipeShell.SetLaw` exposed | WP 2.1 evaluates laws in Python (cached 1D B-splines) and builds sections itself; `SetLaw` only as an optional fast path |
| `GeomFill_BSplineCurves` (Coons / stretched / curved 4-sided patch) | indirectly, through the `Surface::GeomFillSurface` document object (`FillType`: Stretched, Coons, Curved); also `BSplineSurface.buildFromNSections` | exposed | WP 3.3's exact 4-sided mode can start from `Surface::GeomFillSurface`; imposing G1/G2 by control-point rows is GenSurf's own code either way |
| `Geom2dGcc_*` (circles tangent to 2 or 3 elements) | not exposed: `Geom2d.Circle2d` offers `getCircleCenter` and `intersectCC` only | `Geom2dGcc_Circ2d3Tan`, `Geom2dGcc_Circ2d2TanRad` exposed (present, not exercised) | WP 4.4: pythonocc, or GenSurf's own Newton solve |
| Curve blends of any order | `Surface.BlendCurve(BlendPoint, BlendPoint)` with `BlendPoint(vectors)`: a curve matching given derivatives at both ends | — | Candidate engine for Bridge Curve G3 (WP 5.3) |
| Other surfacing document objects | `Surface::Filling`, `Surface::Sections`, `Surface::Extend`, `Surface::GeomFillSurface` | — | Usable as references; GenSurf operators stay self-contained |

## Open question from the plan: does Blend's G2 mode really match curvature?

**Yes, measured.** A blend leaves a straight boundary edge of a cylinder
patch (radius 20 mm) towards a parallel line; its curvature across the
edge is compared with the cylinder's (1/20 = 0.05 mm⁻¹, towards the
axis), at three heights along the edge:

| Blend continuity | Tangent-plane angle | Blend curvature vector | Support | Gap |
|---|---|---|---|---|
| G1 Tangent | 0.0000° | (0, 0, 0) | (0, −0.0500, 0) | 0.05 (100 %) |
| G2 Curvature | 0.0000° | (0, −0.0499, 0) | (0, −0.0500, 0) | 0.00009 (0.18 %) |

OCCT's own checker agrees (G2 mode: `IsG2` true; G1 mode: `IsG1` true,
`IsG2` false). The 0.18 % gap comes from the finite-difference sampling
of the support curvature and is inside the 2 % "Standard" tolerance of
WP 1.1. `test_blend_g2_matches_support_curvature` keeps this measured.

## Consequences for the plan

- WP 1.2 (Continuity Check): build on the FreeCAD API; no dependency
  needed.
- WP 1.6 (Quality retrofit): Fill can read its errors today.
- WP 2.1 (Law), 3.4 (Extend), 3.5 (Loft), 4.4 (Circle): either accept
  pythonocc as an optional dependency (owner's decision, after checking
  the other FreeCAD builds) or implement the missing pieces in GenSurf.
- WP 3.6 (Blend v2): the G2 path is sound; work on G3 and tension laws.
