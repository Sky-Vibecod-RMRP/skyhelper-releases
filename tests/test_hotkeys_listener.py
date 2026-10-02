# -*- coding: utf-8 -*-
"""Слушатель клавиш: один битый бинд не должен ронять всё.

Жалоба 02.10.2026: из текстового поля приходило «zcsda»/«numpad0»,
``keyboard.add_hotkey`` бросал ValueError — и сохранение вместе со всеми
клавишами сорвалось, а в конфиг успевала попасть отрава.
"""
from __future__ import annotations

import sys

import pytest

from app.hotkeys.listener import HotkeyListener, bind_problem


class FakeKeyboard:
    """Как настоящий keyboard, но «zcsda» повесить нельзя."""

    def __init__(self) -> None:
        self.registered: list[str] = []

    def add_hotkey(self, key, callback, suppress=False, **_kwargs):
        if "zcsda" in str(key):
            raise ValueError(f"Key '{key}' is not mapped to any known key.")
        self.registered.append(str(key))
        return object()

    def remove_hotkey(self, handle) -> None:
        pass


def _listener(**kwargs) -> HotkeyListener:
    base: dict = {
        "add_key": "f9",
        "remove_key": "ctrl+f9",
        "on_add": lambda: None,
        "on_remove": lambda: None,
    }
    base.update(kwargs)
    return HotkeyListener(**base)


def test_broken_bind_does_not_kill_the_others(monkeypatch, caplog):
    fake = FakeKeyboard()
    monkeypatch.setitem(sys.modules, "keyboard", fake)
    listener = _listener(
        duty_key="zcsda",
        on_duty=lambda: None,
        toggle_key="insert",
        on_toggle=lambda: None,
    )

    with caplog.at_level("WARNING", logger="app.hotkeys.listener"):
        listener.start()

    assert fake.registered == ["f9", "ctrl+f9", "insert"]
    assert any("zcsda" in record.message for record in caplog.records)
    listener.stop()


def test_bind_problem_rejects_garbage():
    pytest.importorskip("keyboard")   # без библиотеки проверить нечем
    assert bind_problem("f10") is None
    assert bind_problem("ctrl+f9") is None
    assert bind_problem("") is None, "пустое значение — не ошибка (пусто = выкл.)"
    assert bind_problem("zcsda"), "«zcsda» из текстового поля должно отловиться"
    assert bind_problem("numpad0"), "«numpad0» не существует в keyboard"


def test_bind_problem_without_parser_is_not_a_blocker(monkeypatch):
    fake = FakeKeyboard()   # фейк из других тестов — только add/remove
    monkeypatch.setitem(sys.modules, "keyboard", fake)
    assert bind_problem("f10") is None
