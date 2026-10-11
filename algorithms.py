# -*- coding: utf-8 -*-
"""Алгоритмы панели инструментов анализа QGIS.

Каждый алгоритм — тонкая оболочка над расчётным ядром (пакет core): разбирает
параметры диалога, вызывает ядро, записывает результат и назначает оформление.
"""
import datetime
import os
import re

import numpy as np
from qgis.PyQt.QtCore import QUrl, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    NULL, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsFeatureSink, QgsField,
    QgsFields, QgsGeometry, QgsPointXY, QgsProcessing, QgsProcessingAlgorithm,
    QgsProcessingContext, QgsProcessingException, QgsProcessingMultiStepFeedback,
    QgsProcessingOutputFolder, QgsProcessingOutputNumber, QgsProcessingOutputString,
    QgsProcessingParameterBoolean, QgsProcessingParameterCrs, QgsProcessingParameterDefinition,
    QgsProcessingParameterEnum, QgsProcessingParameterExtent, QgsProcessingParameterFeatureSink,
    QgsProcessingParameterFeatureSource, QgsProcessingParameterField, QgsProcessingParameterFile,
    QgsProcessingParameterFolderDestination, QgsProcessingParameterMultipleLayers,
    QgsProcessingParameterNumber, QgsProcessingParameterRasterDestination,
    QgsProcessingParameterString, QgsWkbTypes,
)

from .core import composites, contours, gridio, masks, rates, stac
from .core.sensors import SENSORS
from .styling import StylePostProcessor
from .core.i18n import tr

PLUGIN_DIR = os.path.dirname(__file__)
SENSOR_KEYS = ["landsat", "sentinel2"]
INDEX_KEYS = ["mndwi", "ndwi"]
INSTRUMENTS = ["TM", "ETM+", "OLI"]
OUTLIER_TITLES = [tr("Как в DEA Coastlines (отклонение пары «год — расстояние»)"),
                  tr("По остаткам тренда (прямая Тейла — Сена)"), tr("Не исключать")]
METHOD_NOTE = (tr("<p>Методика: Bishop-Taylor R. et al. Mapping Australia's dynamic coastline at mean "
               "sea level using three decades of Landsat imagery // Remote Sensing of Environment. "
               "2021. Vol. 267. 112734.</p>"))


def _callbacks(feedback):
    return {"log": feedback.pushInfo,
            "progress": lambda frac: feedback.setProgress(100.0 * frac),
            "is_canceled": feedback.isCanceled}


def _advanced(param):
    param.setFlags(param.flags() | QgsProcessingParameterDefinition.FlagAdvanced)
    return param


def _field_types():
    """Типы полей: в QGIS 3.38 и новее конструктор QgsField принимает QMetaType, раньше — QVariant."""
    try:
        from qgis.PyQt.QtCore import QMetaType
        kinds = {QVariant.Int: QMetaType.Type.Int, QVariant.Double: QMetaType.Type.Double,
                 QVariant.String: QMetaType.Type.QString}
        QgsField("probe", kinds[QVariant.Int])
        return kinds
    except Exception:
        return {QVariant.Int: QVariant.Int, QVariant.Double: QVariant.Double,
                QVariant.String: QVariant.String}


_KINDS = _field_types()


def _fields(spec):
    fields = QgsFields()
    for name, kind in spec:
        fields.append(QgsField(name, _KINDS[kind]))
    return fields


def _load_on_completion(context, source, name, kind):
    details = QgsProcessingContext.LayerDetails(name, context.project(), name)
    details.forceName = True              # понятное имя слоя вместо имени файла
    details.setPostProcessor(StylePostProcessor.create(kind))
    context.addLayerToLoadOnCompletion(source, details)


def _style_output(context, dest_id, kind, name=None):
    if context.willLoadLayerOnCompletion(dest_id):
        details = context.layerToLoadOnCompletionDetails(dest_id)
        if name:
            details.name = name
            details.forceName = True
        details.setPostProcessor(StylePostProcessor.create(kind))


def _geoms_wkb(source, epsg, context):
    """Геометрии слоя в системе координат расчётной сетки (WKB)."""
    if source is None:
        return None
    xform = QgsCoordinateTransform(source.sourceCrs(), QgsCoordinateReferenceSystem("EPSG:%d" % epsg),
                                   context.transformContext())
    out = []
    for feat in source.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            continue
        geom.transform(xform)
        out.append(bytes(geom.asWkb()))
    return out or None


def _run(func, *args, **kwargs):
    """Вызов ядра с переводом его ошибок в сообщения панели анализа."""
    try:
        return func(*args, **kwargs)
    except stac.Canceled:
        raise QgsProcessingException(tr("Расчёт остановлен пользователем."))
    except (ValueError, RuntimeError) as exc:
        raise QgsProcessingException(str(exc))


# Число знаков после запятой в полях ввода дробных параметров
DECIMALS = {"MAX_CLOUD": 0, "MIN_CLEAR": 0, "LEVEL_FRACTION": 2, "LEVEL_CENTRE": 2, "THRESHOLD": 2,
            "BUFFER": 0, "STDEV_THRESHOLD": 2, "SPACING": 0, "MAX_DIST": 0, "RADIUS": 0, "SCALE": 6}


class _Base(QgsProcessingAlgorithm):
    ICON = "icon.svg"

    def createInstance(self):
        return self.__class__()

    def addParameter(self, param, *args, **kwargs):
        if isinstance(param, QgsProcessingParameterNumber) and param.name() in DECIMALS:
            param.setMetadata({"widget_wrapper": {"decimals": DECIMALS[param.name()]}})
        return super().addParameter(param, *args, **kwargs)

    def icon(self):
        return QIcon(os.path.join(PLUGIN_DIR, "icons", self.ICON))

    def helpUrl(self):
        return QUrl.fromLocalFile(os.path.join(PLUGIN_DIR, "help", "index.html")).toString()


# =============================================================================== шаг 1

class DownloadScenes(_Base):
    EXTENT, SENSOR, YEAR_FROM, YEAR_TO = "EXTENT", "SENSOR", "YEAR_FROM", "YEAR_TO"
    MONTH_FROM, MONTH_TO, MAX_CLOUD, MIN_CLEAR = "MONTH_FROM", "MONTH_TO", "MAX_CLOUD", "MIN_CLEAR"
    INSTRUMENTS, TIER1, CLOUD_FILTERS, THREADS, CRS = "INSTRUMENTS", "TIER1", "CLOUD_FILTERS", "THREADS", "CRS"
    OUTPUT, N_OK = "OUTPUT_FOLDER", "N_OK"
    ICON = "download.svg"

    def name(self):
        return "download_scenes"

    def displayName(self):
        return tr("1. Загрузка снимков из каталога STAC")

    def shortHelpString(self):
        return (tr("<p>Находит в каталоге Microsoft Planetary Computer все сцены Landsat или Sentinel-2 "
                "на участок за заданные годы и месяцы и сохраняет вырезки по участку в локальный "
                "архив. Сцены целиком не скачиваются: по сети читаются только нужные фрагменты.</p>"
                "<p>В архив попадают три канала отражения (зелёный, ближний ИК, средний ИК); облака, "
                "тени и снег замаскированы. На каждый день съёмки создаётся один файл; сведения о "
                "сценах записываются в таблицу <i>scenes.csv</i>.</p>"
                "<p><b>Повторный запуск с той же папкой докачивает недостающее</b>: уже загруженные "
                "сцены пропускаются, поэтому ряд можно продлевать год за годом.</p>"
                "<p><b>Месяцы.</b> Для замерзающих морей следует ограничиться безлёдным сезоном "
                "(например, с апреля по октябрь): лёд и снег искажают водный индекс.</p>"
                "<p>Регистрация в каталоге не требуется, нужен доступ в интернет.</p>"))

    def initAlgorithm(self, config=None):
        year = datetime.date.today().year
        self.addParameter(QgsProcessingParameterExtent(self.EXTENT, tr("Участок (охват)")))
        self.addParameter(QgsProcessingParameterEnum(
            self.SENSOR, tr("Съёмочная система"), [SENSORS[k]["title"] for k in SENSOR_KEYS], defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.YEAR_FROM, tr("Первый год"), QgsProcessingParameterNumber.Integer, 1984, minValue=1982, maxValue=year))
        self.addParameter(QgsProcessingParameterNumber(
            self.YEAR_TO, tr("Последний год"), QgsProcessingParameterNumber.Integer, year - 1, minValue=1982, maxValue=year))
        self.addParameter(QgsProcessingParameterNumber(
            self.MONTH_FROM, tr("Первый месяц сезона"), QgsProcessingParameterNumber.Integer, 1, minValue=1, maxValue=12))
        self.addParameter(QgsProcessingParameterNumber(
            self.MONTH_TO, tr("Последний месяц сезона"), QgsProcessingParameterNumber.Integer, 12, minValue=1, maxValue=12))
        self.addParameter(QgsProcessingParameterNumber(
            self.MAX_CLOUD, tr("Наибольшая облачность сцены по каталогу, %"),
            QgsProcessingParameterNumber.Double, 80.0, minValue=1, maxValue=100))
        self.addParameter(QgsProcessingParameterNumber(
            self.MIN_CLEAR, tr("Наименьшая доля ясных пикселей на участке, %"),
            QgsProcessingParameterNumber.Double, 10.0, minValue=0, maxValue=100))
        self.addParameter(_advanced(QgsProcessingParameterEnum(
            self.INSTRUMENTS, tr("Приборы Landsat"), ["TM (Landsat 4–5)", "ETM+ (Landsat 7)", "OLI (Landsat 8–9)"],
            allowMultiple=True, defaultValue=[0, 1, 2])))
        self.addParameter(_advanced(QgsProcessingParameterBoolean(
            self.TIER1, tr("Только сцены высшей категории геометрической точности (Tier 1)"), True)))
        self.addParameter(_advanced(QgsProcessingParameterString(
            self.CLOUD_FILTERS, tr("Очистка маски облаков: замыкание, размыкание, расширение, м"),
            "60,300,150")))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.THREADS, tr("Число одновременных загрузок"), QgsProcessingParameterNumber.Integer, 6,
            minValue=1, maxValue=16)))
        self.addParameter(_advanced(QgsProcessingParameterCrs(
            self.CRS, tr("Система координат архива (по умолчанию — зона UTM участка)"), optional=True)))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT, tr("Папка архива сцен")))
        self.addOutput(QgsProcessingOutputNumber(self.N_OK, tr("Число загруженных наблюдений")))

    def processAlgorithm(self, parameters, context, feedback):
        rect = self.parameterAsExtent(parameters, self.EXTENT, context,
                                      QgsCoordinateReferenceSystem("EPSG:4326"))
        if rect.isEmpty():
            raise QgsProcessingException(tr("Не задан участок."))
        bounds = (rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum())
        sensor = SENSOR_KEYS[self.parameterAsEnum(parameters, self.SENSOR, context)]
        m0 = self.parameterAsInt(parameters, self.MONTH_FROM, context)
        m1 = self.parameterAsInt(parameters, self.MONTH_TO, context)
        if m0 > m1:
            raise QgsProcessingException(tr("Первый месяц сезона должен быть не позже последнего."))
        try:
            filters = [float(v) for v in self.parameterAsString(parameters, self.CLOUD_FILTERS, context)
                       .replace(";", ",").split(",")]
            assert len(filters) == 3
        except (ValueError, AssertionError):
            raise QgsProcessingException(tr("Очистка маски облаков задаётся тремя числами через запятую, например 60,300,150."))
        instruments = None
        if sensor == "landsat":
            instruments = [INSTRUMENTS[i] for i in self.parameterAsEnums(parameters, self.INSTRUMENTS, context)]
        crs = self.parameterAsCrs(parameters, self.CRS, context)
        epsg = None
        if crs.isValid():
            if crs.isGeographic() or not crs.authid().startswith("EPSG:"):
                raise QgsProcessingException(tr("Система координат архива должна быть прямоугольной (в метрах) и иметь код EPSG."))
            epsg = int(crs.authid().split(":")[1])
        folder = self.parameterAsString(parameters, self.OUTPUT, context)
        summary = _run(stac.download_scenes, folder, bounds, sensor,
                       self.parameterAsInt(parameters, self.YEAR_FROM, context),
                       self.parameterAsInt(parameters, self.YEAR_TO, context), m0, m1,
                       max_cloud=self.parameterAsDouble(parameters, self.MAX_CLOUD, context),
                       min_clear=self.parameterAsDouble(parameters, self.MIN_CLEAR, context) / 100.0,
                       instruments=instruments,
                       tier1_only=self.parameterAsBool(parameters, self.TIER1, context),
                       epsg=epsg, cloud_filters=filters,
                       threads=self.parameterAsInt(parameters, self.THREADS, context),
                       **_callbacks(feedback))
        total = sum(1 for r in stac.load_catalog(folder) if r["status"] == "ok")
        feedback.pushInfo(tr("Всего пригодных наблюдений в архиве: %d.") % total)
        return {self.OUTPUT: folder, self.N_OK: total}


# =============================================================================== шаг 2

class AnnualComposites(_Base):
    ARCHIVE, INDEX, YEAR_FROM, YEAR_TO = "ARCHIVE", "INDEX", "YEAR_FROM", "YEAR_TO"
    MONTH_FROM, MONTH_TO, GAPFILL, RGB = "MONTH_FROM", "MONTH_TO", "GAPFILL", "RGB"
    LEVELS, LEVEL_FRACTION, LEVEL_CENTRE, LEVEL_MODE = "LEVELS", "LEVEL_FRACTION", "LEVEL_CENTRE", "LEVEL_MODE"
    MEMORY, LOAD, OUTPUT = "MEMORY", "LOAD", "OUTPUT_FOLDER"
    ICON = "composite.svg"

    def name(self):
        return "annual_composites"

    def displayName(self):
        return tr("2. Годовые композиты водного индекса")

    def shortHelpString(self):
        return (tr("<p>По каждой сцене архива вычисляет водный индекс, затем для каждого года находит "
                "попиксельную <b>медиану</b> индекса, его стандартное отклонение и число наблюдений. "
                "Медиана за год подавляет случайные помехи отдельных снимков: остатки облаков, "
                "волнение, сгонно-нагонные колебания уровня.</p>"
                "<p>Для лет с малым числом снимков дополнительно строится <b>трёхлетний композит</b> "
                "(по году и двум соседним): им на следующем шаге заменяются пиксели, где наблюдений меньше шести.</p>"
                "<p><b>Отбор по уровню моря</b> (необязательно). В приливных морях положение уреза "
                "зависит от фазы прилива. Если задать таблицу уровня (CSV: дата и время UTC; уровень), "
                "в расчёт войдут только снимки, сделанные при уровне, близком к среднему: по "
                "умолчанию — средняя половина размаха, как в DEA Coastlines. Для бесприливных морей "
                "со сгонами и нагонами вместо уровня можно подать ветровой показатель и выбрать в "
                "дополнительных параметрах отбор по доле наблюдений.</p>"
                "<p>Результат — папка с файлами <i>mndwi_ГГГГ.tif</i> (каналы: индекс, стандартное "
                "отклонение, число наблюдений), <i>mndwi_ГГГГ_gapfill.tif</i> и <i>rgb_ГГГГ.tif</i> "
                "(цветосинтез для просмотра).</p>") + METHOD_NOTE)

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(
            self.ARCHIVE, tr("Папка архива сцен (результат шага 1)"), QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterEnum(
            self.INDEX, tr("Водный индекс"), [composites.INDEX_TITLES[k] for k in INDEX_KEYS], defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.YEAR_FROM, tr("Первый год (пусто — с начала архива)"), QgsProcessingParameterNumber.Integer,
            optional=True, minValue=1982))
        self.addParameter(QgsProcessingParameterNumber(
            self.YEAR_TO, tr("Последний год (пусто — до конца архива)"), QgsProcessingParameterNumber.Integer,
            optional=True, minValue=1982))
        self.addParameter(QgsProcessingParameterNumber(
            self.MONTH_FROM, tr("Первый месяц сезона"), QgsProcessingParameterNumber.Integer, 1, minValue=1, maxValue=12))
        self.addParameter(QgsProcessingParameterNumber(
            self.MONTH_TO, tr("Последний месяц сезона"), QgsProcessingParameterNumber.Integer, 12, minValue=1, maxValue=12))
        self.addParameter(QgsProcessingParameterBoolean(self.GAPFILL, tr("Строить трёхлетние композиты"), True))
        self.addParameter(QgsProcessingParameterBoolean(self.RGB, tr("Сохранять цветосинтез для просмотра"), True))
        self.addParameter(QgsProcessingParameterFile(
            self.LEVELS, tr("Таблица уровня моря для отбора снимков (CSV)"), optional=True,
            fileFilter=tr("Таблицы CSV (*.csv *.txt)")))
        self.addParameter(_advanced(QgsProcessingParameterEnum(
            self.LEVEL_MODE, tr("Правило отбора по уровню"),
            [tr("По размаху уровня (как в DEA Coastlines; для приливов)"),
             tr("По доле наблюдений, ближайших к центру (для сгонов и нагонов)")], defaultValue=0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.LEVEL_FRACTION, tr("Доля размаха (или доля наблюдений), остающаяся в расчёте"),
            QgsProcessingParameterNumber.Double, 0.5, minValue=0.05, maxValue=1.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.LEVEL_CENTRE, tr("Центральный уровень (пусто — средний по ряду)"),
            QgsProcessingParameterNumber.Double, optional=True)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.MEMORY, tr("Объём оперативной памяти на расчёт, МБ"), QgsProcessingParameterNumber.Integer,
            512, minValue=64, maxValue=16000)))
        self.addParameter(QgsProcessingParameterEnum(
            self.LOAD, tr("Добавить в проект"), [tr("Композиты последнего года"), tr("Композиты всех лет"), tr("Ничего")],
            defaultValue=0))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT, tr("Папка композитов")))

    def processAlgorithm(self, parameters, context, feedback):
        archive = self.parameterAsString(parameters, self.ARCHIVE, context)
        index = INDEX_KEYS[self.parameterAsEnum(parameters, self.INDEX, context)]
        out_dir = self.parameterAsString(parameters, self.OUTPUT, context)
        y0 = self.parameterAsInt(parameters, self.YEAR_FROM, context) if parameters.get(self.YEAR_FROM) is not None else None
        y1 = self.parameterAsInt(parameters, self.YEAR_TO, context) if parameters.get(self.YEAR_TO) is not None else None
        centre = self.parameterAsDouble(parameters, self.LEVEL_CENTRE, context) \
            if parameters.get(self.LEVEL_CENTRE) is not None else None
        meta = _run(composites.build_composites, archive, out_dir, index, y0, y1,
                    self.parameterAsInt(parameters, self.MONTH_FROM, context),
                    self.parameterAsInt(parameters, self.MONTH_TO, context),
                    gapfill=self.parameterAsBool(parameters, self.GAPFILL, context),
                    rgb=self.parameterAsBool(parameters, self.RGB, context),
                    levels_path=self.parameterAsString(parameters, self.LEVELS, context) or None,
                    level_fraction=self.parameterAsDouble(parameters, self.LEVEL_FRACTION, context),
                    level_centre=centre,
                    level_mode=("range", "share")[self.parameterAsEnum(parameters, self.LEVEL_MODE, context)],
                    memory_mb=self.parameterAsInt(parameters, self.MEMORY, context),
                    **_callbacks(feedback))
        load = self.parameterAsEnum(parameters, self.LOAD, context)
        years = meta["years"] if load == 1 else ([meta["years"][-1]] if load == 0 else [])
        for y in years:
            if meta["rgb"]:
                _load_on_completion(context, composites.rgb_path(out_dir, y), tr("Цветосинтез %d") % y, "rgb")
            _load_on_completion(context, composites.composite_path(out_dir, index, y),
                                "%s %d" % (index.upper(), y), "index")
        return {self.OUTPUT: out_dir}


class IndexFromRasters(_Base):
    INPUT, YEAR_REGEX, BAND_A, BAND_B, SCALE, INDEX, OUTPUT = (
        "INPUT", "YEAR_REGEX", "BAND_GREEN", "BAND_IR", "SCALE", "INDEX", "OUTPUT_FOLDER")
    ICON = "composite.svg"

    def name(self):
        return "index_from_rasters"

    def displayName(self):
        return tr("2а. Водный индекс по готовым годовым растрам")

    def shortHelpString(self):
        return (tr("<p>Замена шагов 1 и 2 для случая, когда годовые безоблачные композиты отражения "
                "уже есть (по одному многоканальному растру на год в общей сетке). Алгоритм "
                "вычисляет водный индекс и раскладывает файлы так, как их ожидает шаг 3.</p>"
                "<p>Год берётся из имени файла. Номера каналов зелёного и инфракрасного диапазонов "
                "зависят от состава растра: для шести каналов Landsat в порядке «синий, зелёный, "
                "красный, ближний ИК, средний ИК 1, средний ИК 2» это 2 и 5 (MNDWI) либо 2 и 4 (NDWI).</p>"
                "<p><b>Ограничение.</b> По готовой медиане нельзя восстановить число наблюдений и "
                "разброс индекса, поэтому проверки надёжности («мало наблюдений», «неустойчивый "
                "индекс») на таких данных не срабатывают.</p>"))

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterMultipleLayers(
            self.INPUT, tr("Годовые растры отражения"), QgsProcessing.TypeRaster))
        self.addParameter(QgsProcessingParameterString(
            self.YEAR_REGEX, tr("Шаблон года в имени файла (регулярное выражение)"), r"(19|20)\d{2}"))
        self.addParameter(QgsProcessingParameterNumber(
            self.BAND_A, tr("Номер зелёного канала"), QgsProcessingParameterNumber.Integer, 2, minValue=1))
        self.addParameter(QgsProcessingParameterNumber(
            self.BAND_B, tr("Номер инфракрасного канала"), QgsProcessingParameterNumber.Integer, 5, minValue=1))
        scale = QgsProcessingParameterNumber(
            self.SCALE, tr("Множитель перевода значений в отражение"), QgsProcessingParameterNumber.Double,
            0.0001, minValue=0.0)
        scale.setMetadata({"widget_wrapper": {"decimals": 6}})
        self.addParameter(scale)
        self.addParameter(QgsProcessingParameterEnum(
            self.INDEX, tr("Название индекса"), [composites.INDEX_TITLES[k] for k in INDEX_KEYS], defaultValue=0))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT, tr("Папка композитов")))

    def processAlgorithm(self, parameters, context, feedback):
        layers = self.parameterAsLayerList(parameters, self.INPUT, context)
        pattern = re.compile(self.parameterAsString(parameters, self.YEAR_REGEX, context))
        files, nodata = {}, None
        for lyr in layers:
            path = lyr.source().split("|")[0]
            m = pattern.search(os.path.basename(path))
            if not m:
                feedback.pushWarning(tr("В имени файла не найден год, растр пропущен: %s") % path)
                continue
            files[int(m.group(0))] = path
            if nodata is None and lyr.dataProvider().sourceHasNoDataValue(1):
                nodata = lyr.dataProvider().sourceNoDataValue(1)
        out_dir = self.parameterAsString(parameters, self.OUTPUT, context)
        _run(composites.index_from_rasters, files, out_dir,
             INDEX_KEYS[self.parameterAsEnum(parameters, self.INDEX, context)],
             self.parameterAsInt(parameters, self.BAND_A, context),
             self.parameterAsInt(parameters, self.BAND_B, context),
             self.parameterAsDouble(parameters, self.SCALE, context), nodata, **_callbacks(feedback))
        return {self.OUTPUT: out_dir}


# =============================================================================== шаг 3

class AnnualShorelines(_Base):
    COMPOSITES, THRESHOLD, YEAR_FROM, YEAR_TO, BUFFER = "COMPOSITES", "THRESHOLD", "YEAR_FROM", "YEAR_TO", "BUFFER"
    SEA_MODE, SEA_LAYER, EXCLUDE = "SEA_MODE", "SEA_LAYER", "EXCLUDE"
    MASK_TEMPORAL, MASK_RIVERS, MIN_VERTICES = "MASK_TEMPORAL", "MASK_RIVERS", "MIN_VERTICES"
    STDEV, OBS = "STDEV_THRESHOLD", "OBS_THRESHOLD"
    OUTPUT, OUTPUT_MASK, OUTPUT_FREQ = "OUTPUT", "OUTPUT_MASK", "OUTPUT_FREQ"
    ICON = "shoreline.svg"

    def name(self):
        return "annual_shorelines"

    def displayName(self):
        return tr("3. Годовые береговые линии")

    def shortHelpString(self):
        return (tr("<p>Проводит береговую линию каждого года как изолинию водного индекса на уровне "
                "порога. Положение линии между центрами пикселей находится интерполяцией, поэтому "
                "точность выше размера пикселя.</p>"
                "<p>Перед этим данные очищаются:</p><ul>"
                "<li>пиксели, где за год меньше шести наблюдений, заменяются трёхлетним композитом;</li>"
                "<li>пятна «суши», не подтверждённые соседними годами, отбрасываются;</li>"
                "<li>остаётся только вода, связанная с морем: озёра, пруды и узкие водотоки внутри "
                "суши в расчёт не попадают;</li>"
                "<li>расчёт ограничен прибрежной полосой заданной ширины.</li></ul>"
                "<p><b>Море</b> по умолчанию — крупнейший постоянный водоём участка. Если на участке "
                "есть сопоставимая по размеру лагуна или лиман, укажите слой с точкой или полигоном "
                "в море. Для внутренних водоёмов (озёра, водохранилища, пруды) выберите вариант "
                "«все водоёмы» и отключите в дополнительных параметрах исключение узких водотоков.</p>"
                "<p>Поле <i>certainty</i> отмечает участки линий пониженной надёжности: "
                "<i>insufficient data</i> — меньше пяти наблюдений, <i>unstable data</i> — "
                "стандартное отклонение индекса больше 0,3.</p>") + METHOD_NOTE)

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFile(
            self.COMPOSITES, tr("Папка композитов (результат шага 2)"), QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterNumber(
            self.THRESHOLD, tr("Порог индекса (вода — выше порога)"), QgsProcessingParameterNumber.Double,
            0.0, minValue=-1.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.YEAR_FROM, tr("Первый год (пусто — все)"), QgsProcessingParameterNumber.Integer, optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.YEAR_TO, tr("Последний год (пусто — все)"), QgsProcessingParameterNumber.Integer, optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.BUFFER, tr("Ширина прибрежной полосы в каждую сторону, м"), QgsProcessingParameterNumber.Double,
            1000.0, minValue=60.0))
        self.addParameter(QgsProcessingParameterEnum(
            self.SEA_MODE, tr("Что считать морем"), [tr("Крупнейший постоянный водоём участка"),
                                                 tr("Все водоёмы шире 300 м (лагуны, лиманы, озёра, пруды)")], defaultValue=0))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.SEA_LAYER, tr("Слой морской акватории: точки или полигоны в море"),
            [QgsProcessing.TypeVectorAnyGeometry], optional=True))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.EXCLUDE, tr("Исключаемые участки (полигоны)"), [QgsProcessing.TypeVectorPolygon], optional=True))
        self.addParameter(_advanced(QgsProcessingParameterBoolean(
            self.MASK_TEMPORAL, tr("Отбрасывать «сушу», не подтверждённую соседними годами"), True)))
        self.addParameter(_advanced(QgsProcessingParameterBoolean(
            self.MASK_RIVERS, tr("Исключать узкие водотоки внутри суши"), True)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.MIN_VERTICES, tr("Наименьшее число вершин линии"), QgsProcessingParameterNumber.Integer, 10, minValue=2)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.STDEV, tr("Стандартное отклонение индекса, выше которого данные неустойчивы"),
            QgsProcessingParameterNumber.Double, 0.3, minValue=0.0)))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.OBS, tr("Число наблюдений, ниже которого данных недостаточно"),
            QgsProcessingParameterNumber.Integer, 5, minValue=1)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, tr("Годовые береговые линии"), QgsProcessing.TypeVectorLine))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_MASK, tr("Маска прибрежной полосы"), optional=True, createByDefault=False))
        self.addParameter(QgsProcessingParameterRasterDestination(
            self.OUTPUT_FREQ, tr("Повторяемость суши"), optional=True, createByDefault=False))

    def processAlgorithm(self, parameters, context, feedback):
        folder = self.parameterAsString(parameters, self.COMPOSITES, context)
        index, annual, _ = _run(masks.find_composites, folder)
        grid = gridio.grid_of(annual[sorted(annual)[0]])
        y0 = self.parameterAsInt(parameters, self.YEAR_FROM, context) if parameters.get(self.YEAR_FROM) is not None else None
        y1 = self.parameterAsInt(parameters, self.YEAR_TO, context) if parameters.get(self.YEAR_TO) is not None else None
        cb = _callbacks(feedback)
        prep = _run(masks.preprocess, folder, index,
                    self.parameterAsDouble(parameters, self.THRESHOLD, context), y0, y1,
                    buffer_m=self.parameterAsDouble(parameters, self.BUFFER, context),
                    mask_temporal=self.parameterAsBool(parameters, self.MASK_TEMPORAL, context),
                    mask_rivers=self.parameterAsBool(parameters, self.MASK_RIVERS, context),
                    sea_mode="largest" if self.parameterAsEnum(parameters, self.SEA_MODE, context) == 0 else "all",
                    sea_wkb=_geoms_wkb(self.parameterAsSource(parameters, self.SEA_LAYER, context), grid.epsg, context),
                    exclude_wkb=_geoms_wkb(self.parameterAsSource(parameters, self.EXCLUDE, context), grid.epsg, context),
                    obs_threshold=self.parameterAsInt(parameters, self.OBS, context),
                    stdev_threshold=self.parameterAsDouble(parameters, self.STDEV, context),
                    log=cb["log"], is_canceled=cb["is_canceled"])
        feedback.setProgress(50)
        records = contours.annual_shorelines(
            prep, self.parameterAsInt(parameters, self.MIN_VERTICES, context), cb["log"], cb["is_canceled"])
        if not records:
            raise QgsProcessingException(tr("Береговая линия не выделена ни за один год. Проверьте порог индекса "
                                         "и то, что участок включает и море, и сушу."))
        fields = _fields([("year", QVariant.Int), ("certainty", QVariant.String), ("length_m", QVariant.Double),
                          ("index", QVariant.String), ("threshold", QVariant.Double)])
        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, fields, QgsWkbTypes.MultiLineString,
                                             QgsCoordinateReferenceSystem("EPSG:%d" % grid.epsg))
        for rec in records:
            feat = QgsFeature(fields)
            feat.setGeometry(QgsGeometry.fromMultiPolylineXY(
                [[QgsPointXY(x, y) for x, y in line.tolist()] for line in rec["lines"]]))
            feat.setAttributes([rec["year"], rec["certainty"], round(rec["length_m"], 1), index,
                                float(prep["threshold"])])
            sink.addFeature(feat, QgsFeatureSink.FastInsert)
        _style_output(context, dest_id, "shorelines", tr("Годовые береговые линии"))
        result = {self.OUTPUT: dest_id}
        mask_path = self.parameterAsOutputLayer(parameters, self.OUTPUT_MASK, context)
        if mask_path:
            gridio.write_tif(mask_path, prep["coastal_mask"], grid, "uint8", 255, ["coastal_mask"])
            _style_output(context, mask_path, "coastal_mask", tr("Маска прибрежной полосы"))
            result[self.OUTPUT_MASK] = mask_path
        freq_path = self.parameterAsOutputLayer(parameters, self.OUTPUT_FREQ, context)
        if freq_path:
            gridio.write_tif(freq_path, prep["land_freq"], grid, "float32", np.nan, ["land_frequency"])
            _style_output(context, freq_path, "land_freq", tr("Повторяемость суши"))
            result[self.OUTPUT_FREQ] = freq_path
        return result


# =============================================================================== шаги 4 и 5

def _read_shorelines(source, year_field, epsg, context):
    xform = QgsCoordinateTransform(source.sourceCrs(), QgsCoordinateReferenceSystem("EPSG:%d" % epsg),
                                   context.transformContext())
    if year_field not in source.fields().names():
        raise QgsProcessingException(tr("В слое береговых линий нет поля года «%s».") % year_field)
    records = []
    for feat in source.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty() or feat[year_field] in (None, NULL):
            continue
        geom.transform(xform)
        parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
        lines = [np.array([(p.x(), p.y()) for p in part], dtype=np.float64) for part in parts if len(part) >= 2]
        if lines:
            records.append({"year": int(feat[year_field]), "lines": lines})
    if not records:
        raise QgsProcessingException(tr("Слой береговых линий пуст."))
    return records


def _point_fields(years, hotspot=False):
    spec = [("uid", QVariant.String), ("rate_time", QVariant.Double), ("sig_time", QVariant.Double),
            ("se_time", QVariant.Double), ("outl_time", QVariant.String)]
    spec += [("dist_%d" % y, QVariant.Double) for y in years]
    if hotspot:
        spec += [("radius_m", QVariant.Int), ("n", QVariant.Int)]
    else:
        spec += [("angle_mean", QVariant.Int), ("angle_std", QVariant.Int), ("valid_obs", QVariant.Int),
                 ("valid_span", QVariant.Int), ("sce", QVariant.Double), ("nsm", QVariant.Double),
                 ("max_year", QVariant.Int), ("min_year", QVariant.Int)]
    spec.append(("certainty", QVariant.String))
    return _fields(spec)


def _write_points(sink, fields, records):
    names = fields.names()
    for rec in records:
        feat = QgsFeature(fields)
        feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*rec["xy"])))
        feat.setAttributes([rec.get(n) for n in names])
        sink.addFeature(feat, QgsFeatureSink.FastInsert)


class RatesOfChange(_Base):
    SHORELINES, YEAR_FIELD, COMPOSITES, BASELINE = "SHORELINES", "YEAR_FIELD", "COMPOSITES", "BASELINE_YEAR"
    SPACING, MAX_DIST, OUTLIERS, OUTPUT = "SPACING", "MAX_DIST", "OUTLIERS", "OUTPUT"
    ICON = "rates.svg"

    def name(self):
        return "rates_of_change"

    def displayName(self):
        return tr("4. Темпы смещения берега")

    def shortHelpString(self):
        return (tr("<p>Вдоль береговой линии опорного года (по умолчанию — последнего) через равный шаг "
                "расставляются точки. Для каждой точки измеряется расстояние до береговой линии "
                "каждого года: положительное, если линия лежала мористее опорной, отрицательное — "
                "если ближе к суше. Направление определяется по значениям индекса в композитах.</p>"
                "<p>По ряду расстояний строится линейная регрессия. Её наклон — средний темп, м/год "
                "(<i>rate_time</i>): <b>отрицательный — берег отступает, положительный — нарастает</b>. "
                "Годы с резко выпадающим положением линии предварительно исключаются.</p>"
                "<p>Основные поля: <i>sig_time</i> — значимость тренда (p); <i>se_time</i> — стандартная "
                "ошибка темпа; <i>dist_ГГГГ</i> — положение линии года относительно опорной, м; "
                "<i>nsm</i> — смещение между первым и последним годом; <i>sce</i> — размах положений; "
                "<i>certainty</i> — надёжность (<i>good</i> либо причина сомнения).</p>"
                "<p>Доверять следует точкам, где одновременно <i>certainty = good</i> и "
                "<i>sig_time</i> не больше 0,01: на карте они показаны крупными знаками.</p>") + METHOD_NOTE)

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.SHORELINES, tr("Годовые береговые линии (результат шага 3)"), [QgsProcessing.TypeVectorLine]))
        self.addParameter(_advanced(QgsProcessingParameterField(
            self.YEAR_FIELD, tr("Поле года"), "year", self.SHORELINES, QgsProcessingParameterField.Numeric, optional=True)))
        self.addParameter(QgsProcessingParameterFile(
            self.COMPOSITES, tr("Папка композитов (результат шага 2)"), QgsProcessingParameterFile.Folder))
        self.addParameter(QgsProcessingParameterNumber(
            self.BASELINE, tr("Опорный год (пусто — последний)"), QgsProcessingParameterNumber.Integer, optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.SPACING, tr("Шаг точек вдоль берега, м"), QgsProcessingParameterNumber.Double, 30.0, minValue=1.0))
        self.addParameter(_advanced(QgsProcessingParameterNumber(
            self.MAX_DIST, tr("Наибольшее допустимое расстояние до линии года, м"),
            QgsProcessingParameterNumber.Double, 1200.0, minValue=30.0)))
        self.addParameter(_advanced(QgsProcessingParameterEnum(
            self.OUTLIERS, tr("Исключение выпадающих лет"), OUTLIER_TITLES, defaultValue=0)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, tr("Темпы смещения берега"), QgsProcessing.TypeVectorPoint))

    def processAlgorithm(self, parameters, context, feedback):
        folder = self.parameterAsString(parameters, self.COMPOSITES, context)
        index, annual, _ = _run(masks.find_composites, folder)
        grid = gridio.grid_of(annual[sorted(annual)[0]])
        source = self.parameterAsSource(parameters, self.SHORELINES, context)
        year_field = self.parameterAsString(parameters, self.YEAR_FIELD, context) or "year"
        shorelines = _read_shorelines(source, year_field, grid.epsg, context)
        shorelines = [r for r in shorelines if r["year"] in annual]
        years_in = sorted(set(r["year"] for r in shorelines))
        if len(years_in) < 3:
            raise QgsProcessingException(tr("Береговые линии и композиты совпадают меньше чем по трём годам."))
        cb = _callbacks(feedback)
        prep = _run(masks.load_combined, folder, index, years_in[0], years_in[-1],
                    log=cb["log"], is_canceled=cb["is_canceled"])
        feedback.setProgress(30)
        baseline = self.parameterAsInt(parameters, self.BASELINE, context) \
            if parameters.get(self.BASELINE) is not None else None
        years, points = _run(rates.rates_of_change, shorelines, prep, baseline,
                             self.parameterAsDouble(parameters, self.SPACING, context),
                             self.parameterAsDouble(parameters, self.MAX_DIST, context),
                             rates.OUTLIER_METHODS[self.parameterAsEnum(parameters, self.OUTLIERS, context)],
                             log=cb["log"], is_canceled=cb["is_canceled"])
        fields = _point_fields(years)
        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, fields, QgsWkbTypes.Point,
                                             QgsCoordinateReferenceSystem("EPSG:%d" % grid.epsg))
        _write_points(sink, fields, points)
        _style_output(context, dest_id, "rates", tr("Темпы смещения берега"))
        return {self.OUTPUT: dest_id}


class Hotspots(_Base):
    POINTS, SHORELINES, RADIUS, OUTLIERS, OUTPUT = "POINTS", "SHORELINES", "RADIUS", "OUTLIERS", "OUTPUT"
    ICON = "hotspots.svg"

    def name(self):
        return "hotspots"

    def displayName(self):
        return tr("5. Обобщённые темпы по участкам берега")

    def shortHelpString(self):
        return (tr("<p>Сводит точечные темпы к обзорной картине. Вдоль береговой линии опорного года через "
                "половину радиуса ставятся обобщённые точки; для каждой берётся медиана годовых "
                "положений всех надёжных точек в круге заданного радиуса и по ней заново строится "
                "регрессия.</p><p>Слой удобен для мелких масштабов и для сравнения участков берега "
                "между собой. Точки, в круг которых попало слишком мало исходных точек, помечаются "
                "как <i>insufficient points</i>.</p>") + METHOD_NOTE)

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.POINTS, tr("Темпы смещения берега (результат шага 4)"), [QgsProcessing.TypeVectorPoint]))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.SHORELINES, tr("Годовые береговые линии (результат шага 3)"), [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterNumber(
            self.RADIUS, tr("Радиус обобщения, м"), QgsProcessingParameterNumber.Double, 1000.0, minValue=50.0))
        self.addParameter(_advanced(QgsProcessingParameterEnum(
            self.OUTLIERS, tr("Исключение выпадающих лет"), OUTLIER_TITLES, defaultValue=0)))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, tr("Обобщённые темпы"), QgsProcessing.TypeVectorPoint))

    def processAlgorithm(self, parameters, context, feedback):
        src = self.parameterAsSource(parameters, self.POINTS, context)
        names = src.fields().names()
        years = sorted(int(n[5:]) for n in names if n.startswith("dist_") and n[5:].isdigit())
        if "certainty" not in names or len(years) < 3:
            raise QgsProcessingException(tr("Слой точек не похож на результат шага 4: нет полей dist_ГГГГ и certainty."))
        crs = src.sourceCrs()
        if crs.isGeographic() or not crs.authid().startswith("EPSG:"):
            raise QgsProcessingException(tr("Слой точек должен быть в прямоугольной системе координат с кодом EPSG."))
        epsg = int(crs.authid().split(":")[1])
        points, zero = [], {y: True for y in years}
        for feat in src.getFeatures():
            p = feat.geometry().asPoint()
            rec = {"xy": (p.x(), p.y()), "certainty": feat["certainty"]}
            for y in years:
                v = feat["dist_%d" % y]
                rec["dist_%d" % y] = None if v is None or v == NULL else float(v)
                if rec["dist_%d" % y] != 0.0:
                    zero[y] = False
            points.append(rec)
        base = [y for y in years if zero[y]]
        baseline = base[-1] if base else years[-1]
        feedback.pushInfo(tr("Опорный год: %d.") % baseline)
        lines = []
        for rec in _read_shorelines(self.parameterAsSource(parameters, self.SHORELINES, context), "year", epsg, context):
            if rec["year"] == baseline:
                lines.extend(rec["lines"])
        if not lines:
            raise QgsProcessingException(tr("В слое береговых линий нет линии опорного года %d.") % baseline)
        spacing = 30.0
        if len(points) > 1:
            a, b = points[0]["xy"], points[1]["xy"]
            spacing = max(1.0, float(np.hypot(a[0] - b[0], a[1] - b[1])))
        out = rates.hotspots(points, years, lines, epsg,
                             self.parameterAsDouble(parameters, self.RADIUS, context), spacing,
                             rates.OUTLIER_METHODS[self.parameterAsEnum(parameters, self.OUTLIERS, context)],
                             feedback.pushInfo)
        fields = _point_fields(years, hotspot=True)
        sink, dest_id = self.parameterAsSink(parameters, self.OUTPUT, context, fields, QgsWkbTypes.Point, crs)
        _write_points(sink, fields, out)
        _style_output(context, dest_id, "hotspots", tr("Обобщённые темпы"))
        return {self.OUTPUT: dest_id}


# ========================================================================== полный расчёт

class FullPipeline(_Base):
    EXTENT, SENSOR, YEAR_FROM, YEAR_TO, MONTH_FROM, MONTH_TO = (
        "EXTENT", "SENSOR", "YEAR_FROM", "YEAR_TO", "MONTH_FROM", "MONTH_TO")
    INDEX, THRESHOLD, BUFFER, SEA_LAYER, RADIUS, FOLDER = "INDEX", "THRESHOLD", "BUFFER", "SEA_LAYER", "RADIUS", "FOLDER"
    ICON = "icon.svg"

    def name(self):
        return "full_pipeline"

    def displayName(self):
        return tr("Полный расчёт (шаги 1–5)")

    def shortHelpString(self):
        return (tr("<p>Выполняет всю цепочку за один запуск: загрузка снимков, годовые композиты, "
                "береговые линии, темпы смещения и обобщённые темпы. В рабочей папке создаются "
                "подпапки <i>scenes</i> и <i>composites</i> и файлы <i>shorelines.gpkg</i>, "
                "<i>rates.gpkg</i>, <i>hotspots.gpkg</i>; итоговые слои добавляются в проект.</p>"
                "<p>Параметры, которых здесь нет, берутся по умолчанию. Для тонкой настройки "
                "выполняйте шаги по отдельности: каждый принимает на вход результат предыдущего.</p>"
                "<p>Повторный запуск с той же рабочей папкой не скачивает снимки заново.</p>") + METHOD_NOTE)

    def initAlgorithm(self, config=None):
        year = datetime.date.today().year
        self.addParameter(QgsProcessingParameterExtent(self.EXTENT, tr("Участок (охват)")))
        self.addParameter(QgsProcessingParameterEnum(
            self.SENSOR, tr("Съёмочная система"), [SENSORS[k]["title"] for k in SENSOR_KEYS], defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.YEAR_FROM, tr("Первый год"), QgsProcessingParameterNumber.Integer, 1984, minValue=1982, maxValue=year))
        self.addParameter(QgsProcessingParameterNumber(
            self.YEAR_TO, tr("Последний год"), QgsProcessingParameterNumber.Integer, year - 1, minValue=1982, maxValue=year))
        self.addParameter(QgsProcessingParameterNumber(
            self.MONTH_FROM, tr("Первый месяц сезона"), QgsProcessingParameterNumber.Integer, 1, minValue=1, maxValue=12))
        self.addParameter(QgsProcessingParameterNumber(
            self.MONTH_TO, tr("Последний месяц сезона"), QgsProcessingParameterNumber.Integer, 12, minValue=1, maxValue=12))
        self.addParameter(QgsProcessingParameterEnum(
            self.INDEX, tr("Водный индекс"), [composites.INDEX_TITLES[k] for k in INDEX_KEYS], defaultValue=0))
        self.addParameter(QgsProcessingParameterNumber(
            self.THRESHOLD, tr("Порог индекса"), QgsProcessingParameterNumber.Double, 0.0, minValue=-1.0, maxValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.BUFFER, tr("Ширина прибрежной полосы в каждую сторону, м"), QgsProcessingParameterNumber.Double,
            1000.0, minValue=60.0))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.SEA_LAYER, tr("Слой морской акватории: точки или полигоны в море"),
            [QgsProcessing.TypeVectorAnyGeometry], optional=True))
        self.addParameter(QgsProcessingParameterNumber(
            self.RADIUS, tr("Радиус обобщения, м"), QgsProcessingParameterNumber.Double, 1000.0, minValue=50.0))
        self.addParameter(QgsProcessingParameterFolderDestination(self.FOLDER, tr("Рабочая папка")))
        for key, title in (("SHORELINES", tr("Береговые линии")), ("RATES", tr("Темпы")), ("HOTSPOTS", tr("Обобщённые темпы"))):
            self.addOutput(QgsProcessingOutputString(key, title))
        self.addOutput(QgsProcessingOutputFolder("COMPOSITES", tr("Папка композитов")))

    def processAlgorithm(self, parameters, context, feedback):
        import processing
        folder = self.parameterAsString(parameters, self.FOLDER, context)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        scenes = os.path.join(folder, "scenes")
        comps = os.path.join(folder, "composites")
        out = {k: os.path.join(folder, k.lower() + ".gpkg") for k in ("SHORELINES", "RATES", "HOTSPOTS")}
        multi = QgsProcessingMultiStepFeedback(5, feedback)
        months = {"MONTH_FROM": self.parameterAsInt(parameters, self.MONTH_FROM, context),
                  "MONTH_TO": self.parameterAsInt(parameters, self.MONTH_TO, context)}
        years = {"YEAR_FROM": self.parameterAsInt(parameters, self.YEAR_FROM, context),
                 "YEAR_TO": self.parameterAsInt(parameters, self.YEAR_TO, context)}

        def step(n, alg, params):
            multi.setCurrentStep(n)
            if multi.isCanceled():
                raise QgsProcessingException(tr("Расчёт остановлен пользователем."))
            multi.pushInfo("")
            multi.pushInfo(tr("=== Шаг %d из 5 ===") % (n + 1))
            return processing.run("coastdyn:" + alg, params, context=context, feedback=multi,
                                  is_child_algorithm=True)

        step(0, "download_scenes", dict(months, EXTENT=parameters[self.EXTENT],
                                        SENSOR=self.parameterAsEnum(parameters, self.SENSOR, context),
                                        OUTPUT_FOLDER=scenes, **years))
        step(1, "annual_composites", dict(months, ARCHIVE=scenes,
                                          INDEX=self.parameterAsEnum(parameters, self.INDEX, context),
                                          LOAD=2, OUTPUT_FOLDER=comps, **years))
        step(2, "annual_shorelines", {"COMPOSITES": comps,
                                      "THRESHOLD": self.parameterAsDouble(parameters, self.THRESHOLD, context),
                                      "BUFFER": self.parameterAsDouble(parameters, self.BUFFER, context),
                                      "SEA_LAYER": parameters.get(self.SEA_LAYER), "OUTPUT": out["SHORELINES"]})
        step(3, "rates_of_change", {"SHORELINES": out["SHORELINES"], "COMPOSITES": comps, "OUTPUT": out["RATES"]})
        step(4, "hotspots", {"POINTS": out["RATES"], "SHORELINES": out["SHORELINES"],
                             "RADIUS": self.parameterAsDouble(parameters, self.RADIUS, context),
                             "OUTPUT": out["HOTSPOTS"]})

        meta = composites.load_meta(comps)
        if meta:
            last = meta["years"][-1]
            if meta.get("rgb"):
                _load_on_completion(context, composites.rgb_path(comps, last), tr("Цветосинтез %d") % last, "rgb")
        _load_on_completion(context, out["SHORELINES"], tr("Годовые береговые линии"), "shorelines")
        _load_on_completion(context, out["RATES"], tr("Темпы смещения берега"), "rates")
        _load_on_completion(context, out["HOTSPOTS"], tr("Обобщённые темпы"), "hotspots")
        out["COMPOSITES"] = comps
        return out


ALGORITHMS = [FullPipeline, DownloadScenes, AnnualComposites, IndexFromRasters, AnnualShorelines,
              RatesOfChange, Hotspots]
