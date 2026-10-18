#!/usr/bin/env bash
# Rebuild the headless FreeCAD dev environment in a fresh Cowork cloud sandbox.
# Takes ~1.5-2h on 2 cores; run in background and monitor build.log.
#
# Network constraints (as of 2026-07): conda-forge, GitHub *release assets*,
# Debian, snap and PPAs are blocked; git-over-https to github.com and
# Ubuntu apt work. Hence: source build against Ubuntu's OCCT 7.6.3.
set -euo pipefail

FREECAD_TAG="${FREECAD_TAG:-1.1.2}"

sudo apt-get update -qq || true
sudo apt-get install -y -qq cmake ninja-build g++ \
  libboost-dev libboost-filesystem-dev libboost-program-options-dev \
  libboost-regex-dev libboost-thread-dev \
  libocct-data-exchange-dev libocct-draw-dev libocct-foundation-dev \
  libocct-modeling-algorithms-dev libocct-modeling-data-dev \
  libocct-ocaf-dev libocct-visualization-dev \
  libxerces-c-dev libeigen3-dev zlib1g-dev libyaml-cpp-dev libfmt-dev \
  libtbb-dev python3-dev pybind11-dev swig \
  qt6-base-dev qt6-tools-dev qt6-tools-dev-tools qt6-l10n-tools \
  libqt6svg6-dev libqt6core5compat6-dev

sudo mkdir -p /opt/freecad-src && sudo chown "$(whoami)" /opt/freecad-src
git clone --depth 1 --branch "$FREECAD_TAG" --recurse-submodules \
  --shallow-submodules https://github.com/FreeCAD/FreeCAD.git /opt/freecad-src

# Headless configure still calls qt_add_translation -> needs LinguistTools
# even with BUILD_GUI=OFF (upstream quirk).
sed -i 's/set(FREECAD_QT_COMPONENTS Core Concurrent Network Xml)/set(FREECAD_QT_COMPONENTS Core Concurrent Network Xml LinguistTools)/' \
  /opt/freecad-src/cMake/FreeCAD_Helpers/SetupQt.cmake

mkdir -p /opt/freecad-src/build && cd /opt/freecad-src/build
cmake -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/freecad \
  -DBUILD_GUI=OFF -DBUILD_QT5=OFF \
  -DBUILD_BIM=OFF -DBUILD_CAM=OFF -DBUILD_DRAFT=OFF -DBUILD_SPREADSHEET=OFF \
  -DBUILD_FEM=OFF -DBUILD_SANDBOX=OFF -DBUILD_TEMPLATE=OFF -DBUILD_ADDONMGR=OFF \
  -DBUILD_ARCH=OFF -DBUILD_ASSEMBLY=OFF -DBUILD_DRAWING=OFF -DBUILD_IMPORT=ON \
  -DBUILD_INSPECTION=OFF -DBUILD_JTREADER=OFF -DBUILD_MATERIAL=ON \
  -DBUILD_MESH=OFF -DBUILD_MESH_PART=OFF -DBUILD_FLAT_MESH=OFF \
  -DBUILD_OPENSCAD=OFF -DBUILD_PART=ON -DBUILD_PART_DESIGN=ON \
  -DBUILD_PATH=OFF -DBUILD_PLOT=OFF -DBUILD_POINTS=OFF \
  -DBUILD_REVERSEENGINEERING=OFF -DBUILD_ROBOT=OFF -DBUILD_SHOW=OFF \
  -DBUILD_SKETCHER=ON -DBUILD_START=OFF -DBUILD_SURFACE=ON \
  -DBUILD_TECHDRAW=OFF -DBUILD_TUX=OFF -DBUILD_WEB=OFF -DBUILD_HELP=OFF \
  -DENABLE_DEVELOPER_TESTS=OFF -DPYTHON_EXECUTABLE=/usr/bin/python3 ..

ninja -j"$(nproc)" && sudo ninja install
pip install --quiet --break-system-packages pytest

# Smoke test
python3 -c "
import sys; sys.path.insert(0, '/opt/freecad/lib')
import FreeCAD, Part
print('FreeCAD', '.'.join(FreeCAD.Version()[:3]), '| OCC', Part.OCC_VERSION)
"
echo "Done. Run tests with: FREECAD_LIB=/opt/freecad/lib python3 -m pytest tests/"
