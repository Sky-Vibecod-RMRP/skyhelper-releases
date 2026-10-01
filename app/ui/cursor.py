# -*- coding: utf-8 -*-
"""Кастомный курсор окна — тот же рисунок, что на сайте (``_CURSOR_JS`` + CSS).

Вид выбирается в настройках программы (``config.cursor_style``), поэтому
окно и сайт выглядят одинаково:

* ``white`` — белый кружок 14px с тёмной обводкой 1.5px и мягким свечением
  (так на сайте выглядят ``.sky-cursor-dot.white``);
* ``ring`` — кружок 6px акцентного цвета в кольце 32px (``.sky-cursor-dot``
  и ``.sky-cursor-ring``);
* ``off`` — None: остаётся системный курсор.

Картинку рисуем сами, а не берём из ``web/static/img/cursors/cursor.png``:
старый PNG со временем «пропадал» и курсор становился стандартным
(баг-репорт №4), а рисованный кружок не зависит от файлов рядом с exe.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap

from app.ui import theme

#: Холст 36x36: 14px кружок + обводка + свечение 10px, то же место под
#: кольцо 32px. Центр холста — точка, за которую окно «держит» курсор.
SIZE = 36
CENTER = SIZE // 2


def _color(value: str, alpha: int = 255) -> QColor:
    color = QColor(value)
    color.setAlpha(alpha)
    return color


def _sheet() -> QPixmap:
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def white_pixmap() -> QPixmap:
    """Белый кружок: свечение, тёмная обводка, заливка — как в CSS."""
    pixmap = _sheet()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    center = QPointF(CENTER, CENTER)
    # box-shadow: 0 0 10px rgba(255, 255, 255, 0.35) — десять колец,
    # каждое тусклее предыдущего, читается как мягкий ореол.
    for step in range(10):
        fade = (1 - step / 10) ** 2
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, int(255 * 0.35 * fade)), 1))
        painter.drawEllipse(center, 8.5 + step, 8.5 + step)
    # box-shadow: 0 0 0 1.5px rgba(0, 0, 0, 0.55) — обводка, чтобы кружок
    # был виден и на светлых превью, и на тёмном фоне.
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(0, 0, 0, 140), 1.5))
    painter.drawEllipse(center, 7.75, 7.75)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255))
    painter.drawEllipse(center, 7, 7)   # width: 14px
    painter.end()
    return pixmap


def ring_pixmap(accent: str) -> QPixmap:
    """Кольцо 32px (opacity 0.7) и кружок 6px (opacity 0.9) акцентного цвета."""
    pixmap = _sheet()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    center = QPointF(CENTER, CENTER)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(_color(accent, 179), 2))     # 0.7 * 255 ≈ 179
    painter.drawEllipse(center, 15, 15)              # диаметр 32px
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_color(accent, 230))            # 0.9 * 255 ≈ 230
    painter.drawEllipse(center, 3, 3)                # диаметр 6px
    painter.end()
    return pixmap


def pixmap_for(style: str, accent: str = theme.ACCENT) -> QPixmap | None:
    """Холст курсора для вида из настроек; None — системный курсор."""
    if style == "white":
        return white_pixmap()
    if style == "ring":
        return ring_pixmap(accent)
    return None                               # «off»


def cursor_for(style: str, accent: str = theme.ACCENT) -> QCursor | None:
    """Курсор окна для вида из настроек; None — оставить системный.

    Горячая точка — центр кружка: рисунок симметричный, поэтому курсор
    указывает ровно туда, куда ставит его система.
    """
    pixmap = pixmap_for(style, accent)
    if pixmap is None:
        return None
    return QCursor(pixmap, CENTER, CENTER)
