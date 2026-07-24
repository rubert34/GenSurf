# [Announcement] GenSurf — a Generative Shape Design (GSD) style surfacing workbench

Hello everyone,

I'd like to share a new workbench I've been building: **GenSurf —
Generative Surfaces for FreeCAD**.

## What is "Generative Shape Design"?

If you've never used CATIA: Generative Shape Design (GSD) is the
surfacing environment that much of the automotive and aerospace world
models in every day. Its working method is different from solid-first
CAD. You build **construction wireframe first** — points, lines,
planes, projections, intersections, parallels, spines — and then
stretch **styling surfaces** over that skeleton: sweeps,
multi-sections, blends, fills. Everything stays parametric, and
everything is organized in **Geometrical Sets**, so the construction
geometry that got you there stays cleanly separated from the surfaces
you actually care about. Once you've worked this way, it's hard to go
back — it is, in my view, the most efficient surfacing workflow ever
put in a CAD package.

GenSurf brings that workflow to FreeCAD, natively, on FreeCAD's own
parametric core — nothing external, just Part/OCC and FeaturePython.

## What's in it today

39 parametric operators across CATIA-style toolbars with fly-out
button groups:

- **Wireframe:** Point, Line, Plane, Projection, Intersection, Circle
  (five definition types), Corner, Connect Curve, Spline, Helix,
  Spine, Parallel Curve, 3D Curve Offset
- **Surfaces:** Extrude, Revolve, Sphere, Offset, **Swept Surface in
  all four profile types** (Explicit / Line / Circle / Conic — the
  conic sweep produces true rational conic sections), Fill,
  Multi-Sections (with per-section and per-guide support surfaces and
  G0/G1/G2 continuity), Blend
- **Operations:** Join, Split, Trim, Boundary, Extract, Multiple
  Extract, Shape Fillet, Edge Fillet, Chamfer, Translate, Rotate,
  Scale, Symmetry, Extend (with mathematically *natural*
  extrapolation — the way Rhino extends, not the odd flattening some
  packages do)

Each operator gets a CATIA-style task dialog: click the tool, pick
your inputs in the 3D view, set parameters, Preview/OK. Features idle
quietly until their inputs are complete instead of erroring, and
geometrical sets capture new sketches automatically.

## About the project

The goal is serious: a surfacing environment that aims at the
efficiency of the professional packages — CATIA, Solidworks, NX —
rather than a collection of scripts. Concretely that means: strict
CATIA-fidelity behaviors (operator by operator, dialog by dialog),
one self-contained parametric feature per operator, and a suite of
**166 headless regression tests** that verify the actual mathematics
(continuity conditions, conic exactness, propagation semantics,
extrapolation) against FreeCAD's core on every change. Where a CATIA
option isn't implemented yet, the operator's documentation says so
explicitly — nothing is silently approximated.

Full disclosure on the development method, because I believe in being
upfront: I specify each operator against real CATIA GSD behavior and
validate every release by hand in FreeCAD; the implementation work is
done with Claude (Anthropic's AI) as the coding engine. Every line is
exercised by the numeric test suite before it ships. Judge the tool by
what it does — the repository and tests are open.

**Repository / installation:** https://github.com/rubert34/GenSurf — install via the Addon
Manager (add the repository URL as a custom repository) or copy the
folder into your `Mod` directory. FreeCAD 1.0+.
License: LGPL-2.1-or-later.

## Found a problem? Here's how to report it so it gets fixed

Post it in this thread with three things:

1. **What you were trying to achieve** — the modeling intent, not
   just the button you pressed;
2. **What actually happened** — a screenshot, the error text from the
   Report view if any, and ideally the .FCStd file (or a minimal
   version of it);
3. **What you expected to happen** — especially valuable if you know
   how CATIA/Solidworks behaves for the same operation.

Reports in that format are usually reproducible immediately, and
reproducible issues get fixed fast.

Looking forward to your feedback — and your surface models.

rubert34
