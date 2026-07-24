import math

import FreeCAD as App
import Part
import pytest

from conftest import assert_recomputes
from gensurf.features import (
    make_datum_plane, make_projected_curve, make_extruded_surface,
)
from gensurf.features.base import GSFeatureError


def _support_face(doc):
    """A 20x20 planar face at z=0."""
    obj = doc.addObject("Part::Plane", "Support")
    obj.Length = 20
    obj.Width = 20
    doc.recompute()
    return obj


def _line_edge(doc, p1, p2, name="Line"):
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = Part.makeLine(App.Vector(*p1), App.Vector(*p2))
    return obj


# -- DatumPlane ----------------------------------------------------------


def test_datum_plane_offset(doc):
    support = _support_face(doc)
    plane = make_datum_plane(doc)
    plane.Support = (support, ["Face1"])
    plane.Offset = "5 mm"
    assert_recomputes(doc)

    face = plane.Shape.Faces[0]
    assert isinstance(face.Surface, Part.Plane)
    assert math.isclose(face.CenterOfMass.z, 5.0, abs_tol=1e-7)

    # parametric update propagates
    plane.Offset = "12 mm"
    assert_recomputes(doc)
    assert math.isclose(plane.Shape.Faces[0].CenterOfMass.z, 12.0,
                        abs_tol=1e-7)

    plane.Reverse = True
    assert_recomputes(doc)
    assert math.isclose(plane.Shape.Faces[0].CenterOfMass.z, -12.0,
                        abs_tol=1e-7)


def test_datum_plane_rejects_nonplanar(doc):
    cyl = doc.addObject("Part::Cylinder", "Cyl")
    doc.recompute()
    plane = make_datum_plane(doc)
    plane.Support = (cyl, ["Face1"])  # lateral cylindrical face
    with pytest.raises(Exception):
        plane.Proxy.execute(plane)


# -- ProjectedCurve ------------------------------------------------------


def test_projection_normal_mode(doc):
    support = _support_face(doc)
    line = _line_edge(doc, (2, 2, 7), (15, 11, 7))
    proj = make_projected_curve(doc)
    proj.Base = (line, [])
    proj.Support = (support, ["Face1"])
    assert_recomputes(doc)

    assert proj.Shape.Edges
    for v in proj.Shape.Vertexes:
        assert abs(v.Z) < 1e-6  # landed on the z=0 support
    # length preserved for a normal projection onto a parallel plane
    assert math.isclose(proj.Shape.Edges[0].Length,
                        line.Shape.Edges[0].Length, rel_tol=1e-6)


def test_projection_direction_mode(doc):
    support = _support_face(doc)
    line = _line_edge(doc, (2, 2, 7), (15, 11, 7))
    proj = make_projected_curve(doc)
    proj.Base = (line, [])
    proj.Support = (support, ["Face1"])
    proj.Mode = "Direction"
    proj.Direction = App.Vector(0, 0, -1)
    assert_recomputes(doc)
    assert proj.Shape.Edges


# -- ExtrudedSurface -----------------------------------------------------


def test_extrude_open_profile_gives_face(doc):
    line = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    ext = make_extruded_surface(doc)
    ext.Profile = (line, [])
    ext.Direction = App.Vector(0, 0, 1)
    ext.LengthFwd = "5 mm"
    assert_recomputes(doc)

    assert ext.Shape.ShapeType in ("Face", "Shell")
    assert math.isclose(ext.Shape.Area, 50.0, rel_tol=1e-7)
    assert not ext.Shape.Solids  # surface mode: never a solid


def test_extrude_two_limits(doc):
    line = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    ext = make_extruded_surface(doc)
    ext.Profile = (line, [])
    ext.LengthFwd = "5 mm"
    ext.LengthRev = "3 mm"
    assert_recomputes(doc)

    zs = [v.Z for v in ext.Shape.Vertexes]
    assert math.isclose(min(zs), -3.0, abs_tol=1e-7)
    assert math.isclose(max(zs), 5.0, abs_tol=1e-7)


def test_extrude_null_direction_fails(doc):
    line = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    ext = make_extruded_surface(doc)
    ext.Profile = (line, [])
    ext.Direction = App.Vector(0, 0, 0)
    with pytest.raises(GSFeatureError):
        ext.Proxy.execute(ext)


# -- GUI-parity scenarios (regression for empty-then-filled workflow) ----


def test_feature_created_empty_idles_without_error(doc):
    """A freshly inserted feature has no inputs yet: it must recompute
    cleanly with an empty shape instead of erroring (GUI insert flow)."""
    ext = make_extruded_surface(doc)
    assert_recomputes(doc)  # no inputs — must not fail
    assert ext.Shape.isNull() or not ext.Shape.Faces

    # ...then filling the inputs brings it to life on the next recompute
    line = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    ext.Profile = (line, [])
    ext.LengthFwd = "5 mm"
    assert_recomputes(doc)
    assert ext.Shape.Faces


def _sketch_with_arc(doc):
    import math
    sk = doc.addObject("Sketcher::SketchObject", "Sketch")
    sk.addGeometry(Part.ArcOfCircle(
        Part.Circle(App.Vector(10, 10, 0), App.Vector(0, 0, 1), 5),
        math.radians(20), math.radians(120)), False)
    doc.recompute()
    return sk


def test_extrude_from_sketch(doc):
    """Screenshot scenario: whole Sketch as Profile, fwd 10 / rev 5."""
    sk = _sketch_with_arc(doc)
    ext = make_extruded_surface(doc)
    ext.Profile = (sk, [])
    ext.LengthFwd = "10 mm"
    ext.LengthRev = "5 mm"
    assert_recomputes(doc)

    assert ext.Shape.Faces
    zs = [v.Z for v in ext.Shape.Vertexes]
    assert math.isclose(min(zs), -5.0, abs_tol=1e-6)
    assert math.isclose(max(zs), 10.0, abs_tol=1e-6)


def test_extrude_from_multi_curve_sketch(doc):
    """Sketch with two disconnected curves -> compound of two surfaces."""
    import math as m
    sk = doc.addObject("Sketcher::SketchObject", "Sketch")
    sk.addGeometry(Part.LineSegment(
        App.Vector(0, 0, 0), App.Vector(10, 0, 0)), False)
    sk.addGeometry(Part.ArcOfCircle(
        Part.Circle(App.Vector(0, 20, 0), App.Vector(0, 0, 1), 5),
        0, m.radians(90)), False)
    doc.recompute()

    ext = make_extruded_surface(doc)
    ext.Profile = (sk, [])
    ext.LengthFwd = "5 mm"
    assert_recomputes(doc)
    assert len(ext.Shape.Faces) == 2


def test_projection_from_sketch_base(doc):
    support = _support_face(doc)
    sk = _sketch_with_arc(doc)
    sk.Placement.Base = App.Vector(0, 0, 5)  # lift above support
    proj = make_projected_curve(doc)
    proj.Base = (sk, [])
    proj.Support = (support, ["Face1"])
    assert_recomputes(doc)
    assert proj.Shape.Edges
    for v in proj.Shape.Vertexes:
        assert abs(v.Z) < 1e-6


# -- direction modes ------------------------------------------------------


def test_extrude_direction_auto_uses_profile_normal(doc):
    """Sketch rotated into the XZ plane: Auto mode must extrude along -Y
    (the plane normal), not the default Z vector."""
    sk = _sketch_with_arc(doc)
    sk.Placement = App.Placement(
        App.Vector(0, 0, 0), App.Rotation(App.Vector(1, 0, 0), 90))
    doc.recompute()
    ext = make_extruded_surface(doc)
    ext.Profile = (sk, [])
    ext.LengthFwd = "8 mm"
    assert_recomputes(doc)

    ys = [v.Y for v in ext.Shape.Vertexes]
    assert math.isclose(abs(max(ys) - min(ys)), 8.0, abs_tol=1e-6)


def test_extrude_direction_from_reference_edge(doc):
    line = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    ref = _line_edge(doc, (0, 0, 0), (0, 3, 4), name="Ref")  # slanted
    ext = make_extruded_surface(doc)
    ext.Profile = (line, [])
    ext.DirectionRef = (ref, [])
    assert ext.DirectionMode == "Reference"  # onChanged auto-switch
    ext.LengthFwd = "5 mm"
    assert_recomputes(doc)

    # direction (0, 0.6, 0.8) * 5mm -> dy 3, dz 4
    ys = [v.Y for v in ext.Shape.Vertexes]
    zs = [v.Z for v in ext.Shape.Vertexes]
    assert math.isclose(max(ys) - min(ys), 3.0, abs_tol=1e-6)
    assert math.isclose(max(zs) - min(zs), 4.0, abs_tol=1e-6)


def test_extrude_direction_from_reference_face(doc):
    support = _support_face(doc)  # z=0 plane, normal Z
    line = _line_edge(doc, (0, 0, 10), (10, 0, 10))
    ext = make_extruded_surface(doc)
    ext.Profile = (line, [])
    ext.DirectionRef = (support, ["Face1"])
    ext.LengthFwd = "6 mm"
    assert_recomputes(doc)
    zs = [v.Z for v in ext.Shape.Vertexes]
    assert math.isclose(max(zs) - min(zs), 6.0, abs_tol=1e-6)


def test_extrude_reference_rejects_curved_edge(doc):
    line = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    arc_obj = doc.addObject("Part::Feature", "Arc")
    arc_obj.Shape = Part.makeCircle(5)
    ext = make_extruded_surface(doc)
    ext.Profile = (line, [])
    ext.DirectionRef = (arc_obj, [])
    ext.DirectionMode = "Reference"
    with pytest.raises(GSFeatureError):
        ext.Proxy.execute(ext)


# -- integration: chain + hierarchy --------------------------------------


def test_feature_chain_in_active_set(doc):
    """support -> datum plane -> line -> projection onto plane's face,
    all auto-inserted into the active geometrical set."""
    from gensurf.containers import get_active_set

    support = _support_face(doc)
    plane = make_datum_plane(doc)
    plane.Support = (support, ["Face1"])
    plane.Offset = "4 mm"
    line = _line_edge(doc, (0, 0, 10), (10, 10, 10))
    proj = make_projected_curve(doc)
    proj.Base = (line, [])
    proj.Support = (plane, ["Face1"])
    assert_recomputes(doc)

    for v in proj.Shape.Vertexes:
        assert math.isclose(v.Z, 4.0, abs_tol=1e-6)

    active = get_active_set(doc)
    assert plane in active.Group and proj in active.Group

    # editing the root propagates through the chain
    plane.Offset = "6 mm"
    assert_recomputes(doc)
    for v in proj.Shape.Vertexes:
        assert math.isclose(v.Z, 6.0, abs_tol=1e-6)


# -- OffsetSurface --------------------------------------------------------


def test_offset_planar_face(doc):
    from gensurf.features import make_offset_surface
    support = _support_face(doc)
    off = make_offset_surface(doc)
    off.Source = (support, ["Face1"])
    off.Offset = "4 mm"
    assert_recomputes(doc)
    assert math.isclose(off.Shape.Faces[0].CenterOfMass.z, 4.0, abs_tol=1e-6)

    off.Reverse = True
    assert_recomputes(doc)
    assert math.isclose(off.Shape.Faces[0].CenterOfMass.z, -4.0, abs_tol=1e-6)


def test_offset_curved_surface_from_feature(doc):
    """Chain: sketch arc -> extruded surface -> offset (radius grows)."""
    from gensurf.features import make_offset_surface
    sk = _sketch_with_arc(doc)  # radius 5 arc
    ext = make_extruded_surface(doc)
    ext.Profile = (sk, [])
    ext.LengthFwd = "10 mm"
    doc.recompute()

    off = make_offset_surface(doc)
    off.Source = (ext, ["Face1"])
    off.Offset = "2 mm"
    assert_recomputes(doc)

    # offset follows the face normal (inward here: 5 - 2 = 3);
    # Reverse flips to the other side (5 + 2 = 7)
    assert math.isclose(off.Shape.Faces[0].Surface.Radius, 3.0, abs_tol=1e-6)
    off.Reverse = True
    assert_recomputes(doc)
    assert math.isclose(off.Shape.Faces[0].Surface.Radius, 7.0, abs_tol=1e-6)

    # parametric chain: stretch the extrusion, offset follows
    ext.LengthFwd = "20 mm"
    assert_recomputes(doc)
    zs = [v.Z for v in off.Shape.Vertexes]
    assert math.isclose(max(zs), 20.0, abs_tol=1e-6)


def test_offset_rejects_curve_input(doc):
    from gensurf.features import make_offset_surface
    line = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    off = make_offset_surface(doc)
    off.Source = (line, [])
    with pytest.raises(GSFeatureError):
        off.Proxy.execute(off)


# -- BlendSurface ---------------------------------------------------------


def _blend_setup(doc):
    """Two parallel horizontal edges at different heights, each the
    boundary of a planar support extending away from the gap."""
    from gensurf.features import make_extruded_surface

    e1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="E1")
    supA = doc.addObject("Part::Feature", "SupA")
    supA.Shape = Part.makeLine(
        App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
        App.Vector(0, -20, 0))  # z=0 plane, y in [-20, 0]

    e2 = _line_edge(doc, (0, 10, 5), (10, 10, 5), name="E2")
    supB = doc.addObject("Part::Feature", "SupB")
    supB.Shape = Part.makeLine(
        App.Vector(0, 10, 5), App.Vector(10, 10, 5)).extrude(
        App.Vector(0, 20, 0))  # z=5 plane, y in [10, 30]
    return e1, supA, e2, supB


def _blend_z_at(blend, x, y):
    """Height of the blend surface over (x, y) via vertical projection."""
    probe = Part.makeLine(App.Vector(x, y, -50), App.Vector(x, y, 55))
    dist, pairs, _info = blend.Shape.distToShape(probe)
    assert dist < 1e-5, "probe line missed the blend surface"
    return pairs[0][0].z


def test_blend_position_position_is_ruled(doc):
    from gensurf.features import make_blend_surface
    e1, _supA, e2, _supB = _blend_setup(doc)
    blend = make_blend_surface(doc)
    blend.Curve1 = (e1, [])
    blend.Curve2 = (e2, [])
    assert_recomputes(doc)

    assert blend.Shape.Faces
    # ruled: at mid-gap the height is half of 5
    assert math.isclose(_blend_z_at(blend, 5, 5), 2.5, abs_tol=1e-3)


def test_blend_tangency_flattens_ends(doc):
    from gensurf.features import make_blend_surface
    e1, supA, e2, supB = _blend_setup(doc)
    blend = make_blend_surface(doc)
    blend.Curve1 = (e1, [])
    blend.Support1 = (supA, ["Face1"])
    blend.Curve2 = (e2, [])
    blend.Support2 = (supB, ["Face1"])
    blend.Continuity1 = "Tangency"
    blend.Continuity2 = "Tangency"
    assert_recomputes(doc)

    # tangent to the z=0 support at the start: the surface must hug z=0
    # near y=0 far more closely than the ruled blend does (ruled z = y/2)
    z_near_start = _blend_z_at(blend, 5, 0.5)
    assert z_near_start < 0.1  # ruled would be 0.25
    z_near_end = _blend_z_at(blend, 5, 9.5)
    assert z_near_end > 4.9  # hugs z=5 near the second support
    # and still spans the full gap
    assert math.isclose(_blend_z_at(blend, 5, 0), 0.0, abs_tol=1e-4)
    assert math.isclose(_blend_z_at(blend, 5, 10), 5.0, abs_tol=1e-4)


def test_blend_curvature_builds_and_hugs_harder(doc):
    from gensurf.features import make_blend_surface
    e1, supA, e2, supB = _blend_setup(doc)
    blend = make_blend_surface(doc)
    blend.Curve1 = (e1, [])
    blend.Support1 = (supA, ["Face1"])
    blend.Curve2 = (e2, [])
    blend.Support2 = (supB, ["Face1"])
    blend.Continuity1 = "Curvature"
    blend.Continuity2 = "Curvature"
    assert_recomputes(doc)
    assert blend.Shape.Faces
    # planar supports have zero cross curvature: G2 to a plane must stay
    # extremely flat near the boundary
    assert _blend_z_at(blend, 5, 0.5) < 0.05


def test_blend_tangency_without_support_errors(doc):
    from gensurf.features import make_blend_surface
    e1, _supA, e2, _supB = _blend_setup(doc)
    blend = make_blend_surface(doc)
    blend.Curve1 = (e1, [])
    blend.Curve2 = (e2, [])
    blend.Continuity1 = "Tangency"
    with pytest.raises(GSFeatureError):
        blend.Proxy.execute(blend)


def test_blend_auto_orient_prevents_twist(doc):
    from gensurf.features import make_blend_surface
    e1 = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    # second edge deliberately parametrized right-to-left
    e2 = _line_edge(doc, (10, 10, 0), (0, 10, 0), name="Rev")
    blend = make_blend_surface(doc)
    blend.Curve1 = (e1, [])
    blend.Curve2 = (e2, [])
    assert_recomputes(doc)
    # untwisted flat rectangle: area ~100
    assert math.isclose(blend.Shape.Area, 100.0, rel_tol=1e-3)


def test_blend_tension_shapes_tangent_blend(doc):
    """With tangency constraints, higher tension makes the blend hug the
    support longer (position-only blends are correctly tension-invariant:
    chord-aligned derivatives keep the section on the chord)."""
    from gensurf.features import make_blend_surface
    e1, supA, e2, supB = _blend_setup(doc)
    blend = make_blend_surface(doc)
    blend.Curve1 = (e1, [])
    blend.Support1 = (supA, ["Face1"])
    blend.Curve2 = (e2, [])
    blend.Support2 = (supB, ["Face1"])
    blend.Continuity1 = "Tangency"
    blend.Continuity2 = "Tangency"
    assert_recomputes(doc)
    z_mid_t1 = _blend_z_at(blend, 5, 2.5)

    blend.Tension1 = 2.5
    assert_recomputes(doc)
    z_mid_t25 = _blend_z_at(blend, 5, 2.5)
    # stronger pull toward the flat z=0 support -> lower at the same spot
    assert z_mid_t25 < z_mid_t1 - 0.05

    # blend from a curved sketch edge also builds cleanly
    sk = _sketch_with_arc(doc)
    e3 = _line_edge(doc, (0, 25, 10), (20, 25, 10))
    blend2 = make_blend_surface(doc)
    blend2.Curve1 = (sk, [])
    blend2.Curve2 = (e3, [])
    assert_recomputes(doc)
    assert blend2.Shape.Faces


# -- DatumPlane from origin/datum planes ----------------------------------


def test_datum_plane_from_origin_plane(doc):
    """Screenshot regression: support = App::Plane (e.g. a Body's
    YZ-plane), which has a Placement but no geometric Shape."""
    yz = doc.addObject("App::Plane", "YZ")
    yz.Placement = App.Placement(
        App.Vector(0, 0, 0), App.Rotation(App.Vector(0, 1, 0), 90))
    plane = make_datum_plane(doc)
    plane.Support = (yz, [])
    plane.Offset = "6 mm"
    assert_recomputes(doc)

    face = plane.Shape.Faces[0]
    normal = face.Surface.Axis
    assert abs(abs(normal.x) - 1.0) < 1e-9  # YZ plane -> normal along X
    assert math.isclose(face.CenterOfMass.x, 6.0, abs_tol=1e-6)
    assert face.Area > 1.0  # a real visible patch, not a degenerate sliver


def test_datum_plane_from_datum_plane_chain(doc):
    """A datum plane can support another datum plane (whole-object pick)."""
    support = _support_face(doc)
    p1 = make_datum_plane(doc)
    p1.Support = (support, ["Face1"])
    p1.Offset = "5 mm"
    doc.recompute()
    p2 = make_datum_plane(doc)
    p2.Support = (p1, [])  # whole object, no subelement
    p2.Offset = "5 mm"
    assert_recomputes(doc)
    assert math.isclose(
        p2.Shape.Faces[0].CenterOfMass.z, 10.0, abs_tol=1e-6)


# -- RevolvedSurface ------------------------------------------------------


def test_revolve_full_cylinder(doc):
    from gensurf.features import make_revolved_surface
    profile = _line_edge(doc, (5, 0, 0), (5, 0, 8))  # parallel to Z at x=5
    axis = _line_edge(doc, (0, 0, -10), (0, 0, 10), name="Axis")
    rev = make_revolved_surface(doc)
    rev.Profile = (profile, [])
    rev.AxisRef = (axis, [])
    assert_recomputes(doc)

    face = rev.Shape.Faces[0]
    assert math.isclose(face.Surface.Radius, 5.0, abs_tol=1e-7)
    assert math.isclose(face.Area, 2 * math.pi * 5 * 8, rel_tol=1e-6)
    assert not rev.Shape.Solids  # surface mode


def test_revolve_partial_with_two_limits(doc):
    from gensurf.features import make_revolved_surface
    profile = _line_edge(doc, (5, 0, 0), (5, 0, 8))
    axis = _line_edge(doc, (0, 0, 0), (0, 0, 1), name="Axis")
    rev = make_revolved_surface(doc)
    rev.Profile = (profile, [])
    rev.AxisRef = (axis, [])
    rev.AngleFwd = "60 deg"
    rev.AngleRev = "30 deg"
    assert_recomputes(doc)

    face = rev.Shape.Faces[0]
    assert math.isclose(face.Area, 2 * math.pi * 5 * 8 * 90 / 360,
                        rel_tol=1e-6)
    # rev limit reaches 30 degrees below the profile position (y < 0)
    ys = [v.Y for v in rev.Shape.Vertexes]
    assert min(ys) < -1e-3


def test_revolve_from_datum_axis(doc):
    from gensurf.features import make_revolved_surface
    ax = doc.addObject("App::Line", "ZAxis")
    ax.Placement = App.Placement(
        App.Vector(0, 0, 0), App.Rotation(App.Vector(0, 1, 0), -90))
    # App::Line direction is local X; rotated -90 about Y -> global Z
    profile = _line_edge(doc, (3, 0, 0), (3, 0, 4))
    rev = make_revolved_surface(doc)
    rev.Profile = (profile, [])
    rev.AxisRef = (ax, [])
    assert_recomputes(doc)
    assert math.isclose(rev.Shape.Faces[0].Surface.Radius, 3.0, abs_tol=1e-6)


def test_revolve_rejects_curved_axis(doc):
    from gensurf.features import make_revolved_surface
    profile = _line_edge(doc, (5, 0, 0), (5, 0, 8))
    arc = doc.addObject("Part::Feature", "ArcAxis")
    arc.Shape = Part.makeCircle(4)
    rev = make_revolved_surface(doc)
    rev.Profile = (profile, [])
    rev.AxisRef = (arc, [])
    with pytest.raises(GSFeatureError):
        rev.Proxy.execute(rev)


# -- Blend tangent side flip ----------------------------------------------


def test_blend_reverse_tangent_flips_departure(doc):
    from gensurf.features import make_blend_surface
    e1, supA, e2, supB = _blend_setup(doc)
    blend = make_blend_surface(doc)
    blend.Curve1 = (e1, [])
    blend.Support1 = (supA, ["Face1"])
    blend.Curve2 = (e2, [])
    blend.Support2 = (supB, ["Face1"])
    blend.Continuity1 = "Tangency"
    blend.Continuity2 = "Tangency"
    assert_recomputes(doc)
    y_min_normal = blend.Shape.BoundBox.YMin
    assert y_min_normal > -0.5  # departs toward the gap

    blend.ReverseTangent1 = True
    assert_recomputes(doc)
    # departure flipped: the surface now initially heads to y < 0
    assert blend.Shape.BoundBox.YMin < -0.5


# -- Split ----------------------------------------------------------------


def _vertical_cut_face(doc, x=10.0):
    """A vertical planar face at the given x, big enough to cut the
    standard 20x20 support."""
    obj = doc.addObject("Part::Feature", "Cutter")
    obj.Shape = Part.makeLine(
        App.Vector(x, -5, -5), App.Vector(x, 25, -5)).extrude(
        App.Vector(0, 0, 10))
    return obj


def test_split_surface_by_face(doc):
    from gensurf.features import make_split
    support = _support_face(doc)  # 20x20 at z=0
    cutter = _vertical_cut_face(doc)
    sp = make_split(doc)
    sp.Element = (support, ["Face1"])
    sp.Cutter = (cutter, ["Face1"])
    assert_recomputes(doc)

    # one deterministic side is kept (sign follows the cutter's own
    # face orientation); KeepOtherSide must select the opposite one
    assert math.isclose(sp.Shape.Area, 200.0, rel_tol=1e-6)
    x_default = sp.Shape.CenterOfMass.x

    sp.KeepOtherSide = True
    assert_recomputes(doc)
    assert math.isclose(sp.Shape.Area, 200.0, rel_tol=1e-6)
    assert (sp.Shape.CenterOfMass.x - 10) * (x_default - 10) < 0


def test_split_surface_by_datum_plane_ignores_patch_size(doc):
    """A tiny datum plane must still cut the whole element (conceptually
    infinite)."""
    from gensurf.features import make_split
    support = _support_face(doc)
    yz = doc.addObject("App::Plane", "YZ")
    yz.Placement = App.Placement(
        App.Vector(10, 0, 0), App.Rotation(App.Vector(0, 1, 0), 90))
    sp = make_split(doc)
    sp.Element = (support, ["Face1"])
    sp.Cutter = (yz, [])
    assert_recomputes(doc)
    assert math.isclose(sp.Shape.Area, 200.0, rel_tol=1e-6)


def test_split_curve_by_plane(doc):
    from gensurf.features import make_split
    line = _line_edge(doc, (0, 5, 0), (20, 5, 0))
    cutter = _vertical_cut_face(doc)
    sp = make_split(doc)
    sp.Element = (line, [])
    sp.Cutter = (cutter, ["Face1"])
    assert_recomputes(doc)

    assert math.isclose(sp.Shape.Length, 10.0, rel_tol=1e-6)
    mid_default = sp.Shape.CenterOfMass.x

    sp.KeepOtherSide = True
    assert_recomputes(doc)
    assert math.isclose(sp.Shape.Length, 10.0, rel_tol=1e-6)
    assert (sp.Shape.CenterOfMass.x - 10) * (mid_default - 10) < 0


def test_split_surface_by_curve_on_it(doc):
    from gensurf.features import make_split
    support = _support_face(doc)
    curve = _line_edge(doc, (0, 10, 0), (20, 10, 0))  # lies on the face
    sp = make_split(doc)
    sp.Element = (support, ["Face1"])
    sp.Cutter = (curve, [])
    assert_recomputes(doc)
    assert math.isclose(sp.Shape.Area, 200.0, rel_tol=1e-6)
    y_default = sp.Shape.CenterOfMass.y

    sp.KeepOtherSide = True
    assert_recomputes(doc)
    assert (sp.Shape.CenterOfMass.y - 10) * (y_default - 10) < 0  # flipped


def test_split_no_intersection_errors(doc):
    from gensurf.features import make_split
    support = _support_face(doc)
    far = doc.addObject("Part::Feature", "Far")
    far.Shape = Part.makeLine(
        App.Vector(50, -5, -5), App.Vector(50, 25, -5)).extrude(
        App.Vector(0, 0, 10))
    sp = make_split(doc)
    sp.Element = (support, ["Face1"])
    sp.Cutter = (far, ["Face1"])
    with pytest.raises(GSFeatureError):
        sp.Proxy.execute(sp)


# -- Trim -----------------------------------------------------------------


def test_trim_two_crossing_surfaces(doc):
    from gensurf.features import make_trim
    horiz = _support_face(doc)  # z=0, x/y in [0,20]
    # vertical band whose seam fully traverses both elements
    vert = doc.addObject("Part::Feature", "Vert")
    vert.Shape = Part.makeLine(
        App.Vector(10, 0, -5), App.Vector(10, 20, -5)).extrude(
        App.Vector(0, 0, 10))
    tr = make_trim(doc)
    tr.Element1 = (horiz, ["Face1"])
    tr.Element2 = (vert, ["Face1"])
    assert_recomputes(doc)

    # half of horiz (200) + half of vert (100), joined
    assert math.isclose(tr.Shape.Area, 300.0, rel_tol=1e-6)
    x_default = tr.Shape.CenterOfMass.x

    tr.KeepOtherSide1 = True
    assert_recomputes(doc)
    assert math.isclose(tr.Shape.Area, 300.0, rel_tol=1e-6)
    assert (tr.Shape.CenterOfMass.x - 10) * (x_default - 10) < 0


def test_trim_two_crossing_curves(doc):
    from gensurf.features import make_trim
    l1 = _line_edge(doc, (0, 0, 0), (20, 0, 0), name="L1")
    l2 = _line_edge(doc, (10, -10, 0), (10, 10, 0), name="L2")
    tr = make_trim(doc)
    tr.Element1 = (l1, [])
    tr.Element2 = (l2, [])
    assert_recomputes(doc)

    # each keeps the piece containing its start point: L-shape of 10 + 10
    assert math.isclose(tr.Shape.Length, 20.0, rel_tol=1e-6)
    xs = [v.X for v in tr.Shape.Vertexes]
    ys = [v.Y for v in tr.Shape.Vertexes]
    assert min(xs) <= 1e-6 and min(ys) <= -10 + 1e-6

    tr.KeepOtherSide1 = True
    assert_recomputes(doc)
    assert min(v.X for v in tr.Shape.Vertexes) >= 10 - 1e-6


def test_trim_parametric_chain(doc):
    """Trim survives upstream edits: move the vertical cutter, the trim
    follows."""
    from gensurf.features import make_trim
    horiz = _support_face(doc)
    vert = doc.addObject("Part::Feature", "Vert")

    def vert_shape(x):
        return Part.makeLine(
            App.Vector(x, 0, -5), App.Vector(x, 20, -5)).extrude(
            App.Vector(0, 0, 10))

    vert.Shape = vert_shape(10)
    tr = make_trim(doc)
    tr.Element1 = (horiz, ["Face1"])
    tr.Element2 = (vert, ["Face1"])
    assert_recomputes(doc)
    area_at_10 = tr.Shape.Area
    assert math.isclose(area_at_10, 300.0, rel_tol=1e-6)

    vert.Shape = vert_shape(15)
    assert_recomputes(doc)
    # kept horiz half is now 100 or 300 (not 200) -> total changed
    assert abs(tr.Shape.Area - area_at_10) > 50


# -- Transformations ------------------------------------------------------


def test_translate_by_vector_and_reference(doc):
    from gensurf.features import make_translate
    line = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    tr = make_translate(doc)
    tr.Source = (line, [])
    tr.Direction = App.Vector(0, 1, 0)
    tr.Distance = "7 mm"
    assert_recomputes(doc)
    assert all(math.isclose(v.Y, 7.0, abs_tol=1e-9)
               for v in tr.Shape.Vertexes)

    ref = _line_edge(doc, (0, 0, 0), (0, 0, 3), name="Ref")
    tr.DirectionRef = (ref, [])
    assert_recomputes(doc)
    assert all(math.isclose(v.Z, 7.0, abs_tol=1e-9)
               for v in tr.Shape.Vertexes)
    assert all(math.isclose(v.Y, 0.0, abs_tol=1e-9)
               for v in tr.Shape.Vertexes)


def test_rotate_about_edge_axis(doc):
    from gensurf.features import make_rotate
    line = _line_edge(doc, (10, 0, 0), (20, 0, 0))
    axis = _line_edge(doc, (0, 0, 0), (0, 0, 5), name="Axis")
    rot = make_rotate(doc)
    rot.Source = (line, [])
    rot.AxisRef = (axis, [])
    rot.Angle = "90 deg"
    assert_recomputes(doc)

    pts = sorted([v.Point for v in rot.Shape.Vertexes], key=lambda p: p.y)
    assert math.isclose(pts[0].y, 10.0, abs_tol=1e-9)
    assert math.isclose(pts[1].y, 20.0, abs_tol=1e-9)
    assert all(abs(p.x) < 1e-9 for p in pts)


def test_scale_uniform_about_point(doc):
    from gensurf.features import make_scale
    support = _support_face(doc)  # 20x20 at origin
    pt = doc.addObject("Part::Feature", "Pt")
    pt.Shape = Part.Vertex(App.Vector(0, 0, 0))
    sc = make_scale(doc)
    sc.Source = (support, ["Face1"])
    sc.Reference = (pt, [])
    sc.Ratio = 2.0
    assert_recomputes(doc)

    assert math.isclose(sc.Shape.Area, 1600.0, rel_tol=1e-6)  # 40x40
    assert math.isclose(sc.Shape.BoundBox.XMax, 40.0, abs_tol=1e-6)


def test_scale_along_plane_normal(doc):
    from gensurf.features import make_scale
    # slanted edge: z should double (z=0 plane reference), x unchanged
    line = _line_edge(doc, (0, 0, 0), (10, 0, 5))
    plane_face = _support_face(doc)
    sc = make_scale(doc)
    sc.Source = (line, [])
    sc.Reference = (plane_face, ["Face1"])
    sc.Ratio = 2.0
    assert_recomputes(doc)

    top = max(sc.Shape.Vertexes, key=lambda v: v.Z)
    assert math.isclose(top.Z, 10.0, abs_tol=1e-6)
    assert math.isclose(top.X, 10.0, abs_tol=1e-6)  # in-plane untouched


def test_scale_radially_from_line(doc):
    from gensurf.features import make_scale
    # scale from the Z axis: (3,4,7) -> (6,8,7)
    edge = _line_edge(doc, (3, 4, 0), (3, 4, 7))
    zaxis = _line_edge(doc, (0, 0, -5), (0, 0, 5), name="ZAxis")
    sc = make_scale(doc)
    sc.Source = (edge, [])
    sc.Reference = (zaxis, [])
    sc.Ratio = 2.0
    assert_recomputes(doc)

    top = max(sc.Shape.Vertexes, key=lambda v: v.Z)
    assert math.isclose(top.X, 6.0, abs_tol=1e-6)
    assert math.isclose(top.Y, 8.0, abs_tol=1e-6)
    assert math.isclose(top.Z, 7.0, abs_tol=1e-6)  # along-axis preserved


def test_scale_from_datum_plane_and_mirror(doc):
    from gensurf.features import make_scale
    yz = doc.addObject("App::Plane", "YZ")
    yz.Placement = App.Placement(
        App.Vector(0, 0, 0), App.Rotation(App.Vector(0, 1, 0), 90))
    line = _line_edge(doc, (5, 0, 0), (5, 10, 0))
    sc = make_scale(doc)
    sc.Source = (line, [])
    sc.Reference = (yz, [])
    sc.Ratio = -1.0  # mirror through the YZ plane
    assert_recomputes(doc)
    assert all(math.isclose(v.X, -5.0, abs_tol=1e-6)
               for v in sc.Shape.Vertexes)


def test_scale_rejects_curved_reference(doc):
    from gensurf.features import make_scale
    line = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    arc = doc.addObject("Part::Feature", "Arc")
    arc.Shape = Part.makeCircle(5)
    sc = make_scale(doc)
    sc.Source = (line, [])
    sc.Reference = (arc, [])
    with pytest.raises(GSFeatureError):
        sc.Proxy.execute(sc)


def test_transform_chain_stays_parametric(doc):
    """extrude -> translate -> rotate chain follows upstream edits."""
    from gensurf.features import make_translate, make_rotate
    line = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    ext = make_extruded_surface(doc)
    ext.Profile = (line, [])
    ext.LengthFwd = "5 mm"
    tr = make_translate(doc)
    tr.Source = (ext, [])
    tr.Direction = App.Vector(0, 1, 0)
    tr.Distance = "20 mm"
    axis = _line_edge(doc, (0, 0, 0), (0, 0, 1), name="Axis")
    rot = make_rotate(doc)
    rot.Source = (tr, [])
    rot.AxisRef = (axis, [])
    rot.Angle = "180 deg"
    assert_recomputes(doc)
    assert math.isclose(rot.Shape.BoundBox.YMin, -20.0, abs_tol=1e-6)

    ext.LengthFwd = "9 mm"
    assert_recomputes(doc)
    assert math.isclose(rot.Shape.BoundBox.ZMax, 9.0, abs_tol=1e-6)


# -- Extend ---------------------------------------------------------------


def _pick_vertex_sub(obj, point):
    """Sub-element name of the vertex nearest to a point."""
    best, name = 1e9, None
    for i, v in enumerate(obj.Shape.Vertexes, 1):
        d = (v.Point - App.Vector(*point)).Length
        if d < best:
            best, name = d, f"Vertex{i}"
    return name


def test_extend_line_at_end(doc):
    from gensurf.features import make_extend
    line = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    ex = make_extend(doc)
    ex.Boundary = (line, [_pick_vertex_sub(line, (10, 0, 0))])
    ex.Length = "5 mm"
    assert_recomputes(doc)

    assert math.isclose(ex.Shape.Length, 15.0, rel_tol=1e-9)
    xs = [v.X for v in ex.Shape.Vertexes]
    assert math.isclose(max(xs), 15.0, abs_tol=1e-9)
    assert math.isclose(min(xs), 0.0, abs_tol=1e-9)  # original kept

    # other extremity extends the other way
    ex.Boundary = (line, [_pick_vertex_sub(line, (0, 0, 0))])
    assert_recomputes(doc)
    assert math.isclose(min(v.X for v in ex.Shape.Vertexes), -5.0,
                        abs_tol=1e-9)


def test_extend_arc_stays_on_circle(doc):
    from gensurf.features import make_extend
    arc_obj = doc.addObject("Part::Feature", "Arc")
    arc_obj.Shape = Part.ArcOfCircle(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10),
        0, math.pi / 2).toShape()
    end = arc_obj.Shape.Vertexes[-1].Point
    ex = make_extend(doc)
    ex.Boundary = (arc_obj, [_pick_vertex_sub(arc_obj, (end.x, end.y, 0))])
    ex.Length = "5 mm"
    assert_recomputes(doc)

    orig_len = arc_obj.Shape.Length
    assert math.isclose(ex.Shape.Length, orig_len + 5.0, rel_tol=1e-9)
    # natural: every point of the extension stays on the same circle
    for e in ex.Shape.Edges:
        for f in (0.0, 0.3, 0.7, 1.0):
            p = e.valueAt(e.FirstParameter
                          + f * (e.LastParameter - e.FirstParameter))
            assert math.isclose(p.Length, 10.0, abs_tol=1e-7)


def _spline_obj(doc):
    bs = Part.BSplineCurve()
    bs.interpolate([App.Vector(0, 0, 0), App.Vector(5, 2, 0),
                    App.Vector(10, 1, 0), App.Vector(15, 4, 0)])
    obj = doc.addObject("Part::Feature", "Spline")
    obj.Shape = bs.toShape()
    return obj


def test_extend_spline_polynomial_continuation(doc):
    from gensurf.features import make_extend
    sp = _spline_obj(doc)
    orig = sp.Shape.Length
    ex = make_extend(doc)
    ex.Boundary = (sp, [_pick_vertex_sub(sp, (15, 4, 0))])
    ex.Length = "4 mm"
    assert_recomputes(doc)

    assert math.isclose(ex.Shape.Length, orig + 4.0, rel_tol=1e-6)

    # exact polynomial continuation: extension points must lie on the
    # underlying B-spline evaluated beyond its knot range
    bs = sp.Shape.Edges[0].Curve

    def dist_to_continuation(p):
        lo, hi = bs.LastParameter - 0.5, bs.LastParameter + 3.0
        for _ in range(80):  # golden-section refine of closest point
            m1 = lo + (hi - lo) * 0.382
            m2 = lo + (hi - lo) * 0.618
            if (p - bs.value(m1)).Length < (p - bs.value(m2)).Length:
                hi = m2
            else:
                lo = m1
        return (p - bs.value((lo + hi) / 2)).Length

    ext_edge = max(ex.Shape.Edges, key=lambda e: e.CenterOfMass.x)
    for f in (0.1, 0.5, 0.9):
        p = ext_edge.valueAt(
            ext_edge.FirstParameter
            + f * (ext_edge.LastParameter - ext_edge.FirstParameter))
        assert dist_to_continuation(p) < 1e-7, \
            "extension deviates from natural continuation"

    # tangent continuity across the junction
    orig_edge = sp.Shape.Edges[0]
    t_orig = orig_edge.tangentAt(orig_edge.LastParameter)
    j = App.Vector(15, 4, 0)
    t_ext = ext_edge.tangentAt(
        ext_edge.FirstParameter
        if (ext_edge.valueAt(ext_edge.FirstParameter) - j).Length < 1e-6
        else ext_edge.LastParameter)
    assert t_orig.cross(t_ext).Length < 1e-6

    # and it is genuinely curved (not a tangent-line ribbon)
    a = ext_edge.Vertexes[0].Point
    b = ext_edge.Vertexes[-1].Point
    mid = ext_edge.valueAt(
        (ext_edge.FirstParameter + ext_edge.LastParameter) / 2)
    chord_dev = (mid - (a + b) * 0.5).Length
    assert chord_dev > 1e-3


def test_extend_plane_face(doc):
    from gensurf.features import make_extend
    support = _support_face(doc)  # 20x20
    # find a boundary edge at x = 20 (to extend in +X)
    edge_idx = None
    for i, e in enumerate(support.Shape.Edges, 1):
        if all(abs(v.X - 20.0) < 1e-9 for v in e.Vertexes):
            edge_idx = i
            break
    assert edge_idx is not None
    ex = make_extend(doc)
    ex.Boundary = (support, [f"Edge{edge_idx}"])
    ex.Length = "5 mm"
    assert_recomputes(doc)
    assert math.isclose(ex.Shape.Area, 500.0, rel_tol=1e-9)  # 25 x 20
    assert math.isclose(ex.Shape.BoundBox.XMax, 25.0, abs_tol=1e-9)

    ex.Length = "-3 mm"  # negative shrinks
    assert_recomputes(doc)
    assert math.isclose(ex.Shape.Area, 340.0, rel_tol=1e-9)  # 17 x 20


def test_extend_cylinder_band_both_directions(doc):
    from gensurf.features import make_extend
    band_obj = doc.addObject("Part::Feature", "Band")
    band_obj.Shape = Part.ArcOfCircle(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10),
        0, math.pi / 2).toShape().extrude(App.Vector(0, 0, 8))

    # axial edge (top rim: z = 8)
    top_idx = next(i for i, e in enumerate(band_obj.Shape.Edges, 1)
                   if all(abs(v.Z - 8.0) < 1e-9 for v in e.Vertexes)
                   and e.Length > 1)
    ex = make_extend(doc)
    ex.Boundary = (band_obj, [f"Edge{top_idx}"])
    ex.Length = "4 mm"
    assert_recomputes(doc)
    face = ex.Shape.Faces[0]
    assert math.isclose(face.Surface.Radius, 10.0, abs_tol=1e-9)
    assert math.isclose(ex.Shape.BoundBox.ZMax, 12.0, abs_tol=1e-7)
    assert math.isclose(face.Area, band_obj.Shape.Faces[0].Area * 12 / 8,
                        rel_tol=1e-9)

    # angular edge (a straight vertical rim): extension curls around
    # the same cylinder
    rim_idx = next(i for i, e in enumerate(band_obj.Shape.Edges, 1)
                   if abs(e.Length - 8.0) < 1e-9)
    ex2 = make_extend(doc)
    ex2.Boundary = (band_obj, [f"Edge{rim_idx}"])
    ex2.Length = "6 mm"
    assert_recomputes(doc)
    f2 = ex2.Shape.Faces[0]
    assert math.isclose(f2.Surface.Radius, 10.0, abs_tol=1e-9)
    # numeric arc-length calibration: ~1e-5 relative accuracy
    assert math.isclose(f2.Area, band_obj.Shape.Faces[0].Area + 6 * 8,
                        rel_tol=1e-4)


def test_extend_bspline_surface(doc):
    from gensurf.features import make_extend

    def wirez(z, bump):
        c = Part.BSplineCurve()
        c.interpolate([App.Vector(0, 0, z), App.Vector(5, bump, z),
                       App.Vector(10, 0, z)])
        return Part.Wire([c.toShape()])
    loft_obj = doc.addObject("Part::Feature", "Loft")
    loft_obj.Shape = Part.makeLoft([wirez(0, 2), wirez(5, 4), wirez(10, 1)])

    # boundary edge at z = 10 (last section)
    idx = next(i for i, e in enumerate(loft_obj.Shape.Edges, 1)
               if all(abs(v.Z - 10.0) < 1e-9 for v in e.Vertexes))
    orig_area = loft_obj.Shape.Faces[0].Area
    ex = make_extend(doc)
    ex.Boundary = (loft_obj, [f"Edge{idx}"])
    ex.Length = "5 mm"
    assert_recomputes(doc)

    assert ex.Shape.Faces
    total = sum(f.Area for f in ex.Shape.Faces)
    assert total > orig_area + 30  # a real strip was added
    assert ex.Shape.BoundBox.ZMax > 12.0  # actually went past z=10
    # the original region is untouched
    p_interior = loft_obj.Shape.Faces[0].Surface.value(0.5, 0.5)
    assert ex.Shape.distToShape(Part.Vertex(p_interior))[0] < 1e-7
    # the strip is the natural continuation: a point sampled beyond the
    # boundary from the original surface must lie on the result
    p_beyond = loft_obj.Shape.Faces[0].Surface.value(0.5, 1.1)
    assert ex.Shape.distToShape(Part.Vertex(p_beyond))[0] < 1e-4


def test_extend_closed_direction_errors(doc):
    from gensurf.features import make_extend
    cyl_obj = doc.addObject("Part::Feature", "Cyl")
    cyl_obj.Shape = Part.makeCylinder(5, 10).Faces[0]  # full lateral face
    # top circular rim: extending "around" is impossible; extending past
    # the rim axially is fine — so pick the seam edge (straight, len 10)
    # whose crossing direction is the closed angular one
    rim = next(i for i, e in enumerate(cyl_obj.Shape.Edges, 1)
               if abs(e.Length - 10.0) < 1e-6)
    ex = make_extend(doc)
    ex.Boundary = (cyl_obj, [f"Edge{rim}"])
    with pytest.raises(GSFeatureError):
        ex.Proxy.execute(ex)


def test_extend_whole_object_pick_rejected(doc):
    from gensurf.features import make_extend
    line = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    ex = make_extend(doc)
    ex.Boundary = (line, [])
    with pytest.raises(GSFeatureError):
        ex.Proxy.execute(ex)


def test_extend_modes_on_arc(doc):
    """Same arc, three modes: Natural stays on the circle, Tangent goes
    straight, Curvature (of a circle) equals Natural."""
    from gensurf.features import make_extend
    arc_obj = doc.addObject("Part::Feature", "Arc")
    arc_obj.Shape = Part.ArcOfCircle(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10),
        0, math.pi / 2).toShape()
    end = arc_obj.Shape.Vertexes[-1].Point
    sub = _pick_vertex_sub(arc_obj, (end.x, end.y, 0))

    ex = make_extend(doc)
    ex.Boundary = (arc_obj, [sub])
    ex.Length = "5 mm"
    assert ex.Mode == "Natural"  # the default

    ex.Mode = "Tangent"
    assert_recomputes(doc)
    ext_edge = min(ex.Shape.Edges, key=lambda e: e.Length)
    assert math.isclose(ext_edge.Length, 5.0, rel_tol=1e-9)
    a, b = ext_edge.Vertexes[0].Point, ext_edge.Vertexes[-1].Point
    mid = ext_edge.valueAt(
        (ext_edge.FirstParameter + ext_edge.LastParameter) / 2)
    assert (mid - (a + b) * 0.5).Length < 1e-9  # straight
    # off the circle at its far end
    assert abs(max(p.Length for p in (a, b)) - 10.0) > 0.1

    ex.Mode = "Curvature"
    assert_recomputes(doc)
    for e in ex.Shape.Edges:
        for f in (0.25, 0.75, 1.0):
            p = e.valueAt(e.FirstParameter
                          + f * (e.LastParameter - e.FirstParameter))
            assert math.isclose(p.Length, 10.0, abs_tol=1e-6)


def test_extend_surface_tangent_mode(doc):
    """Cylinder band extended past its straight rim in Tangent mode:
    the ribbon is flat, leaving the cylinder."""
    from gensurf.features import make_extend
    band_obj = doc.addObject("Part::Feature", "Band")
    band_obj.Shape = Part.ArcOfCircle(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10),
        0, math.pi / 2).toShape().extrude(App.Vector(0, 0, 8))
    rim_idx = next(i for i, e in enumerate(band_obj.Shape.Edges, 1)
                   if abs(e.Length - 8.0) < 1e-9)
    ex = make_extend(doc)
    ex.Boundary = (band_obj, [f"Edge{rim_idx}"])
    ex.Length = "6 mm"
    ex.Mode = "Tangent"
    assert_recomputes(doc)

    assert len(ex.Shape.Faces) == 2
    strip = min(ex.Shape.Faces, key=lambda f: f.Area)
    # tangent ribbon at the angle-0 rim: points leave along -Y at x=10
    corner = min(strip.Vertexes, key=lambda v: v.Point.y)
    assert corner.Point.y < -5.9
    assert math.isclose(corner.Point.x, 10.0, abs_tol=1e-3)
    # flat: all strip points stay at x ~= 10 (the tangent plane)
    assert strip.BoundBox.XLength < 1e-3


def test_extend_surface_curvature_mode_follows_cylinder(doc):
    """Curvature mode on a cylinder rim: the osculating continuation IS
    the cylinder, so points stay at radius 10 (approx)."""
    from gensurf.features import make_extend
    band_obj = doc.addObject("Part::Feature", "Band")
    band_obj.Shape = Part.ArcOfCircle(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10),
        0, math.pi / 2).toShape().extrude(App.Vector(0, 0, 8))
    rim_idx = next(i for i, e in enumerate(band_obj.Shape.Edges, 1)
                   if abs(e.Length - 8.0) < 1e-9)
    ex = make_extend(doc)
    ex.Boundary = (band_obj, [f"Edge{rim_idx}"])
    ex.Length = "6 mm"
    ex.Mode = "Curvature"
    assert_recomputes(doc)

    strip = min(ex.Shape.Faces, key=lambda f: f.Area)
    for v in strip.Vertexes:
        r = math.hypot(v.Point.x, v.Point.y)
        assert abs(r - 10.0) < 5e-3


# -- MultiSection ---------------------------------------------------------


def _msec_sections(doc):
    """Three horizontal line sections at increasing heights and widths."""
    s0 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="S0")
    s1 = _line_edge(doc, (-2, 0, 5), (12, 0, 5), name="S1")
    s2 = _line_edge(doc, (0, 0, 10), (10, 0, 10), name="S2")
    return s0, s1, s2


def test_multisection_basic_loft(doc):
    from gensurf.features import make_multisection
    s0, s1, s2 = _msec_sections(doc)
    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, ""), (s2, "")]
    assert_recomputes(doc)

    assert ms.Shape.Faces
    # the surface passes through all three sections
    for s in (s0, s1, s2):
        assert ms.Shape.distToShape(s.Shape)[0] < 1e-7
    assert ms.Shape.BoundBox.XMin < -1.9  # bulges out to the wide section


def test_multisection_needs_two(doc):
    from gensurf.features import make_multisection
    s0 = _line_edge(doc, (0, 0, 0), (10, 0, 0))
    ms = make_multisection(doc)
    ms.Sections = [(s0, "")]
    with pytest.raises(GSFeatureError):
        ms.Proxy.execute(ms)


def test_multisection_ruled(doc):
    from gensurf.features import make_multisection
    s0, s1, s2 = _msec_sections(doc)
    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, ""), (s2, "")]
    ms.Ruled = True
    assert_recomputes(doc)
    # ruled: at z=2.5 the edge x-min is the average of 0 and -2
    section = ms.Shape.slice(App.Vector(0, 0, 1), 2.5)
    xs = [v.X for w in section for v in w.Vertexes]
    assert math.isclose(min(xs), -1.0, abs_tol=1e-6)


def test_multisection_auto_orient(doc):
    from gensurf.features import make_multisection
    s0 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="S0")
    s1r = _line_edge(doc, (10, 0, 5), (0, 0, 5), name="S1r")  # reversed
    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1r, "")]
    assert_recomputes(doc)
    # untwisted: a flat 10x5 rectangle
    assert math.isclose(ms.Shape.Area, 50.0, rel_tol=1e-6)


def test_multisection_two_guides(doc):
    """Two arcs lofted while following two bulging guides: the surface
    must pass through the sections AND hug the guides."""
    from gensurf.features import make_multisection
    s0 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="S0")
    s1 = _line_edge(doc, (0, 0, 10), (10, 0, 10), name="S1")

    def bulge_guide(x, name):
        bs = Part.BSplineCurve()
        bs.interpolate([App.Vector(x, 0, 0), App.Vector(x - 3 if x == 0
                        else x + 3, 0, 5), App.Vector(x, 0, 10)])
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = bs.toShape()
        return obj

    g1 = bulge_guide(0, "G1")
    g2 = bulge_guide(10, "G2")

    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, "")]
    ms.Guides = [(g1, ""), (g2, "")]
    assert_recomputes(doc)

    # passes through sections
    for s in (s0, s1):
        assert ms.Shape.distToShape(s.Shape)[0] < 1e-4
    # hugs the guides: guide midpoints lie on the surface
    for g in (g1, g2):
        mid = g.Shape.Edges[0].valueAt(
            (g.Shape.Edges[0].FirstParameter
             + g.Shape.Edges[0].LastParameter) / 2)
        assert ms.Shape.distToShape(Part.Vertex(mid))[0] < 1e-2
    # and it actually bulges (an unguided loft would stay at x in [0,10])
    assert ms.Shape.BoundBox.XMin < -2.5
    assert ms.Shape.BoundBox.XMax > 12.5


def test_multisection_one_guide_translates(doc):
    from gensurf.features import make_multisection
    s0 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="S0")
    s1 = _line_edge(doc, (0, 0, 10), (10, 0, 10), name="S1")
    # S-shaped guide attached to the x=0 ends
    bs = Part.BSplineCurve()
    bs.interpolate([App.Vector(0, 0, 0), App.Vector(0, 6, 5),
                    App.Vector(0, 0, 10)])
    g = doc.addObject("Part::Feature", "G")
    g.Shape = bs.toShape()

    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, "")]
    ms.Guides = [(g, "")]
    assert_recomputes(doc)
    # mid-height, the whole section is shifted to the guide's y bulge
    assert ms.Shape.BoundBox.YMax > 5.5


def test_multisection_guide_must_touch(doc):
    from gensurf.features import make_multisection
    s0 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="S0")
    s1 = _line_edge(doc, (0, 0, 10), (10, 0, 10), name="S1")
    g = _line_edge(doc, (50, 50, 0), (50, 50, 10), name="Gfar")
    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, "")]
    ms.Guides = [(g, "")]
    with pytest.raises(GSFeatureError):
        ms.Proxy.execute(ms)


def test_multisection_three_guides_rejected(doc):
    from gensurf.features import make_multisection
    s0 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="S0")
    s1 = _line_edge(doc, (0, 0, 10), (10, 0, 10), name="S1")
    gs = [_line_edge(doc, (x, 0, 0), (x, 0, 10), name=f"G{x}")
          for x in (0, 5, 10)]
    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, "")]
    ms.Guides = [(g, "") for g in gs]
    with pytest.raises(GSFeatureError):
        ms.Proxy.execute(ms)


# -- Fill -----------------------------------------------------------------


def _quad_boundary(doc, lift=3.0):
    """Four connected lines, one corner lifted out of plane."""
    pts = [(0, 0, 0), (10, 0, 0), (10, 10, lift), (0, 10, 0)]
    objs = []
    for i in range(4):
        a, b = pts[i], pts[(i + 1) % 4]
        objs.append(_line_edge(doc, a, b, name=f"B{i}"))
    return objs


def test_fill_nonplanar_quad(doc):
    from gensurf.features import make_fill
    lines = _quad_boundary(doc)
    fl = make_fill(doc)
    fl.Boundary = [(o, "") for o in lines]
    assert_recomputes(doc)

    face = fl.Shape.Faces[0]
    assert face.Area > 100.0  # curved patch over the 10x10 footprint
    for o in lines:  # boundary honored exactly
        assert fl.Shape.distToShape(o.Shape)[0] < 1e-6


def test_fill_pick_order_irrelevant(doc):
    from gensurf.features import make_fill
    lines = _quad_boundary(doc)
    fl = make_fill(doc)
    fl.Boundary = [(lines[2], ""), (lines[0], ""),
                   (lines[3], ""), (lines[1], "")]
    assert_recomputes(doc)
    assert fl.Shape.Faces[0].Area > 100.0


def test_fill_circle_gives_disk(doc):
    from gensurf.features import make_fill
    circ = doc.addObject("Part::Feature", "Circ")
    circ.Shape = Part.makeCircle(5)
    fl = make_fill(doc)
    fl.Boundary = [(circ, "")]
    assert_recomputes(doc)
    assert math.isclose(fl.Shape.Faces[0].Area, math.pi * 25, rel_tol=1e-3)


def test_fill_passing_point_bulges(doc):
    from gensurf.features import make_fill
    lines = _quad_boundary(doc, lift=0.0)  # flat square boundary
    pt = doc.addObject("Part::Feature", "P")
    pt.Shape = Part.Vertex(App.Vector(5, 5, 4))

    fl = make_fill(doc)
    fl.Boundary = [(o, "") for o in lines]
    assert_recomputes(doc)
    flat_area = fl.Shape.Faces[0].Area
    assert math.isclose(flat_area, 100.0, rel_tol=1e-6)

    fl.PassingPoints = [(pt, "")]
    assert_recomputes(doc)
    assert fl.Shape.distToShape(pt.Shape)[0] < 1e-3
    assert fl.Shape.Faces[0].Area > flat_area + 5


def test_fill_tangent_boundary_flattens(doc):
    """Quad with a lifted far edge; near edge belongs to a flat support
    strip. G1 on the near edge must flatten the patch's departure."""
    from gensurf.features import make_fill

    # support strip: z=0 plane, y in [-8, 0], carrying edge y=0
    sup = doc.addObject("Part::Feature", "Sup")
    sup.Shape = Part.makeLine(
        App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
        App.Vector(0, -8, 0))
    near_idx = next(i for i, e in enumerate(sup.Shape.Edges, 1)
                    if all(abs(v.Y) < 1e-9 for v in e.Vertexes)
                    and e.Length > 5)
    side1 = _line_edge(doc, (0, 0, 0), (0, 10, 4), name="Sd1")
    far = _line_edge(doc, (0, 10, 4), (10, 10, 4), name="Far")
    side2 = _line_edge(doc, (10, 10, 4), (10, 0, 0), name="Sd2")

    fl_g0 = make_fill(doc)
    fl_g0.Boundary = [(sup, f"Edge{near_idx}"), (side1, ""),
                      (far, ""), (side2, "")]
    assert_recomputes(doc)
    z_g0 = _probe_fill_z(fl_g0, 5, 1.0)

    fl_g1 = make_fill(doc)
    fl_g1.Boundary = [(side1, ""), (far, ""), (side2, "")]
    fl_g1.BoundaryTangent = [(sup, f"Edge{near_idx}")]
    assert_recomputes(doc)
    z_g1 = _probe_fill_z(fl_g1, 5, 1.0)

    # tangent to the flat support: hugs z=0 much longer
    assert z_g1 < z_g0 * 0.6
    # boundary still exact
    assert fl_g1.Shape.distToShape(
        sup.Shape.Edges[near_idx - 1])[0] < 1e-5


def _probe_fill_z(feature, x, y):
    probe = Part.makeLine(App.Vector(x, y, -50), App.Vector(x, y, 50))
    dist, pairs, _ = feature.Shape.distToShape(probe)
    assert dist < 1e-5
    return pairs[0][0].z


def test_fill_open_boundary_errors(doc):
    from gensurf.features import make_fill
    l1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="L1")
    l2 = _line_edge(doc, (10, 0, 0), (10, 10, 0), name="L2")
    fl = make_fill(doc)
    fl.Boundary = [(l1, ""), (l2, "")]
    with pytest.raises(GSFeatureError):
        fl.Proxy.execute(fl)


def test_fill_from_closed_sketch(doc):
    from gensurf.features import make_fill
    sk = doc.addObject("Sketcher::SketchObject", "Sk")
    pts = [App.Vector(0, 0, 0), App.Vector(8, 0, 0),
           App.Vector(8, 8, 0), App.Vector(0, 8, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]), False)
    doc.recompute()
    fl = make_fill(doc)
    fl.Boundary = [(sk, "")]
    assert_recomputes(doc)
    assert math.isclose(fl.Shape.Faces[0].Area, 64.0, rel_tol=1e-6)


# -- Extend disambiguation (corner picks, explicit element) ---------------


def test_extend_surface_corner_gives_clear_error(doc):
    from gensurf.features import make_extend
    support = _support_face(doc)
    ex = make_extend(doc)
    ex.Boundary = (support, ["Vertex1"])  # a corner of the face
    ex.Length = "5 mm"
    with pytest.raises(GSFeatureError, match="ambiguous"):
        ex.Proxy.execute(ex)


def test_extend_explicit_element_face(doc):
    """Explicit Element face pick works even when the boundary edge is
    shared (here: trivial single face, sanity of the path)."""
    from gensurf.features import make_extend
    support = _support_face(doc)
    edge_idx = next(i for i, e in enumerate(support.Shape.Edges, 1)
                    if all(abs(v.X - 20.0) < 1e-9 for v in e.Vertexes))
    ex = make_extend(doc)
    ex.Boundary = (support, [f"Edge{edge_idx}"])
    ex.Element = (support, ["Face1"])
    ex.Length = "5 mm"
    assert_recomputes(doc)
    assert math.isclose(ex.Shape.Area, 500.0, rel_tol=1e-9)


# -- MultiSection end continuity ------------------------------------------


def _mss_support_setup(doc):
    """Three stacked line sections; a flat support strip carries the
    first section (z=0 plane, y in [-8, 0], section at y=0)."""
    sup = doc.addObject("Part::Feature", "MSup")
    sup.Shape = Part.makeLine(
        App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
        App.Vector(0, -8, 0))
    s0 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="M0")
    s1 = _line_edge(doc, (0, 0, 5), (10, 0, 5), name="M1")
    s2 = _line_edge(doc, (0, 0, 10), (10, 0, 10), name="M2")
    return sup, s0, s1, s2


def test_multisection_tangent_first_support(doc):
    from gensurf.features import make_multisection
    sup, s0, s1, s2 = _mss_support_setup(doc)

    plain = make_multisection(doc)
    plain.Sections = [(s0, ""), (s1, ""), (s2, "")]
    assert_recomputes(doc)
    assert plain.Shape.BoundBox.YLength < 1e-9  # stays in the y=0 plane

    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, ""), (s2, "")]
    ms.SectionSupports = [(sup, ["Face1"])]
    ms.SectionSupportRows = [0]
    ms.SectionContinuities = [1, 0, 0]
    assert_recomputes(doc)

    # leaves the first section horizontally, away from the support (+y)
    assert ms.Shape.BoundBox.YMax > 0.8
    # slight opposite-side breathing of the interpolating spline is normal
    assert ms.Shape.BoundBox.YMin > -0.5
    # still passes through all sections
    for s in (s0, s1, s2):
        assert ms.Shape.distToShape(s.Shape)[0] < 5e-3


def test_multisection_curvature_first_support(doc):
    from gensurf.features import make_multisection
    sup, s0, s1, s2 = _mss_support_setup(doc)
    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, ""), (s2, "")]
    ms.SectionSupports = [(sup, ["Face1"])]
    ms.SectionSupportRows = [0]
    ms.SectionContinuities = [2, 0, 0]
    assert_recomputes(doc)
    assert ms.Shape.Faces
    assert ms.Shape.BoundBox.YMax > 0.5  # tangency held too
    for s in (s0, s2):
        assert ms.Shape.distToShape(s.Shape)[0] < 5e-3


def test_multisection_both_end_supports(doc):
    from gensurf.features import make_multisection
    sup, s0, s1, s2 = _mss_support_setup(doc)
    sup2 = doc.addObject("Part::Feature", "MSup2")
    sup2.Shape = Part.makeLine(
        App.Vector(0, 0, 10), App.Vector(10, 0, 10)).extrude(
        App.Vector(0, -8, 0))  # horizontal strip at the top too
    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, ""), (s2, "")]
    ms.SectionSupports = [(sup, ["Face1"]), (sup2, ["Face1"])]
    ms.SectionSupportRows = [0, 2]
    ms.SectionContinuities = [1, 0, 1]
    assert_recomputes(doc)
    # S-shaped: bulges +y at both ends, passes through the middle
    assert ms.Shape.BoundBox.YMax > 0.5
    assert ms.Shape.distToShape(s1.Shape)[0] < 5e-3


def test_multisection_continuity_needs_support(doc):
    from gensurf.features import make_multisection
    _sup, s0, s1, _s2 = _mss_support_setup(doc)
    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, "")]
    ms.SectionContinuities = [1, 0]
    with pytest.raises(GSFeatureError):
        ms.Proxy.execute(ms)


def test_multisection_supports_with_guides_rejected(doc):
    from gensurf.features import make_multisection
    sup, s0, s1, _s2 = _mss_support_setup(doc)
    g = _line_edge(doc, (0, 0, 0), (0, 0, 5), name="MG")
    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, "")]
    ms.Guides = [(g, "")]
    ms.SectionSupports = [(sup, ["Face1"])]
    ms.SectionSupportRows = [0]
    ms.SectionContinuities = [1, 0]
    with pytest.raises(GSFeatureError):
        ms.Proxy.execute(ms)


# -- MultiSection guide supports ------------------------------------------


def _mss_guide_support_setup(doc):
    """Two vertical line sections lofting a flat panel (y=0 plane);
    two guides at bottom (z=0) and top (z=8); the bottom guide lies on a
    horizontal support strip (z=0 plane, y in [0, 8])."""
    s0 = _line_edge(doc, (0, 0, 0), (0, 0, 8), name="V0")
    s1 = _line_edge(doc, (10, 0, 0), (10, 0, 8), name="V1")
    gb = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="Gb")
    gt = _line_edge(doc, (0, 0, 8), (10, 0, 8), name="Gt")
    sup = doc.addObject("Part::Feature", "GSup")
    sup.Shape = Part.makeLine(
        App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
        App.Vector(0, 8, 0))  # z=0 plane strip, y in [0, 8]
    return s0, s1, gb, gt, sup


def test_multisection_guide_support_tangent(doc):
    from gensurf.features import make_multisection
    s0, s1, gb, gt, sup = _mss_guide_support_setup(doc)

    plain = make_multisection(doc)
    plain.Sections = [(s0, ""), (s1, "")]
    plain.Guides = [(gb, ""), (gt, "")]
    assert_recomputes(doc)
    assert plain.Shape.BoundBox.YLength < 1e-6  # flat panel at y=0

    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, "")]
    ms.Guides = [(gb, ""), (gt, "")]
    ms.GuideSupports = [(sup, ["Face1"])]
    ms.GuideSupportRows = [0]        # support belongs to guide 1 (bottom)
    ms.GuideContinuities = [1, 0]    # tangent at bottom, free at top
    assert_recomputes(doc)

    # departs the bottom guide horizontally, away from the support (-y)
    assert ms.Shape.BoundBox.YMin < -0.15
    # true tangency: slice at x=5 and measure the departure slope
    def bottom_slope(shape):
        wires = shape.slice(App.Vector(1, 0, 0), 5.0)
        pts = []
        for w in wires:
            pts.extend(w.discretize(Number=100))
        pts.sort(key=lambda p: p.z)
        a, b = pts[0], next(p for p in pts if p.z > 0.3)
        dy, dz = abs(b.y - a.y), b.z - a.z
        return dz / max(dy, 1e-9)
    # tangent case: leaves nearly horizontally (small dz/dy);
    # the plain loft is perfectly vertical (dy = 0 -> huge slope)
    assert bottom_slope(ms.Shape) < 3.0
    assert bottom_slope(plain.Shape) > 100.0
    # still on the guides
    for g in (gb, gt):
        assert ms.Shape.distToShape(g.Shape)[0] < 5e-3


def test_multisection_guide_support_curvature_builds(doc):
    from gensurf.features import make_multisection
    s0, s1, gb, gt, sup = _mss_guide_support_setup(doc)
    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, "")]
    ms.Guides = [(gb, ""), (gt, "")]
    ms.GuideSupports = [(sup, ["Face1"])]
    ms.GuideSupportRows = [0]
    ms.GuideContinuities = [2, 0]
    assert_recomputes(doc)
    assert ms.Shape.Faces
    assert ms.Shape.BoundBox.YMin < -0.2  # tangency held


def test_multisection_guide_continuity_needs_support(doc):
    from gensurf.features import make_multisection
    s0, s1, gb, _gt, _sup = _mss_guide_support_setup(doc)
    ms = make_multisection(doc)
    ms.Sections = [(s0, ""), (s1, "")]
    ms.Guides = [(gb, "")]
    ms.GuideContinuities = [1]
    with pytest.raises(GSFeatureError):
        ms.Proxy.execute(ms)


# -- ConnectCurve ---------------------------------------------------------


def _connect_setup(doc):
    """Two collinear-ish lines with a gap; ends at (10,0,0) and (20,5,0)."""
    c1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="C1")
    c2 = _line_edge(doc, (20, 5, 0), (30, 5, 0), name="C2")
    return c1, c2


def _vertex_near(obj, pt):
    best, name = 1e9, None
    for i, v in enumerate(obj.Shape.Vertexes, 1):
        d = (v.Point - App.Vector(*pt)).Length
        if d < best:
            best, name = d, f"Vertex{i}"
    return name


def test_connect_tangent_default(doc):
    from gensurf.features import make_connect_curve
    c1, c2 = _connect_setup(doc)
    cn = make_connect_curve(doc)
    assert cn.Continuity1 == "Tangent"  # CATIA default
    cn.Point1 = (c1, [_vertex_near(c1, (10, 0, 0))])
    cn.Point2 = (c2, [_vertex_near(c2, (20, 5, 0))])
    assert_recomputes(doc)

    edge = cn.Shape.Edges[0]
    # joins the two ends
    assert (edge.Vertexes[0].Point - App.Vector(10, 0, 0)).Length < 1e-9
    assert (edge.Vertexes[-1].Point - App.Vector(20, 5, 0)).Length < 1e-9
    # tangent continuity with both lines (both +X at their ends)
    t0 = edge.tangentAt(edge.FirstParameter)
    t1 = edge.tangentAt(edge.LastParameter)
    assert t0.cross(App.Vector(1, 0, 0)).Length < 1e-9
    assert t1.cross(App.Vector(1, 0, 0)).Length < 1e-9


def test_connect_position_is_chord(doc):
    from gensurf.features import make_connect_curve
    c1, c2 = _connect_setup(doc)
    cn = make_connect_curve(doc)
    cn.Point1 = (c1, [_vertex_near(c1, (10, 0, 0))])
    cn.Point2 = (c2, [_vertex_near(c2, (20, 5, 0))])
    cn.Continuity1 = "Position"
    cn.Continuity2 = "Position"
    assert_recomputes(doc)
    edge = cn.Shape.Edges[0]
    chord = (App.Vector(20, 5, 0) - App.Vector(10, 0, 0)).Length
    assert math.isclose(edge.Length, chord, rel_tol=1e-9)  # straight


def test_connect_curvature_matches_arc(doc):
    from gensurf.features import make_connect_curve
    arc_obj = doc.addObject("Part::Feature", "CArc")
    arc_obj.Shape = Part.ArcOfCircle(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10),
        0, math.pi / 2).toShape()
    line = _line_edge(doc, (25, 0, 0), (35, 0, 0), name="CL")
    end = arc_obj.Shape.Vertexes[-1].Point

    cn = make_connect_curve(doc)
    cn.Point1 = (arc_obj, [_vertex_near(arc_obj, (end.x, end.y, end.z))])
    cn.Point2 = (line, [_vertex_near(line, (25, 0, 0))])
    cn.Continuity1 = "Curvature"
    cn.Continuity2 = "Tangent"
    assert_recomputes(doc)

    edge = cn.Shape.Edges[0]
    # curvature at the arc side matches the arc (kappa = 1/10)
    start_param = edge.FirstParameter \
        if (edge.valueAt(edge.FirstParameter) - end).Length < 1e-6 \
        else edge.LastParameter
    k = edge.curvatureAt(start_param)
    assert math.isclose(k, 0.1, rel_tol=5e-2)


def test_connect_tension_changes_shape(doc):
    from gensurf.features import make_connect_curve
    c1, c2 = _connect_setup(doc)
    cn = make_connect_curve(doc)
    cn.Point1 = (c1, [_vertex_near(c1, (10, 0, 0))])
    cn.Point2 = (c2, [_vertex_near(c2, (20, 5, 0))])
    assert_recomputes(doc)
    len_t1 = cn.Shape.Length

    cn.Tension1 = 3.0
    assert_recomputes(doc)
    assert abs(cn.Shape.Length - len_t1) > 1e-3


def test_connect_whole_object_pick_rejected(doc):
    from gensurf.features import make_connect_curve
    c1, c2 = _connect_setup(doc)
    cn = make_connect_curve(doc)
    cn.Point1 = (c1, [])
    cn.Point2 = (c2, [_vertex_near(c2, (20, 5, 0))])
    with pytest.raises(GSFeatureError):
        cn.Proxy.execute(cn)


# -- Boundary -------------------------------------------------------------


def _rounded_band(doc):
    """Extruded surface whose top boundary is line-arc-line (tangent
    chain), sides sharp: an open U profile swept in z."""
    a1 = Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0))
    arc = Part.ArcOfCircle(
        Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 5),
        -math.pi / 2, 0).toShape()
    a2 = Part.makeLine(App.Vector(15, 5, 0), App.Vector(15, 15, 0))
    wire = Part.Wire([a1, arc, a2])
    obj = doc.addObject("Part::Feature", "Band")
    obj.Shape = wire.extrude(App.Vector(0, 0, 6))
    return obj


def test_boundary_complete_loop(doc):
    from gensurf.features import make_boundary
    support = _support_face(doc)  # 20x20 plane
    bd = make_boundary(doc)
    bd.Edge = (support, ["Edge1"])
    bd.Propagation = "Complete boundary"
    assert_recomputes(doc)
    assert math.isclose(bd.Shape.Length, 80.0, rel_tol=1e-9)
    assert bd.Shape.Wires and bd.Shape.Wires[0].isClosed()


def test_boundary_no_propagation(doc):
    from gensurf.features import make_boundary
    support = _support_face(doc)
    bd = make_boundary(doc)
    bd.Edge = (support, ["Edge1"])
    bd.Propagation = "No propagation"
    assert_recomputes(doc)
    assert len(bd.Shape.Edges) == 1
    assert math.isclose(bd.Shape.Length, 20.0, rel_tol=1e-9)


def test_boundary_tangent_stops_at_corners(doc):
    from gensurf.features import make_boundary
    band = _rounded_band(doc)
    # find a top-boundary straight edge lying at z=6, from the first leg
    idx = next(i for i, e in enumerate(band.Shape.Edges, 1)
               if all(abs(v.Z - 6.0) < 1e-9 for v in e.Vertexes)
               and abs(e.Length - 10.0) < 1e-6)
    bd = make_boundary(doc)
    bd.Edge = (band, [f"Edge{idx}"])
    bd.Propagation = "Tangent continuity"
    assert_recomputes(doc)
    # line + tangent arc + line, stops at the free ends: full top chain
    expected = 10.0 + math.pi * 5 / 2 + 10.0
    assert math.isclose(bd.Shape.Length, expected, rel_tol=1e-6)

    # point continuity walks the whole free-boundary loop (top chain +
    # bottom chain + the two side rails)
    bd.Propagation = "Point continuity"
    assert_recomputes(doc)
    assert math.isclose(bd.Shape.Length, 2 * expected + 12.0,
                        rel_tol=1e-6)


def test_boundary_shell_excludes_shared_edge(doc):
    from gensurf.features import make_boundary
    # two faces sharing an edge: L-shell
    f1 = Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
        App.Vector(0, 8, 0))
    f2 = Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
        App.Vector(0, 0, 6))
    shell = Part.makeShell([f1.Faces[0], f2.Faces[0]])
    obj = doc.addObject("Part::Feature", "LShell")
    obj.Shape = shell
    # pick any free boundary edge
    from gensurf.features.boundary import free_boundary_chains
    chains = free_boundary_chains(obj.Shape)
    free_len = sum(w.Length for w in chains)
    # shared edge (length 10) must not be part of the free boundary
    total_edges = sum(e.Length for e in obj.Shape.Edges)
    assert free_len < total_edges - 9.0

    idx = next(i for i, e in enumerate(obj.Shape.Edges, 1)
               if any(e.isSame(be) for w in chains for be in w.Edges))
    bd = make_boundary(doc)
    bd.Edge = (obj, [f"Edge{idx}"])
    bd.Propagation = "Complete boundary"
    assert_recomputes(doc)
    assert not any(
        all(abs(v.Point.y) < 1e-9 and abs(v.Point.z) < 1e-9
            for v in e.Vertexes) and abs(e.Length - 10) < 1e-6
        for e in bd.Shape.Edges)


def test_boundary_limits_keep_picked_side(doc):
    from gensurf.features import make_boundary
    support = _support_face(doc)  # square, corners at (0,0),(20,0),...
    # picked edge: y=0 bottom edge; limits at two opposite corners
    bottom = next(i for i, e in enumerate(support.Shape.Edges, 1)
                  if all(abs(v.Y) < 1e-9 for v in e.Vertexes))
    l1 = doc.addObject("Part::Feature", "L1")
    l1.Shape = Part.Vertex(App.Vector(0, 0, 0))
    l2 = doc.addObject("Part::Feature", "L2")
    l2.Shape = Part.Vertex(App.Vector(20, 0, 0))
    bd = make_boundary(doc)
    bd.Edge = (support, [f"Edge{bottom}"])
    bd.Propagation = "Point continuity"
    bd.Limit1 = (l1, ["Vertex1"])
    bd.Limit2 = (l2, ["Vertex1"])
    assert_recomputes(doc)
    # kept portion: just the bottom edge between the two corners
    assert math.isclose(bd.Shape.Length, 20.0, rel_tol=1e-6)
    assert all(abs(v.Y) < 1e-9 for e in bd.Shape.Edges
               for v in e.Vertexes)


# -- Extract --------------------------------------------------------------


def _three_face_shell(doc):
    """Faces A(z=0, x 0-10) + B(z=0, x 10-20) coplanar, C vertical at
    x=20: A-B smooth, B-C sharp."""
    fa = Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
        App.Vector(0, 8, 0)).Faces[0]
    fb = Part.makeLine(App.Vector(10, 0, 0), App.Vector(20, 0, 0)).extrude(
        App.Vector(0, 8, 0)).Faces[0]
    fc = Part.makeLine(App.Vector(20, 0, 0), App.Vector(20, 0, 6)).extrude(
        App.Vector(0, 8, 0)).Faces[0]
    obj = doc.addObject("Part::Feature", "Shell3")
    obj.Shape = Part.makeShell([fa, fb, fc])
    return obj


def _face_index_at(obj, x):
    return next(i for i, f in enumerate(obj.Shape.Faces, 1)
                if abs(f.CenterOfMass.x - x) < 1e-6)


def test_extract_no_propagation(doc):
    from gensurf.features import make_extract
    shell = _three_face_shell(doc)
    ex = make_extract(doc)
    ex.Element = (shell, [f"Face{_face_index_at(shell, 5)}"])
    assert ex.Propagation == "No propagation"  # CATIA default
    assert_recomputes(doc)
    assert len(ex.Shape.Faces) == 1
    assert math.isclose(ex.Shape.Faces[0].Area, 80.0, rel_tol=1e-9)


def test_extract_tangent_propagation(doc):
    from gensurf.features import make_extract
    shell = _three_face_shell(doc)
    ex = make_extract(doc)
    ex.Element = (shell, [f"Face{_face_index_at(shell, 5)}"])
    ex.Propagation = "Tangent continuity"
    assert_recomputes(doc)
    # A + B (coplanar) but not C (perpendicular)
    assert len(ex.Shape.Faces) == 2
    assert math.isclose(sum(f.Area for f in ex.Shape.Faces), 160.0,
                        rel_tol=1e-9)


def test_extract_point_propagation(doc):
    from gensurf.features import make_extract
    shell = _three_face_shell(doc)
    ex = make_extract(doc)
    ex.Element = (shell, [f"Face{_face_index_at(shell, 5)}"])
    ex.Propagation = "Point continuity"
    assert_recomputes(doc)
    assert len(ex.Shape.Faces) == 3


def test_extract_edge_chain(doc):
    from gensurf.features import make_extract
    # L-polyline object: two edges meeting at a right angle
    obj = doc.addObject("Part::Feature", "LPoly")
    obj.Shape = Part.Wire([
        Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)),
        Part.makeLine(App.Vector(10, 0, 0), App.Vector(10, 8, 0))])
    ex = make_extract(doc)
    ex.Element = (obj, ["Edge1"])
    ex.Propagation = "Tangent continuity"
    assert_recomputes(doc)
    assert len(ex.Shape.Edges) == 1  # right angle stops tangent walk

    ex.Propagation = "Point continuity"
    assert_recomputes(doc)
    assert len(ex.Shape.Edges) == 2


def test_extract_follows_source_edit(doc):
    from gensurf.features import make_extract
    shell = _three_face_shell(doc)
    ex = make_extract(doc)
    ex.Element = (shell, [f"Face{_face_index_at(shell, 5)}"])
    assert_recomputes(doc)
    area_before = ex.Shape.Faces[0].Area
    assert area_before > 0


# -- MultiExtract ---------------------------------------------------------


def test_multi_extract_mixed_rows(doc):
    from gensurf.features import make_multi_extract
    shell = _three_face_shell(doc)
    fa = _face_index_at(shell, 5)
    fc = next(i for i, f in enumerate(shell.Shape.Faces, 1)
              if abs(f.CenterOfMass.x - 20.0) < 1e-6)
    me = make_multi_extract(doc)
    me.Elements = [(shell, [f"Face{fa}"]), (shell, [f"Face{fc}"])]
    me.Propagations = [2, 0]  # tangent on A (-> A+B), none on C
    assert_recomputes(doc)
    assert len(me.Shape.Faces) == 3


def test_multi_extract_dedupes_overlap(doc):
    from gensurf.features import make_multi_extract
    shell = _three_face_shell(doc)
    fa = _face_index_at(shell, 5)
    fb = _face_index_at(shell, 15)
    me = make_multi_extract(doc)
    me.Elements = [(shell, [f"Face{fa}"]), (shell, [f"Face{fb}"])]
    me.Propagations = [2, 0]  # A tangent already captures B
    assert_recomputes(doc)
    assert len(me.Shape.Faces) == 2  # no duplicate B


def test_multi_extract_complementary(doc):
    from gensurf.features import make_multi_extract
    shell = _three_face_shell(doc)
    fa = _face_index_at(shell, 5)
    me = make_multi_extract(doc)
    me.Elements = [(shell, [f"Face{fa}"])]
    me.Propagations = [0]
    me.Complementary = True
    assert_recomputes(doc)
    assert len(me.Shape.Faces) == 2
    assert all(abs(f.CenterOfMass.x - 5.0) > 1e-6
               for f in me.Shape.Faces)


def test_multi_extract_per_row_threshold(doc):
    from gensurf.features import make_multi_extract
    # two faces meeting at a 1-degree dihedral
    fa = Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
        App.Vector(0, 8, 0)).Faces[0]
    d = App.Vector(0, 8 * math.cos(math.radians(1)),
                   8 * math.sin(math.radians(1)))
    fb = Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
        d.negative()).Faces[0]
    obj = doc.addObject("Part::Feature", "Bent")
    obj.Shape = Part.makeShell([fa, fb])
    idx = next(i for i, f in enumerate(obj.Shape.Faces, 1)
               if f.CenterOfMass.y > 0)

    me = make_multi_extract(doc)
    me.Elements = [(obj, [f"Face{idx}"])]
    me.Propagations = [2]
    me.Thresholds = [0.5]  # stricter than the 1-degree bend
    assert_recomputes(doc)
    assert len(me.Shape.Faces) == 1

    me.Thresholds = [2.0]  # looser: crosses the bend
    assert_recomputes(doc)
    assert len(me.Shape.Faces) == 2


def test_multi_extract_edge_rows(doc):
    from gensurf.features import make_multi_extract
    obj = doc.addObject("Part::Feature", "LPoly2")
    obj.Shape = Part.Wire([
        Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)),
        Part.makeLine(App.Vector(10, 0, 0), App.Vector(10, 8, 0))])
    me = make_multi_extract(doc)
    me.Elements = [(obj, ["Edge1"])]
    me.Propagations = [1]  # point continuity: both edges
    assert_recomputes(doc)
    assert len(me.Shape.Edges) == 2


# -- Join -----------------------------------------------------------------


def test_join_touching_surfaces(doc):
    from gensurf.features import make_join
    a = doc.addObject("Part::Feature", "JA")
    a.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)) \
        .extrude(App.Vector(0, 8, 0))
    b = doc.addObject("Part::Feature", "JB")
    b.Shape = Part.makeLine(App.Vector(0, 8, 0), App.Vector(10, 8, 0)) \
        .extrude(App.Vector(0, 8, 0))
    jn = make_join(doc)
    jn.Elements = [(a, ""), (b, "")]
    assert_recomputes(doc)
    assert len(jn.Shape.Faces) == 2
    assert jn.Shape.ShapeType == "Shell"  # properly sewn


def test_join_connectivity_check(doc):
    from gensurf.features import make_join
    a = doc.addObject("Part::Feature", "JA")
    a.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)) \
        .extrude(App.Vector(0, 8, 0))
    b = doc.addObject("Part::Feature", "JB")
    b.Shape = Part.makeLine(App.Vector(0, 50, 0), App.Vector(10, 50, 0)) \
        .extrude(App.Vector(0, 8, 0))
    jn = make_join(doc)
    jn.Elements = [(a, ""), (b, "")]
    with pytest.raises(GSFeatureError):
        jn.Proxy.execute(jn)
    jn.CheckConnectivity = False
    assert_recomputes(doc)
    assert len(jn.Shape.Faces) == 2  # allowed as disconnected compound


def test_join_tangency_check(doc):
    from gensurf.features import make_join
    a = doc.addObject("Part::Feature", "JA")
    a.Shape = Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)) \
        .extrude(App.Vector(0, 8, 0))
    c = doc.addObject("Part::Feature", "JC")  # perpendicular neighbour
    c.Shape = Part.makeLine(App.Vector(0, 8, 0), App.Vector(10, 8, 0)) \
        .extrude(App.Vector(0, 0, 6))
    jn = make_join(doc)
    jn.Elements = [(a, ""), (c, "")]
    jn.CheckTangency = True
    with pytest.raises(GSFeatureError):
        jn.Proxy.execute(jn)
    jn.CheckTangency = False
    assert_recomputes(doc)
    assert len(jn.Shape.Faces) == 2


def test_join_curves_with_merging_distance(doc):
    from gensurf.features import make_join
    c1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="JC1")
    c2 = _line_edge(doc, (10.0005, 0, 0), (20, 0, 0), name="JC2")
    jn = make_join(doc)
    jn.Elements = [(c1, ""), (c2, "")]
    jn.MergingDistance = "0.001 mm"
    assert_recomputes(doc)
    assert len(jn.Shape.Wires) == 1
    assert len(jn.Shape.Edges) == 2

    jn.MergingDistance = "0.0001 mm"  # tighter than the gap
    with pytest.raises(GSFeatureError):
        jn.Proxy.execute(jn)


# -- Point ----------------------------------------------------------------


def test_point_coordinates_and_reference(doc):
    from gensurf.features import make_point
    pt = make_point(doc)
    pt.X, pt.Y, pt.Z = "3 mm", "4 mm", "5 mm"
    assert_recomputes(doc)
    assert (pt.Shape.Point - App.Vector(3, 4, 5)).Length < 1e-9

    ref = doc.addObject("Part::Feature", "Ref")
    ref.Shape = Part.Vertex(App.Vector(10, 10, 10))
    pt.RefPoint = (ref, ["Vertex1"])
    assert_recomputes(doc)
    assert (pt.Shape.Point - App.Vector(13, 14, 15)).Length < 1e-9


def test_point_on_curve_ratio(doc):
    from gensurf.features import make_point
    arc_obj = doc.addObject("Part::Feature", "PArc")
    arc_obj.Shape = Part.ArcOfCircle(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10),
        0, math.pi).toShape()
    pt = make_point(doc)
    pt.PointType = "On curve"
    pt.Curve = (arc_obj, "")
    pt.Ratio = 0.5
    assert_recomputes(doc)
    # halfway along a half-circle: the top of the arc
    assert (pt.Shape.Point - App.Vector(0, 10, 0)).Length < 1e-2


def test_point_center_and_between(doc):
    from gensurf.features import make_point
    circ = doc.addObject("Part::Feature", "PCirc")
    circ.Shape = Part.makeCircle(7, App.Vector(3, 4, 5))
    pt = make_point(doc)
    pt.PointType = "Center"
    pt.Curve = (circ, "")
    assert_recomputes(doc)
    assert (pt.Shape.Point - App.Vector(3, 4, 5)).Length < 1e-9

    p1 = doc.addObject("Part::Feature", "P1")
    p1.Shape = Part.Vertex(App.Vector(0, 0, 0))
    p2 = doc.addObject("Part::Feature", "P2")
    p2.Shape = Part.Vertex(App.Vector(10, 0, 0))
    bt = make_point(doc)
    bt.PointType = "Between"
    bt.RefPoint = (p1, ["Vertex1"])
    bt.Point2 = (p2, ["Vertex1"])
    bt.Ratio = 0.25
    assert_recomputes(doc)
    assert (bt.Shape.Point - App.Vector(2.5, 0, 0)).Length < 1e-9


def test_point_on_surface_projection(doc):
    from gensurf.features import make_point
    support = _support_face(doc)
    ref = doc.addObject("Part::Feature", "PRef")
    ref.Shape = Part.Vertex(App.Vector(5, 7, 12))
    pt = make_point(doc)
    pt.PointType = "On surface"
    pt.Support = (support, ["Face1"])
    pt.RefPoint = (ref, ["Vertex1"])
    assert_recomputes(doc)
    assert (pt.Shape.Point - App.Vector(5, 7, 0)).Length < 1e-9


# -- Line -----------------------------------------------------------------


def test_line_point_point_with_extensions(doc):
    from gensurf.features import make_line
    p1 = doc.addObject("Part::Feature", "LP1")
    p1.Shape = Part.Vertex(App.Vector(0, 0, 0))
    p2 = doc.addObject("Part::Feature", "LP2")
    p2.Shape = Part.Vertex(App.Vector(10, 0, 0))
    ln = make_line(doc)
    ln.Point1 = (p1, ["Vertex1"])
    ln.Point2 = (p2, ["Vertex1"])
    assert_recomputes(doc)
    assert math.isclose(ln.Shape.Length, 10.0, rel_tol=1e-9)

    ln.Start = "2 mm"
    ln.End = "3 mm"
    assert_recomputes(doc)
    assert math.isclose(ln.Shape.Length, 15.0, rel_tol=1e-9)
    xs = [v.X for v in ln.Shape.Vertexes]
    assert math.isclose(min(xs), -2.0, abs_tol=1e-9)
    assert math.isclose(max(xs), 13.0, abs_tol=1e-9)


def test_line_tangent_to_curve(doc):
    from gensurf.features import make_line
    arc_obj = doc.addObject("Part::Feature", "LArc")
    arc_obj.Shape = Part.ArcOfCircle(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 10),
        0, math.pi / 2).toShape()
    p = doc.addObject("Part::Feature", "LTp")
    p.Shape = Part.Vertex(App.Vector(10, 0, 0))  # arc start
    ln = make_line(doc)
    ln.LineType = "Tangent to curve"
    ln.Point1 = (p, ["Vertex1"])
    ln.DirectionRef = (arc_obj, "")
    ln.Length = "8 mm"
    assert_recomputes(doc)
    d = ln.Shape.Vertexes[-1].Point - ln.Shape.Vertexes[0].Point
    assert abs(d.dot(App.Vector(1, 0, 0))) < 1e-6  # tangent at (10,0) is +Y


def test_line_normal_to_surface(doc):
    from gensurf.features import make_line
    support = _support_face(doc)
    p = doc.addObject("Part::Feature", "LNp")
    p.Shape = Part.Vertex(App.Vector(5, 5, 0))
    ln = make_line(doc)
    ln.LineType = "Normal to surface"
    ln.Point1 = (p, ["Vertex1"])
    ln.DirectionRef = (support, ["Face1"])
    ln.Length = "6 mm"
    ln.MirroredExtent = True
    assert_recomputes(doc)
    zs = [v.Z for v in ln.Shape.Vertexes]
    assert math.isclose(max(zs) - min(zs), 12.0, rel_tol=1e-9)
    assert all(abs(v.X - 5) < 1e-9 and abs(v.Y - 5) < 1e-9
               for v in ln.Shape.Vertexes)


# -- Intersection ---------------------------------------------------------


def test_intersection_crossing_lines(doc):
    from gensurf.features import make_intersection
    l1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="X1")
    l2 = _line_edge(doc, (5, -5, 0), (5, 5, 0), name="X2")
    iv = make_intersection(doc)
    iv.Element1 = (l1, "")
    iv.Element2 = (l2, "")
    assert_recomputes(doc)
    assert len(iv.Shape.Vertexes) == 1
    assert (iv.Shape.Vertexes[0].Point - App.Vector(5, 0, 0)).Length < 1e-9


def test_intersection_common_area_curve_and_points(doc):
    from gensurf.features import make_intersection
    l1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="O1")
    l2 = _line_edge(doc, (5, 0, 0), (15, 0, 0), name="O2")
    iv = make_intersection(doc)
    iv.Element1 = (l1, "")
    iv.Element2 = (l2, "")
    assert_recomputes(doc)  # default Result: Curve
    assert len(iv.Shape.Edges) == 1
    assert math.isclose(iv.Shape.Length, 5.0, rel_tol=1e-9)

    iv.CurveResult = "Points"
    assert_recomputes(doc)
    assert not iv.Shape.Edges
    pts = sorted(v.Point.x for v in iv.Shape.Vertexes)
    assert pts == pytest.approx([5.0, 10.0])


def test_intersection_face_face(doc):
    from gensurf.features import make_intersection
    fa = doc.addObject("Part::Feature", "FA")
    fa.Shape = Part.makeLine(
        App.Vector(0, 0, 5), App.Vector(10, 0, 5)).extrude(
        App.Vector(0, 10, 0))
    fb = doc.addObject("Part::Feature", "FB")
    fb.Shape = Part.makeLine(
        App.Vector(0, 5, 0), App.Vector(10, 5, 0)).extrude(
        App.Vector(0, 0, 10))
    iv = make_intersection(doc)
    iv.Element1 = (fa, ["Face1"])
    iv.Element2 = (fb, ["Face1"])
    assert_recomputes(doc)
    assert len(iv.Shape.Edges) == 1
    assert all(abs(v.Y - 5) < 1e-9 and abs(v.Z - 5) < 1e-9
               for v in iv.Shape.Vertexes)


def test_intersection_noncoplanar_lines(doc):
    from gensurf.features import make_intersection
    l1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="N1")
    l2 = _line_edge(doc, (5, -5, 3), (5, 5, 3), name="N2")
    iv = make_intersection(doc)
    iv.Element1 = (l1, "")
    iv.Element2 = (l2, "")
    with pytest.raises(GSFeatureError):
        iv.Proxy.execute(iv)
    iv.NonCoplanarSegments = True
    assert_recomputes(doc)
    assert (iv.Shape.Vertexes[0].Point
            - App.Vector(5, 0, 1.5)).Length < 1e-9


def test_intersection_extend_linear_supports(doc):
    from gensurf.features import make_intersection
    l1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="E1x")
    l2 = _line_edge(doc, (5, 2, 0), (5, 6, 0), name="E2x")  # stops short
    iv = make_intersection(doc)
    iv.Element1 = (l1, "")
    iv.Element2 = (l2, "")
    with pytest.raises(GSFeatureError):
        iv.Proxy.execute(iv)
    iv.ExtendLinear2 = True
    assert_recomputes(doc)
    assert (iv.Shape.Vertexes[0].Point - App.Vector(5, 0, 0)).Length < 1e-9


def test_intersection_surface_part(doc):
    from gensurf.features import make_intersection
    support = _support_face(doc)
    box = doc.addObject("Part::Feature", "IBox")
    box.Shape = Part.makeBox(4, 4, 10, App.Vector(2, 2, -2))
    iv = make_intersection(doc)
    iv.Element1 = (support, ["Face1"])
    iv.Element2 = (box, "")
    assert_recomputes(doc)  # default: Contour
    assert len(iv.Shape.Edges) == 4
    assert math.isclose(iv.Shape.Length, 16.0, rel_tol=1e-9)

    iv.SurfaceResult = "Surface"
    assert_recomputes(doc)
    assert len(iv.Shape.Faces) == 1
    assert math.isclose(iv.Shape.Faces[0].Area, 16.0, rel_tol=1e-9)


# -- ParallelCurve --------------------------------------------------------


def test_parallel_line_and_through_point(doc):
    from gensurf.features import make_parallel_curve
    ln = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="PL")
    pc = make_parallel_curve(doc)
    pc.Curve = (ln, "")
    pc.Constant = "2 mm"
    assert_recomputes(doc)
    assert math.isclose(pc.Shape.Length, 10.0, rel_tol=1e-9)
    assert all(abs(abs(v.Y) - 2.0) < 1e-9 for v in pc.Shape.Vertexes)

    pt = doc.addObject("Part::Feature", "PPt")
    pt.Shape = Part.Vertex(App.Vector(5, 3, 0))
    pc.Point = (pt, ["Vertex1"])
    assert_recomputes(doc)
    assert all(abs(v.Y - 3.0) < 1e-9 for v in pc.Shape.Vertexes)


def test_parallel_corner_sharp_vs_round(doc):
    from gensurf.features import make_parallel_curve
    lw = doc.addObject("Part::Feature", "PLW")
    lw.Shape = Part.Wire([
        Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)),
        Part.makeLine(App.Vector(10, 0, 0), App.Vector(10, 10, 0))])
    pc = make_parallel_curve(doc)
    pc.Curve = (lw, "")
    pc.Constant = "2 mm"
    assert_recomputes(doc)
    sharp_len = pc.Shape.Length
    pc.CornerType = "Round"
    assert_recomputes(doc)
    round_len = pc.Shape.Length
    assert round_len < sharp_len  # arc corner is shorter than the miter
    assert any(not isinstance(e.Curve, Part.Line)
               for e in pc.Shape.Edges)


def test_parallel_both_sides(doc):
    from gensurf.features import make_parallel_curve
    ln = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="PB")
    pc = make_parallel_curve(doc)
    pc.Curve = (ln, "")
    pc.Constant = "2 mm"
    pc.BothSides = True
    assert_recomputes(doc)
    assert len(pc.Shape.Wires) == 2
    ys = sorted(v.Y for v in pc.Shape.Vertexes)
    assert ys[0] == pytest.approx(-2.0) and ys[-1] == pytest.approx(2.0)


def test_parallel_on_cylinder(doc):
    from gensurf.features import make_parallel_curve
    cyl = doc.addObject("Part::Feature", "PCyl")
    cyl.Shape = Part.makeCylinder(10, 20).Faces[0]
    # the bottom circular edge of the lateral face
    bottom = min(range(len(cyl.Shape.Edges)),
                 key=lambda i: cyl.Shape.Edges[i].BoundBox.ZMax)
    pc = make_parallel_curve(doc)
    pc.Curve = (cyl, [f"Edge{bottom + 1}"])
    pc.Support = (cyl, ["Face1"])
    pc.Constant = "5 mm"
    for mode in ("Euclidean", "Geodesic"):
        pc.ParallelMode = mode
        assert_recomputes(doc)
        pts = pc.Shape.Edges[0].discretize(24)
        zs = [p.z for p in pts]
        assert all(abs(abs(z) - 5.0) < 1e-3 for z in zs), mode
        assert all(abs(math.hypot(p.x, p.y) - 10.0) < 1e-3
                   for p in pts), mode


# -- CurveOffset3D --------------------------------------------------------


def test_curve_offset_3d_line(doc):
    from gensurf.features import make_curve_offset_3d
    ln = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="C3L")
    co = make_curve_offset_3d(doc)
    co.Curve = (ln, "")
    co.Offset = "2 mm"  # default pulling direction: +Z
    assert_recomputes(doc)
    assert math.isclose(co.Shape.Length, 10.0, rel_tol=1e-6)
    assert all(abs(v.Y - 2.0) < 1e-6 and abs(v.Z) < 1e-9
               for v in co.Shape.Vertexes)


def test_curve_offset_3d_arc(doc):
    from gensurf.features import make_curve_offset_3d
    arc_obj = doc.addObject("Part::Feature", "C3A")
    arc_obj.Shape = Part.ArcOfCircle(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5),
        0, math.pi / 2).toShape()
    co = make_curve_offset_3d(doc)
    co.Curve = (arc_obj, "")
    co.Offset = "2 mm"
    assert_recomputes(doc)
    for p in co.Shape.Edges[0].discretize(16):
        assert abs(math.hypot(p.x, p.y) - 3.0) < 1e-3  # shrunk arc

    co.ReverseDirection = True
    assert_recomputes(doc)
    for p in co.Shape.Edges[0].discretize(16):
        assert abs(math.hypot(p.x, p.y) - 7.0) < 1e-3  # grown arc


# -- Circle ---------------------------------------------------------------


def test_circle_center_radius_and_angles(doc):
    from gensurf.features import make_circle
    support = _support_face(doc)
    c = doc.addObject("Part::Feature", "CC")
    c.Shape = Part.Vertex(App.Vector(5, 5, 0))
    ci = make_circle(doc)
    ci.Center = (c, ["Vertex1"])
    ci.Support = (support, ["Face1"])
    ci.Radius = "4 mm"
    assert_recomputes(doc)
    assert math.isclose(ci.Shape.Length, 2 * math.pi * 4, rel_tol=1e-9)
    assert all(abs(v.Z) < 1e-9 for v in ci.Shape.Vertexes)

    ci.Limitation = "Start/End angles"
    ci.Start, ci.End = "0 deg", "90 deg"
    assert_recomputes(doc)
    assert math.isclose(ci.Shape.Length, math.pi * 4 / 2, rel_tol=1e-9)


def test_circle_center_point(doc):
    from gensurf.features import make_circle
    c = doc.addObject("Part::Feature", "CPc")
    c.Shape = Part.Vertex(App.Vector(0, 0, 0))
    p = doc.addObject("Part::Feature", "CPp")
    p.Shape = Part.Vertex(App.Vector(3, 4, 0))
    ci = make_circle(doc)
    ci.CircleType = "Center and point"
    ci.Center = (c, ["Vertex1"])
    ci.Point1 = (p, ["Vertex1"])
    assert_recomputes(doc)
    assert math.isclose(ci.Shape.Length, 2 * math.pi * 5, rel_tol=1e-9)


def test_circle_two_points_radius(doc):
    from gensurf.features import make_circle
    p1 = doc.addObject("Part::Feature", "C2a")
    p1.Shape = Part.Vertex(App.Vector(0, 0, 0))
    p2 = doc.addObject("Part::Feature", "C2b")
    p2.Shape = Part.Vertex(App.Vector(6, 0, 0))
    ci = make_circle(doc)
    ci.CircleType = "Two points and radius"
    ci.Point1 = (p1, ["Vertex1"])
    ci.Point2 = (p2, ["Vertex1"])
    ci.Radius = "5 mm"
    assert_recomputes(doc)
    for pt in (App.Vector(0, 0, 0), App.Vector(6, 0, 0)):
        assert ci.Shape.distToShape(Part.Vertex(pt))[0] < 1e-9
    center1 = ci.Shape.Edges[0].Curve.Center
    ci.SecondSolution = True
    assert_recomputes(doc)
    center2 = ci.Shape.Edges[0].Curve.Center
    assert (center1 - center2).Length > 7.9  # (3,4) vs (3,-4)

    ci.Limitation = "Trimmed ends"
    assert_recomputes(doc)
    assert ci.Shape.Length < 2 * math.pi * 5 / 2 + 1e-6
    for pt in (App.Vector(0, 0, 0), App.Vector(6, 0, 0)):
        assert ci.Shape.distToShape(Part.Vertex(pt))[0] < 1e-9


def test_circle_three_points_trimmed(doc):
    from gensurf.features import make_circle
    pts = [App.Vector(0, 0, 0), App.Vector(5, 5, 0), App.Vector(10, 0, 0)]
    objs = []
    for i, p in enumerate(pts):
        o = doc.addObject("Part::Feature", f"C3p{i}")
        o.Shape = Part.Vertex(p)
        objs.append(o)
    ci = make_circle(doc)
    ci.CircleType = "Three points"
    ci.Point1 = (objs[0], ["Vertex1"])
    ci.Point2 = (objs[1], ["Vertex1"])
    ci.Point3 = (objs[2], ["Vertex1"])
    assert_recomputes(doc)
    for p in pts:
        assert ci.Shape.distToShape(Part.Vertex(p))[0] < 1e-9

    ci.Limitation = "Trimmed ends"
    assert_recomputes(doc)
    trimmed_len = ci.Shape.Length
    # the kept arc passes through the middle point
    assert ci.Shape.distToShape(Part.Vertex(pts[1]))[0] < 1e-9
    ci.Limitation = "Complementary"
    assert_recomputes(doc)
    assert ci.Shape.distToShape(Part.Vertex(pts[1]))[0] > 0.5
    full = 2 * math.pi * ci.Shape.Edges[0].Curve.Radius
    assert math.isclose(trimmed_len + ci.Shape.Length, full, rel_tol=1e-6)


def test_circle_center_and_axis(doc):
    from gensurf.features import make_circle
    ax = _line_edge(doc, (0, 0, 0), (0, 0, 10), name="CAx")
    p = doc.addObject("Part::Feature", "CAp")
    p.Shape = Part.Vertex(App.Vector(4, 0, 5))
    ci = make_circle(doc)
    ci.CircleType = "Center and axis"
    ci.Axis = (ax, "")
    ci.Point1 = (p, ["Vertex1"])
    assert_recomputes(doc)
    assert math.isclose(ci.Shape.Length, 2 * math.pi * 4, rel_tol=1e-9)
    assert abs(ci.Shape.BoundBox.ZMin - 5) < 1e-9
    assert abs(ci.Shape.BoundBox.ZMax - 5) < 1e-9


# -- Corner ---------------------------------------------------------------


def test_corner_two_lines(doc):
    from gensurf.features import make_corner
    l1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="K1")
    l2 = _line_edge(doc, (10, 0, 0), (10, 10, 0), name="K2")
    co = make_corner(doc)
    co.Element1 = (l1, "")
    co.Element2 = (l2, "")
    co.Radius = "2 mm"
    assert_recomputes(doc)
    assert len(co.Shape.Edges) == 1
    assert math.isclose(co.Shape.Edges[0].Curve.Radius, 2.0, rel_tol=1e-9)
    # the arc is tangent to both lines: its ends touch them
    assert co.Shape.distToShape(l1.Shape)[0] < 1e-7
    assert co.Shape.distToShape(l2.Shape)[0] < 1e-7


def test_corner_trim_elements(doc):
    from gensurf.features import make_corner
    l1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="KT1")
    l2 = _line_edge(doc, (10, 0, 0), (10, 10, 0), name="KT2")
    co = make_corner(doc)
    co.Element1 = (l1, "")
    co.Element2 = (l2, "")
    co.Radius = "2 mm"
    co.TrimElement1 = True
    co.TrimElement2 = True
    assert_recomputes(doc)
    assert len(co.Shape.Edges) == 3
    assert len(co.Shape.Wires) == 1
    # line + quarter arc + line
    expect = 8.0 + math.pi * 2 / 2 + 8.0
    assert math.isclose(co.Shape.Length, expect, rel_tol=1e-6)


def test_corner_solutions_differ(doc):
    from gensurf.features import make_corner
    l1 = _line_edge(doc, (-10, 0, 0), (10, 0, 0), name="KS1")
    l2 = _line_edge(doc, (0, -10, 0), (0, 10, 0), name="KS2")
    co = make_corner(doc)
    co.Element1 = (l1, "")
    co.Element2 = (l2, "")
    co.Radius = "3 mm"
    assert_recomputes(doc)
    centers = set()
    for i in range(4):
        co.Solution = i
        assert_recomputes(doc)
        c = co.Shape.Edges[0].Curve.Center
        centers.add((round(c.x, 3), round(c.y, 3)))
    assert len(centers) >= 2  # crossing lines: several corner solutions


# -- ConnectCurve upgrade -------------------------------------------------


def test_connect_trim_elements(doc):
    from gensurf.features import make_connect_curve
    c1, c2 = _connect_setup(doc)  # ends at (10,0,0) and (20,5,0)
    cn = make_connect_curve(doc)
    cn.Point1 = (c1, [_vertex_near(c1, App.Vector(10, 0, 0))])
    cn.Point2 = (c2, [_vertex_near(c2, App.Vector(20, 5, 0))])
    cn.TrimElements = True
    assert_recomputes(doc)
    assert len(cn.Shape.Wires) == 1
    assert len(cn.Shape.Edges) == 3
    # spans from the free end of curve 1 to the free end of curve 2
    xs = [v.Point.x for v in cn.Shape.Vertexes]
    assert min(xs) < 1e-9 and max(xs) > 30 - 1e-9


def test_connect_explicit_curve_link(doc):
    from gensurf.features import make_connect_curve
    c1, c2 = _connect_setup(doc)
    cn = make_connect_curve(doc)
    cn.Point1 = (c1, [_vertex_near(c1, App.Vector(10, 0, 0))])
    cn.Curve1 = (c1, "")
    cn.Point2 = (c2, [_vertex_near(c2, App.Vector(20, 5, 0))])
    cn.Curve2 = (c2, "")
    assert_recomputes(doc)
    assert cn.Shape.Vertexes[0].Point.x == pytest.approx(10.0)
    assert cn.Shape.Vertexes[-1].Point.x == pytest.approx(20.0)


# -- Spline ---------------------------------------------------------------


def test_spline_through_points(doc):
    from gensurf.features import make_spline
    pts = [(0, 0, 0), (5, 4, 0), (10, 0, 0), (15, -3, 2)]
    objs = []
    for i, p in enumerate(pts):
        o = doc.addObject("Part::Feature", f"SP{i}")
        o.Shape = Part.Vertex(App.Vector(*p))
        objs.append(o)
    sp = make_spline(doc)
    sp.Points = [(o, "") for o in objs]
    assert_recomputes(doc)
    for p in pts:
        assert sp.Shape.distToShape(
            Part.Vertex(App.Vector(*p)))[0] < 1e-9
    assert not sp.Shape.Edges[0].Closed

    sp.CloseSpline = True
    assert_recomputes(doc)
    assert sp.Shape.Edges[0].Closed


def test_spline_tangent_direction(doc):
    from gensurf.features import make_spline
    objs = []
    for i, p in enumerate([(0, 0, 0), (10, 5, 0), (20, 0, 0)]):
        o = doc.addObject("Part::Feature", f"ST{i}")
        o.Shape = Part.Vertex(App.Vector(*p))
        objs.append(o)
    ref = _line_edge(doc, (0, 0, 0), (0, 5, 0), name="STd")  # +Y direction
    sp = make_spline(doc)
    sp.Points = [(o, "") for o in objs]
    sp.TangentDirections = [(ref, "")]
    sp.TangentRows = [1]
    sp.Tensions = [1.0]
    assert_recomputes(doc)
    edge = sp.Shape.Edges[0]
    t = edge.tangentAt(edge.FirstParameter)
    assert abs(t.x) < 1e-6 and abs(abs(t.y) - 1.0) < 1e-6  # starts along Y


def test_spline_on_support(doc):
    from gensurf.features import make_spline
    support = _support_face(doc)  # z=0 plane
    objs = []
    for i, p in enumerate([(2, 2, 5), (10, 8, -3), (18, 4, 7)]):
        o = doc.addObject("Part::Feature", f"SS{i}")
        o.Shape = Part.Vertex(App.Vector(*p))
        objs.append(o)
    sp = make_spline(doc)
    sp.Points = [(o, "") for o in objs]
    sp.Support = (support, ["Face1"])
    assert_recomputes(doc)
    assert abs(sp.Shape.BoundBox.ZMin) < 1e-9
    assert abs(sp.Shape.BoundBox.ZMax) < 1e-9


# -- Helix ----------------------------------------------------------------


def test_helix_pitch_revolution(doc):
    from gensurf.features import make_helix
    ax = _line_edge(doc, (0, 0, 0), (0, 0, 1), name="HAx")
    p = doc.addObject("Part::Feature", "HP")
    p.Shape = Part.Vertex(App.Vector(5, 0, 0))
    hx = make_helix(doc)
    hx.StartPoint = (p, ["Vertex1"])
    hx.Axis = (ax, "")
    hx.Pitch = "4 mm"
    hx.Revolutions = 3.0
    assert_recomputes(doc)
    bb = hx.Shape.BoundBox
    assert math.isclose(bb.ZMax - bb.ZMin, 12.0, rel_tol=1e-6)
    # starts at the picked point
    assert (hx.Shape.Vertexes[0].Point
            - App.Vector(5, 0, 0)).Length < 1e-7
    # stays on the r=5 cylinder
    for q in hx.Shape.Edges[0].discretize(20):
        assert abs(math.hypot(q.x, q.y) - 5.0) < 1e-4


def test_helix_off_axis_and_reverse(doc):
    from gensurf.features import make_helix
    ax = _line_edge(doc, (10, 10, 0), (10, 10, 8), name="HBx")
    p = doc.addObject("Part::Feature", "HQ")
    p.Shape = Part.Vertex(App.Vector(13, 10, 2))
    hx = make_helix(doc)
    hx.StartPoint = (p, ["Vertex1"])
    hx.Axis = (ax, "")
    hx.HelixType = "Height and Revolution"
    hx.Height = "6 mm"
    hx.Revolutions = 2.0
    assert_recomputes(doc)
    assert (hx.Shape.Vertexes[0].Point
            - App.Vector(13, 10, 2)).Length < 1e-7
    assert math.isclose(hx.Shape.BoundBox.ZMax, 8.0, rel_tol=1e-6)
    for q in hx.Shape.Edges[0].discretize(16):
        assert abs(math.hypot(q.x - 10, q.y - 10) - 3.0) < 1e-4

    hx.ReverseDirection = True
    assert_recomputes(doc)
    assert math.isclose(hx.Shape.BoundBox.ZMin, -4.0, rel_tol=1e-6)


def test_helix_taper(doc):
    from gensurf.features import make_helix
    ax = _line_edge(doc, (0, 0, 0), (0, 0, 1), name="HTx")
    p = doc.addObject("Part::Feature", "HT")
    p.Shape = Part.Vertex(App.Vector(10, 0, 0))
    hx = make_helix(doc)
    hx.StartPoint = (p, ["Vertex1"])
    hx.Axis = (ax, "")
    hx.Pitch = "5 mm"
    hx.Revolutions = 2.0
    hx.TaperAngle = "20 deg"
    hx.Way = "Outward"
    assert_recomputes(doc)
    radii = sorted(math.hypot(v.Point.x, v.Point.y)
                   for v in hx.Shape.Vertexes)
    expect_r = 10.0 + 10.0 * math.tan(math.radians(20))
    assert radii[0] == pytest.approx(10.0)   # start radius
    assert radii[-1] == pytest.approx(expect_r)  # grown end radius

    hx.Way = "Inward"
    assert_recomputes(doc)
    radii = sorted(math.hypot(v.Point.x, v.Point.y)
                   for v in hx.Shape.Vertexes)
    expect_r = 10.0 - 10.0 * math.tan(math.radians(20))
    assert radii[0] == pytest.approx(expect_r)  # shrunk end radius
    assert radii[-1] == pytest.approx(10.0)

    hx.TaperAngle = "50 deg"  # shrinks through zero before 10 mm height
    with pytest.raises(GSFeatureError):
        hx.Proxy.execute(hx)


# -- ShapeFillet ----------------------------------------------------------


def _l_shell(doc):
    """Horizontal face (z=0) + vertical face (y=0) sharing the edge
    x in [0,10] — as two separate document objects."""
    fa = doc.addObject("Part::Feature", "SFh")
    fa.Shape = Part.makeLine(
        App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
        App.Vector(0, 8, 0))
    fb = doc.addObject("Part::Feature", "SFv")
    fb.Shape = Part.makeLine(
        App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
        App.Vector(0, 0, 6))
    return fa, fb


def test_shape_fillet_shared_boundary(doc):
    from gensurf.features import make_shape_fillet
    fa, fb = _l_shell(doc)
    sf = make_shape_fillet(doc)
    sf.Support1 = (fa, ["Face1"])
    sf.Support2 = (fb, ["Face1"])
    sf.Radius = "2 mm"
    assert_recomputes(doc)
    assert len(sf.Shape.Faces) == 3  # two supports + the fillet ribbon
    # the fillet ribbon is cylindrical with the right radius
    cyl = [f for f in sf.Shape.Faces
           if isinstance(f.Surface, Part.Cylinder)]
    assert len(cyl) == 1
    assert math.isclose(cyl[0].Surface.Radius, 2.0, rel_tol=1e-9)


def test_shape_fillet_crossing_faces(doc):
    from gensurf.features import make_shape_fillet
    fa = doc.addObject("Part::Feature", "SXh")   # horizontal at z=0
    fa.Shape = Part.makeLine(
        App.Vector(0, -6, 0), App.Vector(10, -6, 0)).extrude(
        App.Vector(0, 12, 0))
    fb = doc.addObject("Part::Feature", "SXv")   # vertical at y=0
    fb.Shape = Part.makeLine(
        App.Vector(0, 0, -5), App.Vector(10, 0, -5)).extrude(
        App.Vector(0, 0, 10))
    sf = make_shape_fillet(doc)
    sf.Support1 = (fa, ["Face1"])
    sf.Support2 = (fb, ["Face1"])
    sf.Radius = "2 mm"
    assert_recomputes(doc)
    cyl = [f for f in sf.Shape.Faces
           if isinstance(f.Surface, Part.Cylinder)]
    assert len(cyl) == 1
    # supports were trimmed: kept sides only
    assert len(sf.Shape.Faces) == 3


# -- EdgeFillet / Chamfer -------------------------------------------------


def _shell_obj(doc):
    """One object holding the sewn L-shell (two faces, one sharp edge)."""
    comp = Part.makeCompound([
        Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
            App.Vector(0, 8, 0)).Faces[0],
        Part.makeLine(App.Vector(0, 0, 0), App.Vector(10, 0, 0)).extrude(
            App.Vector(0, 0, 6)).Faces[0]])
    comp.sewShape()
    obj = doc.addObject("Part::Feature", "LShell")
    obj.Shape = comp.Shells[0]
    return obj


def _sharp_edge_name(obj):
    """SubName of the edge shared by both faces."""
    shape = obj.Shape
    for i, e in enumerate(shape.Edges):
        count = sum(1 for f in shape.Faces
                    if any(e.isSame(e2) for e2 in f.Edges))
        if count == 2:
            return f"Edge{i + 1}"
    raise AssertionError("no shared edge found")


def test_edge_fillet(doc):
    from gensurf.features import make_edge_fillet
    obj = _shell_obj(doc)
    ef = make_edge_fillet(doc)
    ef.Edges = [(obj, _sharp_edge_name(obj))]
    ef.Radius = "2 mm"
    assert_recomputes(doc)
    cyl = [f for f in ef.Shape.Faces
           if isinstance(f.Surface, Part.Cylinder)]
    assert len(cyl) == 1
    assert math.isclose(cyl[0].Surface.Radius, 2.0, rel_tol=1e-9)


def test_chamfer_modes(doc):
    from gensurf.features import make_chamfer
    obj = _shell_obj(doc)
    ch = make_chamfer(doc)
    ch.Edges = [(obj, _sharp_edge_name(obj))]
    ch.Length1 = "2 mm"
    ch.Angle = "45 deg"
    def bevel_face(shape):
        # the bevel is the plane tilted against both original faces
        return next(f for f in shape.Faces
                    if isinstance(f.Surface, Part.Plane)
                    and abs(f.Surface.Axis.y) > 0.1
                    and abs(f.Surface.Axis.z) > 0.1)

    assert_recomputes(doc)  # Length1/Angle, 45 deg -> symmetric bevel
    assert len(ch.Shape.Faces) == 3
    # bevel width = 2*sqrt(2) for a symmetric 2 mm chamfer
    assert math.isclose(bevel_face(ch.Shape).Area,
                        10 * 2 * math.sqrt(2), rel_tol=1e-6)

    ch.Mode = "Length1/Length2"
    ch.Length2 = "4 mm"
    assert_recomputes(doc)
    assert math.isclose(bevel_face(ch.Shape).Area,
                        10 * math.sqrt(4 + 16), rel_tol=1e-6)


# -- SpineCurve -----------------------------------------------------------


def test_spine_through_planar_sections(doc):
    from gensurf.features import make_spine_curve
    # three parallel vertical section planes stacked along x
    faces = []
    for i, x in enumerate((0.0, 10.0, 20.0)):
        f = doc.addObject("Part::Feature", f"Sec{i}")
        f.Shape = Part.makeLine(
            App.Vector(x, -5, -5), App.Vector(x, 5, -5)).extrude(
            App.Vector(0, 0, 10))
        faces.append(f)
    sp = make_spine_curve(doc)
    sp.Sections = [(f, "Face1") for f in faces]
    assert_recomputes(doc)
    # spine crosses each plane orthogonally: tangent ~ +X everywhere here
    edge = sp.Shape.Edges[0]
    for t in (edge.FirstParameter,
              (edge.FirstParameter + edge.LastParameter) / 2,
              edge.LastParameter):
        tan = edge.tangentAt(t)
        assert abs(abs(tan.x) - 1.0) < 1e-6
    assert math.isclose(sp.Shape.Length, 20.0, rel_tol=1e-6)


def test_spine_with_start_point_and_curved_travel(doc):
    from gensurf.features import make_spine_curve
    s0 = doc.addObject("Part::Feature", "SpS0")  # arc in x=0 plane
    s0.Shape = Part.ArcOfCircle(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(1, 0, 0), 5),
        0, math.pi / 2).toShape()
    s1 = doc.addObject("Part::Feature", "SpS1")                # plane x=z diag
    s1.Shape = Part.makeLine(
        App.Vector(10, -5, 0), App.Vector(10, 5, 0)).extrude(
        App.Vector(1, 0, 1))
    st = doc.addObject("Part::Feature", "SpStart")
    st.Shape = Part.Vertex(App.Vector(0, 2, 0))
    sp = make_spine_curve(doc)
    sp.Sections = [(s0, ""), (s1, "Face1")]
    sp.StartPoint = (st, ["Vertex1"])
    assert_recomputes(doc)
    edge = sp.Shape.Edges[0]
    start = edge.valueAt(edge.FirstParameter)
    ends = (start, edge.valueAt(edge.LastParameter))
    assert any((p - App.Vector(0, 2, 0)).Length < 1e-7 for p in ends)
    # tangent at the first section is the section plane's normal (+X here)
    t0 = edge.tangentAt(edge.FirstParameter)
    t1 = edge.tangentAt(edge.LastParameter)
    tan_at_start = t0 if (start - App.Vector(0, 2, 0)).Length < 1e-7 else t1
    assert abs(abs(tan_at_start.x) - 1.0) < 1e-6


# -- Symmetry -------------------------------------------------------------


def test_symmetry_about_plane(doc):
    from gensurf.features import make_symmetry
    support = _support_face(doc)          # 20x20 at z=0, x,y in [0,20]
    mirror = doc.addObject("Part::Feature", "MirP")   # plane x=25
    mirror.Shape = Part.makeLine(
        App.Vector(25, -5, -5), App.Vector(25, 25, -5)).extrude(
        App.Vector(0, 0, 10))
    sy = make_symmetry(doc)
    sy.Source = (support, ["Face1"])
    sy.Reference = (mirror, ["Face1"])
    assert_recomputes(doc)
    bb = sy.Shape.BoundBox
    assert math.isclose(bb.XMin, 30.0, abs_tol=1e-9)
    assert math.isclose(bb.XMax, 50.0, abs_tol=1e-9)
    assert math.isclose(sy.Shape.Faces[0].Area, 400.0, rel_tol=1e-9)


def test_symmetry_about_line_and_point(doc):
    from gensurf.features import make_symmetry
    src = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="SyS")
    axis = _line_edge(doc, (0, 5, 0), (10, 5, 0), name="SyA")  # y=5 line
    sy = make_symmetry(doc)
    sy.Source = (src, "")
    sy.Reference = (axis, "")
    assert_recomputes(doc)
    assert all(abs(v.Y - 10.0) < 1e-9 for v in sy.Shape.Vertexes)

    pt = doc.addObject("Part::Feature", "SyP")
    pt.Shape = Part.Vertex(App.Vector(5, 5, 5))
    sy.Reference = (pt, ["Vertex1"])
    assert_recomputes(doc)
    xs = sorted(v.Point.x for v in sy.Shape.Vertexes)
    assert xs == pytest.approx([0.0, 10.0])
    assert all(abs(v.Y - 10.0) < 1e-9 and abs(v.Z - 10.0) < 1e-9
               for v in sy.Shape.Vertexes)


# -- Sphere ---------------------------------------------------------------


def test_sphere_whole(doc):
    from gensurf.features import make_sphere
    c = doc.addObject("Part::Feature", "SphC")
    c.Shape = Part.Vertex(App.Vector(3, 4, 5))
    sp = make_sphere(doc)
    sp.Center = (c, ["Vertex1"])
    sp.Radius = "10 mm"
    sp.Limitation = "Whole sphere"
    assert_recomputes(doc)
    assert math.isclose(sp.Shape.Area, 4 * math.pi * 100, rel_tol=1e-6)
    bb = sp.Shape.BoundBox
    assert (App.Vector(bb.Center) - App.Vector(3, 4, 5)).Length < 1e-6


def test_sphere_angle_limits(doc):
    from gensurf.features import make_sphere
    c = doc.addObject("Part::Feature", "SphC2")
    c.Shape = Part.Vertex(App.Vector(0, 0, 0))
    sp = make_sphere(doc)
    sp.Center = (c, ["Vertex1"])
    sp.Radius = "20 mm"     # dialog defaults: -45..45, 0..180
    assert_recomputes(doc)
    # area = r^2 * meridian_span * (sin p1 - sin p0)
    expect = 400 * math.pi * (math.sin(math.pi / 4)
                              - math.sin(-math.pi / 4))
    assert math.isclose(sp.Shape.Area, expect, rel_tol=1e-6)
    # patch spans z in [-r sin45, +r sin45]
    bb = sp.Shape.BoundBox
    assert math.isclose(bb.ZMax, 20 * math.sin(math.pi / 4), rel_tol=1e-6)
    assert math.isclose(bb.ZMin, -20 * math.sin(math.pi / 4), rel_tol=1e-6)
    # meridian 0..180 with meridian-zero at +X: the patch is y >= 0
    assert bb.YMin > -1e-6


def test_sphere_axis_reference(doc):
    from gensurf.features import make_sphere
    c = doc.addObject("Part::Feature", "SphC3")
    c.Shape = Part.Vertex(App.Vector(0, 0, 0))
    ax = _line_edge(doc, (0, 0, 0), (1, 0, 0), name="SphAx")  # +X axis
    sp = make_sphere(doc)
    sp.Center = (c, ["Vertex1"])
    sp.Axis = (ax, "")
    sp.Radius = "20 mm"
    sp.ParallelStart = "-90 deg"
    sp.ParallelEnd = "0 deg"
    sp.MeridianStart = "0 deg"
    sp.MeridianEnd = "360 deg"
    assert_recomputes(doc)
    # southern hemisphere of an X-axis sphere: x in [-20, 0]
    bb = sp.Shape.BoundBox
    assert math.isclose(bb.XMin, -20.0, rel_tol=1e-6)
    assert abs(bb.XMax) < 1e-6
    assert math.isclose(sp.Shape.Area, 2 * math.pi * 400, rel_tol=1e-6)


# -- Sweep Explicit -------------------------------------------------------


def test_sweep_explicit_pulling_direction(doc):
    from gensurf.features import make_sweep_explicit
    guide = doc.addObject("Part::Feature", "SwG")
    guide.Shape = Part.ArcOfCircle(
        Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 20),
        0, math.pi / 2).toShape()
    prof = _line_edge(doc, (20, 0, 0), (20, 0, 8), name="SwP")
    sw = make_sweep_explicit(doc)
    sw.Subtype = "With pulling direction"
    sw.Profile = (prof, "")
    sw.Guide1 = (guide, "")
    assert_recomputes(doc)  # default direction +Z
    assert math.isclose(sw.Shape.Area, math.pi / 2 * 20 * 8,
                        rel_tol=1e-3)


def test_sweep_explicit_default_frame(doc):
    from gensurf.features import make_sweep_explicit
    guide = _line_edge(doc, (0, 0, 0), (30, 0, 0), name="SwG2")
    prof = doc.addObject("Part::Feature", "SwP2")
    prof.Shape = Part.Wire([
        Part.makeLine(App.Vector(0, 0, 0), App.Vector(0, 8, 0)),
        Part.makeLine(App.Vector(0, 8, 0), App.Vector(0, 8, 5))])
    sw = make_sweep_explicit(doc)
    sw.Profile = (prof, "")
    sw.Guide1 = (guide, "")
    assert_recomputes(doc)  # With reference surface, no surface = mean
    assert math.isclose(sw.Shape.Area, 30 * 13, rel_tol=1e-6)


def test_sweep_explicit_two_guides(doc):
    from gensurf.features import make_sweep_explicit
    g1 = _line_edge(doc, (0, 0, 0), (30, 0, 0), name="SwGa")
    g2 = _line_edge(doc, (0, 10, 2), (30, 14, 2), name="SwGb")
    prof = doc.addObject("Part::Feature", "SwP3")
    prof.Shape = Part.Wire([Part.makeLine(
        App.Vector(0, 0, 0), App.Vector(0, 10, 2))])
    sw = make_sweep_explicit(doc)
    sw.Subtype = "With two guide curves"
    sw.Profile = (prof, "")
    sw.Guide1 = (g1, "")
    sw.Guide2 = (g2, "")
    assert_recomputes(doc)
    # the far edge of the sweep tracks guide 2 (y grows to ~14)
    assert sw.Shape.BoundBox.YMax > 13.0


# -- Sweep Line -----------------------------------------------------------


def test_sweep_line_two_limits_and_middle(doc):
    from gensurf.features import make_sweep_line
    g1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="SlG1")
    g2 = _line_edge(doc, (0, 0, 5), (10, 0, 5), name="SlG2")
    sw = make_sweep_line(doc)
    sw.Guide1 = (g1, "")
    sw.Guide2 = (g2, "")
    sw.Length1 = "0 mm"
    sw.Length2 = "0 mm"
    assert_recomputes(doc)
    assert math.isclose(sw.Shape.Area, 50.0, rel_tol=1e-6)

    sw.Length1 = "2 mm"   # extends beyond guide 1 (outward)
    sw.Length2 = "3 mm"   # beyond guide 2
    assert_recomputes(doc)
    assert math.isclose(sw.Shape.Area, 100.0, rel_tol=1e-6)
    assert math.isclose(sw.Shape.BoundBox.ZMin, -2.0, rel_tol=1e-6)
    assert math.isclose(sw.Shape.BoundBox.ZMax, 8.0, rel_tol=1e-6)

    sw.Subtype = "Limit and middle"
    assert_recomputes(doc)  # from g1 through middle g2 to 2*g2-g1
    assert math.isclose(sw.Shape.Area, 100.0, rel_tol=1e-6)
    assert math.isclose(sw.Shape.BoundBox.ZMax, 10.0, rel_tol=1e-6)


def test_sweep_line_reference_surface_angle(doc):
    from gensurf.features import make_sweep_line
    support = _support_face(doc)  # z=0 plane
    g1 = _line_edge(doc, (0, 5, 0), (10, 5, 0), name="SlG3")
    sw = make_sweep_line(doc)
    sw.Subtype = "With reference surface"
    sw.Guide1 = (g1, "")
    sw.ReferenceSurface = (support, ["Face1"])
    sw.Length1 = "6 mm"
    sw.Angle = "90 deg"   # rule leaves the surface perpendicular
    assert_recomputes(doc)
    assert math.isclose(sw.Shape.Area, 60.0, rel_tol=1e-6)
    assert math.isclose(abs(sw.Shape.BoundBox.ZMax
                            - sw.Shape.BoundBox.ZMin), 6.0, rel_tol=1e-6)

    sw.Angle = "0 deg"    # rule lies in the surface plane
    assert_recomputes(doc)
    assert abs(sw.Shape.BoundBox.ZMax) < 1e-6
    assert math.isclose(sw.Shape.Area, 60.0, rel_tol=1e-6)


def test_sweep_line_draft_direction(doc):
    from gensurf.features import make_sweep_line
    g1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="SlG4")
    sw = make_sweep_line(doc)
    sw.Subtype = "With draft direction"
    sw.Guide1 = (g1, "")
    sw.Length1 = "6 mm"   # default draft direction +Z, angle 0
    assert_recomputes(doc)
    assert math.isclose(sw.Shape.Area, 60.0, rel_tol=1e-6)
    assert math.isclose(sw.Shape.BoundBox.ZMax, 6.0, rel_tol=1e-6)


# -- Sweep Circle ---------------------------------------------------------


def test_sweep_circle_center_radius(doc):
    from gensurf.features import make_sweep_circle
    center = _line_edge(doc, (0, 0, 0), (30, 0, 0), name="ScC")
    sw = make_sweep_circle(doc)
    sw.Subtype = "Center and radius"
    sw.Guide1 = (center, "")
    sw.Radius = "5 mm"
    assert_recomputes(doc)
    assert math.isclose(sw.Shape.Area, 2 * math.pi * 5 * 30,
                        rel_tol=1e-3)


def test_sweep_circle_three_guides(doc):
    from gensurf.features import make_sweep_circle
    # circle in the yz-plane through (y,z) = (0,0), (5,5), (10,0)
    g1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="ScG1")
    g2 = _line_edge(doc, (0, 5, 5), (10, 5, 5), name="ScG2")
    g3 = _line_edge(doc, (0, 10, 0), (10, 10, 0), name="ScG3")
    sw = make_sweep_circle(doc)
    sw.Guide1 = (g1, "")
    sw.Guide2 = (g2, "")
    sw.Guide3 = (g3, "")
    assert_recomputes(doc)
    # arc radius 5 centered (y=5, z=0): half-circumference x length
    assert math.isclose(sw.Shape.Area, math.pi * 5 * 10, rel_tol=1e-3)
    assert math.isclose(sw.Shape.BoundBox.ZMax, 5.0, rel_tol=1e-3)


def test_sweep_circle_two_guides_radius(doc):
    from gensurf.features import make_sweep_circle
    g1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="ScH1")
    g2 = _line_edge(doc, (0, 6, 0), (10, 6, 0), name="ScH2")
    sw = make_sweep_circle(doc)
    sw.Subtype = "Two guides and radius"
    sw.Guide1 = (g1, "")
    sw.Guide2 = (g2, "")
    sw.Radius = "5 mm"
    assert_recomputes(doc)
    arc_len = 2 * math.asin(3.0 / 5.0) * 5.0  # minor arc, chord 6
    assert math.isclose(sw.Shape.Area, arc_len * 10, rel_tol=1e-3)
    sag = 5.0 - 4.0
    zext = max(abs(sw.Shape.BoundBox.ZMin), abs(sw.Shape.BoundBox.ZMax))
    assert math.isclose(zext, sag, rel_tol=1e-3)


def test_sweep_circle_center_two_angles(doc):
    from gensurf.features import make_sweep_circle
    center = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="ScK1")
    ref = _line_edge(doc, (0, 4, 0), (10, 4, 0), name="ScK2")
    sw = make_sweep_circle(doc)
    sw.Subtype = "Center and two angles"
    sw.Guide1 = (center, "")
    sw.Guide2 = (ref, "")
    sw.Angle1 = "0 deg"
    sw.Angle2 = "90 deg"
    assert_recomputes(doc)
    assert math.isclose(sw.Shape.Area, (math.pi / 2 * 4) * 10,
                        rel_tol=1e-3)


# -- Sweep Conic ----------------------------------------------------------


def test_sweep_conic_two_guides(doc):
    from gensurf.features import make_sweep_conic
    # guides at (y,z)=(0,0) and (10,0); vertical tangency planes at both
    g1 = _line_edge(doc, (0, 0, 0), (10, 0, 0), name="CoG1")
    g2 = _line_edge(doc, (0, 10, 0), (10, 10, 0), name="CoG2")
    t1 = doc.addObject("Part::Feature", "CoT1")   # plane y=0
    t1.Shape = Part.makeLine(
        App.Vector(0, 0, -5), App.Vector(10, 0, -5)).extrude(
        App.Vector(0, 0, 10))
    t2 = doc.addObject("Part::Feature", "CoT2")   # plane y=10
    t2.Shape = Part.makeLine(
        App.Vector(0, 10, -5), App.Vector(10, 10, -5)).extrude(
        App.Vector(0, 0, 10))
    sw = make_sweep_conic(doc)
    sw.Guide1 = (g1, "")
    sw.Guide2 = (g2, "")
    sw.Tangency1 = (t1, ["Face1"])
    sw.Tangency2 = (t2, ["Face1"])
    assert_recomputes(doc)
    # vertical (parallel) end tangents, parameter 0.5: the section is
    # the exact semicircle of radius 5
    bb = sw.Shape.BoundBox
    zext = max(abs(bb.ZMin), abs(bb.ZMax))
    assert math.isclose(zext, 5.0, rel_tol=1e-6)
    assert math.isclose(sw.Shape.Area, math.pi * 5 * 10, rel_tol=1e-3)
    # ends ride the guides
    assert sw.Shape.distToShape(g1.Shape)[0] < 1e-6
    assert sw.Shape.distToShape(g2.Shape)[0] < 1e-6


def test_sweep_conic_five_guides(doc):
    from gensurf.features import make_sweep_conic
    ys = [0.0, 2.5, 5.0, 7.5, 10.0]
    zs = [0.0, 1.8, 2.4, 1.8, 0.0]
    guides = []
    for i, (y, z) in enumerate(zip(ys, zs)):
        guides.append(_line_edge(doc, (0, y, z), (10, y, z),
                                 name=f"CoF{i}"))
    sw = make_sweep_conic(doc)
    sw.Subtype = "Five guide curves"
    sw.Guide1 = (guides[0], "")
    sw.Guide2 = (guides[1], "")
    sw.Guide3 = (guides[2], "")
    sw.Guide4 = (guides[3], "")
    sw.Guide5 = (guides[4], "")
    assert_recomputes(doc)
    for g in guides:  # the section rides all five guides
        assert sw.Shape.distToShape(g.Shape)[0] < 1e-4


# -- CloseSurface ---------------------------------------------------------


def _box_face_objs(doc, count=6):
    box = Part.makeBox(10, 10, 10)
    objs = []
    for i, f in enumerate(box.Faces[:count]):
        o = doc.addObject("Part::Feature", f"BF{i}")
        o.Shape = f
        objs.append(o)
    return objs


def test_close_surface_closed_set(doc):
    from gensurf.features import make_close_surface
    objs = _box_face_objs(doc)
    cs = make_close_surface(doc)
    cs.Elements = [(o, "") for o in objs]
    assert_recomputes(doc)
    assert len(cs.Shape.Solids) == 1
    assert math.isclose(cs.Shape.Volume, 1000.0, rel_tol=1e-9)


def test_close_surface_caps_planar_hole(doc):
    from gensurf.features import make_close_surface
    objs = _box_face_objs(doc, count=5)  # one face missing
    cs = make_close_surface(doc)
    cs.Elements = [(o, "") for o in objs]
    assert_recomputes(doc)
    assert math.isclose(cs.Shape.Volume, 1000.0, rel_tol=1e-9)

    cs.CapPlanarHoles = False
    with pytest.raises(GSFeatureError):
        cs.Proxy.execute(cs)


def test_close_surface_open_nonplanar_errors(doc):
    from gensurf.features import make_close_surface
    cyl = doc.addObject("Part::Feature", "CSCyl")
    # lateral face of a cylinder cut obliquely: non-planar opening? use
    # a simple lateral face — its openings are planar circles, so use
    # a wavy extrude instead
    prof = Part.BSplineCurve()
    prof.interpolate([App.Vector(0, 0, 0), App.Vector(5, 2, 1),
                      App.Vector(10, 0, 0)])
    cyl.Shape = prof.toShape().extrude(App.Vector(0, 5, 0))
    cs = make_close_surface(doc)
    cs.Elements = [(cyl, "")]
    with pytest.raises(GSFeatureError):
        cs.Proxy.execute(cs)
