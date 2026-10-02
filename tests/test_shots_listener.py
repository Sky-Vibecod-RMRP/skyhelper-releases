"""Тесты слушателя клавиш категорий: привязка, дебаунс, конфликты.

Реальный ``keyboard`` (глобальный хук Windows) подменяется фейком через
``sys.modules``: тесты не должны трогать системные горячие клавиши.
"""
from __future__ import annotations

import sys

import pytest

from app.shots.listener import CategoryListener


class FakeKeyboard:
    def __init__(self) -> None:
        self.added: list[tuple[str, object]] = []
        self.removed: list = []
        self.fail: set[str] = set()

    def add_hotkey(self, key, callback, suppress=False):
        assert suppress is False, "клавиша не должна съедаться — игра её тоже видит"
        if key in self.fail:
            raise ValueError(f"unknown key {key}")
        self.added.append((key, callback))
        return f"handle-{key}"

    def remove_hotkey(self, handle):
        self.removed.append(handle)


@pytest.fixture
def fake_keyboard(monkeypatch):
    fake = FakeKeyboard()
    monkeypatch.setitem(sys.modules, "keyboard", fake)
    return fake


def _categories(*pairs) -> list[dict]:
    return [{"name": name, "hotkey": key, "in_game": False} for name, key in pairs]


def test_reload_binds_every_category(fake_keyboard):
    listener = CategoryListener(lambda _name: None)
    categories = _categories(("День", "f6"), ("Ночь", "shift+f6"))

    assert listener.reload(categories) == []
    assert [key for key, _ in fake_keyboard.added] == ["f6", "shift+f6"]


def test_reload_skips_rows_without_name_or_key(fake_keyboard):
    listener = CategoryListener(lambda _name: None)
    assert listener.reload([
        {"name": "", "hotkey": "f6"},
        {"name": "Без клавиши", "hotkey": ""},
    ]) == []
    assert fake_keyboard.added == []


def test_unrecognized_key_becomes_conflict_not_crash(fake_keyboard):
    fake_keyboard.fail.add("ctrl+q")
    listener = CategoryListener(lambda _name: None)

    conflicts = listener.reload(_categories(("Плохая", "ctrl+q"), ("Хорошая", "f6")))

    assert len(conflicts) == 1 and "ctrl+q" in conflicts[0] and "Плохая" in conflicts[0]
    assert [key for key, _ in fake_keyboard.added] == ["f6"]


def test_stop_removes_all_handles(fake_keyboard):
    listener = CategoryListener(lambda _name: None)
    listener.reload(_categories(("A", "f6"), ("B", "f7")))
    listener.stop()
    listener.stop()                      # повторный вызов — не ошибка

    assert sorted(fake_keyboard.removed) == ["handle-f6", "handle-f7"]


def test_reload_rebinds_after_settings_change(fake_keyboard):
    listener = CategoryListener(lambda _name: None)
    listener.reload(_categories(("A", "f6")))
    listener.reload(_categories(("A", "f7")))

    assert [key for key, _ in fake_keyboard.added] == ["f6", "f7"]
    assert fake_keyboard.removed == ["handle-f6"], "старая привязка снята"


def test_held_key_does_not_produce_a_series_of_shots(fake_keyboard):
    shots: list[str] = []
    now = [0.0]
    listener = CategoryListener(shots.append, clock=lambda: now[0])
    listener.reload(_categories(("Наказания (День)", "f8")))
    callback = fake_keyboard.added[0][1]

    callback(); callback(); callback()   # зажатая клавиша дребезжит
    listener.join()                      # снимок уходит в отдельный поток
    assert shots == ["Наказания (День)"]

    now[0] = 0.5                          # прошло больше дебаунса
    callback()
    listener.join()
    assert shots == ["Наказания (День)", "Наказания (День)"]


def test_callback_failure_is_swallowed(fake_keyboard, caplog):
    def boom(_name):
        raise RuntimeError("нет монитора")

    listener = CategoryListener(boom)
    listener.reload(_categories(("A", "f6")))

    fake_keyboard.added[0][1]()          # не должно поднять исключение
    listener.join()                      # ошибка логируется из потока снимка
    assert "не удался" in caplog.text
