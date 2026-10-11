# -*- coding: utf-8 -*-
"""Темпы смещения береговой линии.

Перенос функций points_on_line, annual_movements, change_regress,
calculate_regressions и all_time_stats из DEA Coastlines (coastlines/vector.py)
и расчёта обобщённых точек из coastlines/continental.py.

Вдоль береговой линии опорного года через равный шаг расставляются точки. Для
каждой точки и каждого года измеряется расстояние до ближайшей точки береговой
линии этого года; знак расстояния показывает, лежала ли линия мористее (+) или
ближе к суше (-) опорной. Наклон линейной регрессии расстояния по годам и есть
средний темп смещения берега, м/год: положительный — берег нарастает,
отрицательный — отступает.
"""
import warnings

import numpy as np
from osgeo import osr
from scipy import ndimage, spatial, stats

from . import gridio

OUTLIER_METHODS = ("dea", "residual", "none")
_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


# --------------------------------------------------------------------------- геометрия

def points_along(lines, spacing):
    """Точки через равный шаг вдоль каждой линии. Возвращает массив (n, 2)."""
    out = []
    for line in lines:
        seg = np.diff(line, axis=0)
        length = np.hypot(seg[:, 0], seg[:, 1])
        cum = np.concatenate([[0.0], np.cumsum(length)])
        if cum[-1] <= 0:
            continue
        at = np.arange(0.0, cum[-1], spacing)
        out.append(np.column_stack([np.interp(at, cum, line[:, 0]), np.interp(at, cum, line[:, 1])]))
    return np.vstack(out) if out else np.empty((0, 2))


class LineIndex(object):
    """Поиск ближайшей точки на наборе ломаных.

    Отрезки заранее покрываются частыми пробными точками; дерево поиска находит
    ближайшие пробные точки, после чего положение уточняется точной проекцией на
    их отрезки и на соседние с ними.
    """

    def __init__(self, lines, step=3.0):
        a, b, first, last = [], [], [], []
        n = 0
        for line in lines:
            if len(line) < 2:
                continue
            a.append(line[:-1])
            b.append(line[1:])
            m = len(line) - 1
            first.extend([n] * m)
            last.extend([n + m - 1] * m)
            n += m
        self.empty = n == 0
        if self.empty:
            return
        self.a = np.vstack(a)
        self.b = np.vstack(b)
        self.first = np.asarray(first)
        self.last = np.asarray(last)
        d = self.b - self.a
        length = np.hypot(d[:, 0], d[:, 1])
        k = np.maximum(1, np.ceil(length / step).astype(int))
        seg = np.repeat(np.arange(n), k + 1)
        offs = np.concatenate([np.arange(v + 1) / float(v) for v in k])
        self.sample_seg = seg
        self.tree = spatial.cKDTree(self.a[seg] + d[seg] * offs[:, None])

    def _project(self, pts, seg):
        a, b = self.a[seg], self.b[seg]
        d = b - a
        den = (d * d).sum(axis=1)
        t = np.where(den > 0, ((pts - a) * d).sum(axis=1) / np.where(den > 0, den, 1.0), 0.0)
        q = a + d * np.clip(t, 0.0, 1.0)[:, None]
        return q, np.hypot(q[:, 0] - pts[:, 0], q[:, 1] - pts[:, 1])

    def nearest(self, pts):
        """Ближайшие точки на линиях и расстояния до них: (n, 2), (n,)."""
        pts = np.asarray(pts, dtype=np.float64)
        if self.empty or len(pts) == 0:
            return np.full((len(pts), 2), np.nan), np.full(len(pts), np.nan)
        k = min(3, self.tree.n)
        _, idx = self.tree.query(pts, k=k)
        idx = idx.reshape(len(pts), -1)
        best_q = np.full((len(pts), 2), np.nan)
        best_d = np.full(len(pts), np.inf)
        for j in range(idx.shape[1]):
            base = self.sample_seg[idx[:, j]]
            for shift in (-1, 0, 1):
                seg = np.clip(base + shift, self.first[base], self.last[base])
                q, dist = self._project(pts, seg)
                better = dist < best_d
                best_q[better] = q[better]
                best_d[better] = dist[better]
        return best_q, best_d


def sample_bilinear(array, grid, pts):
    """Билинейная выборка растра в точках; NaN, если хотя бы один из четырёх соседей — NaN."""
    col, row = grid.xy_to_colrow(pts[:, 0], pts[:, 1])
    filled = np.where(np.isfinite(array), array, 0.0)
    val = ndimage.map_coordinates(filled, [row, col], order=1, mode="nearest")
    bad = ndimage.map_coordinates((~np.isfinite(array)).astype(np.float32), [row, col],
                                  order=1, mode="nearest")
    outside = (col < -0.5) | (row < -0.5) | (col > grid.width - 0.5) | (row > grid.height - 0.5)
    val = val.astype(np.float64)
    val[(bad > 1e-6) | outside | ~np.isfinite(col)] = np.nan
    return val


def to_lonlat(pts, epsg):
    ct = osr.CoordinateTransformation(gridio.srs_from_epsg(epsg), gridio.srs_from_epsg(4326))
    if len(pts) == 0:
        return np.empty((0, 2))
    out = np.asarray(ct.TransformPoints(np.asarray(pts, dtype=np.float64).tolist()))
    return out[:, :2]


def bearings(lonlat1, lonlat2):
    """Азимут с первой точки на вторую, градусы (сферическая формула)."""
    lon1, lat1 = np.radians(lonlat1[:, 0]), np.radians(lonlat1[:, 1])
    lon2, lat2 = np.radians(lonlat2[:, 0]), np.radians(lonlat2[:, 1])
    dlon = lon2 - lon1
    x = np.sin(dlon) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    return np.degrees(np.arctan2(x, y)) % 360.0


def axial_mean_std(angles):
    """Круговое среднее и стандартное отклонение осевых данных (период 180°) по строкам, без NaN."""
    ang = np.radians(angles * 2.0)
    ok = np.isfinite(ang)
    n = np.maximum(ok.sum(axis=1), 1)
    s = np.where(ok, np.sin(ang), 0.0).sum(axis=1) / n
    c = np.where(ok, np.cos(ang), 0.0).sum(axis=1) / n
    mean = (np.degrees(np.arctan2(s, c)) % 360.0) / 2.0
    r = np.clip(np.hypot(s, c), 1e-12, 1.0)
    std = np.degrees(np.sqrt(-2.0 * np.log(r))) / 2.0
    none = ok.sum(axis=1) == 0
    mean[none] = np.nan
    std[none] = np.nan
    return mean, std


def geohash(lon, lat, precision=10):
    """Геохеш точки: короткий идентификатор, однозначно связанный с координатами."""
    lat_rng, lon_rng = [-90.0, 90.0], [-180.0, 180.0]
    out, bit, ch, even = [], 0, 0, True
    while len(out) < precision:
        rng, val = (lon_rng, lon) if even else (lat_rng, lat)
        mid = 0.5 * (rng[0] + rng[1])
        if val >= mid:
            ch = (ch << 1) | 1
            rng[0] = mid
        else:
            ch <<= 1
            rng[1] = mid
        even = not even
        bit += 1
        if bit == 5:
            out.append(_BASE32[ch])
            bit, ch = 0, 0
    return "".join(out)


# ---------------------------------------------------------------------------- регрессия

def outlier_mad(points, thresh=3.5):
    """Выбросы по медианному абсолютному отклонению (Iglewicz, Hoaglin, 1993)."""
    points = np.asarray(points, dtype=np.float64)
    if points.ndim == 1:
        points = points[:, None]
    diff = np.sqrt(((points - np.median(points, axis=0)) ** 2).sum(axis=-1))
    mad = np.median(diff)
    if not mad > 0:
        return np.zeros(len(points), dtype=bool)
    return 0.6745 * diff / mad > thresh


def change_regress(y_vals, x_vals, threshold=3.5, method="dea"):
    """Линейная регрессия расстояний по годам с предварительным исключением выбросов.

    method: "dea" — как в DEA Coastlines, отклонение пары «год — расстояние» от
    медианной пары; "residual" — отклонение от прямой Тейла — Сена; "none" — без исключения.
    Возвращает (наклон, свободный член, p-значение, стандартная ошибка наклона, годы-выбросы,
    логическая маска использованных наблюдений).
    """
    x = np.asarray(x_vals, dtype=np.float64)
    y = np.asarray(y_vals, dtype=np.float64)
    valid = np.isfinite(y)
    used = valid.copy()
    if valid.sum() >= 3 and method != "none":
        xv, yv = x[valid], y[valid]
        if method == "residual":
            slope, intercept = stats.theilslopes(yv, xv)[:2]
            out = outlier_mad(yv - (slope * xv + intercept), threshold)
        else:
            out = outlier_mad(np.column_stack([xv, yv]), threshold)
        used[np.flatnonzero(valid)[out]] = False
    excluded = [int(v) for v in x[~used]]
    if used.sum() < 3 or np.ptp(x[used]) == 0:
        return np.nan, np.nan, np.nan, np.nan, excluded, used
    res = stats.linregress(x[used], y[used])
    return res.slope, res.intercept, res.pvalue, res.stderr, excluded, used


# ------------------------------------------------------------------------------ расчёт

def rates_of_change(shorelines, prep, baseline_year=None, spacing=30.0, max_valid_dist=1200.0,
                    outlier_method="dea", extreme_rate=50.0, max_angle_std=30.0,
                    min_valid_share=0.75, log=None, is_canceled=None):
    """Точки темпов смещения берега.

    shorelines — записи contours.annual_shorelines; prep — результат masks.preprocess.
    Возвращает (годы, список словарей с полями точек и ключом "xy").
    """
    log = log or (lambda msg: None)
    is_canceled = is_canceled or (lambda: False)
    grid = prep["grid"]
    by_year = {}
    for rec in shorelines:
        by_year.setdefault(rec["year"], []).extend(rec["lines"])
    years = sorted(by_year)
    if len(years) < 3:
        raise ValueError("Для оценки темпов нужны береговые линии хотя бы за три года.")
    if baseline_year is None or baseline_year not in by_year:
        if baseline_year is not None:
            log("Опорного года %s нет среди береговых линий; взят последний год ряда." % baseline_year)
        baseline_year = years[-1]
    pts = points_along(by_year[baseline_year], spacing)
    if len(pts) == 0:
        raise ValueError("Береговая линия опорного года пуста.")
    log("Опорный год %d, точек через %.0f м: %d." % (baseline_year, spacing, len(pts)))

    year_pos = {y: k for k, y in enumerate(prep["years"])}
    base_arr = prep["combined"][year_pos[baseline_year]]
    lonlat = to_lonlat(pts, grid.epsg)
    dist = np.full((len(pts), len(years)), np.nan)
    bear = np.full((len(pts), len(years)), np.nan)
    for j, y in enumerate(years):
        if is_canceled():
            return years, []
        if y == baseline_year:
            dist[:, j] = 0.0
            continue
        near, d = LineIndex(by_year[y]).nearest(pts)
        d = np.where(d < max_valid_dist, d, np.nan)
        ok = np.isfinite(d)
        if not ok.any():
            continue
        index_comp_p1 = sample_bilinear(prep["combined"][year_pos[y]], grid, pts[ok])
        index_base_p2 = sample_bilinear(base_arr, grid, near[ok])
        sign = np.where(index_base_p2 > index_comp_p1, 1.0, -1.0)
        sign[~(np.isfinite(index_base_p2) & np.isfinite(index_comp_p1))] = np.nan
        dist[ok, j] = d[ok] * sign
        moved = ok.copy()
        moved[ok] = d[ok] > 0.01
        if moved.any():
            bear[moved, j] = bearings(lonlat[moved], to_lonlat(near[moved], grid.epsg)) % 180.0
    angle_mean, angle_std = axial_mean_std(bear)

    xs = np.asarray(years, dtype=np.float64)
    min_valid = int(len(years) * min_valid_share)
    out = []
    for i in range(len(pts)):
        slope, intercept, pvalue, stderr, excluded, used = change_regress(
            dist[i], xs, method=outlier_method)
        rec = {"xy": (float(pts[i, 0]), float(pts[i, 1])),
               "uid": geohash(lonlat[i, 0], lonlat[i, 1], 10),
               "rate_time": _round(slope, 3), "sig_time": _round(pvalue, 3),
               "se_time": _round(stderr, 3),
               "outl_time": " ".join(str(v) for v in excluded)}
        for j, y in enumerate(years):
            rec["dist_%d" % y] = _round(dist[i, j], 2)
        rec["angle_mean"] = None if not np.isfinite(angle_mean[i]) else int(round(angle_mean[i]))
        rec["angle_std"] = None if not np.isfinite(angle_std[i]) else int(round(angle_std[i]))
        if used.any():
            yv, dv = xs[used], dist[i][used]
            rec["valid_obs"] = int(used.sum())
            rec["valid_span"] = int(yv[-1] - yv[0] + 1)
            rec["sce"] = _round(dv.max() - dv.min(), 2)
            rec["nsm"] = _round(dv[-1] - dv[0], 2)
            rec["max_year"] = int(yv[np.argmax(dv)])
            rec["min_year"] = int(yv[np.argmin(dv)])
        else:
            rec.update(valid_obs=0, valid_span=0, sce=None, nsm=None, max_year=None, min_year=None)
        cert = "good"
        if baseline_year in excluded:
            cert = "baseline outlier"
        if rec["rate_time"] is not None and abs(rec["rate_time"]) > extreme_rate:
            cert = "extreme value (> %g m)" % extreme_rate
        if rec["angle_std"] is not None and rec["angle_std"] > max_angle_std:
            cert = "high angular variability"
        if rec["valid_obs"] < min_valid:
            cert = "insufficient observations"
        rec["certainty"] = cert
        out.append(rec)
    good = sum(1 for r in out if r["certainty"] == "good")
    log("Рассчитаны темпы в %d точках; надёжных (certainty = good): %d." % (len(out), good))
    return years, out


def hotspots(points, years, baseline_lines, epsg, radius=1000.0, spacing=30.0,
             outlier_method="dea", log=None):
    """Обобщённые точки: медиана годовых смещений надёжных точек в круге заданного радиуса.

    Точки ставятся вдоль опорной береговой линии через половину радиуса.
    """
    log = log or (lambda msg: None)
    centres = points_along(baseline_lines, radius / 2.0)
    good = [p for p in points if p["certainty"] == "good"]
    if len(centres) == 0:
        return []
    lonlat = to_lonlat(centres, epsg)
    xs = np.asarray(years, dtype=np.float64)
    out = []
    tree = spatial.cKDTree(np.array([p["xy"] for p in good])) if good else None
    dist = np.array([[np.nan if p["dist_%d" % y] is None else p["dist_%d" % y] for y in years]
                     for p in good], dtype=np.float64) if good else np.empty((0, len(years)))
    min_n = radius / spacing
    for i, c in enumerate(centres):
        ids = tree.query_ball_point(c, radius) if tree is not None else []
        rec = {"xy": (float(c[0]), float(c[1])), "uid": geohash(lonlat[i, 0], lonlat[i, 1], 11),
               "radius_m": int(radius), "n": len(ids)}
        if ids:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")          # год без единого расстояния даёт NaN
                med = np.nanmedian(dist[ids], axis=0)
            slope, _, pvalue, stderr, excluded, _ = change_regress(med, xs, method=outlier_method)
        else:
            med = np.full(len(years), np.nan)
            slope = pvalue = stderr = np.nan
            excluded = []
        rec.update(rate_time=_round(slope, 3), sig_time=_round(pvalue, 3), se_time=_round(stderr, 3),
                   outl_time=" ".join(str(v) for v in excluded))
        for j, y in enumerate(years):
            rec["dist_%d" % y] = _round(med[j], 2)
        rec["certainty"] = "good" if len(ids) >= min_n else "insufficient points"
        out.append(rec)
    log("Обобщённых точек радиуса %.0f м: %d." % (radius, len(out)))
    return out


def _round(value, digits):
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), digits)
