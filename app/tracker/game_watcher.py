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
    #: Сколько проверок подряд можно не увидеть игру, прежде чем поверить,
    #: что её действительно закрыли. Одиночный сбой опроса (psutil иногда
    #: не отдаёт процесс) раньше выключал дежурство сам по себе — сотрудник
    #: жаловался: «дежурство само периодически выключается».
    MISSES_BEFORE_GONE = 2

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
        self._misses = 0
        self._game_seen = False

    def run(self) -> None:
        # Листинг при старте: в логе видно, какие процессы реально загружены
        # из config.json (на случай, если игра «не находится» из-за списка).
        log.info("Отслеживаю процессы: %s", ", ".join(self._names))
        while True:
            try:
                self._poll()
            except Exception:
                log.exception("Ошибка при проверке процесса игры")
            if self._stop_event.wait(self._interval):
                break

    def _poll(self) -> None:
        if self._detector(self._names):
            if self._misses:
                log.info("Процесс игры снова найден")
            self._misses = 0
            self._game_seen = True
            self._session.tick(True)
            return
        self._misses += 1
        if not self._game_seen:
            # Игру ещё ни разу не видели — обычное «нет игры» с первой же
            # проверки (задержка не нужна, менять нечего).
            self._session.tick(False)
            return
        if self._misses < self.MISSES_BEFORE_GONE:
            # Ещё не уверены: держим прежнее состояние, tick не вызываем —
            # одиночный сбой опроса не должен выключать дежурство.
            log.warning(
                "Процесс игры пропал (проверка %d из %d) — жду подтверждения",
                self._misses, self.MISSES_BEFORE_GONE,
            )
            return
        if self._misses == self.MISSES_BEFORE_GONE:
            log.warning(
                "Процесс игры не найден %d раза подряд — считаю игру закрытой",
                self._misses,
            )
        self._session.tick(False)

    def stop(self) -> None:
        self._stop_event.set()
