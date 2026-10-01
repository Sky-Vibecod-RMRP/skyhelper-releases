# -*- coding: utf-8 -*-
"""Дождь в окне программы — то же, что canvas на сайте (``_RAIN_JS``).

Капли рисуются поверх окна, как дождь на стекле, но сами клики не
перехватывают (:class:`RainOverlay` прозрачен для мыши). Плотность,
скорость, наклон и цвет взяты с сайта один в один, чтобы эффект был
узнаваемым; как и на сайте, дождь выключается, если в системе включено
«уменьшить анимацию».
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

#: Цвет капли с сайта: rgba(210, 232, 244, alpha).
_RAIN_COLOR = (210, 232, 244)

#: Наклон капли (d.x += d.speed * tilt) — как в _RAIN_JS.
_TILT = 0.16

#: Интервал кадра в миллисекундах. На сайте кадр идёт через rAF (~60 fps),
#: здесь таймером; скорость капель пересчитывается из «пикселей за кадр 60 fps».
_INTERVAL_MS = 20
_SITE_FPS = 60


def motion_allowed() -> bool:
    """Разрешена ли анимация в системе (Windows: «эффекты анимации»).

    На сайте та же проверка — ``matchMedia('(prefers-reduced-motion: reduce)')``.
    """
    try:
        return bool(QGuiApplication.styleHints().animationEnabled())
    except Exception:                                            # noqa: BLE001
        return True


class RainOverlay(QWidget):
    """Прозрачный для мыши слой с каплями дождя поверх окна."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Клики, наведение и фокус уходят мимо — дождь только рисуется.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        # Ничего не заливаем самим: видно родительское окно сквозь нас.
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
        self.setObjectName("rain-overlay")
        #: Капля: [x, y, длина, скорость, прозрачность].
        self._drops: list[list[float]] = []
        self._timer = QTimer(self)
        self._timer.setInterval(_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    @property
    def active(self) -> bool:
        """Крутится ли анимация (для тестов и настроек)."""
        return self._timer.isActive()

    # --- жизненный цикл -----------------------------------------------------

    def set_enabled(self, enabled: bool) -> None:
        """Включить/выключить дождь (с учётом системного «уменьшить анимацию»)."""
        if enabled and not motion_allowed():
            enabled = False
        if enabled:
            self._rebuild()
            self._timer.start()
            self.show()
        else:
            self._timer.stop()
            self.hide()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802 (имя задано Qt)
        super().resizeEvent(event)
        if self._drops:
            self._rebuild()

    # --- капли --------------------------------------------------------------

    def _rebuild(self) -> None:
        """Пересобрать капли под текущий размер окна.

        Плотность та же, что на сайте: площадь / 26000, но не меньше 40 и
        не больше 160 — иначе большое окно превращается в белёсую кашу.
        """
        width = max(self.width(), 1)
        height = max(self.height(), 1)
        want = round(width * height / 26000)
        want = max(40, min(160, want))
        self._drops = [self._new_drop(width, height, anywhere=True)
                       for _ in range(want)]

    @staticmethod
    def _new_drop(width: int, height: int, anywhere: bool) -> list[float]:
        import random

        return [
            random.random() * (width + 120) - 60,
            random.random() * height if anywhere else -20 - random.random() * 90,
            9 + random.random() * 16,        # длина капли
            5.5 + random.random() * 6.5,     # скорость, пикс/кадр при 60 fps
            0.10 + random.random() * 0.16,   # прозрачность
        ]

    def _tick(self) -> None:
        width = max(self.width(), 1)
        height = max(self.height(), 1)
        # Сайт сдвигает капли на «скорость» за кадр 60 fps; здесь кадр реже,
        # поэтому пересчитываем в пиксели за наш интервал.
        step = 1000 / (_INTERVAL_MS * _SITE_FPS)
        for index, drop in enumerate(self._drops):
            drop[1] += drop[3] * step
            drop[0] += drop[3] * step * _TILT
            if drop[1] > height + 20 or drop[0] > width + 40:
                self._drops[index] = self._new_drop(width, height, anywhere=False)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (имя задано Qt)
        if not self._drops:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(QColor(*_RAIN_COLOR), 1))
        for x, y, length, _speed, alpha in self._drops:
            painter.setOpacity(alpha)
            painter.drawLine(QPointF(x, y),
                             QPointF(x - length * _TILT, y - length))
        painter.setOpacity(1.0)
