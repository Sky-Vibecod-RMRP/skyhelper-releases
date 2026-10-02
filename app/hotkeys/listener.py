"""Глобальные горячие клавиши (работают поверх игры).

Клавиши не подавляются: игра тоже получает нажатие. Если F9 занята
в игре, поменяйте клавишу в config.json.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from app.hotkeys.edge import EdgeGuard

log = logging.getLogger(__name__)

DEBOUNCE_SEC = 0.3  # второй эшелон защиты: первый — edge-гард


def bind_problem(hotkey: str) -> str | None:
    """Что скажет слушатель про этот бинд; None — бинд разбирается.

    Разбирает тем же парсером, что и :meth:`HotkeyListener.start` (жалоба
    02.10.2026): строка вида «zcsda» из текстового поля доезжала до
    ``keyboard.add_hotkey`` и роняла сохранение настроек целиком.
    ``keyboard`` без парсера (фейк в тестах) или вовсе отсутствующий —
    проверить нечем, считаем бинд годным: иначе мешали бы тестам и
    окружениям, где библиотеки нет.
    """
    text = str(hotkey or "").strip().lower()
    if not text:
        return None
    try:
        import keyboard  # импорт здесь, чтобы тесты не требовали keyboard
    except Exception:  # noqa: BLE001 — проверить нечем
        return None
    parse = getattr(keyboard, "parse_hotkey_combinations", None)
    if parse is None:
        return None
    try:
        parse(text)
    except Exception as exc:  # noqa: BLE001 — любая ошибка разбора = битый бинд
        return str(exc)
    return None


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
        self._edge = EdgeGuard()

    def start(self) -> None:
        import keyboard  # импорт здесь, чтобы тесты не требовали keyboard

        # Именно у показа окна suppress=True (баг-репорт №4): клавиша
        # принадлежит программе, иначе игра/лаунчер реагируют на неё тоже
        # — по Insert меню лаунчера закрывалось и тут же открывалось снова.
        # Клавиши +1/−1/дежурство и клавиши категорий скриншотов остаются
        # suppress=False, чтобы игра их по-прежнему видела.
        binds: list[tuple[str, object, bool]] = [
            (self._add_key, self._handle_add, False),
            (self._remove_key, self._handle_remove, False),
        ]
        if self._duty_key and self._on_duty:
            binds.append((self._duty_key, self._handle_duty, False))
        if self._toggle_key and self._on_toggle:
            binds.append((self._toggle_key, self._handle_toggle, True))

        self._handles = []
        for key, callback, suppress in binds:
            try:
                self._handles.append(
                    keyboard.add_hotkey(key, callback, suppress=suppress)
                )
            except Exception as exc:  # noqa: BLE001 — один битый бинд из
                # старого конфига (жалоба 02.10.2026: «zcsda» из текстового
                # поля) не должен убивать остальные клавиши и старт программы.
                log.warning("Клавиша «%s» не повесилась: %s", key, exc)

        # Edge-хуки гасят автоповтор зажатой клавиши ДО дебаунса. Insert
        # (suppress=True) не вешаем: его колбэк живёт в хук-потоке и обгоняет
        # press-хук — там остаётся только тайм-дебаунс.
        for key in (self._add_key, self._remove_key, self._duty_key):
            if key:
                self._edge.watch(key)

    def stop(self) -> None:
        import keyboard

        for handle in self._handles:
            try:
                keyboard.remove_hotkey(handle)
            except (KeyError, ValueError):
                pass
        self._handles = []
        self._edge.unwatch()

    def _debounced(self, name: str) -> bool:
        now = time.monotonic()
        if now - self._last_fired.get(name, 0.0) < DEBOUNCE_SEC:
            return False
        self._last_fired[name] = now
        return True

    def _handle_add(self) -> None:
        import keyboard

        # Автоповтор зажатой клавиши гасится edge-гардом: без него дебаунс
        # «дребезжал» и при удержании +1 уходил раз в 0,3 с.
        if not self._edge.allow(self._add_key):
            return
        # Ctrl+F9 содержит F9: не считаем это нажатие как «+1».
        if keyboard.is_pressed(self._remove_key):
            return
        if self._debounced("add"):
            self._safe_call(self._on_add)

    def _handle_remove(self) -> None:
        if not self._edge.allow(self._remove_key):
            return
        if self._debounced("remove"):
            self._safe_call(self._on_remove)

    def _handle_duty(self) -> None:
        if not self._edge.allow(self._duty_key or ""):
            return
        if self._on_duty and self._debounced("duty"):
            self._safe_call(self._on_duty)

    def _handle_toggle(self) -> None:
        # Insert (suppress=True) вне edge-гарда — его колбэк выполняется
        # в хук-потоке до press-хука, там решает только дебаунс:
        # «залипший Insert» гасим автоповтором.
        if self._on_toggle and self._debounced("toggle"):
            self._safe_call(self._on_toggle)

    @staticmethod
    def _safe_call(func: Callable[[], None]) -> None:
        try:
            func()
        except Exception:
            log.exception("Ошибка в обработчике горячей клавиши")
