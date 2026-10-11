# -*- coding: utf-8 -*-
"""Поиск сцен в каталоге STAC и загрузка вырезок по расчётной сетке.

Сцена не скачивается целиком. Файлы каталога хранятся в формате COG
(Cloud Optimized GeoTIFF), и GDAL читает по сети только те плитки, которые
накрывают участок. Результат — локальный архив: один небольшой GeoTIFF на
каждый день съёмки и таблица сцен scenes.csv.
"""
import calendar
import csv
import datetime as dt
import json
import os
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from osgeo import gdal

from . import gridio, morph
from .sensors import SENSORS, STAC_URL, TOKEN_URL, BANDS, SCALE, NODATA, instrument_of
from .i18n import tr

ARCHIVE_FILE = "archive.json"
CATALOG_FILE = "scenes.csv"
CATALOG_FIELDS = ["obs_id", "date", "time_utc", "platform", "instrument", "path", "year",
                  "cloud_cover", "clear_frac", "status", "file", "items"]
# Очистка маски облаков, метры: замыкание, размыкание, расширение (в DEA Coastlines 2, 10 и 5 пикселей Landsat)
DEFAULT_CLOUD_FILTERS = (60.0, 300.0, 150.0)
L7_SCIENCE_END = "2022-04-06"      # окончание штатной съёмки Landsat 7


class Canceled(Exception):
    pass


# ----------------------------------------------------------------------------- сеть

def http_json(url, payload=None, timeout=90, retries=4):
    """GET или POST (если задан payload) с разбором JSON и повторами при сбоях сети."""
    data = None
    headers = {"Accept": "application/json", "User-Agent": "qgis-coastline-dynamics/0.1"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = exc
            time.sleep(2 + 3 * attempt)
    raise RuntimeError(tr("Нет ответа от %s: %s") % (url.split("?")[0], last))


class Signer(object):
    """Временная подпись ссылок Planetary Computer. Токен живёт меньше часа и обновляется заранее."""

    def __init__(self, collection):
        self.collection = collection
        self._token = None
        self._expiry = 0.0
        self._lock = threading.Lock()

    def token(self, force=False):
        with self._lock:
            if force or self._token is None or time.time() > self._expiry - 300:
                info = http_json(TOKEN_URL + self.collection)
                self._token = info["token"]
                try:
                    exp = dt.datetime.strptime(info["msft:expiry"][:19], "%Y-%m-%dT%H:%M:%S")
                    self._expiry = calendar.timegm(exp.timetuple())
                except (KeyError, ValueError):
                    self._expiry = time.time() + 1800
            return self._token

    def sign(self, href, force=False):
        return href.split("?")[0] + "?" + self.token(force)


def search(sensor_key, bbox, date_from, date_to, max_cloud=100.0):
    """Все сцены набора в рамке bbox (долгота/широта) за интервал дат."""
    body = {"collections": [SENSORS[sensor_key]["collection"]],
            "bbox": [round(float(v), 6) for v in bbox],
            "datetime": "%sT00:00:00Z/%sT23:59:59Z" % (date_from, date_to),
            "limit": 200}
    if max_cloud < 100:
        body["query"] = {"eo:cloud_cover": {"lt": float(max_cloud)}}
    url = STAC_URL + "/search"
    items = []
    while True:
        page = http_json(url, body)
        items.extend(page.get("features", []))
        nxt = [l for l in page.get("links", []) if l.get("rel") == "next"]
        if not nxt:
            break
        link = nxt[0]
        url = link.get("href", url)
        if link.get("method", "GET").upper() == "POST":
            nxt_body = link.get("body") or {}
            body = dict(body or {}, **nxt_body) if link.get("merge") else (nxt_body or body)
        else:                            # постраничная выдача методом GET: всё в адресе
            body = None
    return items


# ----------------------------------------------------------------- отбор и группировка

def _props(item):
    return item.get("properties", {})


def group_observations(items, sensor_key, instruments=None, tier1_only=True):
    """Сцены одного пролёта (соседние кадры одного витка, снятые в один день) образуют одно наблюдение."""
    groups = {}
    for it in items:
        p = _props(it)
        platform = p.get("platform", "")
        inst = instrument_of(sensor_key, platform)
        if inst is None or (instruments and inst not in instruments):
            continue
        when = p.get("datetime") or p.get("start_datetime") or ""
        day = when[:10]
        if sensor_key == "landsat":
            if tier1_only and p.get("landsat:collection_category", "T1") != "T1":
                continue
            if platform == "landsat-7" and day > L7_SCIENCE_END:
                continue
            path = str(p.get("landsat:wrs_path", "")).lstrip("0")
            short = "L" + platform[-1]
        else:
            path = str(p.get("sat:relative_orbit", ""))
            short = "S" + platform[-2:].upper()
        key = "%s_%s_%s" % (day.replace("-", ""), short, path)
        g = groups.setdefault(key, {"obs_id": key, "date": day, "time_utc": when[11:19],
                                    "platform": platform, "instrument": inst, "path": path,
                                    "year": int(day[:4]), "items": []})
        g["items"].append(it)
    out = []
    for key in sorted(groups):
        g = groups[key]
        g["items"].sort(key=lambda i: _props(i).get("eo:cloud_cover", 100.0))
        g["cloud_cover"] = min(_props(i).get("eo:cloud_cover", 100.0) for i in g["items"])
        out.append(g)
    return out


# ------------------------------------------------------------------------ чтение сцены

def _thread_config(extensions):
    for k, v in (("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR"),
                 ("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", extensions),
                 ("GDAL_HTTP_MAX_RETRY", "4"), ("GDAL_HTTP_RETRY_DELAY", "3"),
                 ("GDAL_HTTP_TIMEOUT", "120"), ("GDAL_HTTP_CONNECTTIMEOUT", "30"),
                 ("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES"),
                 ("VSI_CACHE", "TRUE"), ("VSI_CACHE_SIZE", "20000000")):
        gdal.SetThreadLocalConfigOption(k, v)


def _aligned(src, grid):
    gt = src.GetGeoTransform()
    if abs(gt[1] - grid.res) > 1e-6 or abs(abs(gt[5]) - grid.res) > 1e-6 or gt[2] or gt[4]:
        return False
    try:
        srs = src.GetSpatialRef()
        if srs is None or int(srs.GetAuthorityCode(None) or 0) != grid.epsg:
            return False
    except Exception:
        return False
    dx = (grid.x0 - gt[0]) / grid.res
    dy = (grid.y1 - gt[3]) / grid.res
    return abs(dx - round(dx)) < 1e-6 and abs(dy - round(dy)) < 1e-6


def read_to_grid(href, grid, signer, categorical=False):
    """Чтение одного канала сцены в расчётную сетку (массив h x w, 0 — нет данных)."""
    last = None
    for attempt in range(4):
        try:
            src = gdal.Open("/vsicurl/" + signer.sign(href, force=attempt > 0))
            alg = "near" if (categorical or _aligned(src, grid)) else "cubic"
            mem = gdal.Warp("", src, format="MEM", outputBounds=grid.bounds,
                            xRes=grid.res, yRes=grid.res, dstSRS=grid.wkt,
                            resampleAlg=alg, srcNodata=0, dstNodata=0)
            arr = mem.GetRasterBand(1).ReadAsArray()
            mem = None
            src = None
            return arr
        except RuntimeError as exc:
            last = exc
            time.sleep(3 + 4 * attempt)
    raise RuntimeError(tr("Не удалось прочитать %s: %s") % (href.split("?")[0].split("/")[-1], last))


def fetch_observation(obs, sensor_key, grid, signer, min_clear, cloud_px):
    """Загрузка одного наблюдения. Возвращает (статус, массив int16 [3, h, w] или None, доля ясных)."""
    sensor = SENSORS[sensor_key]
    _thread_config(sensor["extensions"])
    h, w = grid.height, grid.width
    valid = np.zeros((h, w), dtype=bool)        # пиксели, уже получившие данные
    covered = np.zeros((h, w), dtype=bool)      # пиксели, попавшие в кадр хотя бы одной сцены
    parts = []
    for it in obs["items"]:
        assets = it.get("assets", {})
        if sensor["qa"] not in assets:
            continue
        qa = read_to_grid(assets[sensor["qa"]]["href"], grid, signer, categorical=True)
        bad, fill = sensor["bad"](qa, it)
        if fill.all():
            continue
        bad = morph.mask_cleanup(bad & ~fill, (("closing", cloud_px[0]), ("opening", cloud_px[1]),
                                              ("dilation", cloud_px[2])))
        clear = ~bad & ~fill
        parts.append((it, clear & ~valid))
        valid |= clear
        covered |= ~fill
        if covered.all():
            break
    if not covered.any():
        return "empty", None, 0.0
    clear_frac = float(valid.mean())
    if clear_frac < min_clear:
        return "cloudy", None, clear_frac
    out = np.full((len(BANDS), h, w), NODATA, dtype=np.int16)
    for it, use in parts:
        if not use.any():
            continue
        for k, name in enumerate(BANDS):
            dn = read_to_grid(it["assets"][sensor["assets"][name]]["href"], grid, signer)
            refl = sensor["reflectance"](dn, it)
            ok = use & np.isfinite(refl)
            val = np.clip(np.round(np.nan_to_num(refl) * SCALE), -2000, 16000).astype(np.int16)
            out[k][ok] = val[ok]
    # пиксель пригоден, только если данные есть во всех каналах
    good = (out != NODATA).all(axis=0)
    out[:, ~good] = NODATA
    return "ok", out, float(good.mean())


# ----------------------------------------------------------------------------- архив

def load_archive(folder):
    path = os.path.join(folder, ARCHIVE_FILE)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_catalog(folder):
    """Таблица сцен архива: список словарей (числовые поля приведены к числам)."""
    path = os.path.join(folder, CATALOG_FILE)
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            r["year"] = int(r["year"])
            r["cloud_cover"] = float(r["cloud_cover"] or 0)
            r["clear_frac"] = float(r["clear_frac"] or 0)
            rows.append(r)
    return rows


def _append_catalog(folder, row):
    path = os.path.join(folder, CATALOG_FILE)
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=CATALOG_FIELDS)
        if new:
            wr.writeheader()
        wr.writerow({k: row.get(k, "") for k in CATALOG_FIELDS})


def prepare_archive(folder, bounds_lonlat, sensor_key, epsg=None, res=None):
    """Создаёт архив или открывает существующий; сетка архива фиксируется при создании."""
    info = load_archive(folder)
    if info is not None:
        if info["sensor"] != sensor_key:
            raise ValueError(tr("В папке уже лежит архив другой съёмочной системы (%s). "
                             "Укажите другую папку.") % info["sensor"])
        return info, gridio.Grid.from_dict(info["grid"])
    sensor = SENSORS[sensor_key]
    lon = 0.5 * (bounds_lonlat[0] + bounds_lonlat[2])
    lat = 0.5 * (bounds_lonlat[1] + bounds_lonlat[3])
    epsg = int(epsg) if epsg else gridio.utm_epsg(lon, lat)
    res = float(res) if res else sensor["res"]
    align = sensor["align"] if abs(res - sensor["res"]) < 1e-9 else 0.0
    bounds = gridio.transform_bounds(bounds_lonlat, 4326, epsg)
    grid = gridio.grid_from_bounds(bounds, epsg, res, align)
    if grid.width * grid.height > 36e6:
        raise ValueError(tr("Участок слишком велик: %d x %d пикселей. Уменьшите охват "
                         "или разбейте его на части.") % (grid.width, grid.height))
    if not os.path.isdir(folder):
        os.makedirs(folder)
    info = {"sensor": sensor_key, "collection": sensor["collection"],
            "bounds_lonlat": [float(v) for v in bounds_lonlat], "grid": grid.to_dict(),
            "bands": list(BANDS), "scale": SCALE, "nodata": NODATA,
            "created": dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open(os.path.join(folder, ARCHIVE_FILE), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    return info, grid


def download_scenes(folder, bounds_lonlat, sensor_key="landsat", year_from=1984, year_to=2025,
                    month_from=1, month_to=12, max_cloud=80.0, min_clear=0.1,
                    instruments=None, tier1_only=True, epsg=None, res=None,
                    cloud_filters=DEFAULT_CLOUD_FILTERS, threads=6,
                    log=None, progress=None, is_canceled=None):
    """Поиск и загрузка сцен в локальный архив. Повторный запуск докачивает недостающее.

    Возвращает словарь со сводкой: число найденных, загруженных, пропущенных наблюдений.
    """
    log = log or (lambda msg: None)
    progress = progress or (lambda frac: None)
    is_canceled = is_canceled or (lambda: False)
    info, grid = prepare_archive(folder, bounds_lonlat, sensor_key, epsg, res)
    sensor = SENSORS[sensor_key]
    bbox = info["bounds_lonlat"]
    log(tr("Расчётная сетка: %s") % grid)
    cloud_px = [f / grid.res for f in cloud_filters]

    done = {r["obs_id"]: r for r in load_catalog(folder)}
    todo, found = [], 0
    for year in range(int(year_from), int(year_to) + 1):
        if is_canceled():
            raise Canceled()
        last_day = calendar.monthrange(year, int(month_to))[1]
        items = search(sensor_key, bbox, "%d-%02d-01" % (year, month_from),
                       "%d-%02d-%02d" % (year, month_to, last_day), max_cloud)
        obs = group_observations(items, sensor_key, instruments, tier1_only)
        found += len(obs)
        new = []
        for o in obs:
            prev = done.get(o["obs_id"])
            if prev is not None:
                if prev["status"] != "ok" or os.path.exists(os.path.join(folder, prev["file"])):
                    continue
            new.append(o)
        todo.extend(new)
        log(tr("%d: в каталоге сцен %d, наблюдений %d, к загрузке %d") % (year, len(items), len(obs), len(new)))
    summary = {"found": found, "todo": len(todo), "ok": 0, "cloudy": 0, "empty": 0, "error": 0,
               "grid": grid, "folder": folder}
    if not todo:
        log(tr("Все найденные наблюдения уже есть в архиве."))
        progress(1.0)
        return summary

    signer = Signer(sensor["collection"])
    signer.token()
    t0 = time.time()

    def work(o):
        if is_canceled():
            return o, "canceled", None, 0.0, ""
        try:
            status, data, frac = fetch_observation(o, sensor_key, grid, signer, min_clear, cloud_px)
            return o, status, data, frac, ""
        except Exception as exc:                      # сбой одной сцены не останавливает загрузку
            return o, "error", None, 0.0, str(exc)

    executor = ThreadPoolExecutor(max_workers=max(1, int(threads)))
    try:
        futures = [executor.submit(work, o) for o in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            if is_canceled():
                raise Canceled()
            o, status, data, frac, err = fut.result()
            if status == "canceled":
                continue
            row = {k: o[k] for k in ("obs_id", "date", "time_utc", "platform", "instrument",
                                     "path", "year")}
            row.update(cloud_cover="%.2f" % o["cloud_cover"], clear_frac="%.4f" % frac,
                       status=status, file="",
                       items=" ".join(i["id"] for i in o["items"]))
            if status == "ok":
                rel = os.path.join(str(o["year"]), o["obs_id"] + ".tif")
                gridio.write_tif(os.path.join(folder, rel), data, grid, "int16", NODATA,
                                 names=list(BANDS),
                                 tags={"obs_id": o["obs_id"], "date": o["date"],
                                       "time_utc": o["time_utc"], "platform": o["platform"],
                                       "scale": SCALE, "items": row["items"]})
                row["file"] = rel.replace("\\", "/")
            summary[status] = summary.get(status, 0) + 1
            if status == "error":
                log("  ! %s: %s" % (o["obs_id"], err))
            else:
                _append_catalog(folder, row)     # сбойные сцены в таблицу не пишутся: повтор их докачает
            if n % 20 == 0 or n == len(todo):
                rate = (time.time() - t0) / n
                log(tr("  загружено %d из %d (пригодных %d, облачных %d, сбоев %d), "
                    "осталось около %.0f мин") % (n, len(todo), summary["ok"], summary["cloudy"],
                                                 summary["error"], rate * (len(todo) - n) / 60.0))
            progress(n / float(len(todo)))
    except Canceled:
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        executor.shutdown(wait=True)
    log(tr("Загрузка завершена за %.1f мин: пригодных наблюдений %d, отброшено по облачности %d, "
        "пустых %d, сбоев %d.") % ((time.time() - t0) / 60.0, summary["ok"], summary["cloudy"],
                                 summary["empty"], summary["error"]))
    return summary
