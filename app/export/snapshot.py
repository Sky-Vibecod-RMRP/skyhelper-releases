"""Снимок статистики для экспорта: собирается заново из базы при каждом обновлении."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from app.config import Config
from app.stats.service import PeriodStats, StatsService, WeekProgress
from app.stats.weeks import day_bounds, week_bounds
from app.storage.db import Database


@dataclass(frozen=True)
class DayRow:
    day: date
    online_seconds: int
    reports: int


@dataclass(frozen=True)
class WeekRow:
    """Одна неделя из истории: для листа «Динамика»."""
    week_start: date
    online_seconds: int
    reports: int


HISTORY_WEEKS = 8  # сколько недель показывать в истории


@dataclass(frozen=True)
class Snapshot:
    generated_at: int
    week_start: date
    week_end: date          # последний день недели включительно
    week: WeekProgress
    days: list[DayRow]      # новые дни сверху
    prev_week: PeriodStats  # прошлая неделя целиком
    month_start: date       # первый день текущего месяца
    month: PeriodStats      # с 1-го числа по конец месяца (учтено то, что уже было)
    month_hours_norm: float     # недельная норма, пересчитанная на дни месяца
    month_reports_norm: float
    # --- поля ниже заполняются автоматом, существующие вызовы их не передают ---
    today: PeriodStats = PeriodStats(0, 0)   # факт за сегодня (для блока «Темп»)
    elapsed_days: int = 1                    # сколько дней недели уже прошло
    history: list[WeekRow] = field(default_factory=list)  # эта неделя сверху


def _local_date(ts: int) -> date:
    return datetime.fromtimestamp(ts).date()


def build_snapshot(stats: StatsService, db: Database, config: Config, now: int) -> Snapshot:
    week_start_ts, _ = week_bounds(now, config.week_start_weekday)
    week_start = _local_date(week_start_ts)

    today = _local_date(now)
    first = db.first_activity_ts()
    first_day = _local_date(first) if first is not None else today

    days: list[DayRow] = []
    day = today
    while day >= first_day:
        # берём полдень дня, чтобы переход на летнее время не сбивал границы
        start, end = day_bounds(datetime(day.year, day.month, day.day, 12).timestamp())
        period = stats.between(start, end, now)
        if period.online_seconds or period.reports or day == today:
            days.append(DayRow(day, period.online_seconds, period.reports))
        day -= timedelta(days=1)

    # Прошлая неделя: берём момент за 12 часов до начала этой недели (это воскресенье).
    prev_start, prev_end = week_bounds(week_start_ts - 12 * 3600, config.week_start_weekday)
    prev_week = stats.between(prev_start, prev_end, now)

    month_first = today.replace(day=1)
    next_month = (month_first + timedelta(days=32)).replace(day=1)
    month_start_ts = int(datetime(month_first.year, month_first.month, 1).timestamp())
    month_end_ts = int(datetime(next_month.year, next_month.month, 1).timestamp())
    month = stats.between(month_start_ts, month_end_ts, now)
    days_in_month = (next_month - month_first).days

    # Сколько дней недели уже прошло (для темпа и прогноза).
    last_day = min(today, week_start + timedelta(days=6))
    elapsed_days = max(1, (last_day - week_start).days + 1)

    # История недель: от текущей назад. Полдень понедельника гарантированно
    # попадает в свою неделю даже при переводе часов.
    history: list[WeekRow] = []
    for i in range(HISTORY_WEEKS):
        noon = week_start_ts - i * 7 * 86400 + 12 * 3600
        start, end = week_bounds(noon, config.week_start_weekday)
        period = stats.between(start, end, now)
        history.append(WeekRow(_local_date(start), period.online_seconds, period.reports))

    return Snapshot(
        generated_at=now,
        week_start=week_start,
        week_end=week_start + timedelta(days=6),
        week=stats.week_progress(now),
        days=days,
        prev_week=prev_week,
        month_start=month_first,
        month=month,
        month_hours_norm=config.weekly_hours_norm * days_in_month / 7,
        month_reports_norm=config.weekly_reports_norm * days_in_month / 7,
        today=stats.today(now),
        elapsed_days=elapsed_days,
        history=history,
    )
