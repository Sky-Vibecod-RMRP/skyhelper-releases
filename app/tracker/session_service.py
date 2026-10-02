"""Учёт сессий: онлайн считается, пока запущена игра и включено дежурство.

Открывает/закрывает сессию, пишет «пульс», ловит сон ПК.
Если require_duty выключено в настройках, дежурство не нужно: считается всё
время, пока игра запущена.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from app.config import Config
from app.storage.db import Database

log = logging.getLogger(__name__)


class SessionService:
    def __init__(self, db: Database, config: Config, clock: Callable[[], float] = time.time):
        self._db = db
        self._config = config
        self._clock = clock
        self._lock = threading.RLock()
        self._session_id: int | None = None
        self._game_running = False
        self._on_duty = False
        self._last_tick = 0
        self._last_heartbeat = 0
        # Вызывается, когда начал или прекратился подсчёт онлайна (аргумент: считаем ли сейчас).
        self.on_state_change: Callable[[bool], None] | None = None
        # Вызывается при смене дежурства (аргумент: на дежурстве ли).
        self.on_duty_change: Callable[[bool], None] | None = None

    @property
    def is_game_running(self) -> bool:
        return self._game_running

    @property
    def is_on_duty(self) -> bool:
        return self._on_duty

    @property
    def is_counting(self) -> bool:
        """Онлайн идёт прямо сейчас (игра запущена и, если нужно, включено дежурство)."""
        return self._session_id is not None

    def recover(self) -> int:
        """Вызвать один раз при старте: закрыть сессии, оборванные вылетом."""
        return self._db.close_orphan_sessions()

    def _should_count(self) -> bool:
        return self._game_running and (self._on_duty or not self._config.require_duty)

    def _reconcile(self, now: int) -> bool | None:
        """Приводит сессию в соответствие с состоянием. True/False = открыли/закрыли."""
        want = self._should_count()
        if want and self._session_id is None:
            self._session_id = self._db.open_session(now)
            self._last_heartbeat = now
            return True
        if not want and self._session_id is not None:
            self._db.close_session(self._session_id, now)
            self._session_id = None
            return False
        if self._session_id is not None and now - self._last_heartbeat >= self._config.heartbeat_interval_sec:
            self._db.touch_session(self._session_id, now)
            self._last_heartbeat = now
        return None

    def tick(self, game_running: bool) -> None:
        """Вызывается GameWatcher после каждой проверки процесса."""
        now = int(self._clock())
        changed: bool | None = None
        duty_off = False

        with self._lock:
            # Между проверками прошло слишком много времени: ПК спал или завис.
            # Старую сессию закрываем по последней проверке, чтобы не насчитать лишнего.
            if self._session_id is not None and now - self._last_tick > self._config.max_gap_sec:
                log.warning("Разрыв %s сек между проверками, закрываю сессию", now - self._last_tick)
                self._db.close_session(self._session_id, self._last_tick)
                self._session_id = None
                changed = False

            game_closed = self._game_running and not game_running
            self._game_running = game_running
            if game_closed and self._on_duty and self._config.duty_auto_off_on_game_close:
                self._on_duty = False
                duty_off = True
                # Причина в логе: по жалобе сотрудник дежурство «само
                # периодически выключалось», а строки с причиной не было.
                log.info("Дежурство выключено (авто: игра закрылась)")

            result = self._reconcile(now)
            if result is not None:
                changed = result
            self._last_tick = now
            counting_now = self._session_id is not None

        # Если сессию закрыли по разрыву и тут же открыли новую, для внешнего
        # мира состояние осталось «считаем».
        if changed is not None and self.on_state_change:
            self.on_state_change(counting_now)
        if duty_off and self.on_duty_change:
            self.on_duty_change(False)

    def set_duty(self, on: bool, reason: str = "") -> None:
        """Включить/выключить дежурство. Онлайн начинает или прекращает считаться сразу.

        ``reason`` — откуда пришло переключение («клавиша F10», «кнопка в меню»,
        «авто: игра закрылась»): причина пишется в лог, чтобы при следующей
        жалобе было видно, кто выключил дежурство.
        """
        now = int(self._clock())
        with self._lock:
            if on == self._on_duty:
                return
            self._on_duty = on
            result = self._reconcile(now)
            counting_now = self._session_id is not None
        log.info(
            "Дежурство %s%s",
            "включено" if on else "выключено",
            f" ({reason})" if reason else "",
        )
        if result is not None and self.on_state_change:
            self.on_state_change(counting_now)
        if self.on_duty_change:
            self.on_duty_change(on)

    def toggle_duty(self, reason: str = "") -> bool:
        self.set_duty(not self._on_duty, reason)
        return self._on_duty

    def shutdown(self) -> None:
        """Корректно закрыть открытую сессию при выходе из программы."""
        with self._lock:
            if self._session_id is not None:
                self._db.close_session(self._session_id, int(self._clock()))
                self._session_id = None
