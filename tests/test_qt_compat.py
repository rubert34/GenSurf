"""Task-panel buttons with PySide6, where Qt enums no longer convert with
int(): every GenSurf task panel failed to open on FreeCAD 1.1 because of
that."""

import os
import re

import pytest

QtWidgets = pytest.importorskip("PySide.QtWidgets")

from gensurf.ui.qt_compat import enum_value, is_apply, standard_buttons  # noqa: E402,E501

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_standard_buttons_is_a_plain_int():
    box = QtWidgets.QDialogButtonBox
    value = standard_buttons()
    assert type(value) is int
    for button in (box.Ok, box.Apply, box.Cancel):
        assert value & enum_value(button)


def test_is_apply_accepts_ints_and_enums():
    box = QtWidgets.QDialogButtonBox
    assert is_apply(box.Apply) and is_apply(enum_value(box.Apply))
    assert not is_apply(enum_value(box.Ok))


def test_ui_code_never_casts_qt_enums_with_int():
    ui = os.path.join(ROOT, "gensurf", "ui")
    pattern = re.compile(r"int\(\s*Qt\w*\.")
    offenders = []
    for name in os.listdir(ui):
        if name.endswith(".py"):
            with open(os.path.join(ui, name), encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    if pattern.search(line):
                        offenders.append(f"{name}:{n}")
    assert not offenders, offenders
