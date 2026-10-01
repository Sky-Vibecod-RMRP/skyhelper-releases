# -*- coding: utf-8 -*-
"""Окно обновления: «доступна версия X» и принудительное отключение.

Два режима одного окна (:mod:`app.update_check` решает, какой):

* **notify** — «Доступна версия X: обновитесь в течение дня». Кнопки
  «Обновить сейчас» и «Напомнить позже» (откладывает напоминание);
* **forced** — срок прошёл, старая версия отключена: остаётся только
  обновиться или выйти. Кнопки «Обновить сейчас» и «Выход»,
  крестика у окна нет.

Загрузка идёт в фоне (:class:`_Download`), с прогрессом; установка —
молчаливый установщик + перезапуск (см. :func:`app.update_check.install_update`).
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

from app import VERSION, update_check as uc
from app.ui.frameless import FramelessMixin

log = logging.getLogger(__name__)

_HINT_STYLE = "color: #8b949e; font-size: 12px;"
_ERROR_STYLE = "color: #e5484d; font-size: 12.5px;"


class _Download(QThread):
    """Скачивание установщика в фоне; результат — сигналом в окно."""

    done = Signal(str)
    failed = Signal(str)
    progressed = Signal(int, int)

    def __init__(self, info: uc.UpdateInfo, parent=None) -> None:
        super().__init__(parent)
        self._info = info

    def run(self) -> None:
        try:
            path = uc.download_update(
                self._info,
                progress=lambda done, total: self.progressed.emit(done, total),
            )
        except Exception as exc:  # noqa: BLE001 — текст ошибки уходит в окно
            log.warning("Обновления: загрузка не удалась: %s", exc)
            self.failed.emit(str(exc))
            return
        self.done.emit(str(path))


class UpdateDialog(FramelessMixin, QDialog):
    """Уведомление об обновлении и принудительное обновление — одним окном."""

    def __init__(
        self,
        info: uc.UpdateInfo,
        *,
        forced: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setModal(True)
        self._info = info
        self._forced = forced
        self.update_started = False
        self.download_thread: _Download | None = None

        if forced:
            intro_text = (
                f"Прошлая версия отключена: доступна {info.version}, "
                f"у вас {VERSION}.\n"
                "Работа возможна только после обновления."
            )
        else:
            intro_text = (
                f"Доступна версия {info.version} (у вас {VERSION}).\n"
                "Обновитесь в течение дня — после этого прошлая версия "
                "будет отключена."
            )
        intro = QLabel(intro_text)
        intro.setWordWrap(True)

        notes = QLabel(info.notes.strip())
        notes.setWordWrap(True)
        notes.setStyleSheet(_HINT_STYLE)
        notes.setVisible(bool(info.notes.strip()))

        hint = QLabel(
            "Сначала скачается установщик, затем программа молча обновится "
            "и перезапустится. Настройки и активация сохранятся."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(_HINT_STYLE)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(_HINT_STYLE)
        self._status.setVisible(False)

        self._bar = QProgressBar()
        self._bar.setVisible(False)

        self.btn_update = QPushButton("Обновить сейчас")
        self.btn_update.setObjectName("primary")
        self.btn_update.clicked.connect(self.start_update)

        self.btn_snooze: QPushButton | None = None
        self.btn_quit: QPushButton | None = None

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        if forced:
            self.btn_quit = QPushButton("Выход")
            self.btn_quit.clicked.connect(self.reject)
            buttons.addWidget(self.btn_quit)
        else:
            self.btn_snooze = QPushButton("Напомнить позже")
            self.btn_snooze.clicked.connect(self.reject)
            buttons.addWidget(self.btn_snooze)
        buttons.addWidget(self.btn_update)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 18)
        layout.setSpacing(10)
        layout.addWidget(self.init_frameless(
            "SKY HELPER — Обновление",
            closable=not forced, minimizable=False, resizable=False,
        ))
        layout.addWidget(intro)
        layout.addWidget(notes)
        layout.addWidget(hint)
        layout.addWidget(self._bar)
        layout.addWidget(self._status)
        layout.addLayout(buttons)

    # --- закрытие ------------------------------------------------------------

    def reject(self) -> None:
        """Закрытие (крестик, Esc, «Напомнить позже», «Выход»).

        Во время загрузки закрыться нельзя — иначе поток останется
        работать на уничтоженном окном. В режиме notify закрытие
        откладывает напоминание.
        """
        if self.download_thread is not None and self.download_thread.isRunning():
            return
        if not self._forced and not self.update_started:
            uc.snooze()
        super().reject()

    # --- действия ------------------------------------------------------------

    def start_update(self) -> None:
        self.btn_update.setEnabled(False)
        if self.btn_snooze is not None:
            self.btn_snooze.setEnabled(False)
        if self.btn_quit is not None:
            self.btn_quit.setEnabled(False)
        self._bar.setVisible(True)
        self._bar.setRange(0, 0)               # размер пока неизвестен
        self._status.setText("Скачивание установщика…")
        self._status.setVisible(True)
        self.download_thread = _Download(self._info, self)
        self.download_thread.progressed.connect(self._on_progress)
        self.download_thread.done.connect(self._on_done)
        self.download_thread.failed.connect(self._on_failed)
        self.download_thread.start()

    def _on_progress(self, done: int, total: int) -> None:
        if total <= 0:
            return
        percent = min(100, int(done * 100 / total))
        self._bar.setRange(0, 100)
        self._bar.setValue(percent)
        self._status.setText(f"Скачивание… {percent}%")

    def _on_done(self, path: str) -> None:
        self._status.setStyleSheet(_HINT_STYLE)
        self._status.setText("Устанавливается — программа перезапустится…")
        try:
            uc.install_update(Path(path))
        except Exception as exc:  # noqa: BLE001 — покажем и дадим повторить
            log.warning("Обновления: запустить установщик не удалось: %s", exc)
            self._on_failed(str(exc))
            return
        self.update_started = True
        self.accept()

    def _on_failed(self, message: str) -> None:
        self._bar.setVisible(False)
        self._status.setStyleSheet(_ERROR_STYLE)
        self._status.setText(
            f"Не получилось обновиться: {message}. Попробуйте ещё раз."
        )
        self._status.setVisible(True)
        self.btn_update.setEnabled(True)
        if self.btn_snooze is not None:
            self.btn_snooze.setEnabled(True)
        if self.btn_quit is not None:
            self.btn_quit.setEnabled(True)


def run_update_gate(config=None, *, parent=None) -> bool:
    """Проверить обновления при запуске. True — продолжаем, False — выходим.

    * всё свежее / обновления выключены / нет сети — продолжаем молча;
    * notify — показываем окно; «Напомнить позже» и Esc — продолжаем,
      «Обновить сейчас» — обновление запущено, выходим (новая копия
      сама перезапустится);
    * forced — как принято: без обновления не пускаем; остаётся
      «Обновить сейчас» или «Выход».

    ``config`` зарезервирован под будущие настройки (как у ensure_licensed).
    """
    try:
        status, info = uc.check_for_update()
    except Exception:  # noqa: BLE001 — проверка обновлений не должна ломать запуск
        log.exception("Обновления: проверка не удалась")
        return True
    if info is None or status == "none":
        return True
    forced = status == "forced"
    log.info("Обновления: статус %s, доступна версия %s (у нас %s)",
             status, info.version, VERSION)
    dialog = UpdateDialog(info, forced=forced, parent=parent)
    try:
        accepted = dialog.exec() == QDialog.Accepted
    finally:
        thread = dialog.download_thread
        if thread is not None:
            thread.wait(60_000)      # не даём уничтожить работающий поток
    if accepted:
        return False                 # обновление запущено — завершаемся
    return not forced                # notify — работаем, forced — выходим
