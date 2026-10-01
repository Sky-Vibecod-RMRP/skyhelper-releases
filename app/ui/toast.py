"""Плашка в углу экрана поверх игры.

Не забирает фокус и пропускает клики, чтобы не мешать игре.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.ui import theme


class ToastOverlay(QWidget):
    MARGIN = 24

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setObjectName("toastRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet("#toastRoot { background: transparent; }")

        self._frame = QFrame(self)
        self._frame.setObjectName("toastFrame")
        self._label = QLabel(self._frame)
        self._label.setStyleSheet(
            f"color: {theme.TEXT}; font-family: 'Segoe UI'; font-size: 15px; "
            "font-weight: 600; padding: 10px 16px; background: transparent;"
        )
        inner = QVBoxLayout(self._frame)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(self._label)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._frame)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, ok: bool = True, duration_ms: int = 2500) -> None:
        color = theme.ACCENT if ok else theme.WARN
        self._frame.setStyleSheet(
            f"QFrame#toastFrame {{ background: rgba(13, 17, 23, 235); "
            f"border: 1px solid {color}; border-radius: 10px; }}"
        )
        self._label.setText(text)
        self.adjustSize()
        self._move_to_corner()
        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def _move_to_corner(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - self.MARGIN, area.top() + self.MARGIN)
