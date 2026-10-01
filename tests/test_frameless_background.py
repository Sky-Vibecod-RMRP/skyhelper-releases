"""Окно не должно просвечивать насквозь (срочный баг-репорт 30.09.2026).

Когда окно сделали безрамочным, ему включили прозрачный фон — чтобы убрать
белую полосу Windows по краю. Но с прозрачным фоном Windows больше НЕ
заливает окно системной кистью: без собственной отрисовки окно стало
полностью прозрачным, был виден рабочий стол, а заголовок и карточки висели
поверх пустоты.

Правило теперь общее и живёт в миксине безрамочных окон, чтобы настройки
не превратились в стекло следом.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def test_frameless_mixin_draws_background():
    """Общее правило: любое окно без системной рамки рисует свой фон."""
    from app.ui.frameless import FramelessMixin

    assert hasattr(FramelessMixin, "paintEvent"), (
        "без своей отрисовки окно с прозрачным фоном будет стеклом"
    )


def test_helper_window_is_opaque(qapp):
    """Ни один пиксель окна не прозрачный, а фон окна — цвет темы."""
    from app.ui import theme
    from app.ui.helper_window import HelperWindow

    window = HelperWindow()
    window.resize(1000, 640)
    window.show()
    qapp.processEvents()
    try:
        image = window.grab().toImage()
        seen = set()
        for x in range(280, window.width() - 6, 40):
            for y in range(40, window.height() - 6, 40):
                pixel = image.pixelColor(x, y)
                assert pixel.alpha() == 255, f"прозрачный пиксель в ({x}, {y})"
                seen.add(pixel.name().lower())
        assert theme.BG.lower() in seen, f"фон окна не нарисован: {sorted(seen)[:6]}"
    finally:
        window.close()


def test_settings_window_is_opaque(qapp):
    """Настройки — тоже окно без системной рамки, значит правило то же."""
    from app.config import Config
    from app.ui.settings_dialog import SettingsDialog

    class _Session:
        def set_duty(self, on: bool) -> None:
            pass

    class _Core:
        def __init__(self) -> None:
            self.config = Config()
            self.session = _Session()
            self.web_running = False
            self.web_error = ""
            self.site_url = None

    dialog = SettingsDialog(_Core())
    dialog.resize(760, 520)
    dialog.show()
    qapp.processEvents()
    try:
        image = dialog.grab().toImage()
        for x in range(10, dialog.width() - 10, 60):
            for y in range(10, dialog.height() - 10, 60):
                assert image.pixelColor(x, y).alpha() == 255, (
                    f"настройки прозрачные в ({x}, {y})"
                )
    finally:
        dialog.close()
