#!/bin/bash
# Wrapper to run scripts with QGIS's bundled Python + PyQGIS available.
# Usage: ./src/run_qgis_python.sh src/build_map.py

set -e

QGIS_APP=$(ls -d /Applications/QGIS.app /Applications/QGIS-LTR.app /Applications/QGIS*.app 2>/dev/null | head -1)
if [ -z "$QGIS_APP" ]; then
    echo "No se encontró QGIS.app en /Applications" >&2
    exit 1
fi
CONTENTS="$QGIS_APP/Contents"

PY_HOME="$CONTENTS/Resources/python3.12"
export PYTHONHOME="$CONTENTS/Frameworks"

PLUGINS_DIR="$HOME/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
export PYTHONPATH="$PY_HOME:$PY_HOME/site-packages:$PLUGINS_DIR"

export PROJ_DATA="$CONTENTS/Resources/qgis/proj"
export PROJ_LIB="$PROJ_DATA"
export GDAL_DATA="$CONTENTS/Resources/qgis/gdal"
export QT_QPA_PLATFORM=offscreen

PYBIN=$(ls "$CONTENTS/MacOS"/python3.* 2>/dev/null | head -1)

exec "$PYBIN" "$@"
