# -*- coding: utf-8 -*-
"""Панель «График смещения берега».

Щелчок по точке слоя темпов показывает ряд годовых положений береговой линии,
линию тренда и сводку по точке. График рисуется средствами Qt и не требует
сторонних библиотек.
"""
import math

from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from qgis.PyQt.QtWidgets import (QDockWidget, QFileDialog, QHBoxLayout, QLabel, QPushButton,
                                 QSizePolicy, QVBoxLayout, QWidget)
from qgis.core import (NULL, QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry, QgsPointXY,
                       QgsProject, QgsRectangle, QgsVectorLayer, QgsWkbTypes)
from qgis.gui import QgsMapTool, QgsRubberBand

CERTAINTY_RU = {
    "good": "надёжно",
    "baseline outlier": "опорный год выпадает из ряда",
    "high angular variability": "линии разных лет не ложатся на одно направление",
    "insufficient observations": "мало лет с данными",
    "insufficient points": "мало точек в круге обобщения",
}


def _num(value):
    if value is None or value == NULL:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def series_from_feature(feature):
    """Данные точки для графика: годы, положения, исключённые годы, сводные показатели."""
    names = feature.fields().names()
    years = sorted(int(n[5:]) for n in names if n.startswith("dist_") and n[5:].isdigit())
    dist = [_num(feature["dist_%d" % y]) for y in years]
    outl = set()
    if "outl_time" in names and feature["outl_time"] not in (None, NULL):
        outl = set(int(v) for v in str(feature["outl_time"]).split() if v.isdigit())
    info = {n: feature[n] for n in ("rate_time", "sig_time", "se_time", "certainty", "nsm", "sce",
                                    "valid_obs", "uid", "n", "radius_m") if n in names}
    return {"years": years, "dist": dist, "outliers": outl, "info": info}


def fit_line(series):
    """Прямая тренда по годам, вошедшим в расчёт (метод наименьших квадратов)."""
    pts = [(y, d) for y, d in zip(series["years"], series["dist"])
           if d is not None and y not in series["outliers"]]
    if len(pts) < 2:
        return None
    n = float(len(pts))
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    sxx = sum((p[0] - mx) ** 2 for p in pts)
    if sxx == 0:
        return None
    slope = sum((p[0] - mx) * (p[1] - my) for p in pts) / sxx
    return slope, my - slope * mx


def _nice_step(span, target=6):
    raw = span / float(target) if span > 0 else 1.0
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


class ChartWidget(QWidget):
    """Поле графика: положение береговой линии по годам."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.series = None
        self.setMinimumSize(360, 240)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_series(self, series):
        self.series = series
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        self.draw(painter, QRectF(self.rect()))
        painter.end()

    def render_pixmap(self, width=1200, height=700):
        pm = QPixmap(width, height)
        pm.fill(Qt.white)
        painter = QPainter(pm)
        painter.scale(2.0, 2.0)
        self.draw(painter, QRectF(0, 0, width / 2.0, height / 2.0))
        painter.end()
        return pm

    def draw(self, p, rect):
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(rect, Qt.white)
        font = QFont(self.font())
        font.setPointSizeF(8.5)
        p.setFont(font)
        s = self.series
        vals = [d for d in s["dist"] if d is not None] if s else []
        if not vals:
            p.setPen(QColor(110, 110, 110))
            p.drawText(rect, Qt.AlignCenter | Qt.TextWordWrap,
                       "Включите инструмент и щёлкните по точке слоя темпов смещения берега")
            return
        left, right, top, bottom = 58.0, 14.0, 12.0, 34.0
        plot = QRectF(rect.left() + left, rect.top() + top,
                      rect.width() - left - right, rect.height() - top - bottom)
        y0, y1 = s["years"][0], s["years"][-1]
        vmin, vmax = min(vals + [0.0]), max(vals + [0.0])
        pad = max(2.0, 0.08 * (vmax - vmin))
        vmin, vmax = vmin - pad, vmax + pad

        def px(year):
            return plot.left() + (year - y0) / float(max(1, y1 - y0)) * plot.width()

        def py(value):
            return plot.bottom() - (value - vmin) / (vmax - vmin) * plot.height()

        # сетка и подписи осей
        grid_pen = QPen(QColor(225, 225, 225))
        text_pen = QPen(QColor(70, 70, 70))
        step = _nice_step(vmax - vmin)
        v = math.ceil(vmin / step) * step
        while v <= vmax:
            p.setPen(grid_pen)
            p.drawLine(QPointF(plot.left(), py(v)), QPointF(plot.right(), py(v)))
            p.setPen(text_pen)
            p.drawText(QRectF(rect.left(), py(v) - 8, left - 6, 16), Qt.AlignRight | Qt.AlignVCenter,
                       ("%g" % round(v, 6)).replace(".", ","))
            v += step
        ystep = 5 if y1 - y0 > 12 else (2 if y1 - y0 > 6 else 1)
        for year in range(int(math.ceil(y0 / float(ystep)) * ystep), y1 + 1, ystep):
            p.setPen(grid_pen)
            p.drawLine(QPointF(px(year), plot.top()), QPointF(px(year), plot.bottom()))
            p.setPen(text_pen)
            p.drawText(QRectF(px(year) - 22, plot.bottom() + 3, 44, 14), Qt.AlignCenter, str(year))
        p.setPen(QPen(QColor(120, 120, 120)))
        p.drawRect(plot)
        p.setPen(QPen(QColor(120, 120, 120), 1, Qt.DashLine))
        p.drawLine(QPointF(plot.left(), py(0.0)), QPointF(plot.right(), py(0.0)))
        p.setPen(text_pen)
        p.drawText(QRectF(plot.left(), plot.bottom() + 17, plot.width(), 14), Qt.AlignCenter, "Год")
        p.save()
        p.translate(rect.left() + 11, plot.center().y())
        p.rotate(-90)
        p.drawText(QRectF(-plot.height() / 2.0, -8, plot.height(), 16), Qt.AlignCenter,
                   "Положение, м   (+ к морю)")
        p.restore()

        # ломаная, тренд, точки
        line = fit_line(s)
        if line:
            slope, icpt = line
            color = QColor(33, 102, 172) if slope >= 0 else QColor(178, 24, 43)
            p.setPen(QPen(color, 1.8))
            p.setClipRect(plot)
            p.drawLine(QPointF(px(y0), py(slope * y0 + icpt)), QPointF(px(y1), py(slope * y1 + icpt)))
            p.setClipping(False)
        used = [(y, d) for y, d in zip(s["years"], s["dist"]) if d is not None and y not in s["outliers"]]
        p.setPen(QPen(QColor(150, 150, 150), 1))
        for (ya, da), (yb, db) in zip(used[:-1], used[1:]):
            p.drawLine(QPointF(px(ya), py(da)), QPointF(px(yb), py(db)))
        for y, d in zip(s["years"], s["dist"]):
            if d is None:
                continue
            c = QPointF(px(y), py(d))
            if y in s["outliers"]:
                p.setPen(QPen(QColor(120, 120, 120), 1.2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, 3.6, 3.6)
                p.drawLine(QPointF(c.x() - 3, c.y() - 3), QPointF(c.x() + 3, c.y() + 3))
            else:
                p.setPen(QPen(QColor(40, 40, 40), 0.8))
                p.setBrush(QColor(70, 70, 70))
                p.drawEllipse(c, 3.2, 3.2)
        p.setBrush(Qt.NoBrush)


def describe(series):
    """Текстовая сводка по точке."""
    info = series["info"]
    rate, se, sig = _num(info.get("rate_time")), _num(info.get("se_time")), _num(info.get("sig_time"))
    if rate is None:
        return "Темп не определён: в точке недостаточно лет с данными."
    verb = "нарастает" if rate > 0 else "отступает"
    text = "<b>Берег %s на %s м/год</b>" % (verb, ("%.2f" % abs(rate)).replace(".", ","))
    if se is not None:
        text += " (±%s, 95 %%)" % ("%.2f" % (1.96 * se)).replace(".", ",")
    if sig is not None:
        # знак «меньше» записан кодом: подпись выводится как размеченный текст
        p_text = "p &lt; 0,001" if sig < 0.001 else "p = " + ("%.3f" % sig).replace(".", ",")
        text += "; %s — тренд %s" % (p_text, "значим" if sig <= 0.01 else "незначим")
    parts = []
    nsm, sce = _num(info.get("nsm")), _num(info.get("sce"))
    if nsm is not None:
        parts.append("смещение за период %s м" % ("%+.0f" % nsm).replace("-", "−"))
    if sce is not None:
        parts.append("размах положений %.0f м" % sce)
    if series["outliers"]:
        missing = [y for y, d in zip(series["years"], series["dist"]) if d is None]
        real = sorted(set(series["outliers"]) - set(missing))
        if real:
            parts.append("исключены годы: %s" % ", ".join(str(y) for y in real))
    cert = info.get("certainty")
    if cert not in (None, NULL):
        parts.append("надёжность: %s" % CERTAINTY_RU.get(str(cert), str(cert)))
    return text + ("<br>" + "; ".join(parts) if parts else "")


class PickTool(QgsMapTool):
    """Инструмент карты: выбор ближайшей к щелчку точки слоя темпов."""

    def __init__(self, canvas, callback):
        super().__init__(canvas)
        self.callback = callback
        self.setCursor(Qt.CrossCursor)

    def canvasReleaseEvent(self, event):
        self.callback(self.toMapCoordinates(event.pos()))


class ChartDock(QDockWidget):

    def __init__(self, iface):
        super().__init__("График смещения берега", iface.mainWindow())
        self.setObjectName("CoastlineDynamicsChart")
        self.iface = iface
        self.tool = PickTool(iface.mapCanvas(), self.pick)
        self.marker = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.PointGeometry)
        self.marker.setColor(QColor(255, 235, 0))
        self.marker.setStrokeColor(QColor(0, 0, 0))
        self.marker.setIconSize(14)
        self.marker.setWidth(2)
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(6, 6, 6, 6)
        row = QHBoxLayout()
        self.btn_pick = QPushButton("Выбрать точку на карте")
        self.btn_pick.setCheckable(True)
        self.btn_pick.toggled.connect(self.toggle_tool)
        self.btn_save = QPushButton("Сохранить график…")
        self.btn_save.clicked.connect(self.save_png)
        self.btn_save.setEnabled(False)
        row.addWidget(self.btn_pick)
        row.addWidget(self.btn_save)
        row.addStretch(1)
        lay.addLayout(row)
        self.chart = ChartWidget()
        lay.addWidget(self.chart, 1)
        self.label = QLabel("Точка не выбрана.")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.RichText)
        lay.addWidget(self.label)
        self.setWidget(body)
        self.tool.deactivated.connect(lambda: self.btn_pick.setChecked(False))

    def toggle_tool(self, on):
        canvas = self.iface.mapCanvas()
        if on:
            canvas.setMapTool(self.tool)
        elif canvas.mapTool() is self.tool:
            canvas.unsetMapTool(self.tool)

    def clear_marker(self):
        """Снимает с карты отметку выбранной точки."""
        self.marker.reset(QgsWkbTypes.PointGeometry)

    def _candidate_layers(self):
        layers = []
        active = self.iface.activeLayer()
        tree = QgsProject.instance().layerTreeRoot()
        for lyr in [active] + list(QgsProject.instance().mapLayers().values()):
            if not isinstance(lyr, QgsVectorLayer) or lyr in layers:
                continue
            if lyr.geometryType() != QgsWkbTypes.PointGeometry or lyr.fields().indexOf("rate_time") < 0:
                continue
            node = tree.findLayer(lyr.id())
            if node is not None and not node.isVisible():
                continue
            layers.append(lyr)
        return layers

    def pick(self, map_point):
        canvas = self.iface.mapCanvas()
        tol = canvas.mapUnitsPerPixel() * 8.0
        best = None
        for lyr in self._candidate_layers():
            xform = QgsCoordinateTransform(canvas.mapSettings().destinationCrs(), lyr.crs(), QgsProject.instance())
            try:
                pt = xform.transform(map_point)
                box = xform.transformBoundingBox(QgsRectangle(map_point.x() - tol, map_point.y() - tol,
                                                              map_point.x() + tol, map_point.y() + tol))
            except Exception:
                continue
            for feat in lyr.getFeatures(QgsFeatureRequest().setFilterRect(box)):
                d = feat.geometry().distance(QgsGeometry.fromPointXY(pt))
                if best is None or d < best[0]:
                    best = (d, feat, lyr)
        if best is None:
            self.label.setText("Рядом со щелчком нет точек слоя темпов. Слой должен быть видимым.")
            return
        self.show_feature(best[1], best[2])

    def show_feature(self, feature, layer):
        series = series_from_feature(feature)
        self.chart.set_series(series)
        self.label.setText(describe(series))
        self.btn_save.setEnabled(True)
        self.marker.reset(QgsWkbTypes.PointGeometry)
        self.marker.addGeometry(feature.geometry(), layer)

    def save_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить график", "", "Изображение PNG (*.png)")
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            self.chart.render_pixmap().save(path)

    def cleanup(self):
        self.toggle_tool(False)
        self.marker.reset(QgsWkbTypes.PointGeometry)
        self.iface.mapCanvas().scene().removeItem(self.marker)
