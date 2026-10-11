# -*- coding: utf-8 -*-
"""Язык интерфейса модуля: русский или английский.

Строки в коде записаны по-русски. Функция tr() возвращает их как есть, если QGIS
работает на русском языке, и перевод из словаря i18n_en.EN во всех остальных случаях:
для пользователя, у которого интерфейс QGIS не русский, английский понятнее русского.

Язык определяется один раз, при первой загрузке модуля. Расчётное ядро от QGIS не
зависит, поэтому вне QGIS язык берётся из настроек системы. Переменная окружения
COASTDYN_LANG (ru или en) задаёт язык принудительно: это нужно для проверок.
"""
import os

LANGUAGES = ("ru", "en")
_language = "ru"
_table = None


def _qgis_locale():
    """Язык, на котором сейчас работает окно QGIS; пустая строка, если QGIS не запущен."""
    try:
        from qgis.core import QgsApplication
    except ImportError:
        return ""
    app = QgsApplication.instance()
    if app is not None:
        try:
            name = app.translation()          # учитывает и ключ запуска --lang, и настройки профиля
            if name:
                return name
        except Exception:
            pass
    try:
        return QgsApplication.locale() or ""
    except Exception:
        return ""


def detect():
    """Код языка интерфейса: ru, если QGIS (или система) работает на русском, иначе en."""
    forced = os.environ.get("COASTDYN_LANG", "").strip().lower()[:2]
    if forced in LANGUAGES:
        return forced
    name = _qgis_locale()
    if not name:
        import locale
        try:
            name = locale.getlocale()[0] or ""
        except Exception:
            name = ""
    return "ru" if name.lower().startswith(("ru", "russian")) else "en"


def set_language(code):
    global _language
    if code not in LANGUAGES:
        raise ValueError("Unknown interface language: %s" % code)
    _language = code


def language():
    return _language


def tr(text):
    """Строка интерфейса на языке пользователя. Без перевода в словаре остаётся русской."""
    global _table
    if _language == "ru":
        return text
    if _table is None:
        from .i18n_en import EN
        _table = EN
    return _table.get(text, text)


def dec(number_text):
    """Число, записанное с десятичной точкой, в принятой для языка записи: в русском — с запятой."""
    return number_text.replace(".", ",") if _language == "ru" else number_text


set_language(detect())
