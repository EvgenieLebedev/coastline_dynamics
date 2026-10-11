# -*- coding: utf-8 -*-
"""Годовые композиты водного индекса: медиана, стандартное отклонение, число наблюдений.

Соответствует растровому этапу DEA Coastlines (coastlines/raster.py): для каждого
года по всем пригодным наблюдениям вычисляется попиксельная медиана индекса; для
лет с малым числом наблюдений готовится запасной трёхлетний композит (gapfill).
Приливная фильтрация оригинала заменена необязательным отбором наблюдений по
внешнему ряду уровня моря: в бесприливных морях она не нужна, а там, где нужна,
ряд уровня задаётся таблицей.
"""
import calendar
import csv
import datetime as dt
import json
import os
import warnings

import numpy as np

from . import gridio
from .sensors import BANDS, SCALE, NODATA
from .stac import load_archive, load_catalog, Canceled

INDICES = {
    "mndwi": ("green", "swir1"),     # Xu, 2006
    "ndwi": ("green", "nir"),        # McFeeters, 1996
}
INDEX_TITLES = {
    "mndwi": "MNDWI (зелёный и средний ИК)",
    "ndwi": "NDWI (зелёный и ближний ИК)",
}
META_FILE = "composites.json"
EPS = 1e-4          # нижняя граница отражения: поверхностное отражение воды в ИК бывает отрицательным


def water_index(a, b):
    """Нормализованная разность двух каналов отражения; значения в пределах [-1, 1]."""
    a = np.maximum(a, EPS)
    b = np.maximum(b, EPS)
    return (a - b) / (a + b)


def stack_stats(stack):
    """Медиана, стандартное отклонение и число наблюдений по оси 0. Массив сортируется на месте."""
    n = stack.shape[0]
    shape = stack.shape[1:]
    if n == 0:
        nan = np.full(shape, np.nan, dtype=np.float32)
        return nan, nan.copy(), np.zeros(shape, dtype=np.int16)
    cnt = np.isfinite(stack).sum(axis=0)
    stack.sort(axis=0)                                   # NaN уходят в конец
    lo = np.clip((cnt - 1) // 2, 0, n - 1)[None]
    hi = np.clip(cnt // 2, 0, n - 1)[None]
    med = 0.5 * (np.take_along_axis(stack, lo, axis=0)[0] + np.take_along_axis(stack, hi, axis=0)[0])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        std = np.nanstd(stack, axis=0)
    empty = cnt == 0
    med[empty] = np.nan
    std[empty] = np.nan
    return med.astype(np.float32), std.astype(np.float32), cnt.astype(np.int16)


# ------------------------------------------------------------------ отбор по уровню моря

def load_levels(path):
    """Таблица уровня моря: первый столбец — дата и время (UTC), второй — уровень.

    Допускаются разделители «,» и «;», десятичная запятая и строка заголовка.
    """
    times, values = [], []
    with open(path, encoding="utf-8-sig") as f:
        sample = f.read(2048)
        f.seek(0)
        delim = ";" if sample.count(";") > sample.count(",") else ","
        for row in csv.reader(f, delimiter=delim):
            if len(row) < 2:
                continue
            stamp = row[0].strip().replace("T", " ").replace("Z", "")
            when = None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d.%m.%Y %H:%M", "%d.%m.%Y"):
                try:
                    when = dt.datetime.strptime(stamp, fmt)
                    break
                except ValueError:
                    continue
            if when is None:
                continue
            try:
                val = float(row[1].strip().replace(",", "."))
            except ValueError:
                continue
            times.append(calendar.timegm(when.timetuple()))
            values.append(val)
    if len(times) < 2:
        raise ValueError("В таблице уровня не найдено ни одной пары «дата — значение»: %s" % path)
    order = np.argsort(times)
    return np.asarray(times, dtype=np.float64)[order], np.asarray(values, dtype=np.float64)[order]


def obs_time(row):
    stamp = "%s %s" % (row["date"], row.get("time_utc") or "00:00:00")
    return calendar.timegm(dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").timetuple())


def level_filter(rows, levels_path, fraction=0.5, centre=None, mode="range"):
    """Отбор наблюдений, снятых при уровне, близком к среднему.

    mode = "range" — как в DEA Coastlines: допуск равен доле fraction размаха уровней,
    отмеченных в моменты съёмки, и откладывается симметрично от центра (по умолчанию —
    от среднего уровня всего ряда). При fraction = 0,5 остаётся средняя половина размаха.
    Правило рассчитано на приливы, распределённые в ограниченных пределах.

    mode = "share" — остаётся доля fraction наблюдений, ближайших к центру. Подходит
    для рядов с редкими сильными отклонениями (сгоны и нагоны, ветровые показатели),
    у которых размах определяется единичными штормами.

    Возвращает (отобранные строки, словарь со сводкой).
    """
    times, values = load_levels(levels_path)
    lev = np.array([np.interp(obs_time(r), times, values, left=np.nan, right=np.nan) for r in rows])
    known = np.isfinite(lev)
    if not known.any():
        raise ValueError("Ряд уровня не перекрывается по времени со снимками.")
    centre = float(np.mean(values)) if centre is None else float(centre)
    if mode == "share":
        half = float(np.quantile(np.abs(lev[known] - centre), min(1.0, max(0.0, fraction))))
    else:
        half = 0.5 * fraction * (np.nanmax(lev) - np.nanmin(lev))
    with np.errstate(invalid="ignore"):
        keep = known & (lev >= centre - half) & (lev <= centre + half)
    info = {"mode": mode, "centre": centre, "low": centre - half, "high": centre + half,
            "total": int(len(rows)), "kept": int(keep.sum()), "unknown": int((~known).sum())}
    for r, v in zip(rows, lev):
        r["level"] = None if not np.isfinite(v) else float(v)
    return [r for r, k in zip(rows, keep) if k], info


# ------------------------------------------------------------------------- композиты

def composite_path(folder, index, year, gapfill=False):
    return os.path.join(folder, "%s_%d%s.tif" % (index, year, "_gapfill" if gapfill else ""))


def rgb_path(folder, year):
    return os.path.join(folder, "rgb_%d.tif" % year)


def load_meta(folder):
    path = os.path.join(folder, META_FILE)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_strip(folder, rows, r0, r1, width, bands):
    """Отражение всех наблюдений года в полосе строк: массив (n, len(bands), h, w) float32 с NaN."""
    out = np.empty((len(rows), len(bands), r1 - r0, width), dtype=np.float32)
    for k, row in enumerate(rows):
        raw = gridio.read_tif(os.path.join(folder, row["file"]), bands=bands, rows=(r0, r1))
        arr = raw.astype(np.float32) / SCALE
        arr[raw == NODATA] = np.nan
        out[k] = arr
    return out


def build_composites(archive_dir, out_dir, index="mndwi", year_from=None, year_to=None,
                     month_from=1, month_to=12, gapfill=True, rgb=True, levels_path=None,
                     level_fraction=0.5, level_centre=None, level_mode="range", memory_mb=512,
                     log=None, progress=None, is_canceled=None):
    """Строит годовые композиты индекса по локальному архиву сцен.

    В папке out_dir появляются файлы <индекс>_<год>.tif (каналы: медиана индекса,
    стандартное отклонение, число наблюдений), <индекс>_<год>_gapfill.tif (то же по
    трём смежным годам), rgb_<год>.tif (медианный цветосинтез SWIR–NIR–Green) и
    composites.json со сводкой. Возвращает словарь сводки.
    """
    log = log or (lambda msg: None)
    progress = progress or (lambda frac: None)
    is_canceled = is_canceled or (lambda: False)
    if index not in INDICES:
        raise ValueError("Неизвестный индекс: %s" % index)
    info = load_archive(archive_dir)
    if info is None:
        raise ValueError("В папке нет архива сцен (файл archive.json): %s" % archive_dir)
    grid = gridio.Grid.from_dict(info["grid"])
    rows = [r for r in load_catalog(archive_dir) if r["status"] == "ok"
            and month_from <= int(r["date"][5:7]) <= month_to
            and os.path.exists(os.path.join(archive_dir, r["file"]))]
    if not rows:
        raise ValueError("В архиве нет пригодных сцен за выбранные месяцы.")
    level_info = None
    if levels_path:
        rows, level_info = level_filter(rows, levels_path, level_fraction, level_centre, level_mode)
        log("Отбор по уровню моря: оставлено %d наблюдений из %d (уровень от %.2f до %.2f)."
            % (level_info["kept"], level_info["total"], level_info["low"], level_info["high"]))
    have = sorted(set(r["year"] for r in rows))
    year_from = have[0] if year_from is None else int(year_from)
    year_to = have[-1] if year_to is None else int(year_to)
    years = [y for y in range(year_from, year_to + 1) if y in have]
    if not years:
        raise ValueError("За годы %d–%d в архиве нет пригодных сцен." % (year_from, year_to))
    by_year = {}
    for r in rows:
        by_year.setdefault(r["year"], []).append(r)
    for y in by_year:
        by_year[y].sort(key=lambda r: r["obs_id"])

    band_a, band_b = (BANDS.index(b) + 1 for b in INDICES[index])
    need = sorted(set([band_a, band_b] + ([1, 2, 3] if rgb else [])))
    pos_a, pos_b = need.index(band_a), need.index(band_b)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    tags = {"index": index, "archive": os.path.abspath(archive_dir),
            "months": "%d-%d" % (month_from, month_to)}
    names = [index, "stdev", "count"]
    out_annual = {y: gridio.create_tif(composite_path(out_dir, index, y), grid, 3, "float32",
                                       np.nan, names, dict(tags, year=y, kind="annual"))
                  for y in years}
    out_gap = {}
    if gapfill:
        out_gap = {y: gridio.create_tif(composite_path(out_dir, index, y, True), grid, 3, "float32",
                                        np.nan, names, dict(tags, year=y, kind="gapfill"))
                   for y in years}
    out_rgb = {}
    if rgb:
        out_rgb = {y: gridio.create_tif(rgb_path(out_dir, y), grid, 3, "int16", NODATA,
                                        ["swir1", "nir", "green"], dict(tags, year=y, scale=SCALE))
                   for y in years}

    nmax = max(len(by_year[y]) for y in by_year)
    per_row = grid.width * nmax * (3 * 4 * 3 + len(need) * 4 * 2)        # байт на строку растра
    step = int(max(8, min(grid.height, memory_mb * 1024.0 * 1024.0 / per_row)))
    strips = [(r0, min(r0 + step, grid.height)) for r0 in range(0, grid.height, step)]
    log("Индекс %s, годы %d–%d (лет с данными: %d), наблюдений %d; сетка %dx%d, полос %d."
        % (index.upper(), years[0], years[-1], len(years), sum(len(by_year[y]) for y in years),
           grid.width, grid.height, len(strips)))

    total = float(len(strips) * len(years))
    done = 0
    for r0, r1 in strips:
        stacks = {}

        def load(y):
            yrows = by_year.get(y, [])
            refl = _load_strip(archive_dir, yrows, r0, r1, grid.width, need)
            idx = water_index(refl[:, pos_a], refl[:, pos_b]) if len(yrows) else \
                np.empty((0, r1 - r0, grid.width), dtype=np.float32)
            if rgb and y in out_rgb:
                for k, name in enumerate(("swir1", "nir", "green")):
                    band = refl[:, need.index(BANDS.index(name) + 1)].copy()
                    med = stack_stats(band)[0]
                    val = np.where(np.isfinite(med), np.clip(np.round(med * SCALE), -2000, 16000),
                                   NODATA).astype(np.int16)
                    out_rgb[y].GetRasterBand(k + 1).WriteArray(val, 0, r0)
            return idx

        for y in years:
            if is_canceled():
                raise Canceled()
            for yy in (y - 1, y, y + 1):
                if yy not in stacks and (yy == y or gapfill):
                    stacks[yy] = load(yy)
            med, std, cnt = stack_stats(stacks[y])
            for k, arr in enumerate((med, std, cnt.astype(np.float32))):
                out_annual[y].GetRasterBand(k + 1).WriteArray(arr, 0, r0)
            if gapfill:
                three = np.concatenate([stacks[y - 1], stacks[y], stacks[y + 1]], axis=0)
                med, std, cnt = stack_stats(three)
                del three
                for k, arr in enumerate((med, std, cnt.astype(np.float32))):
                    out_gap[y].GetRasterBand(k + 1).WriteArray(arr, 0, r0)
            stacks.pop(y - 1, None)
            done += 1
            progress(done / total)
    for group in (out_annual, out_gap, out_rgb):
        for ds in group.values():
            ds.FlushCache()
    out_annual = out_gap = out_rgb = None

    meta = {"index": index, "years": years, "archive": os.path.abspath(archive_dir),
            "sensor": info.get("sensor"), "months": [month_from, month_to],
            "gapfill": bool(gapfill), "rgb": bool(rgb), "grid": grid.to_dict(),
            "observations": {str(y): len(by_year[y]) for y in years},
            "level_filter": level_info,
            "created": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open(os.path.join(out_dir, META_FILE), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    log("Композиты записаны в %s" % out_dir)
    return meta


# ------------------------------------------------- композиты из готовых годовых растров

def index_from_rasters(files_by_year, out_dir, index="mndwi", band_a=2, band_b=5, scale=1.0,
                       nodata=None, log=None, progress=None, is_canceled=None):
    """Водный индекс по готовым годовым композитам отражения (по одному растру на год).

    Применяется, когда годовые безоблачные композиты уже есть (например, собраны
    другим способом). Число наблюдений неизвестно, поэтому в канал count пишется 99,
    а стандартное отклонение принимается нулевым: проверки надёжности на таких
    данных не срабатывают, о чём следует помнить при разборе результата.
    """
    log = log or (lambda msg: None)
    progress = progress or (lambda frac: None)
    is_canceled = is_canceled or (lambda: False)
    years = sorted(files_by_year)
    if not years:
        raise ValueError("Не задано ни одного годового растра.")
    grid = gridio.grid_of(files_by_year[years[0]])
    if grid.epsg == 0:
        raise ValueError("У растра не определён код EPSG системы координат: %s" % files_by_year[years[0]])
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    for n, y in enumerate(years, 1):
        if is_canceled():
            raise Canceled()
        path = files_by_year[y]
        if not gridio.grid_of(path).same_as(grid):
            raise ValueError("Растр %s лежит в другой сетке, чем растр первого года." % path)
        raw = gridio.read_tif(path, bands=[band_a, band_b]).astype(np.float32)
        bad = ~np.isfinite(raw).all(axis=0)
        if nodata is not None:
            bad |= (raw == nodata).any(axis=0)
        refl = raw * float(scale)
        idx = water_index(refl[0], refl[1]).astype(np.float32)
        idx[bad] = np.nan
        std = np.where(bad, np.nan, 0.0).astype(np.float32)
        cnt = np.where(bad, 0.0, 99.0).astype(np.float32)
        gridio.write_tif(composite_path(out_dir, index, y), np.stack([idx, std, cnt]), grid,
                         "float32", np.nan, [index, "stdev", "count"],
                         {"index": index, "year": y, "kind": "annual", "source": os.path.abspath(path)})
        log("%d: %s" % (y, os.path.basename(path)))
        progress(n / float(len(years)))
    meta = {"index": index, "years": years, "archive": None, "sensor": "local",
            "months": None, "gapfill": False, "rgb": False, "grid": grid.to_dict(),
            "observations": {str(y): 99 for y in years}, "level_filter": None,
            "created": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open(os.path.join(out_dir, META_FILE), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return meta
