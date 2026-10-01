# -*- coding: utf-8 -*-
"""Окно активации: первый запуск exe, выдача ключа и его проверка.

Схема (решение 01.10.2026): ключи выдаёт администратор проекта вручную,
привязывая их к коду конкретного ПК. Пользователь здесь видит **свой**
код ПК, копирует его администратору и вставляет полученный ключ.

Проверка ключа — см. :mod:`app.license` (подпись Ed25519 → ПК → срок →
список отзывов → откат часов). Окно занимается только разговором
с человеком и сохранением ключа в ``%APPDATA%``.
"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout,
)

from app import hwid
from app import license as lic
from app.ui.frameless import FramelessMixin

log = logging.getLogger(__name__)

_ERROR_STYLE = "color: #e5484d; font-size: 12.5px;"
_HINT_STYLE = "color: #8b949e; font-size: 12px;"


class ActivationDialog(FramelessMixin, QDialog):
    """Код ПК с одной стороны, ключ — с другой."""

    def __init__(self, reason: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Активация")

        intro = QLabel(
            "Программа активируется ключом. Отправьте показанный ниже код "
            "своему администратору — он выдаст ключ на нужный срок."
        )
        intro.setWordWrap(True)

        self._code = QLineEdit()
        self._code.setReadOnly(True)
        self._code.setObjectName("codeField")
        try:
            self._code.setText(hwid.current())
        except hwid.HwidError as exc:
            self._code.setText("—")
            self._code.setToolTip(str(exc))

        copy = QPushButton("Копировать код")
        copy.clicked.connect(self._copy_code)

        code_row = QHBoxLayout()
        code_row.setSpacing(8)
        code_row.addWidget(self._code, 1)
        code_row.addWidget(copy)

        self._key = QLineEdit()
        self._key.setPlaceholderText("Вставьте ключ сюда (одной длинной строкой)")
        self._key.setClearButtonEnabled(True)

        paste = QPushButton("Вставить")
        paste.setToolTip("Вставить ключ из буфера обмена")
        paste.clicked.connect(self._paste_key)

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_row.addWidget(self._key, 1)
        key_row.addWidget(paste)

        self._error = QLabel(reason or "")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(_ERROR_STYLE if reason else _HINT_STYLE)
        self._error.setVisible(bool(reason))

        self._note = QLabel(
            "Ключ действует ограниченный срок и привязан только к этому "
            "компьютеру."
        )
        self._note.setWordWrap(True)
        self._note.setStyleSheet(_HINT_STYLE)

        activate = QPushButton("Активировать")
        activate.setObjectName("primary")
        activate.clicked.connect(self.activate)
        self._key.returnPressed.connect(self.activate)

        cancel = QPushButton("Выход")
        cancel.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(activate)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 18)
        layout.setSpacing(10)
        layout.addWidget(self.init_frameless(
            "SKY HELPER — Активация", closable=True, minimizable=False,
            resizable=False,
        ))
        layout.addWidget(intro)
        layout.addWidget(QLabel("Код этого компьютера:"))
        layout.addLayout(code_row)
        layout.addWidget(QLabel("Ключ активации:"))
        layout.addLayout(key_row)
        layout.addWidget(self._error)
        layout.addWidget(self._note)
        layout.addLayout(buttons)

    # --- действия -----------------------------------------------------------

    def _copy_code(self) -> None:
        code = self._code.text().strip()
        if code and code != "—":
            QApplication.clipboard().setText(code)
            self._show_hint("Код скопирован — отправьте его администратору")

    def _paste_key(self) -> None:
        self._key.setText(QApplication.clipboard().text().strip())
        self._key.setFocus()

    def _show_hint(self, text: str) -> None:
        self._error.setStyleSheet(_HINT_STYLE)
        self._error.setText(text)
        self._error.setVisible(True)

    def _show_error(self, text: str) -> None:
        self._error.setStyleSheet(_ERROR_STYLE)
        self._error.setText(text)
        self._error.setVisible(True)

    def activate(self) -> bool:
        """Проверить вставленный ключ и, если всё сходится, принять его."""
        text = self._key.text().strip()
        if not text:
            self._show_error("Вставьте ключ — длинную строку из чата")
            return False
        try:
            code = hwid.current()
        except hwid.HwidError as exc:
            self._show_error(f"Не удалось получить код ПК: {exc}")
            return False
        try:
            lic.verify(text, hwid=code)
        except lic.LicenseError as exc:
            log.warning("Лицензия: ключ не принят (%s): %s", exc.code, exc.message)
            self._show_error(exc.message)
            return False
        lic.save_license_text(text)
        try:
            result = lic.check(hwid_value=code)   # отзыв по кэшу + откат часов
        except lic.LicenseError as exc:
            log.warning("Лицензия: ключ не принят (%s): %s", exc.code, exc.message)
            self._show_error(exc.message)
            return False
        log.info("Лицензия: ключ активирован, действует до %s",
                 result.expires.isoformat())
        self.accept()
        return True


def ensure_licensed(config=None, *, parent=None) -> bool:
    """Пустить ли запуск. True — да, False — человек вышел без активации.

    В собранном ``exe`` проверка обязательна; в исходниках она включается
    сама, как только ключ активирован локально (см.
    :func:`app.license.enforcement_required`). После успешной проверки
    запоминается время запуска (защита от отката часов) и, если задан
    адрес списка отзывов, его кэш обновляется в фоне.
    """
    if not lic.enforcement_required():
        return True
    attempts = 0
    while True:
        try:
            result = lic.check()
            break
        except lic.LicenseError as exc:
            log.warning("Лицензия: отказ (%s): %s", exc.code, exc.message)
            dialog = ActivationDialog(reason=exc.message, parent=parent)
            if not dialog.exec():
                return False
            attempts += 1
            if attempts >= 3:
                return False      # не выходим в бесконечный цикл окон
    log.info("Лицензия: ключ %s действует до %s",
             result.key_id, result.expires.isoformat())
    lic.save_state(result)
    url = "" if config is None else (config.revocation_url or "")
    lic.start_revocation_refresh(url or lic.DEFAULT_REVOCATION_URL)
    return True
