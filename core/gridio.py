# -*- coding: utf-8 -*-
"""Расчётная сетка и чтение/запись растров средствами GDAL.

Модуль не зависит от QGIS: используются только numpy и osgeo, поэтому расчётное
ядро можно запускать и из окна программы, и из командной строки.
"""
import math
import os

import numpy as np
from osgeo import gdal, osr

gdal.UseExceptions()
osr.UseExceptions()

NP2GDAL = {
    "uint8": gdal.GDT_Byte,
    "int16": gdal.GDT_Int16,
    "uint16": gdal.GDT_UInt16,
    "int32": gdal.GDT_Int32,
    "float32": gdal.GDT_Float32,
}


class Grid(object):
    """Регулярная сетка: система координат, левый верхний угол, шаг, размер."""

    def __init__(self, epsg, x0, y1, res, width, height):
        self.epsg = int(epsg)
        self.x0 = float(x0)
        self.y1 = float(y1)
        self.res = float(res)
        self.width = int(width)
        self.height = int(height)

    @property
    def geotransform(self):
        return (self.x0, self.res, 0.0, self.y1, 0.0, -self.res)

    @property
    def bounds(self):
        """(xmin, ymin, xmax, ymax)."""
        return (self.x0, self.y1 - self.height * self.res,
                self.x0 + self.width * self.res, self.y1)

    @property
    def wkt(self):
        return srs_from_epsg(self.epsg).ExportToWkt()

    def same_as(self, other):
        return (self.epsg == other.epsg and self.width == other.width
                and self.height == other.height
                and abs(self.x0 - other.x0) < 1e-6 and abs(self.y1 - other.y1) < 1e-6
                and abs(self.res - other.res) < 1e-9)

    def xy_to_colrow(self, x, y):
        """Координаты карты -> дробные индексы пикселей (центр пикселя = целое)."""
        col = (np.asarray(x, dtype=np.float64) - self.x0) / self.res - 0.5
        row = (self.y1 - np.asarray(y, dtype=np.float64)) / self.res - 0.5
        return col, row

    def to_dict(self):
        return {"epsg": self.epsg, "x0": self.x0, "y1": self.y1, "res": self.res,
                "width": self.width, "height": self.height}

    @staticmethod
    def from_dict(d):
        return Grid(d["epsg"], d["x0"], d["y1"], d["res"], d["width"], d["height"])

    def __repr__(self):
        return "Grid(EPSG:%d, %dx%d, шаг %g м, начало %.1f/%.1f)" % (
            self.epsg, self.width, self.height, self.res, self.x0, self.y1)


def srs_from_epsg(epsg):
    s = osr.SpatialReference()
    s.ImportFromEPSG(int(epsg))
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


def utm_epsg(lon, lat):
    """Код EPSG зоны UTM (WGS 84), в которую попадает точка."""
    zone = int(math.floor((lon + 180.0) / 6.0)) % 60 + 1
    return (32600 if lat >= 0 else 32700) + zone


def transform_bounds(bounds, epsg_from, epsg_to, densify=21):
    """Пересчёт рамки между системами координат с уплотнением сторон."""
    if int(epsg_from) == int(epsg_to):
        return tuple(bounds)
    ct = osr.CoordinateTransformation(srs_from_epsg(epsg_from), srs_from_epsg(epsg_to))
    xmin, ymin, xmax, ymax = bounds
    xs, ys = [], []
    for i in range(densify):
        t = i / float(densify - 1)
        for x, y in ((xmin + t * (xmax - xmin), ymin), (xmin + t * (xmax - xmin), ymax),
                     (xmin, ymin + t * (ymax - ymin)), (xmax, ymin + t * (ymax - ymin))):
            px, py, _ = ct.TransformPoint(x, y)
            xs.append(px)
            ys.append(py)
    return (min(xs), min(ys), max(xs), max(ys))


def grid_from_bounds(bounds, epsg, res, align=0.0):
    """Сетка, накрывающая рамку; границы пикселей привязаны к кратным шагу + align.

    Для Landsat align = 15 м: именно так расположена сетка исходных сцен,
    поэтому чтение обходится без передискретизации.
    """
    xmin, ymin, xmax, ymax = bounds
    x0 = math.floor((xmin - align) / res) * res + align
    y1 = math.ceil((ymax - align) / res) * res + align
    width = int(math.ceil((xmax - x0) / res - 1e-9))
    height = int(math.ceil((y1 - ymin) / res - 1e-9))
    return Grid(epsg, x0, y1, res, max(width, 1), max(height, 1))


def grid_of(path):
    ds = gdal.Open(path)
    gt = ds.GetGeoTransform()
    srs = osr.SpatialReference(wkt=ds.GetProjection())
    srs.AutoIdentifyEPSG()
    code = srs.GetAuthorityCode(None)
    g = Grid(int(code) if code else 0, gt[0], gt[3], gt[1], ds.RasterXSize, ds.RasterYSize)
    ds = None
    return g


def read_tif(path, bands=None, rows=None):
    """Чтение каналов (нумерация с 1) в массив (n, h, w); rows = (r0, r1) — полоса строк."""
    ds = gdal.Open(path)
    if bands is None:
        bands = list(range(1, ds.RasterCount + 1))
    r0, r1 = (0, ds.RasterYSize) if rows is None else rows
    out = np.empty((len(bands), r1 - r0, ds.RasterXSize),
                   dtype=gdal_array_type(ds.GetRasterBand(bands[0]).DataType))
    for k, b in enumerate(bands):
        out[k] = ds.GetRasterBand(b).ReadAsArray(0, r0, ds.RasterXSize, r1 - r0)
    ds = None
    return out


def gdal_array_type(gdt):
    return {gdal.GDT_Byte: np.uint8, gdal.GDT_Int16: np.int16, gdal.GDT_UInt16: np.uint16,
            gdal.GDT_Int32: np.int32, gdal.GDT_Float32: np.float32,
            gdal.GDT_Float64: np.float64}.get(gdt, np.float32)


def band_names(path):
    ds = gdal.Open(path)
    names = [ds.GetRasterBand(i + 1).GetDescription() for i in range(ds.RasterCount)]
    ds = None
    return names


def create_tif(path, grid, count, dtype, nodata=None, names=None, tags=None):
    """Создаёт сжатый плиточный GeoTIFF и возвращает открытый набор данных."""
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    if os.path.exists(path):
        os.remove(path)
    opts = ["COMPRESS=DEFLATE", "TILED=YES", "BLOCKXSIZE=256", "BLOCKYSIZE=256",
            "ZLEVEL=6", "BIGTIFF=IF_SAFER"]
    opts.append("PREDICTOR=3" if dtype == "float32" else "PREDICTOR=2")
    ds = gdal.GetDriverByName("GTiff").Create(path, grid.width, grid.height, count,
                                             NP2GDAL[dtype], options=opts)
    ds.SetGeoTransform(grid.geotransform)
    ds.SetProjection(grid.wkt)
    for i in range(count):
        b = ds.GetRasterBand(i + 1)
        if nodata is not None:
            b.SetNoDataValue(float(nodata))
        if names:
            b.SetDescription(names[i])
    if tags:
        ds.SetMetadata({str(k): str(v) for k, v in tags.items()})
    return ds


def write_tif(path, data, grid, dtype, nodata=None, names=None, tags=None):
    """Запись массива (n, h, w) или (h, w) в GeoTIFF."""
    data = np.asarray(data)
    if data.ndim == 2:
        data = data[None]
    ds = create_tif(path, grid, data.shape[0], dtype, nodata, names, tags)
    for i in range(data.shape[0]):
        ds.GetRasterBand(i + 1).WriteArray(data[i].astype(dtype, copy=False))
    ds.FlushCache()
    ds = None
    return path


def mem_raster(array, grid, nodata=None):
    """Одноканальный растр в памяти (для построения изолиний и векторизации)."""
    array = np.asarray(array)
    ds = gdal.GetDriverByName("MEM").Create("", grid.width, grid.height, 1,
                                           NP2GDAL[str(array.dtype)])
    ds.SetGeoTransform(grid.geotransform)
    ds.SetProjection(grid.wkt)
    b = ds.GetRasterBand(1)
    if nodata is not None:
        b.SetNoDataValue(float(nodata))
    b.WriteArray(array)
    return ds
