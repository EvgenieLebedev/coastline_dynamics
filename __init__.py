# -*- coding: utf-8 -*-
"""Динамика береговой линии — модуль QGIS.

Годовые положения береговой линии и темпы её смещения по многолетним рядам
снимков Landsat и Sentinel-2. Методика следует проекту Digital Earth Australia
Coastlines (Bishop-Taylor et al., 2021).
"""


def classFactory(iface):
    from .plugin import CoastlineDynamicsPlugin
    return CoastlineDynamicsPlugin(iface)
