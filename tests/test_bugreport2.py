"""Тесты по второму баг-репорту (30.09.2026, вечер).

Проверяем ровно то, что было сломано на скриншотах: белая системная
плашка, невозможность растянуть окно, синяя рамка на кнопке дежурства,
разъезжающиеся фото транспорта и поиск по правилам из двух букв.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.catalog import data as cat_data
from app.help import data as help_data

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

PALETTE = {"card": "#161b22", "border": "#30363d", "accent": "#38bdf8",
           "muted": "#8b98a9", "text": "#edeef1", "field": "#0b0c0e",
           "success": "#3fb950", "danger": "#f85149"}


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


# --- баг №2 и №3: белая плашка Windows и невозможность растянуть окно ------


def test_helper_window_has_no_system_frame(qapp):
    """Системная белая плашка висела потому, что окно не было безрамочным."""
    from app.ui.helper_window import HelperWindow

    window = HelperWindow()
    try:
        assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
        assert window.testAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        ), "без прозрачного фона Windows рисует белую полосу по краю"
        assert window._title_bar is not None, "у окна должна быть своя шапка"
    finally:
        window.close()


def test_helper_window_can_be_resized(qapp):
    from app.ui.helper_window import HelperWindow

    window = HelperWindow()
    try:
        assert window._resizable is True
        assert window._edge_dir == 0
        window.resize(1400, 900)
        assert window.width() == 1400
    finally:
        window.close()


def test_closing_helper_hides_it_instead_of_quitting(qapp):
    from PySide6.QtGui import QCloseEvent

    from app.ui.helper_window import HelperWindow

    window = HelperWindow()
    try:
        event = QCloseEvent()
        window.closeEvent(event)
        assert not event.isAccepted(), "крестик не должен закрывать программу"
    finally:
        window.deleteLater()


# --- баг №1: синяя рамка вокруг кнопки дежурства --------------------------


def test_duty_button_has_no_glow_while_off(qapp, monkeypatch):
    """Эффект свечения навешивается только на время дежурства."""
    from app.ui.helper_window import HelperWindow

    window = HelperWindow()
    try:
        assert window._duty.graphicsEffect() is None, (
            "на выключенной кнопке эффект даёт синюю рамку — вешаем по необходимости"
        )
    finally:
        window.close()


# --- баг №5: фото транспорта разъезжались и перекрывали текст --------------


def test_transport_photo_has_fixed_size_and_own_line():
    html = cat_data.row_html("gt", 0, 0, PALETTE)
    # QTextBrowser не понимает max-width: фото вылезало за карточку.
    assert "max-width" not in html
    assert f'width="{cat_data.PHOTO_WIDTH}"' in html
    # img идёт строчным элементом — без обёртки текст вставал рядом.
    assert html.index("<div style=\"margin:6px 0 7px 0;\">") < html.index("<img")


def test_transport_photo_width_is_reasonable():
    assert 160 <= cat_data.PHOTO_WIDTH <= 360, "фото должно помещаться в карточку"


# --- баг №4: поиск по правилам из двух букв (например «DM») -----------------


def _found(query: str) -> int:
    return sum(len(cat["items"]) for cat in help_data.filter_rules(query))


def test_two_letter_query_finds_rules():
    """«DM» — ровно тот запрос, который не находил ничего."""
    assert _found("DM") > 0
    assert _found("дп") > 0


def test_common_two_letter_queries_are_not_noise():
    """«по», «не», «ин» встречаются почти везде — ими полнота не нужна."""
    for query in ("по", "не", "ин", "на"):
        assert _found(query) < 10, f"«{query}» находит слишком много"


def test_long_queries_still_work():
    assert _found("допрос") > 0
    assert _found("война") > 0
    assert _found("правило 12") > 0


def test_short_stem_allow_list_is_measured_from_the_rules():
    rules = help_data.load_rules()
    allow = help_data._short_stems("DM по не", rules)
    assert "dm" in allow
    assert "по" not in allow
    assert "не" not in allow
