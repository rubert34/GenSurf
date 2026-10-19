"""Feature package — importing this module registers every feature.

Registration lines (one per feature file):
"""

from .registry import FEATURES, register, factory  # noqa: F401
from .base import (GSFeature, GenSurfError, GSFeatureError,  # noqa: F401
                   ERROR, WARNING, INFO, make_feature)

from . import datum_plane  # noqa: F401
from . import projected_curve  # noqa: F401
from . import extruded_surface  # noqa: F401
from . import offset_surface  # noqa: F401
from . import blend_surface  # noqa: F401
from . import revolved_surface  # noqa: F401
from . import split  # noqa: F401
from . import trim  # noqa: F401
from . import translate  # noqa: F401
from . import rotate  # noqa: F401
from . import scale  # noqa: F401
from . import extend  # noqa: F401
from . import loft  # noqa: F401
from . import fill  # noqa: F401
from . import bridge_curve  # noqa: F401
from . import boundary_curves  # noqa: F401
from . import extract  # noqa: F401
from . import join  # noqa: F401
from . import point  # noqa: F401
from . import line  # noqa: F401
from . import intersection  # noqa: F401
from . import offset_curve_on_surface  # noqa: F401
from . import offset_curve_3d  # noqa: F401
from . import circle  # noqa: F401
from . import curve_fillet  # noqa: F401
from . import spline  # noqa: F401
from . import helix  # noqa: F401
from . import surface_fillet  # noqa: F401
from . import edge_fillet  # noqa: F401
from . import chamfer  # noqa: F401
from . import spine_curve  # noqa: F401
from . import symmetry  # noqa: F401
from . import sphere  # noqa: F401
from . import sweep_explicit  # noqa: F401
from . import sweep_line  # noqa: F401
from . import sweep_circle  # noqa: F401
from . import sweep_conic  # noqa: F401
from . import make_solid  # noqa: F401
from . import heal  # noqa: F401
from . import curvature_comb  # noqa: F401

from .datum_plane import make_datum_plane  # noqa: F401
from .projected_curve import make_projected_curve  # noqa: F401
from .extruded_surface import make_extruded_surface  # noqa: F401
from .offset_surface import make_offset_surface  # noqa: F401
from .blend_surface import make_blend_surface  # noqa: F401
from .revolved_surface import make_revolved_surface  # noqa: F401
from .split import make_split  # noqa: F401
from .trim import make_trim  # noqa: F401
from .translate import make_translate  # noqa: F401
from .rotate import make_rotate  # noqa: F401
from .scale import make_scale  # noqa: F401
from .extend import make_extend  # noqa: F401
from .loft import make_loft  # noqa: F401
from .fill import make_fill  # noqa: F401
from .bridge_curve import make_bridge_curve  # noqa: F401
from .boundary_curves import make_boundary_curves  # noqa: F401
from .extract import make_extract  # noqa: F401
from .join import make_join  # noqa: F401
from .point import make_point  # noqa: F401
from .line import make_line  # noqa: F401
from .intersection import make_intersection  # noqa: F401
from .offset_curve_on_surface import make_offset_curve_on_surface  # noqa: F401,E501
from .offset_curve_3d import make_offset_curve_3d  # noqa: F401
from .circle import make_circle  # noqa: F401
from .curve_fillet import make_curve_fillet  # noqa: F401
from .spline import make_spline  # noqa: F401
from .helix import make_helix  # noqa: F401
from .surface_fillet import make_surface_fillet  # noqa: F401
from .edge_fillet import make_edge_fillet  # noqa: F401
from .chamfer import make_chamfer  # noqa: F401
from .spine_curve import make_spine_curve  # noqa: F401
from .symmetry import make_symmetry  # noqa: F401
from .sphere import make_sphere  # noqa: F401
from .sweep_explicit import make_sweep_explicit  # noqa: F401
from .sweep_line import make_sweep_line  # noqa: F401
from .sweep_circle import make_sweep_circle  # noqa: F401
from .sweep_conic import make_sweep_conic  # noqa: F401
from .make_solid import make_make_solid  # noqa: F401
from .heal import make_heal  # noqa: F401
from .curvature_comb import make_curvature_comb  # noqa: F401

from gensurf import migrations as _migrations  # noqa: E402

# old documents name their proxies by former module paths
_migrations.install_legacy_modules("gensurf.features.")
