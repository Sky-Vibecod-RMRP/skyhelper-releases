"""Панель «Главная»: прогресс к недельной норме и цифры за сегодня.

Раньше это было отдельное окно, теперь — первый раздел общего окна SKY HELPER
(предложение №1 из баг-репорта: одно окно вместо двух). Кнопка дежурства
уехала в левое меню, чтобы быть на виду из любого раздела.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from app import OWNER_NOTICE
from app.core import Core
from app.export.service import ExportResult
from app.stats.streak import current_streak
from app.ui import theme
from app.util import format_duration

log = logging.getLogger(__name__)

BAR_SCALE = 1000


def days_word(days: int) -> str:
    """3 дня, 5 дней, 1 день — русская плюрация для стрика."""
    if days % 10 == 1 and days % 100 != 11:
        return "день"
    if 2 <= days % 10 <= 4 and not 12 <= days % 100 <= 14:
        return "дня"
    return "дней"


def _repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class ProgressCard(QFrame):
    """Карточка-прогресс: подпись, значение, процент и полоса."""

    def __init__(self, caption: str) -> None:
        super().__init__()
        self.setObjectName("card")
        self._caption = QLabel(caption)
        self._caption.setObjectName("caption")
        self.value = QLabel("-")
        self.value.setObjectName("value")
        self.percent = QLabel("0%")
        self.percent.setObjectName("percent")
        self.bar = QProgressBar()
        self.bar.setRange(0, BAR_SCALE)
        self.bar.setTextVisible(False)

        top = QHBoxLayout()
        top.addWidget(self.value)
        top.addStretch()
        top.addWidget(self.percent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(8)
        layout.addWidget(self._caption)
        layout.addLayout(top)
        layout.addWidget(self.bar)

    def update_values(self, text: str, percent: float) -> None:
        done = percent >= 100
        self.value.setText(text)
        self.percent.setText(f"{percent:.0f}%")
        self.bar.setValue(min(BAR_SCALE, int(percent * BAR_SCALE / 100)))
        for widget in (self.bar, self.percent):
            widget.setProperty("done", done)
            _repolish(widget)


class DashboardPanel(QWidget):
    """Содержимое раздела «Главная»: статистика, стрик, действия."""

    # Готовые цифры приходят из фонового потока: главный поток никогда не
    # читает базу — иначе окно могло зависнуть целиком (AppHang).
    stats_ready = Signal(object)

    def __init__(
        self,
        core: Core,
        actions: Sequence[tuple[str, Callable[[], None]]] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._core = core
        self._stats_snapshot: tuple | None = None
        self._stats_pending = False
        self._stats_stopped = False
        self.stats_ready.connect(self._apply_stats)

        self._game = QLabel()
        self._game.setObjectName("caption")
        self._hours = ProgressCard("ОНЛАЙН ЗА НЕДЕЛЮ")
        self._reports = ProgressCard("ОБРАЩЕНИЯ ЗА НЕДЕЛЮ")
        self._streak = QLabel()
        self._streak.setObjectName("caption")
        self._today = QLabel()
        self._today.setObjectName("caption")
        self._export = QLabel("Таблица: ещё не обновлялась")
        self._export.setObjectName("caption")

        cards = QHBoxLayout()
        cards.setSpacing(12)
        cards.addWidget(self._hours, 1)
        cards.addWidget(self._reports, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 6, 2, 6)
        layout.setSpacing(12)
        layout.addWidget(self._game)
        layout.addLayout(cards)
        layout.addWidget(self._streak)
        layout.addWidget(self._today)
        layout.addStretch(1)

        if actions:
            row = QHBoxLayout()
            row.setSpacing(8)
            for title, callback in actions:
                button = QPushButton(title)
                button.clicked.connect(lambda _checked=False, cb=callback: cb())
                row.addWidget(button)
            row.addStretch()
            layout.addLayout(row)

        layout.addWidget(self._export)

        # предупреждение о правообладании — в самом низу главной страницы
        self._owner = QLabel(OWNER_NOTICE)
        self._owner.setWordWrap(True)
        self._owner.setObjectName("owner-notice")
        self._owner.setStyleSheet(f"color: {theme.MUTED};")
        layout.addWidget(self._owner)
        self.refresh()

    # --- обновление --------------------------------------------------------

    def refresh(self) -> None:
        """Секундный тик: живые флаги сразу, цифры — запросом в фон.

        Главный поток здесь НЕ читает базу: секундный refresh мог
        застрять в SQLite (AppHang — окно «не отвечало», процесс падал).
        """
        self._game.setText(self._status_text(self._core.config.require_duty))
        if self._stats_stopped or self._stats_pending:
            return
        self._stats_pending = True
        threading.Thread(
            target=self._compute_stats, name="stats", daemon=True
        ).start()

    def _compute_stats(self) -> None:
        """Фоновый расчёт: ошибка здесь не должна уронить интерфейс."""
        payload = None
        try:
            now = int(time.time())
            progress = self._core.stats.week_progress(now)
            today = self._core.stats.today(now)
            streak = current_streak(self._core.stats, self._core.config, now)
            payload = (progress, today, streak)
        except Exception:
            if not self._stats_stopped:
                log.exception("Фоновый расчёт статистики не удался")
        finally:
            self._stats_pending = False
        if payload is None:
            return
        try:
            self.stats_ready.emit(payload)
        except RuntimeError:
            pass  # окно уже уничтожено (выход из приложения)

    def _apply_stats(self, payload) -> None:
        """Снимок из фона — обновляем цифры (главный поток)."""
        progress, today, streak = payload
        cfg = self._core.config
        self._stats_snapshot = payload
        self._hours.update_values(
            f"{format_duration(progress.stats.online_seconds)}  из {cfg.weekly_hours_norm:g} ч",
            progress.hours_percent,
        )
        self._reports.update_values(
            f"{progress.stats.reports}  из {cfg.weekly_reports_norm}",
            progress.reports_percent,
        )
        self._set_streak(streak)
        self._today.setText(
            f"Сегодня: {format_duration(today.online_seconds)}, обращений {today.reports}   |   "
            f"{cfg.hotkey_add.upper()} = +1, {cfg.hotkey_remove.upper()} = -1"
        )

    @property
    def stats_snapshot(self) -> tuple | None:
        """Последний готовый снимок — для трея и темпа без чтения базы."""
        return self._stats_snapshot

    def stop_stats(self) -> None:
        """Больше не запускать расчёты (выход из приложения)."""
        self._stats_stopped = True

    def _set_streak(self, streak) -> None:
        if streak.plan_hours > 0 or streak.plan_reports > 0:
            plan = f"норма дня {streak.plan_hours:g} ч / {streak.plan_reports}"
        else:
            plan = "норма дня не задана"
        if streak.days:
            state = "сегодня выполнено" if streak.today_done else "сегодня в процессе"
            self._streak.setStyleSheet(
                f"color: {theme.OK if streak.today_done else theme.TEXT};"
            )
            self._streak.setText(
                f"Стрик: {streak.days} {days_word(streak.days)} подряд  ·  {state}  ·  {plan}"
            )
        else:
            self._streak.setStyleSheet(f"color: {theme.MUTED};")
            self._streak.setText(f"Стрик: нет  ·  сегодня в процессе  ·  {plan}")

    def _status_text(self, require_duty: bool) -> str:
        session = self._core.session
        if session.is_counting:
            return "● Онлайн считается" + (" (на дежурстве)" if require_duty else "")
        if session.is_game_running:
            return "○ Игра запущена, но дежурство выключено: онлайн не считается"
        if session.is_on_duty:
            return "○ Игра не найдена (дежурство включено, ждём запуск игры)"
        return "○ Игра не найдена"

    def set_export_status(self, result: ExportResult) -> None:
        when = time.strftime("%H:%M", time.localtime(result.at))
        if result.ok and result.warning:
            self._export.setStyleSheet(f"color: {theme.WARN};")
            self._export.setText(f"Таблица обновлена в {when}. {result.warning}")
        elif result.ok:
            self._export.setStyleSheet("")
            self._export.setText(f"{result.message} в {when}")
        else:
            self._export.setStyleSheet(f"color: {theme.WARN};")
            self._export.setText(f"Таблица не обновлена ({when}): {result.message}")
