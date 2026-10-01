"""Живой статус для сайта: один словарь, который отдаётся в JSON.

Схема согласована с ``app.web.page`` (см. докстринг того модуля): ключи
``date/weekday/week/today/week_stats/streak/flags/days``. Лишние поля
(``plan_hours``, ``in_progress``, ``is_today``…) добавлены сверх схемы —
страница их просто игнорирует.

Ничего не пишет на диск и не держит состояние — просто читает базу на каждый
запрос, поэтому веб-сервер можно спокойно перезапускать и дергать откуда угодно.
"""
from __future__ import annotations

import time
from datetime import datetime

from app.config import Config
from app.paths import default_output_dir
from app.stats.service import StatsService
from app.stats.streak import current_streak, day_plan
from app.stats.weeks import day_bounds, week_bounds
from app.tracker.session_service import SessionService
from app.util import format_duration

DAYS_IN_VIEW = 7  # сколько последних дней рисуем на сайте

_WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _percent(value: float, norm: float) -> float:
    return round(value / norm * 100, 1) if norm > 0 else 0.0


def _day_view(stats: StatsService, config: Config, now: int, offset: int) -> dict:
    """Один календарный день: 0 = сегодня, 1 = вчера и т.д."""
    base = datetime.fromtimestamp(now)
    label = datetime(base.year, base.month, base.day, 12).timestamp() - offset * 86400
    start, end = day_bounds(label)
    period = stats.between(start, end, now)
    local = datetime.fromtimestamp(label)
    plan_hours, plan_reports = day_plan(config)
    hours_ok = plan_hours <= 0 or period.online_hours >= plan_hours
    reports_ok = plan_reports <= 0 or period.reports >= plan_reports
    done = (plan_hours > 0 or plan_reports > 0) and hours_ok and reports_ok
    date_text = local.strftime("%d.%m")
    weekday = _WEEKDAYS[local.weekday()]
    return {
        "label": f"{date_text} {weekday}",   # так подпись идёт в столбиках
        "date": date_text,
        "weekday": weekday,
        "seconds": period.online_seconds,
        "reports": period.reports,
        "text": format_duration(period.online_seconds),
        "hours_pct": _percent(period.online_hours, plan_hours),
        "done": done,
        "is_today": offset == 0,
    }


def build_status(
    stats: StatsService,
    session: SessionService,
    config: Config,
    now: int | None = None,
) -> dict:
    """Собрать всё, что нужно сайту, одним вызовом."""
    now = int(time.time()) if now is None else now
    today = stats.today(now)
    week = stats.week(now)
    streak = current_streak(stats, config, now)
    local = datetime.fromtimestamp(now)
    w_start, w_end = week_bounds(now, config.week_start_weekday)
    week_label = (
        f"{datetime.fromtimestamp(w_start).strftime('%d.%m')} – "
        f"{datetime.fromtimestamp(w_end - 1).strftime('%d.%m')}"
    )

    plan_hours, plan_reports = streak.plan_hours, streak.plan_reports
    return {
        "ok": True,
        "now": now,
        "date": local.strftime("%d.%m.%Y"),
        "weekday": _WEEKDAYS[local.weekday()],
        "week": week_label,
        "today": {
            "seconds": today.online_seconds,
            "reports": today.reports,
            "text": format_duration(today.online_seconds),
            "plan_seconds": int(plan_hours * 3600),
            "plan_hours": plan_hours,
            "plan_reports": plan_reports,
            "hours_pct": _percent(today.online_hours, plan_hours),
            "reports_pct": _percent(today.reports, plan_reports),
            "done": streak.today_done,
        },
        "week_stats": {
            "seconds": week.online_seconds,
            "reports": week.reports,
            "text": format_duration(week.online_seconds),
            "hours_percent": _percent(week.online_hours, config.weekly_hours_norm),
            "reports_percent": _percent(week.reports, config.weekly_reports_norm),
            "hours_norm": config.weekly_hours_norm,
            "reports_norm": config.weekly_reports_norm,
        },
        "streak": {
            "days": streak.days,
            "today_done": streak.today_done,
            "in_progress": streak.in_progress,
            "plan_hours": plan_hours,
            "plan_reports": plan_reports,
        },
        "flags": {
            "duty": session.is_on_duty,
            "game": session.is_game_running,
            "counting": session.is_counting,
            "require_duty": config.require_duty,
        },
        # От старого дня к сегодняшнему: столбики читаются слева направо.
        "days": [_day_view(stats, config, now, offset)
                 for offset in range(DAYS_IN_VIEW - 1, -1, -1)],
        # Папка с отчётами — её подставляет хелпер (в окне и на сайте).
        "output_dir": str(config.output_dir or default_output_dir()),
    }
