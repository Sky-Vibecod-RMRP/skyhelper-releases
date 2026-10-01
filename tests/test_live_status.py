import json
from datetime import datetime

from app.config import Config
from app.services.live_status import build_status
from app.stats.service import StatsService
from app.storage.db import Database
from app.tracker.session_service import SessionService
from app.web.page import dashboard_page

NOW = int(datetime(2026, 9, 29, 21, 0).timestamp())  # вторник, 29.09.2026


def make_env(tmp_path, **overrides):
    config = Config(**overrides)
    db = Database(tmp_path / "live.db")
    session = SessionService(db, config)
    stats = StatsService(db, config)
    return config, db, session, stats


def fill_today(db, hours: float, reports: int) -> None:
    start = int(datetime(2026, 9, 29, 8, 0).timestamp())
    sid = db.open_session(start)
    db.close_session(sid, start + int(hours * 3600))
    for i in range(reports):
        db.add_report_event(start + 60 + i, 1)


def test_status_matches_page_schema(tmp_path):
    """Ключи ровно те, что ждёт app.web.page — иначе страница покажет нули."""
    config, db, session, stats = make_env(tmp_path)
    try:
        status = build_status(stats, session, config, NOW)
        for key in ("date", "weekday", "week", "today", "week_stats",
                    "streak", "flags", "days"):
            assert key in status, key
        assert isinstance(status["week"], str) and status["week"].startswith("28.09")
        assert set(status["flags"]) >= {"duty", "game", "counting"}
        assert set(status["today"]) >= {"seconds", "reports", "plan_seconds"}
        assert set(status["week_stats"]) >= {"seconds", "reports",
                                             "hours_percent", "reports_percent"}
        assert set(status["streak"]) >= {"days", "today_done"}
        # Папка с отчётами нужна хелперу (в окне и на сайте).
        assert status["output_dir"]
        # Рендер страницы на реальных данных не должен падать.
        page = dashboard_page(status)
        assert "SKY-GRAFANA.RMRP" in page and "СЕГОДНЯ" in page
        assert "29.09.2026" in page
        # Отдаём живой JSON — значит, он обязан сериализоваться.
        assert json.dumps(status, ensure_ascii=False)
    finally:
        db.close()


def test_today_and_week_numbers_match_stats(tmp_path):
    config, db, session, stats = make_env(tmp_path, weekly_hours_norm=70.0,
                                           weekly_reports_norm=600)
    try:
        fill_today(db, 3.6, 5)
        status = build_status(stats, session, config, NOW)
        today = status["today"]
        assert today["seconds"] == int(3.6 * 3600)
        assert today["reports"] == 5
        assert today["text"] == "3 ч 36 мин"
        assert today["plan_hours"] == 10.0
        assert today["plan_seconds"] == 36000
        assert today["plan_reports"] == 86
        assert today["hours_pct"] == 36.0
        assert status["week_stats"]["reports"] == 5
        assert status["week_stats"]["hours_norm"] == 70.0
    finally:
        db.close()


def test_seven_days_are_ordered_oldest_to_today(tmp_path):
    config, db, session, stats = make_env(tmp_path)
    try:
        status = build_status(stats, session, config, NOW)
        days = status["days"]
        assert len(days) == 7
        assert days[-1]["is_today"] is True
        assert days[0]["is_today"] is False
        assert days[0]["date"] == "23.09"
        assert days[-1]["date"] == "29.09"
        assert days[-1]["label"] == "29.09 Вт"
        assert [d["weekday"] for d in days[-3:]] == ["Вс", "Пн", "Вт"]
    finally:
        db.close()


def test_session_flags_reflect_reality(tmp_path):
    config, db, session, stats = make_env(tmp_path, require_duty=False)
    try:
        status = build_status(stats, session, config, NOW)
        assert status["flags"]["game"] is False
        assert status["flags"]["counting"] is False

        session.tick(True)          # игра запущена, дежурство не нужно
        status = build_status(stats, session, config, NOW)
        assert status["flags"]["game"] is True
        assert status["flags"]["counting"] is True
        assert status["flags"]["require_duty"] is False
    finally:
        db.close()


def test_streak_block_present(tmp_path):
    config, db, session, stats = make_env(tmp_path)
    try:
        fill_today(db, 10, 86)      # сегодняшняя норма закрыта
        status = build_status(stats, session, config, NOW)
        assert status["streak"]["days"] == 1
        assert status["streak"]["today_done"] is True
        assert status["streak"]["in_progress"] is False
        assert status["today"]["done"] is True
        assert status["days"][-1]["done"] is True
    finally:
        db.close()


def test_empty_norms_do_not_divide_by_zero(tmp_path):
    config, db, session, stats = make_env(tmp_path, weekly_hours_norm=0,
                                           weekly_reports_norm=0)
    try:
        status = build_status(stats, session, config, NOW)
        assert status["today"]["hours_pct"] == 0.0
        assert status["today"]["plan_seconds"] == 0
        assert status["week_stats"]["reports_percent"] == 0.0
        assert status["streak"]["days"] == 0
    finally:
        db.close()
