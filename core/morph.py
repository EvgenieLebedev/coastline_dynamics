# -*- coding: utf-8 -*-
"""Морфологические операции над булевыми растрами.

Расширение и сжатие кругом радиуса r выполняются через евклидово
преобразование расстояний: результат совпадает с применением круглого
структурного элемента, но время счёта не зависит от радиуса.
За границей растра расширение ничего не добавляет, а сжатие ничего не
снимает (так же ведёт себя scikit-image, применяемый в DEA Coastlines).
"""
import numpy as np
from scipy import ndimage


def dilate(mask, r):
    mask = np.asarray(mask, dtype=bool)
    if r <= 0 or not mask.any():
        return mask.copy()
    return ndimage.distance_transform_edt(~mask) <= r


def erode(mask, r):
    mask = np.asarray(mask, dtype=bool)
    if r <= 0 or mask.all():
        return mask.copy()
    return ndimage.distance_transform_edt(mask) > r


def closing(mask, r):
    return erode(dilate(mask, r), r)


def opening(mask, r):
    return dilate(erode(mask, r), r)


def black_tophat(mask, r):
    """Замыкание минус исходное: узкие «тёмные» (ложные) детали внутри истинной области."""
    mask = np.asarray(mask, dtype=bool)
    return closing(mask, r) & ~mask


def label(mask, connectivity=1):
    """Связные области: connectivity = 1 — по сторонам, 2 — по сторонам и углам."""
    structure = ndimage.generate_binary_structure(2, connectivity)
    return ndimage.label(np.asarray(mask, dtype=bool), structure=structure)


def sieve(mask, min_size, connectivity=1):
    """Области обоих значений мельче min_size пикселей получают значение окружения.

    Соответствует rasterio.features.sieve для булева растра: сначала снимаются
    мелкие истинные пятна, затем заливаются мелкие ложные.
    """
    mask = np.asarray(mask, dtype=bool).copy()
    if min_size <= 1:
        return mask
    for value in (True, False):
        lab, n = label(mask == value, connectivity)
        if n == 0:
            continue
        sizes = np.bincount(lab.ravel())
        small = sizes < min_size
        small[0] = False
        mask[small[lab]] = not value
    return mask


def mask_cleanup(mask, filters):
    """Последовательность операций над маской: [("closing", r), ("opening", r), ("dilation", r)]."""
    ops = {"closing": closing, "opening": opening, "dilation": dilate, "erosion": erode}
    out = np.asarray(mask, dtype=bool)
    for name, radius in filters:
        if radius and radius > 0:
            out = ops[name](out, radius)
    return out
