# -*- coding: utf-8 -*-
"""Правообладание: предупреждение видно в окне, на сайте и в инструкции."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import OWNER_NOTICE  # noqa: E402
from app.web.page import LOGIN_PAGE, dashboard_page  # noqa: E402


@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def test_notice_names_owner_and_contacts():
    assert "Арсений Скай" in OWNER_NOTICE
    assert "01.10.2026" in OWNER_NOTICE
    assert "@Sledak_69" in OWNER_NOTICE
    assert "sky404.exe_" in OWNER_NOTICE


def test_dashboard_page_footer_shows_owner_notice():
    page = dashboard_page({"today": {"seconds": 3600}, "days": []})
    assert "Арсений Скай" in page
    assert "@Sledak_69" in page
    assert "sky404.exe_" in page


def test_login_page_shows_owner_notice():
    assert "Арсений Скай" in LOGIN_PAGE
    assert "@Sledak_69" in LOGIN_PAGE


def test_instruction_file_mentions_owner():
    text = (ROOT / "Инструкция_для_админов.txt").read_text(encoding="utf-8")
    assert "Арсений Скай" in text
    assert "@Sledak_69" in text
    assert "sky404.exe_" in text


def test_home_panel_shows_owner_notice(qapp, monkeypatch):
    from PySide6.QtWidgets import QLabel

    from app.ui import dashboard as dash

    monkeypatch.setattr(
        dash, "current_streak",
        lambda *a, **k: SimpleNamespace(
            plan_hours=0, plan_reports=0, days=0, today_done=False,
        ),
    )
    core = SimpleNamespace(
        config=SimpleNamespace(
            require_duty=False, weekly_hours_norm=70, weekly_reports_norm=600,
            hotkey_add="f9", hotkey_remove="ctrl+f9",
        ),
        stats=SimpleNamespace(
            week_progress=lambda now: SimpleNamespace(
                stats=SimpleNamespace(online_seconds=0, reports=0),
                hours_percent=0.0, reports_percent=0.0,
            ),
            today=lambda now: SimpleNamespace(online_seconds=0, reports=0),
        ),
        session=SimpleNamespace(
            is_counting=False, is_game_running=False, is_on_duty=False,
        ),
    )
    panel = dash.DashboardPanel(core)
    texts = [w.text() for w in panel.findChildren(QLabel)]
    notice = [t for t in texts if "Арсений Скай" in t]
    assert notice, "на «Главной» должен быть текст о владельце"
    assert "@Sledak_69" in notice[0] and "sky404.exe_" in notice[0]
