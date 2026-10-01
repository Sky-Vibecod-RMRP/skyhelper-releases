from __future__ import annotations

from dataclasses import dataclass

from app.config import Config
from app.stats.weeks import day_bounds, overlap_seconds, week_bounds
from app.storage.db import Database


@dataclass(frozen=True)
class PeriodStats:
    online_seconds: int
    reports: int

    @property
    def online_hours(self) -> float:
        return self.online_seconds / 3600


@dataclass(frozen=True)
class WeekProgress:
    stats: PeriodStats
    hours_norm: float
    reports_norm: int

    @property
    def hours_percent(self) -> float:
        return self._percent(self.stats.online_hours, self.hours_norm)

    @property
    def reports_percent(self) -> float:
        return self._percent(self.stats.reports, self.reports_norm)

    @staticmethod
    def _percent(value: float, norm: float) -> float:
        return value / norm * 100 if norm > 0 else 0.0


class StatsService:
    def __init__(self, db: Database, config: Config):
        self._db = db
        self._config = config

    def between(self, start: int, end: int, now: int) -> PeriodStats:
        intervals = self._db.sessions_overlapping(start, end)
        return PeriodStats(
            online_seconds=overlap_seconds(intervals, start, end, now),
            reports=self._db.report_total(start, end),
        )

    def today(self, now: int) -> PeriodStats:
        start, end = day_bounds(now)
        return self.between(start, end, now)

    def week(self, now: int) -> PeriodStats:
        start, end = week_bounds(now, self._config.week_start_weekday)
        return self.between(start, end, now)

    def week_reports(self, now: int) -> int:
        start, end = week_bounds(now, self._config.week_start_weekday)
        return self._db.report_total(start, end)

    def week_progress(self, now: int) -> WeekProgress:
        return WeekProgress(
            stats=self.week(now),
            hours_norm=self._config.weekly_hours_norm,
            reports_norm=self._config.weekly_reports_norm,
        )
