"""gensurf — core package of the Generative Surfaces workbench.

Everything under this package except `gensurf.ui` must be importable
headless (freecadcmd / pytest), with no FreeCADGui dependency.
"""

import os

__version__ = "0.24.0"

# Root of the addon (the folder containing package.xml).
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
