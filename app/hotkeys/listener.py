"""Глобальные горячие клавиши (работают поверх игры).

Клавиши не подавляются: игра тоже получает нажатие. Если F9 занята
в игре, поменяйте клавишу в config.json.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

log = logging.getLogger(__name__)

DEBOUNCE_SEC = 0.3  # защита от автоповтора при удержании клавиши


class HotkeyListener:
    def __init__(
        self,
        add_key: str,
        remove_key: str,
        on_add: Callable[[], None],
        on_remove: Callable[[], None],
        duty_key: str | None = None,
        on_duty: Callable[[], object] | None = None,
        toggle_key: str | None = None,
        on_toggle: Callable[[], object] | None = None,
    ):
        self._add_key = add_key
        self._remove_key = remove_key
        self._on_add = on_add
        self._on_remove = on_remove
        self._duty_key = duty_key
        self._on_duty = on_duty
        self._toggle_key = toggle_key
        self._on_toggle = on_toggle
        self._handles: list = []
        self._last_fired: dict[str, float] = {}

    def start(self) -> None:
        import keyboard  # импорт здесь, чтобы тесты не требовали keyboard

        self._handles = [
            keyboard.add_hotkey(self._add_key, self._handle_add, suppress=False),
            keyboard.add_hotkey(self._remove_key, self._handle_remove, suppress=False),
        ]
        if self._duty_key and self._on_duty:
            self._handles.append(
                keyboard.add_hotkey(self._duty_key, self._handle_duty, suppress=False)
            )
        if self._toggle_key and self._on_toggle:
            # Именно здесь suppress=True (баг-репорт №4): клавиша показа окна
            # принадлежит программе, иначе игра/лаунчер реагируют на неё тоже
            # — по Insert меню лаунчера закрывалось и тут же открывалось снова.
            # Клавиши +1/−1/дежурство и клавиши категорий скриншотов остаются
            # suppress=False, чтобы игра их по-прежнему видела.
            self._handles.append(
                keyboard.add_hotkey(
                    self._toggle_key, self._handle_toggle, suppress=True
                )
            )

    def stop(self) -> None:
        import keyboard

        for handle in self._handles:
            try:
                keyboard.remove_hotkey(handle)
            except (KeyError, ValueError):
                pass
        self._handles = []

    def _debounced(self, name: str) -> bool:
        now = time.monotonic()
        if now - self._last_fired.get(name, 0.0) < DEBOUNCE_SEC:
            return False
        self._last_fired[name] = now
        return True

    def _handle_add(self) -> None:
        import keyboard

        # Ctrl+F9 содержит F9: не считаем это нажатие как «+1».
        if keyboard.is_pressed(self._remove_key):
            return
        if self._debounced("add"):
            self._safe_call(self._on_add)

    def _handle_remove(self) -> None:
        if self._debounced("remove"):
            self._safe_call(self._on_remove)

    def _handle_duty(self) -> None:
        if self._on_duty and self._debounced("duty"):
            self._safe_call(self._on_duty)

    def _handle_toggle(self) -> None:
        # Insert тоже может «залипнуть» при удержании — гасим автоповтор.
        if self._on_toggle and self._debounced("toggle"):
            self._safe_call(self._on_toggle)

    @staticmethod
    def _safe_call(func: Callable[[], None]) -> None:
        try:
            func()
        except Exception:
            log.exception("Ошибка в обработчике горячей клавиши")
