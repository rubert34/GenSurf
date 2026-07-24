"""Feature registry — one file + one registration line per feature.

Each feature module calls ``register(cls, make_fn)`` at import time. The
registry drives command generation (GUI) and gives tests a uniform factory.
"""

FEATURES = {}


def register(proxy_cls, factory):
    FEATURES[proxy_cls.TYPE_ID] = {
        "proxy": proxy_cls,
        "factory": factory,
    }
    return proxy_cls


def factory(type_id):
    return FEATURES[type_id]["factory"]
