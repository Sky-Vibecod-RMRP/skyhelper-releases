from datetime import date, datetime, timedelta

import pytest

from app.config import Config
from app.stats.service import StatsService
from app.stats.streak import current_streak, day_plan, is_day_done
from app.storage.db import Database

TODAY = date(2026, 9, 29)          # вторник
NOW = int(datetime(2026, 9, 29, 21, 0).timestamp())


@pytest.fixture
def env(tmp_path):
    config = Config(weekly_hours_norm=70.0, weekly_reports_norm=600)
    db = Database(tmp_path / "streak.db")
    stats = StatsService(db, config)
    yield config, db, stats
    db.close()


def fill_day(db, day: date, hours: float, reports: int) -> None:
    """Записать день с заданным онлайном и числом обращений."""
    start = int(datetime(day.year, day.month, day.day, 8).timestamp())
    sid = db.open_session(start)
    db.close_session(sid, start + int(hours * 3600))
    for i in range(reports):
        db.add_report_event(start + 60 + i, 1)


def back(days: int) -> date:
    return TODAY - timedelta(days=days)


def test_day_plan_is_weekly_norm_divided_by_seven(env):
    config, _, _ = env
    assert day_plan(config) == (10.0, 86)  # 600 / 7 = 85.7 → 86


def test_empty_norms_give_no_streak(env):
    config, db, stats = env
    config.weekly_hours_norm = 0
    config.weekly_reports_norm = 0
    assert day_plan(config) == (0.0, 0)
    assert not is_day_done(stats, config, back(1), NOW)
    assert current_streak(stats, config, NOW).days == 0


def test_streak_counts_completed_days_ending_yesterday(env):
    config, db, stats = env
    fill_day(db, back(1), 10, 86)
    fill_day(db, back(2), 11, 90)
    fill_day(db, back(3), 10, 86)
    result = current_streak(stats, config, NOW)
    assert result.days == 3
    assert not result.today_done
    assert result.in_progress  # сегодня ещё идёт — стрик не сломан


def test_today_counts_only_when_already_done(env):
    config, db, stats = env
    fill_day(db, back(1), 10, 86)
    fill_day(db, TODAY, 10, 86)
    result = current_streak(stats, config, NOW)
    assert result.days == 2
    assert result.today_done


def test_gap_breaks_the_streak(env):
    config, db, stats = env
    fill_day(db, back(1), 10, 86)
    fill_day(db, back(2), 10, 86)
    fill_day(db, back(3), 0, 0)   # дырка
    fill_day(db, back(4), 10, 86)
    assert current_streak(stats, config, NOW).days == 2


def test_day_without_reports_is_not_done(env):
    config, db, stats = env
    fill_day(db, back(1), 12, 0)      # часы есть, обращений нет
    assert not is_day_done(stats, config, back(1), NOW)
    assert current_streak(stats, config, NOW).days == 0

    fill_day(db, back(1), 10, 86)     # теперь норма дня закрыта
    assert is_day_done(stats, config, back(1), NOW)
    assert current_streak(stats, config, NOW).days == 1


def test_today_alone_makes_streak_one(env):
    config, db, stats = env
    fill_day(db, TODAY, 10, 86)
    fill_day(db, back(1), 0, 0)
    result = current_streak(stats, config, NOW)
    assert result.days == 1
    assert result.today_done


def test_streak_survives_long_history_without_scanning_forever(env):
    config, db, stats = env
    for offset in range(1, 40):           # почти два месяца нормы подряд
        fill_day(db, back(offset), 10, 86)
    assert current_streak(stats, config, NOW).days == 39
