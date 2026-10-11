# -*- coding: utf-8 -*-
"""Оформление результатов: условные знаки слоёв и русские подписи полей."""
from qgis.core import (
    QgsCategorizedSymbolRenderer, QgsLayerTreeLayer, QgsProject, QgsColorRampShader, QgsContrastEnhancement,
    QgsGraduatedSymbolRenderer, QgsLineSymbol, QgsMarkerSymbol, QgsMultiBandColorRenderer,
    QgsPalettedRasterRenderer, QgsProcessingLayerPostProcessorInterface, QgsProperty,
    QgsRasterLayer, QgsRasterShader, QgsRendererCategory, QgsRendererRange,
    QgsSingleBandPseudoColorRenderer, QgsSymbol, QgsSymbolLayer, QgsVectorLayer,
)
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QColor

# Шкала лет: от тёмно-фиолетового (давние годы) к жёлтому (недавние)
YEAR_STOPS = [(0.0, (13, 8, 135)), (0.25, (126, 3, 168)), (0.5, (204, 71, 120)),
              (0.75, (248, 149, 64)), (1.0, (240, 249, 33))]
# Шкала темпов, м/год: красное — отступание, синее — нарастание
RATE_CLASSES = [
    (-1e9, -5.0, (165, 0, 38), "отступание быстрее 5 м/год"),
    (-5.0, -2.0, (215, 48, 39), "отступание 2–5 м/год"),
    (-2.0, -1.0, (244, 109, 67), "отступание 1–2 м/год"),
    (-1.0, -0.3, (253, 174, 97), "отступание 0,3–1 м/год"),
    (-0.3, 0.3, (235, 235, 235), "устойчиво (менее 0,3 м/год)"),
    (0.3, 1.0, (171, 217, 233), "нарастание 0,3–1 м/год"),
    (1.0, 2.0, (116, 173, 209), "нарастание 1–2 м/год"),
    (2.0, 5.0, (69, 117, 180), "нарастание 2–5 м/год"),
    (5.0, 1e9, (49, 54, 149), "нарастание быстрее 5 м/год"),
]
ALIASES = {
    "uid": "Идентификатор", "year": "Год", "certainty": "Надёжность", "length_m": "Длина, м",
    "index": "Индекс", "threshold": "Порог индекса",
    "rate_time": "Темп, м/год", "sig_time": "Значимость (p)", "se_time": "Ст. ошибка темпа, м/год",
    "outl_time": "Годы вне расчёта", "angle_mean": "Направление смещения, °",
    "angle_std": "Разброс направлений, °", "valid_obs": "Лет в расчёте", "valid_span": "Охват, лет",
    "sce": "Размах положений, м", "nsm": "Итоговое смещение, м",
    "max_year": "Год наибольшего выдвижения", "min_year": "Год наибольшего отступания",
    "radius_m": "Радиус обобщения, м", "n": "Точек в круге",
}


def _ramp(stops, t):
    t = min(1.0, max(0.0, t))
    for (t0, c0), (t1, c1) in zip(stops[:-1], stops[1:]):
        if t <= t1:
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return QColor(*[int(round(a + f * (b - a))) for a, b in zip(c0, c1)])
    return QColor(*stops[-1][1])


def year_color(year, y0, y1):
    return _ramp(YEAR_STOPS, 0.5 if y1 == y0 else (year - y0) / float(y1 - y0))


def _aliases(layer):
    for i, f in enumerate(layer.fields()):
        name = f.name()
        if name in ALIASES:
            layer.setFieldAlias(i, ALIASES[name])
        elif name.startswith("dist_"):
            layer.setFieldAlias(i, "%s г., м" % name[5:])


def style_shorelines(layer):
    idx = layer.fields().indexOf("year")
    if idx < 0:
        return
    years = sorted(int(v) for v in layer.uniqueValues(idx) if v is not None)
    if not years:
        return
    cats = []
    for y in years:
        sym = QgsLineSymbol.createSimple({"line_width": "0.5", "capstyle": "round", "joinstyle": "round"})
        sym.setColor(year_color(y, years[0], years[-1]))
        sl = sym.symbolLayer(0)
        sl.setDataDefinedProperty(QgsSymbolLayer.PropertyStrokeStyle, QgsProperty.fromExpression(
            "if(\"certainty\" = 'good', 'solid', 'dot')"))
        cats.append(QgsRendererCategory(y, sym, str(y)))
    layer.setRenderer(QgsCategorizedSymbolRenderer("year", cats))
    _aliases(layer)
    layer.triggerRepaint()


def _rate_renderer(size_expr, outline):
    ranges = []
    for lo, hi, rgb, label in RATE_CLASSES:
        sym = QgsMarkerSymbol.createSimple({"name": "circle", "outline_color": outline,
                                            "outline_width": "0.15"})
        sym.setColor(QColor(*rgb))
        sym.setDataDefinedSize(QgsProperty.fromExpression(size_expr))
        ranges.append(QgsRendererRange(lo, hi, sym, label))
    renderer = QgsGraduatedSymbolRenderer("rate_time", ranges)
    renderer.setSymbolSizes(1.0, 1.0)
    return renderer


def style_rates(layer):
    """Крупные знаки — статистически значимый тренд (p <= 0,01) в надёжных точках; остальные мельче."""
    if layer.fields().indexOf("rate_time") < 0:
        return
    layer.setRenderer(_rate_renderer(
        "if(\"certainty\" = 'good' and \"sig_time\" <= 0.01, 2.6, 1.1)", "60,60,60,160"))
    _aliases(layer)
    layer.triggerRepaint()


def style_hotspots(layer):
    if layer.fields().indexOf("rate_time") < 0:
        return
    layer.setRenderer(_rate_renderer(
        "if(\"certainty\" = 'good' and \"sig_time\" <= 0.01, 6.5, 3.5)", "30,30,30,255"))
    _aliases(layer)
    layer.triggerRepaint()


def style_index(layer):
    """Канал 1 — медиана индекса: суша в охристых тонах, вода в синих, порог около нуля — светлый."""
    stops = [(-0.6, QColor(140, 81, 10)), (-0.3, QColor(216, 179, 101)), (0.0, QColor(245, 245, 245)),
             (0.3, QColor(90, 180, 172)), (0.6, QColor(1, 102, 94))]
    fn = QgsColorRampShader(-0.6, 0.6)
    fn.setColorRampType(QgsColorRampShader.Interpolated)
    fn.setColorRampItemList([QgsColorRampShader.ColorRampItem(v, c, ("%.1f" % v).replace(".", ","))
                             for v, c in stops])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(fn)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))
    layer.triggerRepaint()


def style_rgb(layer):
    """Цветосинтез SWIR–NIR–Green: вода тёмная, растительность зелёная, песок и застройка светлые."""
    renderer = QgsMultiBandColorRenderer(layer.dataProvider(), 1, 2, 3)
    for band, setter, top in ((1, renderer.setRedContrastEnhancement, 3500.0),
                              (2, renderer.setGreenContrastEnhancement, 4500.0),
                              (3, renderer.setBlueContrastEnhancement, 2000.0)):
        ce = QgsContrastEnhancement(layer.dataProvider().dataType(band))
        ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
        ce.setMinimumValue(0.0)
        ce.setMaximumValue(top)
        setter(ce)
    layer.setRenderer(renderer)
    layer.triggerRepaint()


def style_coastal_mask(layer):
    classes = [QgsPalettedRasterRenderer.Class(0, QColor(166, 206, 227, 120), "море"),
               QgsPalettedRasterRenderer.Class(1, QColor(255, 237, 111, 150), "прибрежная полоса"),
               QgsPalettedRasterRenderer.Class(2, QColor(120, 120, 120, 110), "суша и внутренние воды")]
    layer.setRenderer(QgsPalettedRasterRenderer(layer.dataProvider(), 1, classes))
    layer.triggerRepaint()


def style_land_freq(layer):
    stops = [(0.0, QColor(8, 81, 156)), (0.5, QColor(255, 255, 191)), (1.0, QColor(140, 81, 10))]
    fn = QgsColorRampShader(0.0, 1.0)
    fn.setColorRampType(QgsColorRampShader.Interpolated)
    fn.setColorRampItemList([QgsColorRampShader.ColorRampItem(v, c, "%d %%" % round(v * 100))
                             for v, c in stops])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(fn)
    layer.setRenderer(QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader))
    layer.triggerRepaint()


STYLES = {"shorelines": style_shorelines, "rates": style_rates, "hotspots": style_hotspots,
          "index": style_index, "rgb": style_rgb, "coastal_mask": style_coastal_mask,
          "land_freq": style_land_freq}


def apply_style(layer, kind):
    if layer is None or not layer.isValid() or kind not in STYLES:
        return
    if kind in ("shorelines", "rates", "hotspots") and not isinstance(layer, QgsVectorLayer):
        return
    if kind in ("index", "rgb", "coastal_mask", "land_freq") and not isinstance(layer, QgsRasterLayer):
        return
    STYLES[kind](layer)


VECTOR_KINDS = ("shorelines", "rates", "hotspots")


def arrange_layer(layer_id, kind, attempt=0):
    """Ставит слой результата на своё место в дереве слоёв.

    Векторные результаты поднимаются наверх; растры опускаются под все векторные слои
    верхнего уровня, чтобы не закрывать линии и точки. Вызывается после того, как
    слой добавлен в проект; пока слоя в дереве нет, попытка повторяется.
    """
    root = QgsProject.instance().layerTreeRoot()
    node = root.findLayer(layer_id)
    if node is None:
        if attempt < 8:
            QTimer.singleShot(300, lambda: arrange_layer(layer_id, kind, attempt + 1))
        return
    parent = node.parent() or root
    children = root.children()
    if kind in VECTOR_KINDS:
        if parent is root and children and children[0] is node:
            return
        target = 0
    else:
        vectors = [i for i, child in enumerate(children)
                   if isinstance(child, QgsLayerTreeLayer) and isinstance(child.layer(), QgsVectorLayer)]
        if not vectors:
            return
        if parent is root and children.index(node) > vectors[-1]:
            return
        target = vectors[-1] + 1
    clone = node.clone()
    root.insertChildNode(target, clone)
    parent.removeChildNode(node)


class StylePostProcessor(QgsProcessingLayerPostProcessorInterface):
    """Назначает слою оформление и место в дереве слоёв после добавления результата в проект."""

    _instances = {}

    def __init__(self, kind):
        super().__init__()
        self.kind = kind

    def postProcessLayer(self, layer, context, feedback):
        apply_style(layer, self.kind)
        layer_id, kind = layer.id(), self.kind
        QTimer.singleShot(0, lambda: arrange_layer(layer_id, kind))

    @classmethod
    def create(cls, kind):
        # ссылка хранится в классе: иначе объект будет удалён до вызова
        if kind not in cls._instances:
            cls._instances[kind] = cls(kind)
        return cls._instances[kind]
