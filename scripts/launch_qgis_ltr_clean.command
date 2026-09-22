#!/bin/bash
# Launch QGIS LTR with its own GIS libraries. All variables are limited to the
# QGIS process and its children; the user's global shell configuration is not changed.
GAUSSIAN_QGIS_APP="${GAUSSIAN_QGIS_APP:-/Applications/QGIS-LTR.app}"
QGIS_CONTENTS="$GAUSSIAN_QGIS_APP/Contents"
if [ ! -x "$QGIS_CONTENTS/MacOS/QGIS" ]; then
    echo "No se encontró QGIS en: $GAUSSIAN_QGIS_APP" >&2
    exit 1
fi

QGIS_GIS_RESOURCES="$QGIS_CONTENTS/Resources"
export QGIS_PREFIX_PATH="$QGIS_CONTENTS/MacOS"
if [ -f "$QGIS_CONTENTS/Resources/qgis/proj/proj.db" ]; then
    QGIS_GIS_RESOURCES="$QGIS_CONTENTS/Resources/qgis"
    export QGIS_PREFIX_PATH="$QGIS_GIS_RESOURCES"
fi
export PROJ_LIB="$QGIS_GIS_RESOURCES/proj"
export PROJ_DATA="$QGIS_GIS_RESOURCES/proj"
export GDAL_DATA="$QGIS_GIS_RESOURCES/gdal"
export GDAL_DRIVER_PATH="$QGIS_CONTENTS/MacOS/lib/gdalplugins"
export PATH="$QGIS_CONTENTS/MacOS/bin:$PATH"
unset PYTHONHOME
unset PYTHONPATH
if [ "$QGIS_GIS_RESOURCES" = "$QGIS_CONTENTS/Resources/qgis" ]; then
    for candidate in "$QGIS_CONTENTS"/Resources/python*; do
        if [ -d "$candidate/encodings" ] && [ -d "$candidate/site-packages" ]; then
            export PYTHONHOME="$QGIS_CONTENTS/Resources"
            export PYTHONPATH="$candidate:$candidate/lib-dynload:$candidate/site-packages"
            break
        fi
    done
fi

exec "$QGIS_CONTENTS/MacOS/QGIS" "$@"
