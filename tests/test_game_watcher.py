"""N-under-run детектора игры: одиночный сбой опроса не выключает дежурство.

По жалобе сотрудника «дежурство само периодически выключалось» — раньше
достаточно одного ``tick(False)``, чтобы авто-выключение сработало. Теперь
``GameWatcher`` верит в закрытие игры только после MISSES_BEFORE_GONE
проверок подряд, а всё промежуточное пишет в лог.
"""
from __future__ import annotations

import logging
import time

from app.tracker.game_watcher import GameWatcher


class FakeSession:
    def __init__(self) -> None:
        self.ticks: list[bool] = []

    def tick(self, game_running: bool) -> None:
        self.ticks.append(game_running)


def _make(results: list[bool]):
    """Watcher с детектором-сценарием и фейковой сессией (без потока)."""
    seq = iter(results)
    session = FakeSession()
    watcher = GameWatcher(
        session, ["gta5.exe"], 0.01, detector=lambda _names: next(seq)
    )
    return watcher, session


def test_single_miss_keeps_running_state():
    """Один пропуск опроса не доходит до сессии: дежурство не выключается."""
    watcher, session = _make([True, False, True])

    for _ in range(3):
        watcher._poll()

    assert session.ticks == [True, True]  # промежуточный False подменён


def test_two_misses_in_a_row_turn_game_off():
    """Два пропуска подряд = игра закрыта."""
    watcher, session = _make([True, False, False, False])

    for _ in range(4):
        watcher._poll()

    # первый пропуск — пауза, дальше честные False
    assert session.ticks == [True, False, False]


def test_never_seen_game_goes_off_immediately():
    """Игру не видели — задержка не нужна, поведение как раньше."""
    watcher, session = _make([False, False])

    for _ in range(2):
        watcher._poll()

    assert session.ticks == [False, False]


def test_recovery_resets_counter(caplog):
    """После пропусков и находки счётчик обнуляется, логи видны."""
    watcher, session = _make([True, False, False, True])

    with caplog.at_level(logging.INFO, logger="app.tracker.game_watcher"):
        for _ in range(4):
            watcher._poll()

    assert session.ticks == [True, False, True]
    assert any("не найден 2 раза подряд" in r.getMessage() for r in caplog.records)
    assert any("снова найден" in r.getMessage() for r in caplog.records)


def test_lists_configured_processes_at_start(caplog):
    """При старте в лог пишется листинг game_processes из конфига."""
    session = FakeSession()
    watcher = GameWatcher(
        session, ["GTA5.exe", "FiveM.exe"], 0.01,
        detector=lambda _names: False,
    )

    with caplog.at_level(logging.INFO, logger="app.tracker.game_watcher"):
        watcher.start()
        try:
            time.sleep(0.1)  # даём один-два тика
        finally:
            watcher.stop()
            watcher.join(2.0)

    assert any(
        "Отслеживаю процессы: GTA5.exe, FiveM.exe" in r.getMessage()
        for r in caplog.records
    )
