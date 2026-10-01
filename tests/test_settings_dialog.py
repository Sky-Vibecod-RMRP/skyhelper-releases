"""Тесты экрана настроек.

Ядро подменяется фейком: настоящий Core трогает реальные data.db и config.json
в %APPDATA%, в тестах такое недопустимо.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # без экрана и без окон

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.config import Config  # noqa: E402
from app.ui.settings_dialog import SettingsDialog  # noqa: E402


class FakeCore:
    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.web_running = False
        self.web_error = ""
        self.site_url = None
        self.apply_calls = 0

    def apply_config(self) -> None:
        self.apply_calls += 1
        self.web_running = self.config.web_enabled


@pytest.fixture(scope="session")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def core():
    return FakeCore()


def test_dialog_shows_current_values(qapp, core):
    dialog = SettingsDialog(core)
    assert dialog._hours_norm.value() == 70.0
    assert dialog._reports_norm.value() == 600
    assert dialog._web_port.value() == 80
    assert dialog._web_on.isChecked() is False
    assert dialog._key_duty.text() == "f10"
    assert dialog._ui_theme.currentData() == "dark"


def test_save_writes_values_back_and_restarts_services(qapp, core):
    dialog = SettingsDialog(core)
    dialog._hours_norm.setValue(65.5)
    dialog._reports_norm.setValue(540)
    dialog._require_duty.setChecked(False)
    dialog._processes.setText("RAGE.exe, GTA5.exe")

    dialog.accept()

    assert core.apply_calls == 1
    assert core.config.weekly_hours_norm == 65.5
    assert core.config.weekly_reports_norm == 540
    assert core.config.require_duty is False
    assert core.config.game_processes == ["RAGE.exe", "GTA5.exe"]


def test_pin_is_stored_only_as_hash(qapp, core):
    dialog = SettingsDialog(core)
    dialog._web_on.setChecked(True)
    dialog._pin.setText("секретный-код")

    dialog.accept()

    stored = core.config.web_pin_hash
    assert stored.startswith("pbkdf2_sha256$")
    assert "секретный-код" not in stored
    assert core.config.web_enabled is True


def test_clearing_pin_removes_it(qapp, core):
    core.config.web_pin_hash = "pbkdf2_sha256$1$aa$bb"
    dialog = SettingsDialog(core)
    dialog._clear_pin()
    dialog.accept()
    assert core.config.web_pin_hash == ""


def test_network_access_flips_host(qapp, core):
    dialog = SettingsDialog(core)
    dialog._web_on.setChecked(True)
    dialog._web_lan.setChecked(True)
    dialog.accept()
    assert core.config.web_host == "0.0.0.0"

    dialog = SettingsDialog(core)
    dialog._web_lan.setChecked(False)
    dialog.accept()
    assert core.config.web_host == "127.0.0.1"


def test_empty_hotkey_blocks_saving(qapp, core, monkeypatch):
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning",
                        lambda *args, **kwargs: warnings.append(str(args[2])))
    dialog = SettingsDialog(core)
    dialog._key_duty.setText("   ")

    dialog.accept()

    assert core.apply_calls == 0, "сохраняться с пустой клавишей не должно"
    assert warnings and "дежурства" in warnings[0]


def test_unknown_theme_in_config_does_not_crash(qapp):
    core = FakeCore(Config(ui_theme="alien", sound_theme="mute"))
    dialog = SettingsDialog(core)
    assert dialog._ui_theme.currentData() in ("dark", "midnight", "light")
    assert dialog._sound_theme.currentData() in ("off", "system", "soft")
