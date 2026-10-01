"""Запись снимка в файл Excel (.xlsx).

Три листа: «Неделя» (KPI, сравнение, месяц, темп и прогноз), «По дням»
(детализация с планом и выполнением, диаграмма) и «Динамика» (последние
недели с диаграммой часов и обращений).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.export.snapshot import Snapshot
from app.util import (
    MONTHS_RU,
    format_signed_duration,
    percent_change,
)

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
FONT_NAME = "Segoe UI"
DURATION_FORMAT = "[h]:mm"
SECONDS_IN_DAY = 86400


def _font(**kwargs):
    """Шрифт с явным семейством: иначе Excel подставит свой."""
    kwargs.setdefault("name", FONT_NAME)
    return Font(**kwargs)

# Палитра: тёмные заголовки как в приложении, светлые полосы для разделов.
TITLE_FILL = PatternFill("solid", fgColor="11161F")
HEADER_FILL = PatternFill("solid", fgColor="151B26")
SECTION_FILL = PatternFill("solid", fgColor="E8F0FE")
ZEBRA_FILL = PatternFill("solid", fgColor="F5F7FA")
TOTAL_FILL = PatternFill("solid", fgColor="EDF1F7")
HEADER_FONT = _font(bold=True, color="FFFFFF")
TITLE_FONT = _font(bold=True, size=14, color="FFFFFF")
SUBTITLE_FONT = _font(size=10, color="C9D1D9")
UPDATED_FONT = _font(size=10, color="8B98A9")
SECTION_FONT = _font(bold=True, size=11, color="1F6FEB")
LABEL_FONT = _font(bold=True, color="1F2937")
VALUE_FONT = _font(bold=True, size=11)
MUTED_FONT = _font(size=10, color="6B7280")
GREEN = "1E8E5A"
RED = "C0392B"
BLUE = "1F6FEB"
AMBER = "B45309"

THIN = Side(style="thin", color="D5DBE5")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
TOTAL_BORDER = Border(left=THIN, right=THIN, top=Side(style="double", color="9AA4B2"),
                      bottom=THIN)


class ExportError(Exception):
    """Ошибка, которую можно показать пользователю как есть."""


# --- небольшие помощники стилей -----------------------------------------

def _style_header(ws, row: int, columns: int) -> None:
    for col in range(1, columns + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    ws.row_dimensions[row].height = 20


def _set_widths(ws, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width


def _banner(ws, columns: int, title: str, subtitle: str, updated: str) -> None:
    """Тёмный блок шапки из трёх строк."""
    for row in range(1, 4):
        for col in range(1, columns + 1):
            ws.cell(row=row, column=col).fill = TITLE_FILL
    ws["A1"] = title
    ws["A1"].font = TITLE_FONT
    ws["A2"] = subtitle
    ws["A2"].font = SUBTITLE_FONT
    ws["A3"] = updated
    ws["A3"].font = UPDATED_FONT
    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 15
    ws.row_dimensions[3].height = 15


def _section(ws, row: int, text: str, columns: int) -> None:
    for col in range(1, columns + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = SECTION_FILL
        cell.font = SECTION_FONT
    ws.cell(row=row, column=1).value = text
    ws.row_dimensions[row].height = 20


def _zebra(ws, rows: range, columns: int) -> None:
    """Полосатые строки с рамками: читается даже без границ экрана."""
    for index, row in enumerate(rows):
        for col in range(1, columns + 1):
            cell = ws.cell(row=row, column=col)
            cell.border = BORDER
            if index % 2:
                cell.fill = ZEBRA_FILL
        ws.row_dimensions[row].height = 19


def _pct(cell, value: float, fmt: str = "0%") -> None:
    """Процент: формат, цвет и жирность по результату."""
    cell.value = value
    cell.number_format = fmt
    if value >= 1:
        color, bold = GREEN, True
    elif value >= 0.5:
        color, bold = BLUE, False
    else:
        color, bold = AMBER, False
    cell.font = _font(bold=bold, color=color, size=11)
    cell.alignment = Alignment(horizontal="center")


def _signed(cell, delta: float, text: str | None = None) -> None:
    """Значение со знаком: зелёный рост, красный спад."""
    if text is not None:
        cell.value = text
    color = GREEN if delta > 0 else RED if delta < 0 else "6B7280"
    cell.font = _font(bold=True, color=color)
    cell.alignment = Alignment(horizontal="right")


def _percent(value: float, norm: float) -> float:
    return value / norm if norm > 0 else 0.0


def _day_count(value: float) -> float:
    return value / SECONDS_IN_DAY


# --- лист «Неделя» -------------------------------------------------------

def _fill_week_sheet(ws, snapshot: Snapshot) -> None:
    _banner(
        ws, 5,
        "SKY HELPER",
        f"Неделя {snapshot.week_start:%d.%m.%Y} — {snapshot.week_end:%d.%m.%Y}",
        f"Обновлено: {datetime.fromtimestamp(snapshot.generated_at):%d.%m.%Y %H:%M}",
    )

    for col, title in enumerate(["Показатель", "Факт", "Норма", "Выполнено"], start=1):
        ws.cell(row=5, column=col, value=title)
    _style_header(ws, 5, 4)

    week = snapshot.week
    ws["A6"] = "Онлайн (ч:мм)"
    ws["B6"] = _day_count(week.stats.online_seconds)
    ws["C6"] = week.hours_norm / 24
    ws["B6"].number_format = DURATION_FORMAT
    ws["C6"].number_format = DURATION_FORMAT

    ws["A7"] = "Обращения"
    ws["B7"] = week.stats.reports
    ws["C7"] = week.reports_norm
    ws["B7"].number_format = "#,##0"
    ws["C7"].number_format = "#,##0"

    _pct(ws["D6"], _percent(week.stats.online_hours, week.hours_norm))
    _pct(ws["D7"], _percent(week.stats.reports, week.reports_norm))
    _zebra(ws, range(6, 8), 4)
    for row in (6, 7):
        ws.cell(row=row, column=1).font = LABEL_FONT
        for col in (2, 3):
            ws.cell(row=row, column=col).font = VALUE_FONT
            ws.cell(row=row, column=col).alignment = Alignment(horizontal="right")
    ws.conditional_formatting.add(
        "D6:D7", DataBarRule(start_type="num", start_value=0, end_type="num",
                             end_value=1, color=BLUE, showValue=True),
    )

    # --- как читать таблицу ---
    ws["A4"] = ("Как читать: % выполнения — зелёный = норма выполнена, синий = 50–99%, "
                "оранжевый = меньше половины; полоса в «Выполнено» — прогресс к норме")
    ws["A4"].font = MUTED_FONT

    # --- сегодня: план на день против факта ---
    plan_hours = week.hours_norm / 7
    plan_reports = week.reports_norm / 7
    _section(ws, 9, "Сегодня: план на день и факт", 5)
    for col, title in enumerate(["Показатель", "План в день", "Факт сегодня", "Выполнено"],
                                start=1):
        ws.cell(row=10, column=col, value=title)
    _style_header(ws, 10, 4)

    today = snapshot.today
    ws["A11"] = "Онлайн (ч:мм)"
    ws["B11"] = plan_hours / 24
    ws["C11"] = _day_count(today.online_seconds)
    ws["B11"].number_format = DURATION_FORMAT
    ws["C11"].number_format = DURATION_FORMAT
    ws["A12"] = "Обращения"
    ws["B12"] = round(plan_reports)
    ws["C12"] = today.reports
    _pct(ws["D11"], _percent(today.online_hours, plan_hours))
    _pct(ws["D12"], _percent(today.reports, plan_reports))
    _zebra(ws, range(11, 13), 4)
    for row in (11, 12):
        ws.cell(row=row, column=1).font = LABEL_FONT
        for col in (2, 3):
            ws.cell(row=row, column=col).font = VALUE_FONT
            ws.cell(row=row, column=col).alignment = Alignment(horizontal="right")

    # --- сравнение с прошлой неделей ---
    _section(ws, 14, "Сравнение с прошлой неделей", 5)
    titles = ["Показатель", "Эта неделя", "Прошлая неделя", "Разница", "Изменение"]
    for col, title in enumerate(titles, start=1):
        ws.cell(row=15, column=col, value=title)
    _style_header(ws, 15, 5)

    cur, prev = week.stats, snapshot.prev_week
    ws["A16"] = "Онлайн (ч:мм)"
    ws["B16"] = _day_count(cur.online_seconds)
    ws["C16"] = _day_count(prev.online_seconds)
    ws["B16"].number_format = DURATION_FORMAT
    ws["C16"].number_format = DURATION_FORMAT
    ws["A17"] = "Обращения"
    ws["B17"] = cur.reports
    ws["C17"] = prev.reports
    ws["B17"].number_format = "#,##0"
    ws["C17"].number_format = "#,##0"
    ws["D17"] = cur.reports - prev.reports
    ws["D17"].number_format = "+#,##0;-#,##0;0"

    for row, (now_v, prev_v) in ((16, (cur.online_seconds, prev.online_seconds)),
                                 (17, (cur.reports, prev.reports))):
        delta = now_v - prev_v
        if row == 16:
            _signed(ws.cell(row=row, column=4), delta,
                    format_signed_duration(cur.online_seconds - prev.online_seconds))
        else:
            _signed(ws.cell(row=row, column=4), delta)

        change = percent_change(now_v, prev_v)
        cell = ws.cell(row=row, column=5)
        if change is None:
            cell.value = "—"
            cell.font = _font(color="6B7280")
        else:
            cell.value = change / 100
            cell.number_format = "+0%;-0%;0%"
            cell.font = _font(bold=True, color=GREEN if change > 0 else RED if change < 0 else "6B7280")
        cell.alignment = Alignment(horizontal="right")
        ws.cell(row=row, column=4).alignment = Alignment(horizontal="right")

    _zebra(ws, range(16, 18), 5)
    for row in (16, 17):
        ws.cell(row=row, column=1).font = LABEL_FONT
        for col in (2, 3):
            ws.cell(row=row, column=col).font = VALUE_FONT
            ws.cell(row=row, column=col).alignment = Alignment(horizontal="right")

    # --- прогноз к концу недели ---
    elapsed = max(1, snapshot.elapsed_days)
    forecast_hours = week.stats.online_hours / elapsed * 7
    forecast_reports = max(0.0, week.stats.reports / elapsed * 7)
    _section(ws, 19, "Прогноз к концу недели при текущем темпе", 5)
    for col, title in enumerate(["Показатель", "Прогноз", "Норма", "Выполнено"], start=1):
        ws.cell(row=20, column=col, value=title)
    _style_header(ws, 20, 4)

    ws["A21"] = "Онлайн (ч:мм)"
    ws["B21"] = forecast_hours / 24
    ws["C21"] = week.hours_norm / 24
    ws["B21"].number_format = DURATION_FORMAT
    ws["C21"].number_format = DURATION_FORMAT
    ws["A22"] = "Обращения"
    ws["B22"] = round(forecast_reports)
    ws["C22"] = week.reports_norm
    _pct(ws["D21"], _percent(forecast_hours, week.hours_norm))
    _pct(ws["D22"], _percent(forecast_reports, week.reports_norm))
    _zebra(ws, range(21, 23), 4)
    for row in (21, 22):
        ws.cell(row=row, column=1).font = LABEL_FONT
        for col in (2, 3):
            ws.cell(row=row, column=col).font = VALUE_FONT
            ws.cell(row=row, column=col).alignment = Alignment(horizontal="right")

    # --- итог за месяц ---
    month_title = MONTHS_RU[snapshot.month_start.month - 1]
    month = snapshot.month
    _section(ws, 24, f"Итог за месяц: {month_title} {snapshot.month_start.year}", 5)
    for col, title in enumerate(["Показатель", "Факт", "Норма (≈)", "Выполнено"], start=1):
        ws.cell(row=25, column=col, value=title)
    _style_header(ws, 25, 4)

    ws["A26"] = "Онлайн (ч:мм)"
    ws["B26"] = _day_count(month.online_seconds)
    ws["C26"] = snapshot.month_hours_norm / 24
    ws["B26"].number_format = DURATION_FORMAT
    ws["C26"].number_format = DURATION_FORMAT
    ws["A27"] = "Обращения"
    ws["B27"] = month.reports
    ws["C27"] = round(snapshot.month_reports_norm)
    ws["B27"].number_format = "#,##0"
    ws["C27"].number_format = "#,##0"
    _pct(ws["D26"], _percent(month.online_hours, snapshot.month_hours_norm))
    _pct(ws["D27"], _percent(month.reports, snapshot.month_reports_norm))
    _zebra(ws, range(26, 28), 4)
    for row in (26, 27):
        ws.cell(row=row, column=1).font = LABEL_FONT
        for col in (2, 3):
            ws.cell(row=row, column=col).font = VALUE_FONT
            ws.cell(row=row, column=col).alignment = Alignment(horizontal="right")

    ws["A29"] = (f"Учтено дней недели: {snapshot.elapsed_days} из 7  •  "
                  f"Дежурство F10, обращения F9 / Ctrl+F9")
    ws["A29"].font = MUTED_FONT

    _set_widths(ws, [30, 20, 20, 18, 16])
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A5"


# --- лист «По дням» ------------------------------------------------------

def _fill_days_sheet(ws, snapshot: Snapshot) -> None:
    titles = ["Дата", "День", "Онлайн (ч:мм)", "Часы", "Обращения", "План (ч)",
              "Онлайн к плану", "Обращения к плану"]
    for col, title in enumerate(titles, start=1):
        ws.cell(row=1, column=col, value=title)
    _style_header(ws, 1, len(titles))

    plan_hours = snapshot.week.hours_norm / 7
    plan_reports = snapshot.week.reports_norm / 7

    # дни по порядку: от раннего к позднему, как читают слева направо
    for row, item in enumerate(reversed(snapshot.days), start=2):
        ws.cell(row=row, column=1, value=item.day).number_format = "DD.MM.YYYY"
        ws.cell(row=row, column=2, value=WEEKDAYS[item.day.weekday()])
        online = ws.cell(row=row, column=3, value=_day_count(item.online_seconds))
        online.number_format = DURATION_FORMAT
        hours = ws.cell(row=row, column=4, value=round(item.online_seconds / 3600, 2))
        hours.number_format = "0.00"
        reports = ws.cell(row=row, column=5, value=item.reports)
        reports.number_format = "#,##0"
        plan = ws.cell(row=row, column=6, value=round(plan_hours, 2))
        plan.number_format = "0.00"
        _pct(ws.cell(row=row, column=7),
             _percent(item.online_seconds / 3600, plan_hours))
        _pct(ws.cell(row=row, column=8), _percent(item.reports, plan_reports))

    last_data_row = 1 + len(snapshot.days)
    _zebra(ws, range(2, last_data_row + 1), len(titles))
    for row in range(2, last_data_row + 1):
        for col in (3, 4, 5, 6):
            cell = ws.cell(row=row, column=col)
            cell.font = VALUE_FONT
            cell.alignment = Alignment(horizontal="right")
        ws.cell(row=row, column=2).alignment = Alignment(horizontal="center")

    ws.conditional_formatting.add(
        f"G2:G{last_data_row}",
        DataBarRule(start_type="num", start_value=0, end_type="num", end_value=1,
                    color=BLUE, showValue=True),
    )

    # --- итог ---
    total_row = last_data_row + 1
    ws.cell(row=total_row, column=1, value="ИТОГО")
    ws.cell(row=total_row, column=2, value=f"{len(snapshot.days)} дн.")
    total_seconds = sum(item.online_seconds for item in snapshot.days)
    total = ws.cell(row=total_row, column=3, value=_day_count(total_seconds))
    total.number_format = DURATION_FORMAT
    ws.cell(row=total_row, column=4,
            value=round(total_seconds / 3600, 2)).number_format = "0.00"
    reports_total = ws.cell(row=total_row, column=5,
                            value=sum(item.reports for item in snapshot.days))
    reports_total.number_format = "#,##0"
    ws.cell(row=total_row, column=6,
            value=round(plan_hours * len(snapshot.days), 2)).number_format = "0.00"
    _pct(ws.cell(row=total_row, column=7),
         _percent(total_seconds / 3600, plan_hours * len(snapshot.days)))
    _pct(ws.cell(row=total_row, column=8),
         _percent(sum(item.reports for item in snapshot.days),
                  plan_reports * len(snapshot.days)))
    for col in range(1, len(titles) + 1):
        cell = ws.cell(row=total_row, column=col)
        cell.fill = TOTAL_FILL
        cell.border = TOTAL_BORDER
        if col == 1:
            cell.font = _font(bold=True, color="1F2937")

    # --- диаграмма по дням ---
    chart = BarChart()
    chart.type = "col"
    chart.style = 10
    chart.title = "Часы и обращения по дням"
    chart.y_axis.title = "часы"
    chart.height = 8.5
    chart.width = 17
    data = Reference(ws, min_col=4, min_row=1, max_row=last_data_row)
    categories = Reference(ws, min_col=2, min_row=2, max_row=last_data_row)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(categories)

    line = LineChart()
    line.add_data(Reference(ws, min_col=5, min_row=1, max_row=last_data_row),
                  titles_from_data=True)
    line.y_axis.axId = 200
    line.y_axis.title = "обращения"
    chart.y_axis.crosses = "autoZero"
    line.y_axis.crosses = "max"
    chart += line
    ws.add_chart(chart, "J2")

    ws.auto_filter.ref = f"A1:H{last_data_row}"
    _set_widths(ws, [13, 8, 17, 10, 13, 11, 21, 24])
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A2"


# --- лист «Динамика» -----------------------------------------------------

def _fill_history_sheet(ws, snapshot: Snapshot) -> None:
    titles = ["Неделя", "Онлайн (ч:мм)", "Часы", "Обращения",
              "Выполнение часов", "Выполнение обращений"]
    for col, title in enumerate(titles, start=1):
        ws.cell(row=1, column=col, value=title)
    _style_header(ws, 1, len(titles))

    history = snapshot.history or []
    for row, item in enumerate(history, start=2):
        week_end = item.week_start + timedelta(days=6)
        ws.cell(row=row, column=1, value=f"{item.week_start:%d.%m} — {week_end:%d.%m}")
        duration = ws.cell(row=row, column=2, value=_day_count(item.online_seconds))
        duration.number_format = DURATION_FORMAT
        hours = ws.cell(row=row, column=3, value=round(item.online_seconds / 3600, 2))
        hours.number_format = "0.00"
        reports = ws.cell(row=row, column=4, value=item.reports)
        reports.number_format = "#,##0"
        _pct(ws.cell(row=row, column=5),
             _percent(item.online_seconds / 3600, snapshot.week.hours_norm))
        _pct(ws.cell(row=row, column=6),
             _percent(item.reports, snapshot.week.reports_norm))

    last_row = 1 + len(history)
    _zebra(ws, range(2, last_row + 1), len(titles))
    for row in range(2, last_row + 1):
        for col in (2, 3, 4):
            cell = ws.cell(row=row, column=col)
            cell.font = VALUE_FONT
            cell.alignment = Alignment(horizontal="right")
    if history:  # текущая неделя сверху — подсветим
        for col in range(1, len(titles) + 1):
            ws.cell(row=2, column=col).fill = PatternFill("solid", fgColor="E8F0FE")

    ws.conditional_formatting.add(
        f"E2:E{last_row}",
        DataBarRule(start_type="num", start_value=0, end_type="num", end_value=1,
                    color=BLUE, showValue=True),
    )

    # --- комбинированная диаграмма: столбцы часов + линия обращений ---
    if history:
        bar = BarChart()
        bar.type = "col"
        bar.style = 10
        bar.title = "Часы и обращения по неделям"
        bar.y_axis.title = "часы"
        bar.height = 9
        bar.width = 18
        bar.add_data(Reference(ws, min_col=3, min_row=1, max_row=last_row),
                     titles_from_data=True)
        bar.set_categories(Reference(ws, min_col=1, min_row=2, max_row=last_row))

        line = LineChart()
        line.add_data(Reference(ws, min_col=4, min_row=1, max_row=last_row),
                      titles_from_data=True)
        line.y_axis.axId = 200
        line.y_axis.title = "обращения"
        bar.y_axis.crosses = "autoZero"
        line.y_axis.crosses = "max"
        bar += line
        ws.add_chart(bar, "H2")

    ws["A" + str(last_row + 2)] = (
        f"Норма: {snapshot.week.hours_norm:g} ч и {snapshot.week.reports_norm} "
        f"обращений в неделю"
    )
    ws["A" + str(last_row + 2)].font = MUTED_FONT
    _set_widths(ws, [16, 17, 10, 13, 21, 26])
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A2"


def build_workbook(snapshot: Snapshot) -> Workbook:
    wb = Workbook()
    _fill_week_sheet(wb.active, snapshot)
    week_ws = wb.active
    week_ws.title = "Неделя"
    days_ws = wb.create_sheet("По дням")
    _fill_days_sheet(days_ws, snapshot)
    history_ws = wb.create_sheet("Динамика")
    _fill_history_sheet(history_ws, snapshot)

    # цвета вкладок: сразу видно, где что
    week_ws.sheet_properties.tabColor = "151B26"
    days_ws.sheet_properties.tabColor = "1F6FEB"
    history_ws.sheet_properties.tabColor = "00A8CC"
    return wb


def write_excel(snapshot: Snapshot, path: Path) -> None:
    """Пишет файл во временный, затем подменяет основной: недописанный файл не появится."""
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        build_workbook(snapshot).save(tmp)
        os.replace(tmp, path)
    except PermissionError as exc:
        _remove_quietly(tmp)
        raise ExportError("Файл Excel открыт в другой программе, закрой его") from exc
    except OSError as exc:
        _remove_quietly(tmp)
        raise ExportError(f"Не удалось записать Excel: {exc.strerror or exc}") from exc


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass
