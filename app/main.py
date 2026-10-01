"""Консольный запуск (этапы 1-3): учёт онлайна и обращений без окон.

Запуск из папки проекта:  python -m app.main
"""
from __future__ import annotations

import logging
import time

from app.config import Config
from app.hotkeys.listener import HotkeyListener
from app.paths import config_path, db_path, logs_dir, program_logs_dir
from app.services.report_counter import (
    REASON_GAME_NOT_RUNNING,
    REASON_NOT_ON_DUTY,
    REASON_NOTHING_TO_UNDO,
    ReportCounter,
    ReportResult,
)
from app.stats.service import StatsService
from app.storage.db import Database
from app.tracker.game_watcher import GameWatcher
from app.tracker.session_service import SessionService
from app.util import format_duration

STATUS_EVERY_SEC = 60


def setup_logging() -> None:
    """Логи и в папке пользователя, и рядом с программой (предложение №1)."""
    handlers = [
        logging.FileHandler(logs_dir() / "app.log", encoding="utf-8"),
        logging.FileHandler(program_logs_dir() / "app.log", encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def status_line(stats: StatsService, session: SessionService, config: Config) -> str:
    now = int(time.time())
    progress = stats.week_progress(now)
    today = stats.today(now)
    game = "запущена" if session.is_game_running else "не найдена"
    duty = "да" if session.is_on_duty else "нет"
    return (
        f"Игра: {game} | Дежурство: {duty} | Сегодня: {format_duration(today.online_seconds)}, "
        f"обращений {today.reports} | Неделя: "
        f"{format_duration(progress.stats.online_seconds)} из {config.weekly_hours_norm:g} ч, "
        f"обращений {progress.stats.reports} из {config.weekly_reports_norm}"
    )


def describe(result: ReportResult, norm: int) -> str:
    if result.ok:
        sign = "+1" if result.delta > 0 else "-1"
        return f"{sign} -> {result.week_total} из {norm}"
    if result.reason == REASON_GAME_NOT_RUNNING:
        return "Не засчитано: игра не запущена"
    if result.reason == REASON_NOT_ON_DUTY:
        return "Не засчитано: дежурство выключено"
    if result.reason == REASON_NOTHING_TO_UNDO:
        return "Нечего отменять: на этой неделе 0 обращений"
    return "Не засчитано"


def main() -> None:
    setup_logging()
    config = Config.load(config_path())
    db = Database(db_path())

    session = SessionService(db, config)
    recovered = session.recover()
    stats = StatsService(db, config)
    counter = ReportCounter(db, stats, session, config)

    session.on_state_change = lambda counting: print(
        "Онлайн считается" if counting else "Онлайн не считается, сессия сохранена"
    )
    session.on_duty_change = lambda on: print(
        "Дежурство начато" if on else "Дежурство закончено"
    )
    counter.on_result = lambda r: print(describe(r, config.weekly_reports_norm))

    watcher = GameWatcher(session, config.game_processes, config.poll_interval_sec)
    hotkeys = HotkeyListener(
        config.hotkey_add, config.hotkey_remove, counter.add, counter.undo,
        config.hotkey_duty, session.toggle_duty,
    )

    print(f"Отслеживаю процессы: {', '.join(config.game_processes)}")
    print(f"Клавиши: {config.hotkey_add.upper()} = +1, {config.hotkey_remove.upper()} = -1, "
          f"{config.hotkey_duty.upper()} = дежурство. Выход: Ctrl+C")
    if recovered:
        print(f"Закрыто оборванных сессий после прошлого запуска: {recovered}")

    watcher.start()
    hotkeys.start()
    try:
        while True:
            time.sleep(STATUS_EVERY_SEC)
            print(status_line(stats, session, config))
    except KeyboardInterrupt:
        print("Выход...")
    finally:
        hotkeys.stop()
        watcher.stop()
        session.shutdown()
        db.close()


if __name__ == "__main__":
    main()
