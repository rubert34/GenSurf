# GenSurf — Generative Surfaces for FreeCAD

A generative surfacing workbench, built natively on FreeCAD's
parametric core.

GenSurf brings history-based surface modelling to FreeCAD: construction
curves first, surfaces on top, everything parametric, everything
organised in **construction sets** that keep helper geometry apart from
the surfaces that matter. The way of working is that of
history-based surfacing as found in tools such as CATIA, Creo, NX and
SOLIDWORKS. GenSurf is an independent project with its own operators,
vocabulary and interface; it is not affiliated with or endorsed by any
of their vendors.

## What's inside

**40 parametric operators** on five task toolbars, with fly-out groups
that bring related operators together:

- **Sets** — Construction Set and Set Active: new curves, sketches and
  surfaces land in the active set automatically.
- **Curves** — Point, Line and Plane, plus four groups:
  - *Curve shapes:* Circle (five definitions, arc limits), Spline
    (per-point tangents and tensions), Helix (pitch / revolutions /
    height, taper, winding sense), Spine.
  - *Curve fillet & bridge:* Curve Fillet (trimming, choice among the
    possible fillets), Bridge Curve (G0 / G1 / G2 at each end, with
    tension).
  - *Offset curves:* Offset Curve on Surface (Euclidean or geodesic
    distance), Offset Curve 3D.
  - *Derive curves:* Extract (several faces or edges at once, each with
    its own propagation, or their complement), Boundary Curves
    (propagation and limits), Intersection, Projection.
- **Surfaces**
  - *Basic surfaces:* Extrude, Revolve, Sphere, Offset Surface.
  - *Surfaces from curves:* four sweeps, one per profile — Sweep Curve
    (1 rail, 2 rails, rail + direction), Sweep Ruled (between rails,
    rail 2 as middle, angle to a surface, draft from a direction), Sweep
    Arc (through 3 rails, 2 rails + radius, around a center rail) and
    Sweep Conic (exact rational conics tangent to 2 surfaces, or through
    5 rails); Loft (sections and rails, with G1 / G2 supports at the end
    sections and along the rails); Fill (true per-edge G0 / G1 / G2,
    passing points); Blend (G0 / G1 / G2 per side, with tension).
- **Edit**
  - *Cut & combine:* Split, Trim, Join (connectivity, manifold and
    tangency checks), Make Solid (caps planar openings).
  - *Edges & fillets:* Surface Fillet, Edge Fillet, Chamfer.
  - Extend: natural continuation of curves and surfaces (the underlying
    mathematics is continued exactly), or tangent or curvature
    extension.
  - *Transform:* Translate, Rotate, Scale (about a point, plane or
    line), Symmetry.
  - Heal: geometry repair, small-edge clean-up, simplification.
- **Inspect** — Curvature Comb.

Every operator has a pick-driven task panel (select inputs in the 3D
view, set parameters, OK / Apply / Cancel), idles quietly until its
inputs are complete, and recomputes parametrically when upstream
geometry changes. The terms GenSurf uses are defined in
[docs/glossary.md](docs/glossary.md).

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
**more than 200 headless regression tests** that run against FreeCAD's
own core on every change — each operator's mathematics (continuity
conditions, extrapolation, conic exactness, propagation semantics) is
verified numerically, not just visually.

Documents saved with earlier GenSurf versions keep opening and
recomputing identically: renamed operators, options and values are
migrated when the document loads, and a geometry algorithm that changes
keeps its old behaviour for existing objects until you choose
"Upgrade to current algorithm". See [CHANGELOG.md](CHANGELOG.md).

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
GenSurf/
├── package.xml            addon metadata
├── Init.py                headless init (registers feature classes)
├── InitGui.py             workbench + toolbars (GUI only)
├── gensurf/
│   ├── containers/        construction sets, active-set logic
│   ├── features/          feature framework + one file per operator
│   ├── migrations.py      old → new names for older documents
│   └── ui/                commands, task panels, selection manager
├── docs/                  glossary
├── resources/icons/       generated by tools/gen_icons.py
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
(Anthropic). The workflow: each operator is designed around what the
user wants to achieve, drawing on the mathematics of surface modelling,
implemented as a self-contained parametric feature, covered by numeric
regression tests, and validated in an interactive FreeCAD session
before release.

License: LGPL-2.1-or-later (see LICENSE).
