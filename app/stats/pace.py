"""Темп: плановая норма на день и сообщение о выполнении."""
from __future__ import annotations

from app.config import Config
from app.stats.service import PeriodStats
from app.util import format_duration

DAYS_IN_WEEK = 7


def daily_plan(config: Config) -> tuple[float, float]:
    """Норма на день = недельная норма / 7 (часы, обращения)."""
    return (
        config.weekly_hours_norm / DAYS_IN_WEEK,
        config.weekly_reports_norm / DAYS_IN_WEEK,
    )


def pace_message(today: PeriodStats, config: Config) -> str:
    plan_hours, plan_reports = daily_plan(config)
    hours_pct = today.online_hours / plan_hours * 100 if plan_hours > 0 else 0
    reports_pct = today.reports / plan_reports * 100 if plan_reports > 0 else 0
    return (
        f"Темп за сегодня\n"
        f"Онлайн {hours_pct:.0f}%: {format_duration(today.online_seconds)} из {plan_hours:g} ч\n"
        f"Обращения {reports_pct:.0f}%: {today.reports} из {round(plan_reports)}"
    )
