# Generative Surfaces workbench — headless initialization.
# Runs in both GUI and console (freecadcmd) sessions. Keep GUI-free.
#
# Importing gensurf.features ensures all FeaturePython proxy classes are
# importable when documents containing them are loaded headless.

import gensurf.features  # noqa: F401  (registers feature classes)
