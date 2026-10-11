# -*- coding: utf-8 -*-
"""Подключение модуля к окну QGIS: меню, панель инструментов, поставщик алгоритмов."""
import os

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import QgsApplication

from .provider import CoastlineProvider, PROVIDER_ID
from .core.i18n import language, tr

MENU = tr("&Динамика береговой линии")
PLUGIN_DIR = os.path.dirname(__file__)

# (идентификатор алгоритма, подпись, значок, показывать ли на панели инструментов)
ACTIONS = [
    ("full_pipeline", tr("Полный расчёт (шаги 1–5)…"), "icon.svg", True),
    (None, None, None, True),
    ("download_scenes", tr("1. Загрузка снимков из каталога STAC…"), "download.svg", True),
    ("annual_composites", tr("2. Годовые композиты водного индекса…"), "composite.svg", True),
    ("index_from_rasters", tr("2а. Водный индекс по готовым годовым растрам…"), "composite.svg", False),
    ("annual_shorelines", tr("3. Годовые береговые линии…"), "shoreline.svg", True),
    ("rates_of_change", tr("4. Темпы смещения берега…"), "rates.svg", True),
    ("hotspots", tr("5. Обобщённые темпы по участкам берега…"), "hotspots.svg", True),
]


def _icon(name):
    return QIcon(os.path.join(PLUGIN_DIR, "icons", name))


class CoastlineDynamicsPlugin(object):

    def __init__(self, iface):
        self.iface = iface
        self.provider = None
        self.actions = []
        self.toolbar = None
        self.dock = None
        self.dock_action = None

    def initProcessing(self):
        self.provider = CoastlineProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        self.toolbar = self.iface.addToolBar(tr("Динамика береговой линии"))
        self.toolbar.setObjectName("CoastlineDynamicsToolbar")
        for alg_id, title, icon, on_toolbar in ACTIONS:
            if alg_id is None:
                self.toolbar.addSeparator()
                continue
            action = QAction(_icon(icon), title, self.iface.mainWindow())
            action.triggered.connect(lambda checked=False, a=alg_id: self.run_algorithm(a))
            self.iface.addPluginToMenu(MENU, action)
            if on_toolbar:
                self.toolbar.addAction(action)
            self.actions.append(action)
        self.toolbar.addSeparator()
        self.dock_action = QAction(_icon("chart.svg"), tr("График смещения берега в точке"), self.iface.mainWindow())
        self.dock_action.setCheckable(True)
        self.dock_action.triggered.connect(self.toggle_dock)
        self.iface.addPluginToMenu(MENU, self.dock_action)
        self.toolbar.addAction(self.dock_action)
        help_action = QAction(_icon("help.svg"), tr("Справка"), self.iface.mainWindow())
        help_action.triggered.connect(self.show_help)
        self.iface.addPluginToMenu(MENU, help_action)
        self.actions.append(help_action)

    def unload(self):
        for action in self.actions + ([self.dock_action] if self.dock_action else []):
            self.iface.removePluginMenu(MENU, action)
        self.actions = []
        if self.dock is not None:
            self.dock.cleanup()
            self.iface.removeDockWidget(self.dock)
            self.dock.deleteLater()
            self.dock = None
        if self.toolbar is not None:
            self.toolbar.deleteLater()
            self.toolbar = None
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None

    def run_algorithm(self, alg_id):
        try:
            import processing
        except ImportError:
            QMessageBox.warning(self.iface.mainWindow(), tr("Динамика береговой линии"),
                                tr("Не включён модуль «Processing» (Анализ данных). Включите его в "
                                "диалоге «Модули — Управление модулями» и повторите."))
            return
        processing.execAlgorithmDialog("%s:%s" % (PROVIDER_ID, alg_id), {})

    def toggle_dock(self, on):
        if self.dock is None:
            from .chart_dock import ChartDock
            self.dock = ChartDock(self.iface)
            self.iface.addDockWidget(Qt.BottomDockWidgetArea, self.dock)
            self.dock.visibilityChanged.connect(self.dock_visibility_changed)
        self.dock.setVisible(on)
        if on:
            self.dock.btn_pick.setChecked(True)

    def dock_visibility_changed(self, visible):
        """Панель закрыта (кнопкой или крестиком): снять инструмент и отметку точки с карты."""
        self.dock_action.setChecked(visible)
        if not visible and self.dock is not None:
            self.dock.btn_pick.setChecked(False)
            self.dock.toggle_tool(False)
            self.dock.clear_marker()

    def show_help(self):
        path = os.path.join(PLUGIN_DIR, "help", "index.html" if language() == "ru" else "index_en.html")
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
