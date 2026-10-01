# -*- coding: utf-8 -*-
"""Окно активации, гейт запуска и вкладка «Лицензия» в настройках.

Как и в test_license.py, тут одноразовые ключи Ed25519 и временная папка
вместо %APPDATA%: приватный ключ администратора и реальные настройки
участниками тестов не становятся.
"""
from __future__ import annotations

import datetime as dt
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QTabWidget  # noqa: E402

from app import hwid  # noqa: E402
from app import license as lic  # noqa: E402
from app import license_public  # noqa: E402
from app.config import Config  # noqa: E402
from app.ui import activation_dialog as gate  # noqa: E402
from app.ui.activation_dialog import ActivationDialog  # noqa: E402
from app.ui.settings_dialog import SettingsDialog  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def pair():
    private = Ed25519PrivateKey.generate()
    pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private, pem


@pytest.fixture()
def sandbox(tmp_path, monkeypatch, pair):
    """Временная папка приложения + свой ключ подписи вместо общего."""
    monkeypatch.setattr(lic, "app_dir", lambda: tmp_path)
    monkeypatch.setattr(license_public, "PUBLIC_KEY_PEM", pair[1])
    monkeypatch.setattr(lic.sys, "frozen", False, raising=False)
    return tmp_path


def issue(private, *, pc: str, days: int = 30) -> str:
    payload = lic.build_payload(
        pc, "2026-10-01T10:00:00Z",
        dt.date.today() + dt.timedelta(days=days), "Тест",
    )
    return lic.sign_payload(payload, private)


# --- окно активации ---------------------------------------------------------


def test_dialog_shows_reason_and_code(qapp, sandbox):
    dialog = ActivationDialog(reason="Срок ключа истёк 01.10.2026")
    assert dialog._error.isVisible() or dialog._error.text()
    assert "истёк" in dialog._error.text()
    # код ПК этой машины (или «—», если источники недоступны)
    code = dialog._code.text()
    assert code == "—" or hwid.matches(code, hwid.current())


def test_activate_empty_key_shows_error(qapp, sandbox):
    dialog = ActivationDialog()
    assert dialog.activate() is False
    assert "Вставьте ключ" in dialog._error.text()
    assert not lic.license_path().exists()      # ничего не сохранилось


def test_activate_rejects_foreign_pc(qapp, sandbox, pair):
    private, _pem = pair
    dialog = ActivationDialog()
    dialog._key.setText(issue(private, pc="RM-AAAA-BBBB-CCCC-DDDD"))
    assert dialog.activate() is False
    assert "другого компьютера" in dialog._error.text()
    assert not lic.license_path().exists()


def test_activate_rejects_broken_key(qapp, sandbox, pair):
    private, _pem = pair
    stranger = Ed25519PrivateKey.generate()
    dialog = ActivationDialog()
    dialog._key.setText(issue(stranger, pc=hwid.current()))
    assert dialog.activate() is False
    assert "Подпись не проходит" in dialog._error.text()


def test_activate_accepts_valid_key(qapp, sandbox, pair):
    private, _pem = pair
    dialog = ActivationDialog()
    dialog._key.setText(issue(private, pc=hwid.current()))
    assert dialog.activate() is True
    assert dialog.result() == dialog.DialogCode.Accepted
    assert lic.read_license_text()             # ключ сохранился


def test_activate_rejects_revoked_key(qapp, sandbox, pair):
    private, _pem = pair
    text = issue(private, pc=hwid.current())
    kid = lic.key_id(lic.parse_and_verify(text, public_pem=pair[1])[0])
    lic.save_cached_revocations(
        lic.sign_revocations([kid], private_key=private)
    )
    dialog = ActivationDialog()
    dialog._key.setText(text)
    assert dialog.activate() is False
    assert "отозван" in dialog._error.text()
    # ключ мог записаться в файл, но пуска не будет — на старте тоже откажем


# --- гейт запуска -----------------------------------------------------------


def test_gate_off_in_sources_without_key(sandbox, monkeypatch):
    # разработка и тесты: ключа нет и exe не собран — пускаем
    assert gate.ensure_licensed(Config()) is True


def test_gate_passes_with_valid_license(sandbox, pair, monkeypatch):
    private, _pem = pair
    lic.save_license_text(issue(private, pc=hwid.current()))
    assert gate.ensure_licensed(Config()) is True
    # запуск запомнился — работает защита от отката часов
    assert lic.load_state().get("last_seen")


def test_gate_exits_when_dialog_cancelled(sandbox, monkeypatch):
    monkeypatch.setattr(lic.sys, "frozen", True, raising=False)   # как в exe
    seen: list[str] = []

    class _Cancel:
        def __init__(self, reason: str = "", parent=None) -> None:
            seen.append(reason)

        def exec(self) -> bool:
            return False

    monkeypatch.setattr(gate, "ActivationDialog", _Cancel)
    assert gate.ensure_licensed(Config()) is False
    assert seen and "не найден" in seen[0]


def test_gate_does_not_loop_forever(sandbox, monkeypatch):
    # окно «приняло» ключ, но check всё равно падает — выходим, не зависаем
    monkeypatch.setattr(lic.sys, "frozen", True, raising=False)   # как в exe
    calls = {"n": 0}

    class _Accept:
        def __init__(self, reason: str = "", parent=None) -> None:
            pass

        def exec(self) -> bool:
            calls["n"] += 1
            return True

    monkeypatch.setattr(gate, "ActivationDialog", _Accept)
    assert gate.ensure_licensed(Config()) is False
    assert calls["n"] == 3


def test_gate_skipped_only_in_sources(sandbox, monkeypatch):
    # в собранный exe проверка обязательна даже без файла ключа
    monkeypatch.setattr(lic.sys, "frozen", True, raising=False)
    assert lic.enforcement_required()


# --- вкладка «Лицензия» в настройках ---------------------------------------

class _Core:
    def __init__(self) -> None:
        self.config = Config()
        self.web_running = False
        self.web_error = ""
        self.site_url = None
        self.apply_calls = 0

    def apply_config(self) -> None:
        self.apply_calls += 1


def test_settings_have_license_tab(qapp):
    dialog = SettingsDialog(_Core())
    try:
        tabs = dialog.findChild(QTabWidget)
        labels = [tabs.tabText(i) for i in range(tabs.count())]
        assert "Лицензия" in labels
        # код ПК показан (или честный прочерк, если отпечаток недоступен)
        assert dialog._lic_code.text() in {"—"} | {hwid.current()}
    finally:
        dialog.close()


def test_settings_status_without_key(qapp, sandbox):
    dialog = SettingsDialog(_Core())
    try:
        dialog._refresh_license_status()
        assert "не активирован" in dialog._lic_status.text().lower()
    finally:
        dialog.close()


def test_settings_status_with_key(qapp, sandbox, pair):
    private, _pem = pair
    lic.save_license_text(issue(private, pc=hwid.current(), days=30))
    dialog = SettingsDialog(_Core())
    try:
        dialog._refresh_license_status()
        assert "действует до" in dialog._lic_status.text().lower()
    finally:
        dialog.close()


def test_settings_activation_saves_key(qapp, sandbox, pair):
    private, _pem = pair
    dialog = SettingsDialog(_Core())
    try:
        dialog._lic_key.setText(issue(private, pc=hwid.current()))
        dialog._activate_license()
        assert lic.read_license_text()
        assert "действует до" in dialog._lic_status.text().lower()
    finally:
        dialog.close()


def test_settings_collect_writes_revocation_url(qapp):
    core = _Core()
    dialog = SettingsDialog(core)
    try:
        dialog._revocation_url.setText("https://example.test/revoked.json")
        assert dialog._collect() is True
        assert core.config.revocation_url == "https://example.test/revoked.json"
    finally:
        dialog.close()
