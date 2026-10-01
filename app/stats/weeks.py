"""Границы дня/недели по местному времени ПК и подсчёт пересечений."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable


def day_bounds(ts: float) -> tuple[int, int]:
    local = datetime.fromtimestamp(ts)
    start = datetime(local.year, local.month, local.day)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def week_bounds(ts: float, week_start_weekday: int = 0) -> tuple[int, int]:
    """Начало и конец недели, содержащей ts. По умолчанию неделя с понедельника 00:00."""
    local = datetime.fromtimestamp(ts)
    day = datetime(local.year, local.month, local.day)
    offset = (local.weekday() - week_start_weekday) % 7
    start = day - timedelta(days=offset)
    end = start + timedelta(days=7)
    return int(start.timestamp()), int(end.timestamp())


def overlap_seconds(
    intervals: Iterable[tuple[int, int | None]], start: int, end: int, now: int
) -> int:
    """Сумма секунд, в которые интервалы пересекаются с [start, end).

    Интервал без конца (игра идёт сейчас) считается закончившимся в now.
    Сессия через полночь/границу недели обрезается здесь, а не при записи.
    """
    total = 0
    for s, e in intervals:
        e = now if e is None else e
        total += max(0, min(e, end) - max(s, start))
    return total
