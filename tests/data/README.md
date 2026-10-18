# Test documents

Frozen documents saved by earlier GenSurf versions. They are never
regenerated: their purpose is to prove that old files keep opening and
recomputing identically (`tests/test_migrations.py`).

| File | Saved by | Contents |
|---|---|---|
| `GenSurf_Demo.FCStd` | 0.24 (before the Blend `Borders` option) | The demo model: two sets, points, splines, extrudes and a curvature-continuous blend |
| `gensurf_v028_legacy.FCStd` | 0.28.0 schema | One object of every operator and mode renamed or merged after 0.28: loft with rails and supports, blend, bridge curve, curve fillet, offset curves, surface fillet, single and multi-pick extracts, boundary curves, heal, make solid, and every sweep mode |

The test compares each recomputed shape with the shape stored in the
file (`tests/helpers/shape_fingerprint.py`).
