"""Pytest harness: import FreeCAD headless and expose fresh documents.

Runs with plain pytest — FreeCAD's lib directory is put on sys.path from
$FREECAD_LIB (default /opt/freecad/lib). The addon root is added so the
gensurf package imports exactly as it does inside FreeCAD.
"""

import os
import sys

import pytest

FREECAD_LIB = os.environ.get("FREECAD_LIB", "/opt/freecad/lib")
ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for p in (FREECAD_LIB, ADDON_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import FreeCAD as App  # noqa: E402


@pytest.fixture()
def doc():
    d = App.newDocument("test")
    name = d.Name
    yield d
    if name in App.listDocuments():
        App.closeDocument(name)


def assert_recomputes(document):
    failed = document.recompute()
    errors = [o.Name for o in document.Objects
              if o.State and "Invalid" in str(o.State)]
    assert not errors, f"recompute failed for: {errors} (rc={failed})"
