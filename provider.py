# -*- coding: utf-8 -*-
"""Поставщик алгоритмов для панели инструментов анализа QGIS."""
import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider

from .algorithms import ALGORITHMS
from .core.i18n import tr

PROVIDER_ID = "coastdyn"


class CoastlineProvider(QgsProcessingProvider):

    def id(self):
        return PROVIDER_ID

    def name(self):
        return tr("Динамика береговой линии")

    def longName(self):
        return tr("Динамика береговой линии: годовые береговые линии и темпы их смещения по спутниковым снимкам")

    def icon(self):
        return QIcon(os.path.join(os.path.dirname(__file__), "icons", "icon.svg"))

    def loadAlgorithms(self):
        for alg in ALGORITHMS:
            self.addAlgorithm(alg())
