"""Фоновый поток: раз в несколько секунд проверяет, запущена ли игра."""
from __future__ import annotations

import logging
import threading
from typing import Callable, Iterable

from app.tracker.session_service import SessionService

log = logging.getLogger(__name__)


def find_running(process_names: Iterable[str]) -> bool:
    import psutil  # импорт здесь, чтобы тесты не требовали psutil

    wanted = {name.lower() for name in process_names}
    for proc in psutil.process_iter(["name"]):
        name = proc.info.get("name")
        if name and name.lower() in wanted:
            return True
    return False


class GameWatcher(threading.Thread):
    def __init__(
        self,
        session: SessionService,
        process_names: list[str],
        poll_interval: float,
        detector: Callable[[Iterable[str]], bool] = find_running,
    ):
        super().__init__(name="GameWatcher", daemon=True)
        self._session = session
        self._names = process_names
        self._interval = poll_interval
        self._detector = detector
        self._stop_event = threading.Event()

    def run(self) -> None:
        while True:
            try:
                self._session.tick(self._detector(self._names))
            except Exception:
                log.exception("Ошибка при проверке процесса игры")
            if self._stop_event.wait(self._interval):
                break

    def stop(self) -> None:
        self._stop_event.set()
