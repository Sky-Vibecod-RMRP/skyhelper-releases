# -*- coding: utf-8 -*-
"""Тесты экрана входа (вариант B): логин + пароль."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.login_dialog import LoginDialog, hash_password

LOGIN = "Tester-STAFF-SKYHELPER"
PASSWORD = "VibecodRMRP-Staff"


@pytest.fixture(scope="session")
def qapp():
    yield QApplication.instance() or QApplication([])


def _dialog() -> LoginDialog:
    return LoginDialog(LOGIN, hash_password(PASSWORD))


def test_hash_password_is_stable():
    assert hash_password(PASSWORD) == hash_password(PASSWORD)
    assert hash_password(PASSWORD) != hash_password("wrong")


def test_correct_credentials_are_accepted(qapp):
    dialog = _dialog()
    dialog._login.setText(LOGIN)
    dialog._password.setText(PASSWORD)
    dialog._check()
    assert dialog.result() == 1          # QDialog.Accepted


def test_wrong_password_is_rejected(qapp):
    dialog = _dialog()
    dialog._login.setText(LOGIN)
    dialog._password.setText("wrong")
    dialog._check()
    assert dialog.result() == 0          # QDialog.Rejected
    assert dialog._error.text() == "Неверный логин или пароль"


def test_wrong_login_is_rejected(qapp):
    dialog = _dialog()
    dialog._login.setText("admin")
    dialog._password.setText(PASSWORD)
    dialog._check()
    assert dialog.result() == 0


def test_empty_credentials_are_rejected(qapp):
    dialog = _dialog()
    dialog._check()
    assert dialog.result() == 0


def test_remember_me_checkbox_is_exposed(qapp):
    dialog = _dialog()
    assert dialog.remember_checked() is False
    dialog._remember.setChecked(True)
    assert dialog.remember_checked() is True
