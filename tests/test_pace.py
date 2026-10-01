from app.config import Config
from app.stats.pace import daily_plan, pace_message
from app.stats.service import PeriodStats


def test_daily_plan_is_weekly_norm_divided_by_seven():
    hours, reports = daily_plan(Config())
    assert hours == 10.0
    assert round(reports) == 86


def test_pace_message_shows_percent_and_plan():
    message = pace_message(PeriodStats(online_seconds=6 * 3600, reports=43), Config())
    assert "Онлайн 60%" in message
    assert "6 ч 00 мин из 10 ч" in message
    assert "Обращения 50%" in message
    assert "43 из 86" in message


def test_pace_message_with_zero_norm_does_not_crash():
    config = Config(weekly_hours_norm=0, weekly_reports_norm=0)
    assert "0%" in pace_message(PeriodStats(0, 0), config)
