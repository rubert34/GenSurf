# GenSurf glossary

The words GenSurf uses, each followed by the general concept behind it.
Most are standard terms of surface modelling and of the geometry
textbooks; where GenSurf gives a word a precise meaning, the entry says
so.

## Organisation

| Term | Meaning |
|---|---|
| **Construction Set** | A container in the model tree that groups related geometry: helper points, curves and planes apart from the surfaces built from them. Sets can be nested. An *ordered* set keeps its children as a linear history. |
| **Active set** | The construction set that receives every newly created feature (and new sketches). There is exactly one per document. |
| **Set Active** | The command that makes the selected construction set the active one. |
| **Operator** | One kind of GenSurf feature (Loft, Fill, Split …), created from a toolbar command. |
| **Feature** | One parametric object made by an operator. It recomputes when its inputs change. |
| **Input** / **role** | A slot of an operator that takes picked geometry, such as *Profile*, *Rail 1* or *Support*. |
| **Algorithm version** (`GenSurfAlgo`) | The version of an operator's mathematics a feature is built with. Old features keep their version, so old documents recompute identically; *Upgrade to current algorithm* moves one forward. |
| **Migration** | The renaming of old types, properties and option values when a document saved by an earlier version is opened. |

## Curves and references

| Term | Meaning |
|---|---|
| **Support** | The surface (or plane) that a curve lies on, or against which a continuity condition is measured. |
| **Section** | A curve that a surface must pass through, across its main direction (Loft). |
| **Profile** | The curve that is moved along a path to make a sweep. |
| **Rail** | A curve that a surface must follow along its main direction (Loft, sweeps). |
| **Spine** | A curve that sets the orientation of the moving profile planes, independent of the rails. The Spine operator builds one that crosses given planes at right angles. |
| **Datum plane** | A construction plane; conceptually infinite, displayed as a patch whose size never affects other geometry. |
| **Direction reference** | A picked straight edge (its direction) or planar face (its normal) that sets a direction. |
| **Limit** | A point that cuts a derived curve (Boundary Curves). |

## Continuity

| Term | Meaning |
|---|---|
| **G0 Position** | The two elements touch: no gap. |
| **G1 Tangent** | G0, and the tangents (curves) or tangent planes (surfaces) agree: no crease. |
| **G2 Curvature** | G1, and the curvatures agree: no sudden change in reflections. |
| **G3** | G2, and the rate of change of curvature agrees as well. |
| **Tension** | A factor scaling the end derivatives of a bridge or blend: higher tension holds the end direction longer. 1 is proportional to the chord length. |
| **Coupling** | How points on two curves are paired: by equal arc-length fractions, or by equal parameter (ratio) fractions. |

## Propagation

| Term | Meaning |
|---|---|
| **None** | Only the picked element. |
| **Connected** | Everything connected to the picked element: faces through shared edges, edges through shared vertices. |
| **Tangent** | Connected, and smooth across each junction within a threshold angle. |
| **Whole boundary** | The complete free-boundary loop containing the picked edge (Boundary Curves). |
| **Complementary** | Everything of the source except what the rows captured (Extract). |

## Operators

| Term | Meaning |
|---|---|
| **Point, Line, Plane, Circle, Spline, Helix** | The classic construction elements, each with several ways to define it. |
| **Curve Fillet** | An arc of given radius tangent to two curves, optionally trimming them. |
| **Bridge Curve** | A curve joining the ends of two curves with chosen continuity (G0 / G1 / G2) and tension at each end. |
| **Offset Curve on Surface** | A curve at a constant distance from another on the same support, measured straight (*Euclidean*) or along the surface (*geodesic*). |
| **Offset Curve 3D** | A curve offset perpendicular to a direction, so that the two curves look parallel when viewed along it. |
| **Extract** | Faces or edges pulled out of a shape as their own feature, with propagation. |
| **Boundary Curves** | The free boundary of a surface as a curve. |
| **Intersection, Projection** | The common geometry of two elements; a curve projected onto a surface. |
| **Extrude, Revolve, Sphere, Offset Surface** | Surfaces from a profile pushed along a direction, turned about an axis, a sphere, or a surface offset along its normals. |
| **Sweep** | A surface made by moving a profile along one or more rails. GenSurf has four sweeps, named by profile: *Curve* (any curve), *Ruled* (a straight line), *Arc* (a circle or arc) and *Conic* (an exact conic). Their modes are named by geometry, e.g. *2 rails*, *Rail + direction*, *Angle to surface*. |
| **Conic parameter** | The fullness of a conic section: 0.5 is a parabola, below is an ellipse, above a hyperbola. |
| **Loft** | A surface through ordered sections, optionally following rails, with optional continuity to supports at the end sections and along the rails. |
| **Fill** | An n-sided patch bounded by a closed loop of curves, with per-edge continuity and optional passing points. |
| **Blend** | A surface between two curves with chosen continuity to the supports on each side. |
| **Split, Trim** | Cut one element by another and keep one side; cut two elements by each other and join what is kept. |
| **Join** | Assemble surfaces or curves into one element, with connectivity, manifold and tangency checks. |
| **Make Solid** | Turn a closed set of surfaces into a solid. |
| **Surface Fillet, Edge Fillet, Chamfer** | A rolling-ball fillet between two surfaces; rounding or bevelling the edges of a surface. |
| **Extend** | Continue a curve or surface past an end. *Natural* extension continues the underlying mathematics exactly (an arc stays on its circle); *Tangent* and *Curvature* add a straight or curving continuation. |
| **Translate, Rotate, Scale, Symmetry** | Transformed copies of an element. |
| **Heal** | Repair surfaces: fix invalid geometry, remove tiny edges, merge faces lying on the same surface. |
| **Curvature Comb** | A display of curvature along a curve as spikes normal to it, whose lengths are proportional to the curvature. |
| **Solution** | When a construction has several valid results (e.g. fillets on either side), the one to keep. |
| **Station** | One of the positions along a rail where a sweep or loft builds its section before the sections are joined. |
