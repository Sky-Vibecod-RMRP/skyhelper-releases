# -*- coding: utf-8 -*-
"""Баг-репорты №2 и №4: дождь в окне и курсор, одинаковый с сайтом.

Окно рисуется без экрана (QT_QPA_PLATFORM=offscreen), эффекты проверяются
теми же средствами, что и в программе: таймер дождя, pixmap курсора,
фильтр, возвращающий курсор окна над ссылками.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # без экрана и без окон

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, Qt   # noqa: E402
from PySide6.QtGui import QCursor                         # noqa: E402
from PySide6.QtWidgets import QApplication                # noqa: E402

from app.ui import cursor as cursor_mod                   # noqa: E402
from app.ui import rain as rain_mod                       # noqa: E402
from app.ui.helper_window import HelperWindow             # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    win = HelperWindow(theme_name="dark", output_dir=r"C:\Отчёты")
    win.resize(1000, 700)
    win.show()
    for _ in range(10):
        qapp.processEvents()
    yield win
    win.hide()


# --- баг-репорт №2: дождя в приложении не было -------------------------------


def test_rain_overlay_exists_and_cannot_steal_clicks(window):
    """Слой дождя создан, лежит поверх окна и прозрачен для мыши."""
    overlay = window._rain_overlay
    assert overlay is not None
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert not overlay.active              # выключен по умолчанию (настройка)
    assert overlay.geometry().size() == window.size()


def test_rain_switches_on_and_off(window):
    """Настойка «Дождь» запускает капли и останавливает их."""
    overlay = window._rain_overlay
    window.set_rain(True)
    assert overlay.active and overlay.isVisible()
    # плотность как на сайте: площадь / 26000, но не меньше 40 и не больше 160
    assert 40 <= len(overlay._drops) <= 160
    window.set_rain(False)
    assert not overlay.active and not overlay.isVisible()


def test_rain_follows_window_resize(qapp, window):
    """Капли пересчитываются под новый размер, слой повторяет окно."""
    overlay = window._rain_overlay
    window.set_rain(True)
    window.resize(760, 520)
    for _ in range(10):
        qapp.processEvents()
    assert overlay.geometry().size() == window.size()
    assert 40 <= len(overlay._drops) <= 160
    window.set_rain(False)


def test_rain_respects_reduced_motion(monkeypatch, window):
    """Как на сайте: системное «уменьшить анимацию» отключает дождь."""
    monkeypatch.setattr(rain_mod, "motion_allowed", lambda: False)
    window.set_rain(True)
    assert not window._rain_overlay.active


def test_rain_drops_move_and_respawn(window):
    """Капли падают вниз и родятся заново сверху — иначе дождь «заканчивается»."""
    overlay = window._rain_overlay
    window.set_rain(True)
    first = [drop[:] for drop in overlay._drops]
    overlay._tick()
    for before, after in zip(first, overlay._drops):
        if after[1] >= 0:                  # долетевшие просто падают дальше
            assert after[1] > before[1]
            assert after[0] > before[0]    # и по наклонной, как на сайте
    # капля, долетевшая до низа, должна родиться над окном, а не пропасть
    overlay._drops[0][1] = window.height() + 21
    overlay._tick()
    born = overlay._drops[0]
    assert born[1] < 0
    born[0] = 40                           # держим её внутри окна по горизонтали
    y_before = born[1]
    overlay._tick()
    assert overlay._drops[0][1] > y_before  # уже падает вниз
    window.set_rain(False)


# --- баг-репорт №4: курсор со временем становился стандартным ----------------


def test_white_cursor_is_drawn_like_the_site():
    """Белый кружок 14px с обводкой — тот же, что .sky-cursor-dot.white."""
    pixmap = cursor_mod.pixmap_for("white")
    assert pixmap is not None
    assert (pixmap.width(), pixmap.height()) == (cursor_mod.SIZE, cursor_mod.SIZE)
    image = pixmap.toImage()
    center = image.pixelColor(cursor_mod.CENTER, cursor_mod.CENTER)
    assert center.alpha() == 255 and center.red() > 240      # залитый кружок
    corner = image.pixelColor(1, 1)
    assert corner.alpha() < 10                               # углы прозрачны


def test_ring_and_off_cursors():
    """ring — кружок с кольцом, off — системный курсор (None)."""
    assert cursor_mod.pixmap_for("ring") is not None
    assert cursor_mod.pixmap_for("off") is None
    assert cursor_mod.cursor_for("off") is None


def test_cursor_hotspot_is_the_center():
    """Точка курсора — центр кружка: рисунок симметричный, указывает в точку."""
    custom = cursor_mod.cursor_for("white")
    assert isinstance(custom, QCursor)
    assert custom.hotSpot().x() == cursor_mod.CENTER
    assert custom.hotSpot().y() == cursor_mod.CENTER


def test_window_uses_the_drawn_cursor_and_can_drop_it(window):
    """Свой курсор ставится на всё окно, «Системный» возвращает стрелку."""
    custom = cursor_mod.cursor_for("white")
    window.set_custom_cursor(custom)
    assert window._custom_cursor is custom
    assert window.cursor().pixmap().cacheKey() == custom.pixmap().cacheKey()
    window.set_custom_cursor(None)
    assert window._custom_cursor is None
    assert window.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_system_hand_over_links_is_replaced(window):
    """Над ссылками Qt ставит «руку» — окно возвращает свой курсор.

    Именно так стандартный курсор и «проявлялся» в программе: текстовые
    списки (команды, правила, транспорт) — почти одни ссылки.
    """
    custom = cursor_mod.cursor_for("white")
    window.set_custom_cursor(custom)
    viewport = window._body.viewport()
    QCoreApplication.sendEvent(viewport, QEvent(QEvent.Type.CursorChange))
    assert viewport.cursor().pixmap().cacheKey() == custom.pixmap().cacheKey()

    # при виде «Системный» фильтр не мешает Qt делать по-своему
    window.set_custom_cursor(None)
    QCoreApplication.sendEvent(viewport, QEvent(QEvent.Type.CursorChange))
    assert viewport.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_settings_row_labels_match_reality():
    """Подписи в настройках больше не обещают «только сайт»."""
    from PySide6.QtWidgets import QLabel

    from app.config import Config
    from app.ui.settings_dialog import SettingsDialog

    class _Core:
        """Подмена ядра: настоящее трогает файлы в %APPDATA%."""

        def __init__(self) -> None:
            self.config = Config()
            self.web_running = False
            self.web_error = ""
            self.site_url = None

        def apply_config(self) -> None:
            pass

    dialog = SettingsDialog(_Core())
    try:
        labels = [widget.text() for widget in dialog.findChildren(QLabel)]
        assert "Дождь" in labels and "Курсор" in labels
        assert "Курсор на сайте" not in labels
        assert dialog._rain.text() == "Дождь на фоне сайта и в окне"
    finally:
        dialog.deleteLater()


def test_gui_main_wires_config_to_window(qapp):
    """Проводка gui_main: настройки доходят до окна, включая сброс.

    Именно её проверяет баг-репорт №4: курсор обязан оставаться кастомным
    после любого пути (старт программы, сохранение настроек), а дождь —
    включаться и выключаться тем же переключателем, что и на сайте.
    """
    from app.config import Config
    from app.gui_main import apply_window_effects
    from app.ui import theme as theme_mod

    win = HelperWindow(theme_name="midnight", output_dir=r"C:\Отчёты")
    win.resize(820, 600)
    win.show()
    try:
        cfg = Config()
        cfg.rain_enabled = True
        cfg.cursor_style = "white"
        apply_window_effects(win, cfg, "midnight")
        assert win._rain_overlay.active, "дождь должен включиться из конфига"
        assert win._custom_cursor is not None

        # «Системный» курсор и выключенный дождь — честный сброс
        cfg.rain_enabled = False
        cfg.cursor_style = "off"
        apply_window_effects(win, cfg, "midnight")
        assert not win._rain_overlay.active
        assert win._custom_cursor is None
        assert win.cursor().shape() == Qt.CursorShape.ArrowCursor

        # кольцо красится акцентом темы: midnight — фиолетовый, не циан
        cfg.cursor_style = "ring"
        apply_window_effects(win, cfg, "midnight")
        assert theme_mod.THEMES["midnight"]["accent"] == "#7c5cff"
        center = win._custom_cursor.pixmap().toImage().pixelColor(
            cursor_mod.CENTER, cursor_mod.CENTER)
        assert center.blue() > 180 and center.green() < 140
    finally:
        win.hide()
