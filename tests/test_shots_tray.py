"""Пункт меню трея «Посмотреть недельный отчёт» — ровно один, без лишнего."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # без экрана и без окон

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.tray import create_tray  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    yield QApplication.instance() or QApplication([])


def _titles(tray) -> list[str]:
    menu = tray.contextMenu()
    return [action.text() for action in menu.actions()]


def test_week_report_item_is_present_and_fires(qapp):
    opened: list = []

    tray = create_tray(qapp, qapp, on_week_report=lambda: opened.append(1))
    titles = _titles(tray)
    menu = tray.contextMenu()

    assert titles.count("Посмотреть недельный отчёт") == 1
    index = titles.index("Посмотреть недельный отчёт")

    # Ни подменю, ни счётчиков, ни второго пункта про отчёт — только он один.
    assert menu.actions()[index].menu() is None
    assert [t for i, t in enumerate(titles)
            if i != index and ("отчёт" in t.lower() or "недел" in t.lower())] == []
    following = titles[index + 1] if index + 1 < len(titles) else None
    assert following in (None, "", "Выход"), f"за пунктом лишнее: {following!r}"

    menu.actions()[index].trigger()
    assert opened == [1]
    tray.deleteLater()


def test_week_report_item_is_absent_without_handler(qapp):
    tray = create_tray(qapp, qapp)
    assert "Посмотреть недельный отчёт" not in _titles(tray)
    tray.deleteLater()
