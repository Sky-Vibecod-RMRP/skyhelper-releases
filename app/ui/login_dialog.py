# -*- coding: utf-8 -*-
"""Экран входа в программу (вариант B): логин + пароль.

Локальная защита: логин и хэш пароля хранятся в config.json. Это не
защита от того, кто разбирается в коде, — только от посторонних.
"""
from __future__ import annotations

import hashlib

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
)

from app.ui.frameless import FramelessMixin


def hash_password(password: str) -> str:
    """SHA-256 хэш пароля (UTF-8) — для локального входа."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class LoginDialog(FramelessMixin, QDialog):
    """Окно входа: логин и пароль. Своя шапка, без системной рамки Windows."""

    def __init__(self, login: str, password_hash: str, parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self._expected_login = login
        self._expected_hash = password_hash

        self._login = QLineEdit()
        self._login.setPlaceholderText("Логин")
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("Пароль")

        self._error = QLabel()
        self._error.setStyleSheet("color: #e5484d; font-size: 12.5px;")
        self._error.setVisible(False)

        self._remember = QCheckBox("Запомнить меня")

        form = QFormLayout()
        form.addRow("Логин:", self._login)
        form.addRow("Пароль:", self._password)

        enter = QPushButton("Войти")
        enter.setObjectName("primary")
        enter.clicked.connect(self._check)
        self._password.returnPressed.connect(self._check)
        self._login.returnPressed.connect(self._password.setFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 18)
        layout.setSpacing(10)
        layout.addWidget(self.init_frameless(
            "SKY HELPER — Вход", closable=True, minimizable=False, resizable=False
        ))
        layout.addLayout(form)
        layout.addWidget(self._remember)
        layout.addWidget(self._error)
        layout.addWidget(enter)

    def remember_checked(self) -> bool:
        """Отмечена ли галочка «Запомнить меня» (для сохранения в настройки)."""
        return self._remember.isChecked()

    def _check(self) -> None:
        login = self._login.text().strip()
        password = self._password.text()
        if (login == self._expected_login
                and hash_password(password) == self._expected_hash):
            self.accept()
            return
        self._error.setText("Неверный логин или пароль")
        self._error.setVisible(True)
        self._password.clear()
        self._password.setFocus()
