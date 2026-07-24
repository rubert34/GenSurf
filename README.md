# GenSurf — Generative Surfaces for FreeCAD

A generative surfacing workbench, built natively on FreeCAD's
parametric core.

GenSurf brings to FreeCAD the surfacing method used by the advanced
parametric CAD packages of the automotive and aerospace world
(Solidworks, NX, CATIA, Creo and the like): construction wireframe
first, styling surfaces on top, everything parametric, everything
organized in **Geometrical Sets** that separate construction geometry
from the surfaces that matter.

## What's inside

**40 parametric operators** across four toolbars, with fly-out button
groups:

- **Structure** — Geometrical Set insertion with an active-set
  workflow: new wireframe, sketches and surfaces land in the active
  set automatically.
- **Wireframe** — Point, Line, Plane, Projection, Intersection,
  Circle (five definition types + arc limitations), Corner (fillet arc
  with trimming and solution cycling), Connect Curve (per-side
  continuity and tension), Spline (per-point tangents), Helix (pitch /
  revolutions / height, taper, orientation), Spine, Parallel Curve
  (Euclidean and geodesic), 3D Curve Offset.
- **Surfaces** — Extrude, Revolve, Sphere, Offset, **Swept Surface in
  all four classic profile types** (Explicit with reference surface /
  two guides / pulling direction; Line with two limits, limit-middle,
  reference surface, draft direction; Circle with three guides, two
  guides + radius, center-based; Conic with true rational-conic
  sections), Fill (per-edge continuity, passing points),
  Multi-Sections (per-section and per-guide supports and continuity),
  Blend (per-side position / tangency / curvature with tension).
- **Operations** — Join (with connectivity / manifold / tangency
  checks), Split, Trim, Boundary (propagation + limits), Extract,
  Multiple Extract, Shape Fillet, Edge Fillet, Chamfer, Translate,
  Rotate, Scale (point / plane / line reference), Symmetry, Extend
  (mathematically natural extrapolation of curves and surfaces —
  Natural / Tangent / Curvature modes), Close Surface (closed
  surfaces into a solid, with planar-hole capping).

Every operator has a pick-driven task dialog (select inputs in the 3D
view, set parameters, OK / Apply / Cancel), idles quietly until its
inputs are complete, and recomputes parametrically when upstream
geometry changes.

## Installation

**Addon Manager (custom repository):** Edit → Preferences → Addon
Manager → Custom Repositories, add this repository's URL, then install
*GenSurf* from the Addon Manager and restart FreeCAD.

**Manual:** clone or download this repository into your FreeCAD `Mod`
directory (`~/.local/share/FreeCAD/Mod/` on Linux,
`~/Library/Application Support/FreeCAD/Mod/` on macOS,
`%APPDATA%\FreeCAD\Mod\` on Windows) and restart FreeCAD.

Then select the **GenSurf** workbench from the workbench selector.
Requires FreeCAD 1.0 or newer.

## Status & quality

Active development. The geometry work is validated by a suite of
**170 headless regression tests** that run against FreeCAD's own core
on every change — each operator's mathematics (continuity conditions,
extrapolation, conic exactness, propagation semantics) is verified
numerically, not just visually.

Some advanced options are intentionally not implemented yet; each
operator's source docstring states precisely what is covered and what
is skipped, so nothing is silently approximated.

## Reporting issues

Please report problems in the project's FreeCAD forum thread, and
include three things: **what you were trying to achieve**, **what
went wrong** (with a screenshot and, if possible, the .FCStd file),
and **what you expected to happen**. That format makes issues
reproducible — and reproducible issues get fixed fast.

## Project layout

```
GenerativeSurfaces/
├── package.xml            addon metadata
├── Init.py                headless init (registers feature classes)
├── InitGui.py             workbench + toolbars (GUI only)
├── gensurf/
│   ├── containers/        GeometricalSet, active-set logic
│   ├── features/          feature framework + one file per feature
│   └── ui/                commands, task panels, selection manager
├── resources/icons/
└── tests/                 headless pytest suite (no GUI required)
```

Each feature is one file declaring `TYPE_ID`, a `PROPERTIES` table and
a `build(obj) -> Part.Shape` method, plus one `register(...)` line.
Run the tests headlessly with:

```
FREECAD_LIB=/path/to/freecad/lib python3 -m pytest tests/ -v
```

## Development

GenSurf is developed by rubert34, with implementation by Claude
(Anthropic). The workflow: each operator is specified against the
behavior of professional surfacing packages, implemented as a
self-contained parametric feature, covered by numeric regression
tests, and validated in an interactive FreeCAD session before release.

License: LGPL-2.1-or-later (see LICENSE).
