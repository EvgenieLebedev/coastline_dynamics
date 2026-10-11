# -*- coding: utf-8 -*-
"""Подготовка годовых композитов к выделению береговой линии.

Перенос функции contours_preprocess из DEA Coastlines (coastlines/vector.py):

1) малонаблюдаемые пиксели годового композита заменяются трёхлетним композитом;
2) индекс делится порогом на сушу и воду;
3) временная маска убирает пятна «суши», не подтверждённые соседними годами;
4) по всему ряду определяется море (вода, связанная с открытой акваторией) и
   строится прибрежная полоса заданной ширины вокруг его многолетней границы;
5) узкие водотоки внутри суши исключаются из расчёта, кроме приустьевых участков;
6) в каждом году остаётся только вода, связанная с морем, и трёхпиксельная кайма суши.

Отличие от оригинала одно: в Австралии море задаётся готовой картой береговой
линии, здесь оно определяется по самим снимкам (крупнейший постоянный водоём)
либо по слою, указанному пользователем.
"""
import os

import numpy as np
from osgeo import gdal, ogr
from scipy import ndimage

from . import composites, gridio, morph
from .stac import Canceled
from .i18n import tr

# Размеры морфологических элементов DEA Coastlines, пересчитанные из пикселей Landsat в метры
RIVER_WIDTH_M = 240.0        # disk(8): водотоки уже примерно 2 x 240 м считаются реками
RIVER_MOUTH_M = 360.0        # disk(12): приустьевая часть реки остаётся в расчёте
RIVER_BUFFER_M = 120.0       # disk(4): полоса вдоль реки, исключаемая из расчёта
ISLAND_AREA_M2 = 5.0e6       # острова меньше 5 км2 не мешают распознаванию рек
OCEAN_EROSION_M = 600.0      # disk(20): «открытая вода» — дальше 600 м от суши
WATERBODY_EROSION_M = 150.0  # режим «все водоёмы»: достаточно 150 м от берега (водоёмы шире 300 м)
ANNUAL_DILATION_PX = 3       # кайма суши вокруг моря, нужная для построения изолинии
CERTAINTY_SIEVE_PX = 128
CERTAINTY_DILATION_PX = 3

CERTAINTY_CLASSES = {0: "good", 1: "unstable data", 2: "insufficient data"}


def find_composites(folder, index=None):
    """Годовые композиты в папке: (индекс, {год: путь}, {год: путь gapfill})."""
    meta = composites.load_meta(folder)
    if index is None and meta:
        index = meta.get("index")
    names = sorted(os.listdir(folder))
    if index is None:
        for cand in composites.INDICES:
            if any(n.startswith(cand + "_") and n.endswith(".tif") for n in names):
                index = cand
                break
    if index is None:
        raise ValueError(tr("В папке не найдены годовые композиты индекса (файлы вида mndwi_2020.tif): %s") % folder)
    annual, gap = {}, {}
    for n in names:
        if not (n.startswith(index + "_") and n.endswith(".tif")):
            continue
        stem = n[len(index) + 1:-4]
        target = annual
        if stem.endswith("_gapfill"):
            stem, target = stem[:-8], gap
        if stem.isdigit():
            target[int(stem)] = os.path.join(folder, n)
    if not annual:
        raise ValueError(tr("В папке нет файлов %s_<год>.tif: %s") % (index, folder))
    return index, annual, gap


def rasterize_geoms(wkb_list, grid, all_touched=True):
    """Булев растр по списку геометрий (WKB в системе координат сетки)."""
    out = np.zeros((grid.height, grid.width), dtype=np.uint8)
    if not wkb_list:
        return out.astype(bool)
    drv = ogr.GetDriverByName("Memory") or ogr.GetDriverByName("MEM")
    vds = drv.CreateDataSource("geoms")
    lyr = vds.CreateLayer("geoms", gridio.srs_from_epsg(grid.epsg), ogr.wkbUnknown)
    for wkb in wkb_list:
        feat = ogr.Feature(lyr.GetLayerDefn())
        feat.SetGeometry(ogr.CreateGeometryFromWkb(bytes(wkb)))
        lyr.CreateFeature(feat)
    ds = gridio.mem_raster(out, grid)
    gdal.RasterizeLayer(ds, [1], lyr, burn_values=[1],
                        options=["ALL_TOUCHED=TRUE"] if all_touched else [])
    out = ds.GetRasterBand(1).ReadAsArray()
    return out.astype(bool)


def ocean_masking(land, seeds, connectivity=1, dilation=None):
    """Вода, связанная с морем: области «не суши», в которые попадает хотя бы один затравочный пиксель."""
    seeds = seeds & ~land
    lab, n = morph.label(~land, connectivity)
    if n == 0 or not seeds.any():
        return np.zeros(land.shape, dtype=bool)
    keep = np.unique(lab[seeds])
    keep = keep[keep > 0]
    ocean = np.isin(lab, keep)
    if dilation:
        ocean = morph.dilate(ocean, dilation)
    return ocean


def temporal_masking(land):
    """Ложь для пятен «суши», не совпадающих ни с одним пикселем суши в соседние годы.

    Так устраняются одиночные помехи: неотфильтрованные облака, пена прибоя, сбои
    съёмки. Настоящая суша соседствует с сушей предыдущего или следующего года.
    Пятна выделяются в трёхмерном массиве «год — строка — столбец», как в оригинале.
    """
    lab, n = ndimage.label(land, structure=np.ones((3, 3, 3), dtype=bool))
    mask = np.ones(land.shape, dtype=bool)
    if n == 0:
        return mask
    for k in range(land.shape[0]):
        neigh = np.zeros(land.shape[1:], dtype=bool)
        if k > 0:
            neigh |= land[k - 1]
        if k < land.shape[0] - 1:
            neigh |= land[k + 1]
        ids = np.unique(lab[k])
        ids = ids[ids > 0]
        if ids.size == 0:
            continue
        hit = ndimage.maximum(neigh.astype(np.uint8), labels=lab[k], index=ids)
        lonely = ids[np.asarray(hit) == 0]
        if lonely.size:
            mask[k][np.isin(lab[k], lonely)] = False
    return mask


def certainty_masking(std, cnt, obs_threshold=5, stdev_threshold=0.3):
    """Растр надёжности года: 0 — надёжно, 1 — неустойчивый индекс, 2 — мало наблюдений."""
    with np.errstate(invalid="ignore"):
        unstable = std > stdev_threshold
        insufficient = cnt < obs_threshold
    unstable = morph.sieve(unstable & ~insufficient, CERTAINTY_SIEVE_PX)
    insufficient = morph.sieve(insufficient, CERTAINTY_SIEVE_PX)
    out = np.zeros(std.shape, dtype=np.uint8)
    out[morph.dilate(unstable, CERTAINTY_DILATION_PX)] = 1
    out[morph.dilate(insufficient, CERTAINTY_DILATION_PX)] = 2
    return out


def load_combined(folder, index=None, year_from=None, year_to=None, gapfill_below=6,
                  min_annual_obs=2, obs_threshold=5, stdev_threshold=0.3, log=None,
                  is_canceled=None):
    """Годовые композиты после подстановки трёхлетних и растры надёжности.

    Ключи результата: index, years, grid, combined (год x h x w), certainty (uint8),
    gapfilled (доля подставленных пикселей по годам).
    """
    log = log or (lambda msg: None)
    is_canceled = is_canceled or (lambda: False)
    index, annual, gap = find_composites(folder, index)
    years = sorted(y for y in annual if (year_from is None or y >= year_from)
                   and (year_to is None or y <= year_to))
    if not years:
        raise ValueError(tr("В папке нет композитов за выбранные годы."))
    grid = gridio.grid_of(annual[years[0]])
    px = grid.res
    shape = (len(years), grid.height, grid.width)
    combined = np.empty(shape, dtype=np.float32)
    certainty = np.empty(shape, dtype=np.uint8)
    gapfilled = []
    for k, y in enumerate(years):
        if is_canceled():
            raise Canceled()
        a = gridio.read_tif(annual[y])
        idx, std, cnt = a[0], a[1], np.nan_to_num(a[2])
        if y in gap:
            g = gridio.read_tif(gap[y])
            use = cnt < gapfill_below
            idx = np.where(use, g[0], idx)
            std = np.where(use, g[1], std)
            cnt_c = np.where(use, np.nan_to_num(g[2]), cnt)
            gapfilled.append(float((use & np.isfinite(g[0])).mean()))
        else:
            cnt_c = cnt
            gapfilled.append(0.0)
        idx[cnt < min_annual_obs] = np.nan       # единственное наблюдение за год слишком уязвимо к помехам
        combined[k] = idx
        certainty[k] = certainty_masking(std, cnt_c, obs_threshold, stdev_threshold)
    log(tr("Загружены композиты %s за %d–%d (лет: %d), сетка %dx%d.") %
        (index.upper(), years[0], years[-1], len(years), grid.width, grid.height))
    return {"index": index, "years": years, "grid": grid, "combined": combined,
            "certainty": certainty, "gapfilled": gapfilled}


def preprocess(folder, index=None, threshold=0.0, year_from=None, year_to=None,
               buffer_m=1000.0, mask_temporal=True, mask_rivers=True, sea_mode="largest",
               sea_wkb=None, exclude_wkb=None, gapfill_below=6, min_annual_obs=2,
               obs_threshold=5, stdev_threshold=0.3, log=None, is_canceled=None):
    """Возвращает словарь с подготовленными данными для выделения береговых линий.

    К ключам load_combined добавляются: masked (индекс в прибрежной полосе, NaN вне её),
    coastal_mask (0 — море, 1 — прибрежная полоса, 2 — суша и внутренние воды),
    land_freq (доля лет, когда пиксель был сушей), threshold.
    """
    log = log or (lambda msg: None)
    is_canceled = is_canceled or (lambda: False)
    data = load_combined(folder, index, year_from, year_to, gapfill_below, min_annual_obs,
                         obs_threshold, stdev_threshold, log, is_canceled)
    index, years, grid = data["index"], data["years"], data["grid"]
    combined, certainty, gapfilled = data["combined"], data["certainty"], data["gapfilled"]
    px = grid.res
    shape = combined.shape

    nodata = ~np.isfinite(combined)
    with np.errstate(invalid="ignore"):
        land = (combined < threshold) & ~nodata
    if mask_temporal and len(years) < 2:
        log(tr("Композит один: временная маска не применяется (не с чем сравнивать)."))
        mask_temporal = False
    if mask_temporal:
        tmask = temporal_masking(land)
        removed = int((land & ~tmask).sum())
        land &= tmask
        nodata |= ~tmask
        log(tr("Временная маска: снято %d пикселей неподтверждённой «суши».") % removed)
    else:
        tmask = np.ones(shape, dtype=bool)

    valid_n = (~nodata).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        land_freq = np.where(valid_n > 0, land.sum(axis=0) / np.maximum(valid_n, 1), np.nan).astype(np.float32)
        all20 = land_freq > 0.2
        all80 = land_freq > 0.8

    rivers = np.zeros(all20.shape, dtype=bool)
    river_mask = np.ones(all20.shape, dtype=bool)
    if mask_rivers:
        island_px = int(ISLAND_AREA_M2 / (px * px))
        sieved = morph.sieve(all80, island_px)
        rivers = morph.black_tophat(sieved & all80, RIVER_WIDTH_M / px)
        mouth = morph.erode(all80 | rivers, RIVER_MOUTH_M / px)
        rivers &= mouth
        river_mask = ~morph.dilate(rivers, RIVER_BUFFER_M / px)
        log(tr("Маска водотоков: исключено %.2f км2.") % ((~river_mask).sum() * px * px / 1e6))

    # Затравка моря: заведомо открытая вода
    persistent = ~all20 & (valid_n > 0)
    if sea_wkb:
        seeds = morph.dilate(rasterize_geoms(sea_wkb, grid), 1) & persistent
        if not seeds.any():
            raise ValueError(tr("Слой морской акватории не попадает на воду в пределах участка."))
    else:
        radius = (OCEAN_EROSION_M if sea_mode == "largest" else WATERBODY_EROSION_M) / px
        seeds = morph.erode(persistent, radius)
        while not seeds.any() and radius >= 1:
            radius /= 2.0
            seeds = morph.erode(persistent, radius)
        if not seeds.any():
            raise ValueError(tr("На участке не найдено открытой воды. Проверьте порог индекса и охват."))
        if sea_mode == "largest":
            lab, n = morph.label(persistent)
            sizes = np.bincount(lab.ravel())
            cand = np.unique(lab[seeds])
            cand = cand[cand > 0]
            best = cand[np.argmax(sizes[cand])]
            seeds &= lab == best
            log(tr("Море: крупнейший постоянный водоём, %.1f км2 в пределах участка.")
                % (sizes[best] * px * px / 1e6))
        else:
            lab, n = morph.label(persistent)
            found = np.unique(lab[seeds])
            log(tr("Море и водоёмы: все постоянные водоёмы шире %.0f м, найдено %d.")
                % (2 * WATERBODY_EROSION_M, int((found > 0).sum())))

    all_time_ocean = ocean_masking(all20 | rivers, seeds)
    buffer_px = buffer_m / px
    coastal = morph.dilate(all_time_ocean, buffer_px) & morph.dilate(~all_time_ocean, buffer_px)
    coastal_mask = np.where(coastal, 1, np.where(all_time_ocean, 0, 2)).astype(np.uint8)
    coastal_mask[~river_mask] = 2
    if exclude_wkb:
        coastal_mask[rasterize_geoms(exclude_wkb, grid)] = 2
    inland = coastal_mask == 2

    masked = np.full(shape, np.nan, dtype=np.float32)
    for k in range(len(years)):
        if is_canceled():
            raise Canceled()
        annual_ocean = ocean_masking(land[k] | nodata[k] | inland, seeds, connectivity=1,
                                     dilation=ANNUAL_DILATION_PX)
        keep = tmask[k] & annual_ocean & (coastal_mask == 1)
        masked[k][keep] = combined[k][keep]
    log(tr("Прибрежная полоса %.0f м: %.1f км2.") % (buffer_m, (coastal_mask == 1).sum() * px * px / 1e6))
    return {"index": index, "years": years, "grid": grid, "masked": masked, "combined": combined,
            "certainty": certainty, "coastal_mask": coastal_mask, "land_freq": land_freq,
            "gapfilled": gapfilled, "threshold": threshold}
