"""Edge-гард: автоповтор зажатой клавиши не доходит до хоткея.

Гард живёт на ``nonblocking_keys`` (press/release-хуки) и выполняется в
``pre_process_event`` раньше колбэков ``add_hotkey``. Здесь проверяем саму
логику (fresh/down, потребление свежести) и фолбэк: нет ``hook_key`` —
гард выключен, работает только тайм-дебаунс.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app.hotkeys.edge import EdgeGuard, keys_of


class FakeKeyboard:
    """Минимальный keyboard: hook_key + умение нажать/отпустить клавишу."""

    KEY_DOWN = "down"
    KEY_UP = "up"

    def __init__(self) -> None:
        self.hooks: dict[str, list] = {}
        self.removed: list[str] = []

    def hook_key(self, key, callback, suppress=False):
        assert suppress is False, "гард не должен подавлять события"
        self.hooks.setdefault(key, []).append(callback)

        def remove():
            self.hooks[key].remove(callback)
            self.removed.append(key)

        return remove

    def press(self, key: str) -> None:
        for cb in list(self.hooks.get(key, [])):
            cb(SimpleNamespace(event_type=self.KEY_DOWN, name=key))

    def release(self, key: str) -> None:
        for cb in list(self.hooks.get(key, [])):
            cb(SimpleNamespace(event_type=self.KEY_UP, name=key))


@pytest.fixture
def fake(monkeypatch):
    kb = FakeKeyboard()
    monkeypatch.setitem(sys.modules, "keyboard", kb)
    return kb


def test_keys_of():
    assert keys_of("F10") == ("f10",)
    assert keys_of("Ctrl + F9") == ("ctrl", "f9")
    assert keys_of("") is None
    assert keys_of("f6, f7") == ("f6, f7",)  # разложение не наше дело — упадёт hook


def test_fallback_when_not_watched():
    """Гард без регистрации (фейковый keyboard, сбой) не блокирует ничего."""
    guard = EdgeGuard()

    assert guard.allow("f10") is True


def test_fallback_when_keyboard_has_no_hook_key(monkeypatch):
    """Старый/фейковый keyboard без hook_key — просто дебаунс, как раньше."""
    monkeypatch.setitem(sys.modules, "keyboard", SimpleNamespace(add_hotkey=object()))
    guard = EdgeGuard()

    assert guard.watch("f10") is False
    assert guard.allow("f10") is True


def test_first_press_allowed_repeat_blocked(fake):
    guard = EdgeGuard()
    assert guard.watch("F10") is True

    fake.press("f10")                     # первое нажатие
    assert guard.allow("F10") is True

    fake.press("f10")                     # автоповтор
    assert guard.allow("f10") is False
    fake.press("f10")
    assert guard.allow("f10") is False

    fake.release("f10")                   # отпустили — можно снова
    fake.press("f10")
    assert guard.allow("f10") is True


def test_combo_consumes_all_fresh_keys(fake):
    """После срабатывания ctrl+f9 автоповтор модификатора не выстрелит."""
    guard = EdgeGuard()
    assert guard.watch("ctrl+f9") is True

    fake.press("ctrl")
    fake.press("f9")
    assert guard.allow("ctrl+f9") is True

    fake.press("ctrl")                    # автоповтор ctrl при зажатом f9
    assert guard.allow("ctrl+f9") is False

    fake.release("f9")
    fake.press("f9")                      # новое нажатие f9 — новая комбинация
    assert guard.allow("ctrl+f9") is True


def test_release_drops_stale_fresh(fake):
    """Нажатие, до которого хоткей не дошёл, не выстрелит позже."""
    guard = EdgeGuard()
    assert guard.watch("f6") is True

    fake.press("f6")                      # гард пометил, но allow не вызывали
    fake.release("f6")                    # заброшенное нажатие схлопнулось
    fake.press("f6")                      # свежесть только от нового нажатия

    assert guard.allow("f6") is True
    fake.press("f6")                      # повтор уже после потребления
    assert guard.allow("f6") is False


def test_unwatch_disables_and_unhooks(fake):
    guard = EdgeGuard()
    guard.watch("f10")
    assert fake.hooks.get("f10")

    guard.unwatch()

    assert not fake.hooks.get("f10")      # хук снят
    fake.press("f10")
    assert guard.allow("f10") is True     # и всё равно фолбэк
