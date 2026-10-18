"""Static checks of the GUI command layout (no GUI needed).

gensurf/ui/commands.py imports FreeCADGui, so it is read as source here:
every operator has exactly one command, every command has its icon and
appears once in the toolbars, and the toolbars are the task groups.
"""

import ast
import os

from gensurf.features import FEATURES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS = os.path.join(ROOT, "resources", "icons")


def _layout():
    path = os.path.join(ROOT, "gensurf", "ui", "commands.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                isinstance(node.targets[0], ast.Name):
            values[node.targets[0].id] = node.value
    features = ast.literal_eval(values["_FEATURES"])
    toolbars = ast.literal_eval(values["TOOLBARS"])
    groups = {}
    for key, call in zip(values["_GROUPS"].keys, values["_GROUPS"].values):
        groups[ast.literal_eval(key)] = ast.literal_eval(call.args[2])
    return features, toolbars, groups


def test_every_operator_has_one_command_with_an_icon():
    features, _toolbars, _groups = _layout()
    type_ids = [type_id for _n, type_id, _t, _tip in features]
    assert sorted(type_ids) == sorted(FEATURES), \
        set(type_ids) ^ set(FEATURES)
    for name, *_rest in features:
        assert os.path.isfile(os.path.join(ICONS, f"{name}.svg")), name
    for name in ("GenSurf_ConstructionSet", "GenSurf_SetActive",
                 "GenSurf_DevReload", "GenSurf_Workbench"):
        assert os.path.isfile(os.path.join(ICONS, f"{name}.svg")), name


def test_toolbars_are_task_groups_and_place_each_command_once():
    features, toolbars, groups = _layout()
    assert [title for title, _items in toolbars] == [
        "Sets", "Curves", "Surfaces", "Edit", "Inspect",
        "GenSurf development"]
    placed = []
    for _title, items in toolbars:
        for item in items:
            placed.extend(groups.get(item, [item]))
    expected = [name for name, *_r in features] + [
        "GenSurf_ConstructionSet", "GenSurf_SetActive", "GenSurf_DevReload"]
    assert sorted(placed) == sorted(expected)
    assert all(len(cmds) >= 2 for cmds in groups.values())


def test_no_unused_icons():
    features, _toolbars, _groups = _layout()
    used = {f"{name}.svg" for name, *_r in features} | {
        "GenSurf_ConstructionSet.svg", "GenSurf_SetActive.svg",
        "GenSurf_DevReload.svg", "GenSurf_Workbench.svg"}
    assert set(os.listdir(ICONS)) - used == set()
