"""Счётчик обращений: +1 и отмена, с защитой от лишних нажатий."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

from app.config import Config
from app.stats.service import StatsService
from app.storage.db import Database
from app.tracker.session_service import SessionService

REASON_GAME_NOT_RUNNING = "game_not_running"
REASON_NOTHING_TO_UNDO = "nothing_to_undo"
REASON_NOT_ON_DUTY = "not_on_duty"


@dataclass(frozen=True)
class ReportResult:
    ok: bool
    week_total: int
    delta: int
    reason: str = ""


class ReportCounter:
    def __init__(
        self,
        db: Database,
        stats: StatsService,
        session: SessionService,
        config: Config,
        clock: Callable[[], float] = time.time,
    ):
        self._db = db
        self._stats = stats
        self._session = session
        self._config = config
        self._clock = clock
        self._lock = threading.Lock()
        self.on_result: Callable[[ReportResult], None] | None = None

    def add(self) -> ReportResult:
        return self._apply(+1)

    def undo(self) -> ReportResult:
        return self._apply(-1)

    def _apply(self, delta: int) -> ReportResult:
        now = int(self._clock())
        with self._lock:
            week_total = self._stats.week_reports(now)
            if self._config.count_only_in_game and not self._session.is_game_running:
                result = ReportResult(False, week_total, delta, REASON_GAME_NOT_RUNNING)
            elif self._config.require_duty and not self._session.is_on_duty:
                result = ReportResult(False, week_total, delta, REASON_NOT_ON_DUTY)
            elif delta < 0 and week_total <= 0:
                result = ReportResult(False, week_total, delta, REASON_NOTHING_TO_UNDO)
            else:
                self._db.add_report_event(now, delta)
                result = ReportResult(True, week_total + delta, delta)
        if self.on_result:
            self.on_result(result)
        return result
