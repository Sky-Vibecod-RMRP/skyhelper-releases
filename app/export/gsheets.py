"""Выгрузка статистики в Google Таблицу через сервисный аккаунт.

Листы те же, что в Excel: «Неделя» (с блоками «Сравнение» и «Месяц») и «По дням».
Лист целиком перезаписывается при каждом обновлении.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from app.export.snapshot import Snapshot
from app.util import (
    MONTHS_RU,
    format_hm,
    format_percent_change,
    format_signed_duration,
    format_signed_int,
)

log = logging.getLogger(__name__)

try:
    from gspread.exceptions import APIError, SpreadsheetNotFound
except ImportError:  # gspread не установлен: классы-заглушки, их никто не бросит
    class SpreadsheetNotFound(Exception):  # type: ignore[no-redef]
        pass

    class APIError(Exception):  # type: ignore[no-redef]
        pass

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
API_TIMEOUT_SEC = 20


class GoogleSheetsError(Exception):
    """Ошибка, которую можно показать пользователю как есть."""


@dataclass
class Table:
    rows: list[list[Any]]
    bold_rows: list[int] = field(default_factory=list)  # номера строк с 1
    freeze_rows: int = 0


def _pct(value: float, norm: float) -> str:
    return f"{value / norm * 100:.0f}%" if norm > 0 else "0%"


def build_tables(snapshot: Snapshot) -> dict[str, Table]:
    week = snapshot.week
    cur, prev, month = week.stats, snapshot.prev_week, snapshot.month
    updated = datetime.fromtimestamp(snapshot.generated_at)
    month_title = f"{MONTHS_RU[snapshot.month_start.month - 1]} {snapshot.month_start.year}"

    elapsed = max(1, snapshot.elapsed_days)
    plan_hours = week.hours_norm / 7
    plan_reports = week.reports_norm / 7
    forecast_hours = cur.online_hours / elapsed * 7
    forecast_reports = max(0.0, cur.reports / elapsed * 7)
    today = snapshot.today

    summary = [
        ["SKY HELPER"],
        [f"Неделя {snapshot.week_start:%d.%m.%Y} — {snapshot.week_end:%d.%m.%Y}"],
        [f"Обновлено: {updated:%d.%m.%Y %H:%M}"],
        [],
        ["Показатель", "Факт", "Норма", "Выполнено"],                                   # 5
        ["Онлайн (ч:мм)", format_hm(cur.online_seconds),
         format_hm(week.hours_norm * 3600), _pct(cur.online_hours, week.hours_norm)],
        ["Обращения", cur.reports, week.reports_norm, _pct(cur.reports, week.reports_norm)],
        [],
        ["Сегодня: план на день и факт"],                                               # 9
        ["Показатель", "План в день", "Факт сегодня", "Выполнено"],                      # 10
        ["Онлайн (ч:мм)", format_hm(plan_hours * 3600),
         format_hm(today.online_seconds), _pct(today.online_hours, plan_hours)],
        ["Обращения", round(plan_reports), today.reports,
         _pct(today.reports, plan_reports)],
        [],
        ["Сравнение с прошлой неделей"],                                                # 14
        ["Показатель", "Эта неделя", "Прошлая неделя", "Разница", "Изменение"],         # 15
        ["Онлайн (ч:мм)", format_hm(cur.online_seconds), format_hm(prev.online_seconds),
         format_signed_duration(cur.online_seconds - prev.online_seconds),
         format_percent_change(cur.online_seconds, prev.online_seconds)],
        ["Обращения", cur.reports, prev.reports,
         format_signed_int(cur.reports - prev.reports),
         format_percent_change(cur.reports, prev.reports)],
        [],
        ["Прогноз к концу недели при текущем темпе"],                                   # 19
        ["Показатель", "Прогноз", "Норма", "Выполнено"],                                # 20
        ["Онлайн (ч:мм)", format_hm(forecast_hours * 3600),
         format_hm(week.hours_norm * 3600), _pct(forecast_hours, week.hours_norm)],
        ["Обращения", round(forecast_reports), week.reports_norm,
         _pct(forecast_reports, week.reports_norm)],
        [],
        [f"Итог за месяц: {month_title}"],                                              # 24
        ["Показатель", "Факт", "Норма (≈)", "Выполнено"],                               # 25
        ["Онлайн (ч:мм)", format_hm(month.online_seconds),
         format_hm(snapshot.month_hours_norm * 3600),
         _pct(month.online_hours, snapshot.month_hours_norm)],
        ["Обращения", month.reports, round(snapshot.month_reports_norm),
         _pct(month.reports, snapshot.month_reports_norm)],
    ]

    days = [["Дата", "День", "Онлайн (ч:мм)", "Часы", "Обращения"]]
    for item in reversed(snapshot.days):  # по порядку, от раннего дня к позднему
        days.append([
            f"{item.day:%d.%m.%Y}",
            WEEKDAYS[item.day.weekday()],
            format_hm(item.online_seconds),
            round(item.online_seconds / 3600, 2),
            item.reports,
        ])

    return {
        "Неделя": Table(summary, bold_rows=[1, 5, 9, 10, 14, 15, 19, 20, 24, 25]),
        "По дням": Table(days, bold_rows=[1], freeze_rows=1),
    }


def _default_client(credentials_path: str):
    import gspread  # импорт здесь: без Google-настроек библиотека не нужна

    client = gspread.service_account(filename=credentials_path)
    if hasattr(client, "set_timeout"):
        client.set_timeout(API_TIMEOUT_SEC)
    return client


def upload_tables(
    tables: dict[str, Table],
    spreadsheet_id: str,
    credentials_path: str,
    client_factory: Callable[[str], Any] = _default_client,
) -> None:
    """Перезаписывает листы в Google Таблице. Бросает GoogleSheetsError с понятным текстом."""
    try:
        client = client_factory(credentials_path)
        spreadsheet = client.open_by_key(spreadsheet_id)
        existing = {ws.title: ws for ws in spreadsheet.worksheets()}
        for title, table in tables.items():
            width = max((len(r) for r in table.rows), default=1)
            rows_needed = max(len(table.rows) + 20, 50)
            cols_needed = max(width, 6)
            ws = existing.get(title)
            if ws is None:
                ws = spreadsheet.add_worksheet(
                    title=title, rows=rows_needed, cols=cols_needed
                )
            elif rows_needed > ws.row_count or cols_needed > ws.col_count:
                # Лист «По дням» растёт на строку в день: если не расширить сетку,
                # API вернёт 400 «exceeds grid limits» и выгрузка сломается насовсем.
                ws.resize(
                    rows=max(ws.row_count, rows_needed),
                    cols=max(ws.col_count, cols_needed),
                )
            ws.clear()
            ws.update(values=table.rows, range_name="A1")
            for row in table.bold_rows:
                ws.format(f"{row}:{row}", {"textFormat": {"bold": True}})
            if table.freeze_rows:
                ws.freeze(rows=table.freeze_rows)
    except GoogleSheetsError:
        raise
    except ImportError as exc:
        raise GoogleSheetsError("Не установлена библиотека gspread (pip install gspread)") from exc
    except SpreadsheetNotFound as exc:
        raise GoogleSheetsError(
            "Google Таблица не найдена: проверь gsheet_id и дай доступ «Редактор» "
            "e-mail сервисного аккаунта"
        ) from exc
    except APIError as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        if code in (403, 404):
            raise GoogleSheetsError(
                "Google не пускает к таблице: дай доступ «Редактор» e-mail сервисного аккаунта"
            ) from exc
        raise GoogleSheetsError(f"Ошибка Google API ({code or '?'})") from exc
    except FileNotFoundError as exc:
        raise GoogleSheetsError(f"Не найден ключ Google: {credentials_path}") from exc
    except (OSError, ValueError) as exc:
        # сюда попадают и нет интернета, и битый JSON-ключ
        raise GoogleSheetsError(f"Не удалось связаться с Google: {exc}") from exc
