# Copyright (C) 2026 Sebastián Pacheco Mercado
# SPDX-License-Identifier: GPL-2.0-or-later

"""Spanish/English UI catalog selected from QGIS's configured language.

Only display text is translated. Algorithm IDs, parameter keys, CSV columns,
units and scenario records remain language independent. Reload the plugin
after changing the QGIS language, as for the rest of the application.
"""
from functools import lru_cache
from pathlib import Path
import json

from qgis.core import QgsApplication, QgsSettings
from qgis.PyQt.QtCore import QCoreApplication


def language():
    settings = QgsSettings()
    override = settings.value("locale/overrideFlag", False, type=bool)
    locale = (settings.value("locale/userLocale", "en") if override
              else QgsApplication.locale())
    return "es" if str(locale).lower().startswith("es") else "en"


@lru_cache(maxsize=1)
def english_catalog():
    return json.loads((Path(__file__).parent / "i18n/en.json").read_text(encoding="utf-8"))


def tr(text):
    translated = QCoreApplication.translate("GaussianEducational", text)
    if translated != text:
        return translated
    return text if language() == "es" else english_catalog().get(text, text)
