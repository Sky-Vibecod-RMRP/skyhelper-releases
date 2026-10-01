"""Стрик: сколько дней подряд выполнена дневная норма.

День считается выполненным, если в нём набраны И часы, И обращения
не меньше дневного плана (недельная норма / 7). Сегодняшний день
не ломает стрик, пока не закончился: он показывается отдельно.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.config import Config
from app.stats.pace import daily_plan
from app.stats.service import StatsService
from app.stats.weeks import day_bounds

MAX_LOOKBACK_DAYS = 365  # чтобы не гонять базу по году в бесконечном цикле


@dataclass(frozen=True)
class Streak:
    days: int                 # выполненных дней подряд (сегодня, если уже выполнен, + прошлые)
    today_done: bool          # сегодняшняя норма уже закрыта
    plan_hours: float         # дневной план по часам
    plan_reports: int         # дневной план по обращениям

    @property
    def in_progress(self) -> bool:
        """Сегодня ещё идёт и норма пока не закрыта."""
        return not self.today_done


def day_plan(config: Config) -> tuple[float, int]:
    """Дневной план (часы, обращения). Деление общее с «темпом», но обращения округлены."""
    hours, reports = daily_plan(config)
    return hours, round(reports)


def _noon(day: date) -> int:
    """Полдень дня — чтобы границы дня не съехали при переводе часов."""
    return int(datetime(day.year, day.month, day.day, 12).timestamp())


def is_day_done(stats: StatsService, config: Config, day: date, now: int) -> bool:
    """Выполнена ли норма за конкретный календарный день."""
    plan_hours, plan_reports = day_plan(config)
    if plan_hours <= 0 and plan_reports <= 0:
        return False  # нормы не заданы — считать стрик бессмысленно
    start, end = day_bounds(_noon(day))
    period = stats.between(start, end, now)
    hours_ok = plan_hours <= 0 or period.online_hours >= plan_hours
    reports_ok = plan_reports <= 0 or period.reports >= plan_reports
    return hours_ok and reports_ok


def current_streak(stats: StatsService, config: Config, now: int) -> Streak:
    """Считает стрик: сегодня (если уже выполнен), затем дни назад."""
    plan_hours, plan_reports = day_plan(config)
    today = datetime.fromtimestamp(now).date()
    today_done = is_day_done(stats, config, today, now)

    days = 1 if today_done else 0
    day = today - timedelta(days=1)
    for _ in range(MAX_LOOKBACK_DAYS):
        if not is_day_done(stats, config, day, now):
            break
        days += 1
        day -= timedelta(days=1)
    return Streak(days=days, today_done=today_done,
                  plan_hours=plan_hours, plan_reports=plan_reports)
