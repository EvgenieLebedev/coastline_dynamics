# -*- coding: utf-8 -*-
"""Описание съёмочных систем: где искать сцены, какие каналы брать, как маскировать.

Оба набора размещены в каталоге Microsoft Planetary Computer и открыты для
анонимного чтения: достаточно временной подписи ссылок (SAS-токена), которую
каталог выдаёт без регистрации.
"""
import numpy as np
from .i18n import tr

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/"

# Каналы, сохраняемые в локальный архив сцен (порядок каналов в файле)
BANDS = ("green", "nir", "swir1")
SCALE = 10000.0          # отражение хранится как int16 = отражение * 10000
NODATA = -32768


def _landsat_reflectance(dn, item):
    """Collection 2 Level-2: отражение = DN * 2,75e-5 - 0,2; DN = 0 — нет данных."""
    out = dn.astype(np.float32) * 2.75e-5 - 0.2
    out[dn == 0] = np.nan
    return out


def _landsat_bad(qa, item):
    """Маска непригодных пикселей по QA_PIXEL.

    Биты: 0 — заполнение, 3 — облако, 4 — тень облака, 5 — снег и лёд.
    Биты 1 (расширенное облако) и 2 (перистые) намеренно не используются:
    расширение облаков выполняется собственной морфологической очисткой,
    перед которой узкие ложные «облака» над пляжами и прибоем удаляются.
    """
    qa = qa.astype(np.uint16)
    fill = (qa & 1) > 0
    bad = (qa & 0b111000) > 0
    return bad, fill


def _s2_reflectance(dn, item):
    """Sentinel-2 L2A: отражение = (DN - сдвиг) / 10000; сдвиг 1000 с версии обработки 04.00."""
    try:
        baseline = float(item["properties"].get("s2:processing_baseline", "0"))
    except (TypeError, ValueError):
        baseline = 0.0
    offset = 1000.0 if baseline >= 4.0 else 0.0
    out = (dn.astype(np.float32) - offset) / 10000.0
    out[dn == 0] = np.nan
    return out


def _s2_bad(scl, item):
    """Маска по слою классификации сцены SCL.

    Непригодны: 0 — нет данных, 1 — дефектные, 3 — тени облаков, 8 и 9 — облака
    средней и высокой вероятности, 10 — перистые, 11 — снег и лёд.
    """
    fill = scl == 0
    bad = np.isin(scl, (1, 3, 8, 9, 10, 11))
    return bad, fill


SENSORS = {
    "landsat": {
        "title": tr("Landsat 4–9, Collection 2 Level-2 (30 м, с 1982 г.)"),
        "collection": "landsat-c2-l2",
        "assets": {"green": "green", "nir": "nir08", "swir1": "swir16"},
        "qa": "qa_pixel",
        "res": 30.0,
        "align": 15.0,
        "reflectance": _landsat_reflectance,
        "bad": _landsat_bad,
        "platforms": {
            "TM": ("landsat-4", "landsat-5"),
            "ETM+": ("landsat-7",),
            "OLI": ("landsat-8", "landsat-9"),
        },
        "extensions": ".tif,.TIF",
    },
    "sentinel2": {
        "title": tr("Sentinel-2 L2A (10 м, с 2015 г.)"),
        "collection": "sentinel-2-l2a",
        "assets": {"green": "B03", "nir": "B08", "swir1": "B11"},
        "qa": "SCL",
        "res": 10.0,
        "align": 0.0,
        "reflectance": _s2_reflectance,
        "bad": _s2_bad,
        "platforms": {"MSI": ("Sentinel-2A", "Sentinel-2B", "Sentinel-2C",
                              "sentinel-2a", "sentinel-2b", "sentinel-2c")},
        "extensions": ".tif,.TIF",
    },
}


def instrument_of(sensor_key, platform):
    for name, plats in SENSORS[sensor_key]["platforms"].items():
        if platform in plats:
            return name
    return None
