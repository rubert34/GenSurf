#!/bin/bash
# One-time installer: links the GenerativeSurfaces workbench into the
# dedicated FreeCAD.app so it appears in the workbench selector.
# Double-click me. Safe to run again anytime.

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"                # .../FreeCAD GSD
WB="$HERE/GenerativeSurfaces"
MOD="$HERE/FreeCAD Install/FreeCAD.app/Contents/Resources/Mod"

echo "Workbench source : $WB"
echo "FreeCAD Mod dir  : $MOD"

if [ ! -d "$WB" ]; then
  echo "ERROR: workbench folder not found next to this script."; exit 1
fi
if [ ! -d "$MOD" ]; then
  echo "ERROR: FreeCAD.app not found at the expected location."; exit 1
fi

ln -sfn "$WB" "$MOD/GenerativeSurfaces"
echo
echo "Done! 'Generative Surfaces' is linked into FreeCAD."
echo "Start (or restart) the FreeCAD in 'FreeCAD Install' and pick"
echo "'Generative Surfaces' in the workbench dropdown."
