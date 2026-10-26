from .construction_set import (  # noqa: F401
    ConstructionSet,
    make_construction_set,
    is_set,
    get_active_set,
    set_active_set,
    set_inactive,
    has_gensurf_features,
    insert_into_active_set,
    TYPE_ID as SET_TYPE_ID,
)

from gensurf import migrations as _migrations  # noqa: E402

# old documents name their set proxies by former module paths
_migrations.install_legacy_modules("gensurf.containers.")
