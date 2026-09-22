#!/bin/bash
# Run tests with the selected macOS QGIS Python, with process-local settings.
GAUSSIAN_QGIS_APP="${GAUSSIAN_QGIS_APP:-/Applications/QGIS-LTR.app}"
GAUSSIAN_QGIS_CONTENTS="$GAUSSIAN_QGIS_APP/Contents"
unset PYTHONHOME PYTHONPATH
if [ -x "$GAUSSIAN_QGIS_CONTENTS/MacOS/bin/python3" ]; then
    exec "$GAUSSIAN_QGIS_CONTENTS/MacOS/bin/python3" "$@"
fi
GAUSSIAN_QGIS_PYTHON=""
for candidate in "$GAUSSIAN_QGIS_CONTENTS"/MacOS/python3.*; do
    if [ -x "$candidate" ] && [ ! -d "$candidate" ]; then
        GAUSSIAN_QGIS_PYTHON="$candidate"
        break
    fi
done
GAUSSIAN_QGIS_LIBRARY=""
for candidate in "$GAUSSIAN_QGIS_CONTENTS"/Resources/python*; do
    if [ -d "$candidate/encodings" ] && [ -d "$candidate/site-packages" ]; then
        GAUSSIAN_QGIS_LIBRARY="$candidate"
        break
    fi
done
if [ -z "$GAUSSIAN_QGIS_PYTHON" ] || [ -z "$GAUSSIAN_QGIS_LIBRARY" ]; then
    echo "No se encontró Python incluido en: $GAUSSIAN_QGIS_APP" >&2
    exit 1
fi
export PYTHONHOME="$GAUSSIAN_QGIS_CONTENTS/Resources"
export PYTHONPATH="$GAUSSIAN_QGIS_LIBRARY:$GAUSSIAN_QGIS_LIBRARY/lib-dynload:$GAUSSIAN_QGIS_LIBRARY/site-packages"
export QT_PLUGIN_PATH="$GAUSSIAN_QGIS_CONTENTS/PlugIns"
exec "$GAUSSIAN_QGIS_PYTHON" "$@"
