#!/bin/bash
# Developer helper (macOS): links this GenSurf checkout into FreeCAD's
# user Mod folder so the workbench appears in the workbench selector.
#   Usage: "tools/Install into FreeCAD.command" [/path/to/Mod]
#   Default: FreeCAD 1.1's user Mod folder. Safe to run again anytime.

set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MOD="${1:-$HOME/Library/Application Support/FreeCAD/v1-1/Mod}"

echo "Workbench source : $REPO"
echo "FreeCAD Mod dir  : $MOD"

if [ ! -f "$REPO/package.xml" ]; then
  echo "ERROR: GenSurf checkout not found at $REPO."; exit 1
fi
mkdir -p "$MOD"
ln -sfn "$REPO" "$MOD/GenSurf"
echo
echo "Done! GenSurf is linked into FreeCAD."
echo "Start (or restart) FreeCAD and pick 'GenSurf' in the workbench"
echo "selector."
