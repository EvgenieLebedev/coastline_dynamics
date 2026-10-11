# -*- coding: utf-8 -*-
"""Выделение береговой линии с подпиксельной точностью.

Береговая линия — изолиния водного индекса на уровне порога. Положение изолинии
между центрами соседних пикселей находится линейной интерполяцией («шагающие
квадраты»), поэтому линия не привязана к границам пикселей (Bishop-Taylor et al.,
2019). В DEA Coastlines для этого служит skimage.measure.find_contours; здесь тот
же алгоритм выполняет GDAL (ContourGenerate), входящий в состав QGIS.
"""
import numpy as np
from osgeo import gdal, ogr

from . import gridio
from .masks import CERTAINTY_CLASSES
from .i18n import tr

_FILL = -9999.0


def contour_lines(array, grid, level=0.0, min_vertices=10):
    """Изолинии уровня level по растру с NaN. Возвращает список массивов координат (n, 2)."""
    data = np.where(np.isfinite(array), array, _FILL).astype(np.float32)
    ds = gridio.mem_raster(data, grid, nodata=_FILL)
    drv = ogr.GetDriverByName("Memory") or ogr.GetDriverByName("MEM")
    vds = drv.CreateDataSource("contours")
    lyr = vds.CreateLayer("contours", gridio.srs_from_epsg(grid.epsg), ogr.wkbLineString)
    lyr.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
    lyr.CreateField(ogr.FieldDefn("level", ogr.OFTReal))
    gdal.ContourGenerateEx(ds.GetRasterBand(1), lyr,
                           options=["FIXED_LEVELS=%.6f" % level, "ID_FIELD=0", "ELEV_FIELD=1",
                                    "NODATA=%.1f" % _FILL])
    lines = []
    lyr.ResetReading()
    for feat in lyr:
        geom = feat.GetGeometryRef()
        if geom is None:
            continue
        parts = [geom] if geom.GetGeometryCount() == 0 else [geom.GetGeometryRef(i)
                                                             for i in range(geom.GetGeometryCount())]
        for part in parts:
            pts = np.asarray(part.GetPoints(), dtype=np.float64)
            if pts.ndim == 2 and len(pts) >= max(2, min_vertices):
                lines.append(pts[:, :2].copy())
    return lines


def split_by_class(line, grid, classes):
    """Делит линию на участки по значению растра классов под серединами её отрезков."""
    mid = 0.5 * (line[:-1] + line[1:])
    col, row = grid.xy_to_colrow(mid[:, 0], mid[:, 1])
    col = np.clip(np.rint(col).astype(int), 0, grid.width - 1)
    row = np.clip(np.rint(row).astype(int), 0, grid.height - 1)
    cls = classes[row, col]
    out = []
    start = 0
    for i in range(1, len(cls) + 1):
        if i == len(cls) or cls[i] != cls[start]:
            out.append((int(cls[start]), line[start:i + 1]))
            start = i
    return out


def line_length(line):
    d = np.diff(line, axis=0)
    return float(np.hypot(d[:, 0], d[:, 1]).sum())


def annual_shorelines(prep, min_vertices=10, log=None, is_canceled=None):
    """Береговые линии всех лет.

    prep — результат masks.preprocess. Возвращает список записей
    {"year", "certainty", "lines" (список массивов координат), "length_m"}:
    по одной записи на каждое сочетание года и класса надёжности.
    """
    log = log or (lambda msg: None)
    is_canceled = is_canceled or (lambda: False)
    grid = prep["grid"]
    records = []
    for k, year in enumerate(prep["years"]):
        if is_canceled():
            break
        lines = contour_lines(prep["masked"][k], grid, prep["threshold"], min_vertices)
        by_class = {}
        for line in lines:
            for cls, part in split_by_class(line, grid, prep["certainty"][k]):
                by_class.setdefault(cls, []).append(part)
        total = 0.0
        for cls in sorted(by_class):
            length = sum(line_length(p) for p in by_class[cls])
            total += length
            records.append({"year": int(year), "certainty": CERTAINTY_CLASSES[cls],
                            "lines": by_class[cls], "length_m": length})
        if not lines:
            log(tr("%d: береговая линия не выделена (нет данных в прибрежной полосе).") % year)
        else:
            log(tr("%d: длина береговой линии %.1f км.") % (year, total / 1000.0))
    return records
