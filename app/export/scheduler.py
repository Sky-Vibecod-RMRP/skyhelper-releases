"""Запускает экспорт по расписанию (по умолчанию раз в 2 часа)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

log = logging.getLogger(__name__)

# Замок и реестр потоков общие на все экземпляры: в core при сохранении настроек
# создаётся новый ExportScheduler, а старый может ещё доэкспортить. Без общей
# блокировки два экспорта писали бы один и тот же временный файл и портили его.
_JOB_LOCK = threading.Lock()
_THREADS_LOCK = threading.Lock()
_LIVE_THREADS: list[threading.Thread] = []


def _register(thread: threading.Thread) -> None:
    with _THREADS_LOCK:
        if thread not in _LIVE_THREADS:
            _LIVE_THREADS.append(thread)


def _unregister(thread: threading.Thread) -> None:
    with _THREADS_LOCK:
        if thread in _LIVE_THREADS:
            _LIVE_THREADS.remove(thread)


def wait_for_exports(timeout: float = 20.0) -> bool:
    """Дождаться всех идущих экпортов (и по расписанию, и «Обновить сейчас»).

    Нужно перед закрытием базы: работающий экспорт читает её в своём потоке.
    True — всё завершилось, False — остались потоки (выходить не стали ждать).
    """
    deadline = time.monotonic() + timeout
    with _THREADS_LOCK:
        threads = list(_LIVE_THREADS)
    finished = True
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
        if thread.is_alive():
            finished = False
    return finished


class ExportScheduler(threading.Thread):
    def __init__(self, job: Callable[[], object], interval_sec: float, first_delay_sec: float = 30.0):
        super().__init__(name="ExportScheduler", daemon=True)
        self._job = job
        self._interval = max(60.0, interval_sec)
        self._first_delay = first_delay_sec
        self._stop_event = threading.Event()

    def run(self) -> None:
        if self._stop_event.wait(self._first_delay):
            return
        while True:
            self.run_now()
            if self._stop_event.wait(self._interval):
                return

    def run_now(self) -> None:
        current = threading.current_thread()
        _register(current)  # wait_for_exports увидит и поток расписания, и «Обновить сейчас»
        # Замок общий на все экземпляры: два экспорта не бьются за один tmp-файл.
        if not _JOB_LOCK.acquire(blocking=False):
            _unregister(current)
            return
        try:
            self._job()
        except Exception:
            log.exception("Ошибка в задаче экспорта")
        finally:
            _JOB_LOCK.release()
            _unregister(current)

    def trigger(self) -> None:
        """Обновить прямо сейчас, не блокируя вызывающий поток."""
        thread = threading.Thread(target=self.run_now, name="ExportNow", daemon=True)
        _register(thread)  # до старта: ждём и поток, который ещё ждёт замок
        thread.start()

    def stop(self) -> None:
        self._stop_event.set()
