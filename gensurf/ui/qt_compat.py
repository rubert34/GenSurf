"""Qt helpers that work with both PySide2 (FreeCAD 0.x) and PySide6
(FreeCAD 1.x). Imports PySide only, so the headless tests can check it."""

from PySide import QtWidgets


def enum_value(member):
    """Integer value of a Qt enum or flag member. PySide6 enums no longer
    convert with int(); PySide2 ones have no .value."""
    value = getattr(member, "value", member)
    return int(value)


def standard_buttons():
    """OK / Apply / Cancel, as the integer FreeCAD's task dialog expects."""
    box = QtWidgets.QDialogButtonBox
    return (enum_value(box.Ok) | enum_value(box.Apply)
            | enum_value(box.Cancel))


def is_apply(button):
    """True when the task dialog's clicked() reports the Apply button."""
    return enum_value(button) == \
        enum_value(QtWidgets.QDialogButtonBox.Apply)
