# -*- coding: utf-8 -*-
"""Окно обновления и гейт запуска: два режима, откладывание, загрузка.

Экран выключен (QT_QPA_PLATFORM=offscreen) — как и в остальных UI-тестах.
Состояние обновлений уходит во временную папку, сеть не трогается:
загрузка подменяется, установщик не запускается.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from app import update_check as uc
from app.ui import update_dialog as ud


@pytest.fixture
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(uc, "app_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def info():
    return uc.UpdateInfo(
        version="1.1.0",
        url="https://example.invalid/SKYHELPER_Setup.exe",
        sha256="a" * 64,
        released_at=1_800_000_000.0,
        notes="Что нового: стало лучше",
    )


def _labels(dialog) -> str:
    return " ".join(w.text() for w in dialog.findChildren(QLabel))


def _wait(qapp, condition, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if condition():
            return True
        QTest.qWait(20)
    return condition()


def _finish_thread(dialog) -> None:
    thread = dialog.download_thread
    if thread is not None:
        thread.wait(5_000)


# --- режимы ------------------------------------------------------------------

def test_notify_text_speaks_of_one_day(qapp, state_dir, info):
    dialog = ud.UpdateDialog(info, forced=False)
    text = _labels(dialog)
    assert "1.1.0" in text
    assert "в течение дня" in text
    assert "будет отключена" in text
    assert "Что нового: стало лучше" in text


def test_forced_text_and_buttons(qapp, state_dir, info):
    dialog = ud.UpdateDialog(info, forced=True)
    assert dialog.btn_quit is not None
    assert dialog.btn_snooze is None, "в принудительном режиме не откладываем"
    text = _labels(dialog)
    assert "отключена" in text
    assert "только после обновления" in text


def test_notify_reject_snoozes(qapp, state_dir, info, monkeypatch):
    calls = []
    monkeypatch.setattr(uc, "snooze", lambda now=None: calls.append(now))
    dialog = ud.UpdateDialog(info, forced=False)
    dialog.reject()
    assert calls, "«Напомнить позже» должен отложить напоминание"
    assert dialog.result() == QDialog.Rejected


def test_forced_reject_does_not_snooze(qapp, state_dir, info, monkeypatch):
    calls = []
    monkeypatch.setattr(uc, "snooze", lambda now=None: calls.append(now))
    dialog = ud.UpdateDialog(info, forced=True)
    dialog.reject()
    assert not calls, "отключение не откладывается"


def test_cannot_close_while_downloading(qapp, state_dir, info):
    class _Busy:
        @staticmethod
        def isRunning() -> bool:
            return True

    dialog = ud.UpdateDialog(info, forced=False)
    dialog.download_thread = _Busy()
    dialog.accept()
    dialog.reject()                     # должен игнорироваться
    assert dialog.result() == QDialog.Accepted, "окно закрылось во время загрузки"


# --- загрузка и установка ----------------------------------------------------

def test_update_flow_installs_and_accepts(qapp, state_dir, info, tmp_path,
                                          monkeypatch):
    setup = tmp_path / "fake_setup.exe"
    setup.write_bytes(b"MZ")
    monkeypatch.setattr(
        uc, "download_update",
        lambda i, dest=None, progress=None: setup,
    )
    installed = []
    monkeypatch.setattr(
        uc, "install_update",
        lambda path, target=None: installed.append(Path(path)),
    )
    dialog = ud.UpdateDialog(info, forced=False)
    dialog.start_update()
    assert not dialog.btn_update.isEnabled(), "на время загрузки кнопки блокируются"
    assert _wait(qapp, lambda: dialog.result() == QDialog.Accepted)
    assert dialog.update_started
    assert installed == [setup]
    _finish_thread(dialog)


def test_download_failure_reports_and_reenables(qapp, state_dir, info,
                                                monkeypatch):
    def fail(i, dest=None, progress=None):
        raise uc.UpdateError("нет связи")
    monkeypatch.setattr(uc, "download_update", fail)
    dialog = ud.UpdateDialog(info, forced=True)
    dialog.start_update()
    assert _wait(qapp, lambda: "Не получилось обновиться" in dialog._status.text())
    assert dialog.btn_update.isEnabled(), "после ошибки можно повторить"
    assert dialog.btn_quit.isEnabled()
    assert dialog.result() != QDialog.Accepted
    _finish_thread(dialog)


# --- гейт запуска ------------------------------------------------------------

class _StubDialog:
    """Окно-заглушка: гейт проверяем, не рисуя настоящее."""

    accept_result = False

    def __init__(self, info, *, forced=False, parent=None):
        self.info = info
        self.forced = forced
        self.download_thread = None
        self.update_started = False

    def exec(self):
        return QDialog.Accepted if self.accept_result else QDialog.Rejected


def test_gate_passes_when_updates_off(state_dir, monkeypatch):
    monkeypatch.setattr(uc, "UPDATE_REPO", "")
    assert ud.run_update_gate() is True


def test_gate_survives_broken_check(state_dir, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("что-то странное")
    monkeypatch.setattr(uc, "check_for_update", boom)
    assert ud.run_update_gate() is True, "поломка проверки не должна ронять запуск"


def test_gate_notify_declined_continues(state_dir, info, monkeypatch):
    monkeypatch.setattr(uc, "check_for_update", lambda **kw: ("notify", info))
    monkeypatch.setattr(ud, "UpdateDialog", _StubDialog)
    _StubDialog.accept_result = False
    assert ud.run_update_gate() is True


def test_gate_notify_accepted_exits(state_dir, info, monkeypatch):
    monkeypatch.setattr(uc, "check_for_update", lambda **kw: ("notify", info))
    monkeypatch.setattr(ud, "UpdateDialog", _StubDialog)
    _StubDialog.accept_result = True
    assert ud.run_update_gate() is False, "обновление запущено — выходим"


def test_gate_forced_cannot_continue(state_dir, info, monkeypatch):
    """Как решено: после срока работа возможна только с обновлением."""
    monkeypatch.setattr(uc, "check_for_update", lambda **kw: ("forced", info))
    monkeypatch.setattr(ud, "UpdateDialog", _StubDialog)
    _StubDialog.accept_result = False
    assert ud.run_update_gate() is False, "отказ от обновления = не пускаем"


def test_gate_forced_update_accepted_exits(state_dir, info, monkeypatch):
    monkeypatch.setattr(uc, "check_for_update", lambda **kw: ("forced", info))
    monkeypatch.setattr(ud, "UpdateDialog", _StubDialog)
    _StubDialog.accept_result = True
    assert ud.run_update_gate() is False


def test_gate_none_state_passes(state_dir, info, monkeypatch):
    monkeypatch.setattr(uc, "check_for_update", lambda **kw: ("none", None))
    assert ud.run_update_gate() is True
