"""Генерация недельного PNG-отчёта в стиле Grafana-дашборда.

Сетка 1400x1080: шапка, пять карточек KPI (включая дневной результат «Сегодня»),
панель «по дням» с двумя шкалами, пунктирной линией среднего и подсветкой
сегодняшнего дня, сравнение с прошлой неделей, итог за месяц, подвал.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.export.snapshot import Snapshot
from app.util import (
    MONTHS_RU,
    format_duration,
    format_hm,
    format_percent_change,
    format_signed_duration,
    format_signed_int,
)

BG = "#0b0c0e"
HEADER_BG = "#0f1013"
CARD = "#141519"
BORDER = "#24262b"
GRID = "#1e2025"
TEXT = "#edeef1"
MUTED = "#8a8c94"
ACCENT = "#4ec3f0"
ACCENT_2 = "#2fa6d8"
OK = "#3ddc97"
WARN = "#ffb547"
DANGER = "#ff6b81"
BAR_BG = "#1e2025"
BAR_PREV = "#5b6b84"
ZERO_BAR = "#24262b"
CHIP_OK_BG = "#11332a"
CHIP_BAD_BG = "#3a1f26"
CHIP_NEUTRAL_BG = "#232b38"
TODAY_BG = "#17202e"      # подсветка сегодняшнего дня на графике
TODAY_BORDER = "#2f415c"

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# --- сетка ---
MARGIN = 45
CARD_W = 250          # 5 карточек: 5 * 250 + 4 * 15 = 1310
CARD_H = 196
CARD_Y = 126
CARD_GAP = 15
KPI_COUNT = 5

CHART_TOP = 340
CHART_BOTTOM = 706
BOTTOM_TOP = 724
BOTTOM_BOTTOM = 1006


@lru_cache(maxsize=None)
def _font(size: int, bold: bool = False):
    candidates = (
        ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold else
        ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for name in candidates:
        if os.path.exists(name):
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def _panel(draw, box, radius: int = 16) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=CARD, outline=BORDER, width=1)


def _percent(value: float, norm: float) -> float:
    return value / norm if norm > 0 else 0.0


def _progress(draw, x: int, y: int, width: int, height: int, pct: float, color: str,
              radius: int = 5) -> None:
    draw.rounded_rectangle((x, y, x + width, y + height), radius=radius, fill=BAR_BG)
    if pct <= 0:
        return
    fill = max(height, int(width * min(pct, 1.0)))
    draw.rounded_rectangle((x, y, x + fill, y + height), radius=radius, fill=color)


def _chip(draw, right: int, cy: int, text: str, font, fg: str, bg: str,
          pad_x: int = 9, pad_y: int = 4, radius: int = 7) -> int:
    """Плашка с правым краем в right и вертикальным центром cy. Возвращает ширину."""
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0] + pad_x * 2
    height = bbox[3] - bbox[1] + pad_y * 2
    left = right - width
    draw.rounded_rectangle((left, cy - height // 2, right, cy + height // 2),
                           radius=radius, fill=bg)
    draw.text(((left + right) // 2, cy), text, font=font, fill=fg, anchor="mm")
    return width


def _gauge(draw, cx: int, cy: int, radius: int, pct: float, color: str,
           thickness: int = 12) -> None:
    bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
    draw.arc(bbox, start=135, end=405, fill=BAR_BG, width=thickness)
    clamped = min(1.0, max(0.0, pct))
    if clamped > 0:
        draw.arc(bbox, start=135, end=135 + 270 * clamped, fill=color, width=thickness)


def _nice_step(value: float) -> float:
    """Круглый шаг шкалы не меньше value (для делений 0..4)."""
    if value <= 0:
        return 1.0
    exp = math.floor(math.log10(value))
    for mult in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        candidate = mult * 10 ** exp
        if candidate >= value:
            return float(candidate)
    return float(10 ** (exp + 1))


def _legend_item(draw, right: int, cy: int, text: str, color, font) -> int:
    """Квадратик + подпись, правый край в right. Возвращает ширину."""
    bbox = draw.textbbox((0, 0), text, font=font)
    total = 14 + 8 + (bbox[2] - bbox[0])
    x = right - total
    draw.rounded_rectangle((x, cy - 7, x + 14, cy + 7), radius=4, fill=color)
    draw.text((x + 22, cy), text, font=font, fill=MUTED, anchor="lm")
    return total


def _delta_colors(delta: float) -> tuple[str, str]:
    if delta > 0:
        return OK, CHIP_OK_BG
    if delta < 0:
        return DANGER, CHIP_BAD_BG
    return MUTED, CHIP_NEUTRAL_BG


def _days_left_text(days: int) -> str:
    """«осталось 1 день / 2 дня / 5 дней»."""
    if days % 10 == 1 and days % 100 != 11:
        word = "день"
    elif days % 10 in (2, 3, 4) and days % 100 not in (12, 13, 14):
        word = "дня"
    else:
        word = "дней"
    return f"осталось {days} {word}"


def _elapsed_days(snapshot: Snapshot) -> int:
    today = datetime.fromtimestamp(snapshot.generated_at).date()
    last = min(today, snapshot.week_end)
    return max(1, (last - snapshot.week_start).days + 1)


# --- шапка ---------------------------------------------------------------

def _header(draw, snapshot: Snapshot, width: int) -> None:
    draw.rectangle((0, 0, width, 104), fill=HEADER_BG)
    draw.rectangle((0, 0, 6, 104), fill=ACCENT)
    draw.line((0, 104, width, 104), fill=BORDER, width=1)

    draw.text((MARGIN, 30), "SKY HELPER", font=_font(28, True), fill=TEXT)
    draw.text(
        (MARGIN, 70),
        f"Недельный отчёт  •  {snapshot.week_start:%d.%m.%Y} — {snapshot.week_end:%d.%m.%Y}",
        font=_font(15), fill=MUTED,
    )

    updated = datetime.fromtimestamp(snapshot.generated_at)
    draw.text((width - MARGIN, 34), f"Обновлено {updated:%d.%m.%Y %H:%M}",
              font=_font(13), fill=MUTED, anchor="ra")
    week = snapshot.week
    _chip(
        draw, width - MARGIN, 74,
        f"НОРМА {week.hours_norm:g} Ч • {week.reports_norm} ОБРАЩЕНИЙ",
        _font(12, True), ACCENT, "#0e2b38",
    )


# --- карточки KPI --------------------------------------------------------

def _kpi_card(draw, x: int) -> int:
    box = (x, CARD_Y, x + CARD_W, CARD_Y + CARD_H)
    _panel(draw, box)
    return x + CARD_W


def _kpi_row(draw, snapshot: Snapshot) -> None:
    week = snapshot.week
    elapsed = _elapsed_days(snapshot)
    plan_hours = week.hours_norm / 7
    xs = [MARGIN + i * (CARD_W + CARD_GAP) for i in range(KPI_COUNT)]

    # 1. Сегодня: дневной результат против плана на день.
    today = snapshot.today
    today_pct = _percent(today.online_hours, plan_hours)
    today_color = OK if today_pct >= 1 else ACCENT
    _kpi_card(draw, xs[0])
    draw.text((xs[0] + 18, CARD_Y + 16), "СЕГОДНЯ", font=_font(12, True), fill=ACCENT)
    draw.text((xs[0] + 18, CARD_Y + 52), format_duration(today.online_seconds),
              font=_font(30, True), fill=TEXT)
    draw.text((xs[0] + 18, CARD_Y + 104),
              f"обращения {today.reports}  •  план {plan_hours:g} ч",
              font=_font(12), fill=MUTED)
    _progress(draw, xs[0] + 18, CARD_Y + 138, CARD_W - 36, 10, today_pct, today_color)
    _chip(draw, xs[0] + CARD_W - 18, CARD_Y + 174, f"{today_pct * 100:.0f}% плана",
          _font(12, True), today_color,
          CHIP_OK_BG if today_pct >= 1 else "#0e2b38")

    # 2. Онлайн за неделю: кольцо.
    _kpi_card(draw, xs[1])
    draw.text((xs[1] + 18, CARD_Y + 16), "ОНЛАЙН ЗА НЕДЕЛЮ",
              font=_font(12, True), fill=MUTED)
    hours_pct = _percent(week.stats.online_hours, week.hours_norm)
    color = OK if hours_pct >= 1 else ACCENT
    cx, cy = xs[1] + CARD_W // 2, CARD_Y + 100
    _gauge(draw, cx, cy, 48, hours_pct, color, thickness=11)
    draw.text((cx, cy - 7), format_hm(week.stats.online_seconds),
              font=_font(24, True), fill=TEXT, anchor="mm")
    draw.text((cx, cy + 18), "чч:мм", font=_font(11), fill=MUTED, anchor="mm")
    draw.text((cx, CARD_Y + 172),
              f"{hours_pct * 100:.0f}% нормы  •  {week.hours_norm:g} ч",
              font=_font(12), fill=color, anchor="mm")

    # 3. Обращения: кольцо.
    _kpi_card(draw, xs[2])
    draw.text((xs[2] + 18, CARD_Y + 16), "ОБРАЩЕНИЯ ЗА НЕДЕЛЮ",
              font=_font(12, True), fill=MUTED)
    reports_pct = _percent(week.stats.reports, week.reports_norm)
    color = OK if reports_pct >= 1 else ACCENT_2
    cx = xs[2] + CARD_W // 2
    _gauge(draw, cx, cy, 48, reports_pct, color, thickness=11)
    draw.text((cx, cy - 5), str(week.stats.reports),
              font=_font(30, True), fill=TEXT, anchor="mm")
    draw.text((cx, CARD_Y + 172),
              f"{reports_pct * 100:.0f}% нормы  •  {week.reports_norm}",
              font=_font(12), fill=color, anchor="mm")

    # 4. Среднее в день: обычный stat.
    _kpi_card(draw, xs[3])
    draw.text((xs[3] + 18, CARD_Y + 16), "СРЕДНЕЕ В ДЕНЬ",
              font=_font(12, True), fill=MUTED)
    avg_hours = week.stats.online_hours / elapsed
    draw.text((xs[3] + 18, CARD_Y + 52), format_duration(int(avg_hours * 3600)),
              font=_font(30, True), fill=TEXT)
    draw.text((xs[3] + 18, CARD_Y + 104),
              f"план {plan_hours:g} ч в день  •  {elapsed} дн. учтено",
              font=_font(12), fill=MUTED)
    plan_pct = _percent(avg_hours, plan_hours)
    _progress(draw, xs[3] + 18, CARD_Y + 138, CARD_W - 36, 10, plan_pct,
              OK if plan_pct >= 1 else ACCENT)
    _chip(draw, xs[3] + CARD_W - 18, CARD_Y + 174, f"{plan_pct * 100:.0f}% плана",
          _font(12, True), OK if plan_pct >= 1 else ACCENT,
          CHIP_OK_BG if plan_pct >= 1 else "#0e2b38")

    # 5. Прогноз к концу недели.
    _kpi_card(draw, xs[4])
    draw.text((xs[4] + 18, CARD_Y + 16), "ПРОГНОЗ НА КОНЕЦ НЕДЕЛИ",
              font=_font(12, True), fill=MUTED)
    forecast_hours = week.stats.online_hours / elapsed * 7
    forecast_reports = max(0.0, week.stats.reports / elapsed * 7)
    forecast_pct = _percent(forecast_hours, week.hours_norm)
    color = OK if forecast_pct >= 1 else WARN
    draw.text((xs[4] + 18, CARD_Y + 52), format_duration(int(forecast_hours * 3600)),
              font=_font(30, True), fill=color)
    draw.text((xs[4] + 18, CARD_Y + 104),
              f"норма {week.hours_norm:g} ч  •  обращения ≈ {forecast_reports:.0f}",
              font=_font(12), fill=MUTED)
    _progress(draw, xs[4] + 18, CARD_Y + 138, CARD_W - 36, 10, forecast_pct, color)
    _chip(draw, xs[4] + CARD_W - 18, CARD_Y + 174, f"{forecast_pct * 100:.0f}% нормы",
          _font(12, True), color, CHIP_OK_BG if forecast_pct >= 1 else "#3a2f14")


# --- панель «по дням» ----------------------------------------------------

def _daily_chart(draw, snapshot: Snapshot, days) -> None:
    _panel(draw, (MARGIN, CHART_TOP, 1355, CHART_BOTTOM))
    draw.text((MARGIN + 30, CHART_TOP + 24), "ПО ДНЯМ НЕДЕЛИ",
              font=_font(18, True), fill=TEXT)
    draw.text((MARGIN + 30, CHART_TOP + 52),
              "левая шкала — часы, правая — обращения",
              font=_font(11), fill=MUTED)

    # легенда
    legend_font = _font(12)
    group_w = _legend_item(draw, 1325, CHART_TOP + 34, "Обращения", ACCENT_2, legend_font)
    _legend_item(draw, 1325 - group_w - 20, CHART_TOP + 34, "Онлайн", ACCENT, legend_font)

    x0, x1 = 110, 1298
    top, bottom = CHART_TOP + 110, CHART_TOP + 310
    slot = (x1 - x0) / 7

    # подсветка сегодняшнего дня (под сеткой, чтобы линии остались сверху)
    today = datetime.fromtimestamp(snapshot.generated_at).date()
    today_index = next((i for i, (day, _, _) in enumerate(days) if day == today), None)
    if today_index is not None:
        draw.rounded_rectangle(
            (x0 + slot * today_index + 3, top - 10,
             x0 + slot * (today_index + 1) - 3, bottom + 56),
            radius=10, fill=TODAY_BG, outline=TODAY_BORDER, width=1,
        )

    hours = [sec / 3600 for _, sec, _ in days]
    reports = [r for _, _, r in days]
    # 4 деления шкалы, чтобы подписи были круглыми
    hours_step = max(1.0, _nice_step(max(hours + [1.0]) / 4))
    reports_step = max(1.0, _nice_step(max(reports + [1]) / 4))
    max_hours, max_reports = hours_step * 4, reports_step * 4

    # сетка и подписи осей
    axis_font = _font(11)
    for i in range(5):
        y = bottom - (bottom - top) * i / 4
        draw.line((x0, y, x1, y), fill=GRID, width=1)
        draw.text((x0 - 12, y), f"{max_hours * i / 4:g} ч", font=axis_font,
                  fill=MUTED, anchor="rm")
        draw.text((x1 + 12, y), f"{max_reports * i / 4:.0f}", font=axis_font,
                  fill="#5f7fb0", anchor="lm")

    # линия среднего по часам
    avg_hours = sum(hours) / max(1, _elapsed_days(snapshot))
    if avg_hours > 0:
        avg_y = bottom - (bottom - top) * (avg_hours / max_hours)
        x = x0
        while x < x1:
            draw.line((x, avg_y, min(x + 8, x1), avg_y), fill=WARN, width=1)
            x += 16
        _chip(draw, x1 - 4, int(avg_y) - 18, f"среднее {avg_hours:.1f} ч/день",
              _font(11, True), WARN, "#3a2f14", pad_x=8, pad_y=3, radius=6)

    # отметка «СЕГОДНЯ» над подсвеченным столбцом
    if today_index is not None:
        center = x0 + slot * today_index + slot / 2
        text = "СЕГОДНЯ"
        font_today = _font(11, True)
        bbox = draw.textbbox((0, 0), text, font=font_today)
        half = (bbox[2] - bbox[0]) // 2 + 8
        _chip(draw, int(center + half), top - 6, text, font_today, ACCENT, "#0e2b38",
              pad_x=8, pad_y=3, radius=6)

    # столбцы
    plan_hours = snapshot.week.hours_norm / 7
    bar_w = 40
    label_font = _font(13, True)
    value_font = _font(11, True)
    small_font = _font(11)

    for i, (day, sec, report_count) in enumerate(days):
        center = x0 + slot * i + slot / 2
        day_hours = sec / 3600

        h_px = max(0, int((bottom - top) * (day_hours / max_hours))) if max_hours else 0
        r_px = max(0, int((bottom - top) * (report_count / max_reports))) if max_reports else 0

        left = int(center - bar_w - 4)
        draw.rounded_rectangle(
            (left, bottom - max(h_px, 2), left + bar_w, bottom),
            radius=7, fill=ACCENT if h_px else ZERO_BAR,
        )
        draw.rounded_rectangle(
            (int(center + 4), bottom - max(r_px, 2), int(center + 4 + bar_w), bottom),
            radius=7, fill=ACCENT_2 if r_px else ZERO_BAR,
        )

        if day_hours > 0:
            label_y = bottom - h_px - 8
            if label_y < top + 24:
                # столбец почти во всю высоту: подпись внутри, чтобы не лезла
                # на плашку «СЕГОДНЯ» и линию среднего
                draw.text((left + bar_w // 2, bottom - h_px + 6), f"{day_hours:.1f}",
                          font=value_font, fill=BG, anchor="ma")
            else:
                draw.text((left + bar_w // 2, label_y), f"{day_hours:.1f}",
                          font=value_font, fill=TEXT, anchor="md")
        if report_count > 0:
            label_y = bottom - r_px - 8
            bar_left = int(center + 4)
            if label_y < top + 24:
                draw.text((bar_left + bar_w // 2, bottom - r_px + 6),
                          str(report_count), font=value_font, fill=BG, anchor="ma")
            else:
                draw.text((bar_left + bar_w // 2, label_y),
                          str(report_count), font=value_font, fill=TEXT, anchor="md")

        meets_plan = day_hours >= plan_hours
        label_fill = ACCENT if day == today else (OK if meets_plan else TEXT)
        draw.text((center, bottom + 22), WEEKDAYS[day.weekday()], font=label_font,
                  fill=label_fill, anchor="mm")
        draw.text((center, bottom + 44), f"{format_hm(sec)}  •  {report_count}",
                  font=small_font, fill=MUTED, anchor="mm")


# --- сравнение с прошлой неделей ----------------------------------------

def _compare_panel(draw, snapshot: Snapshot) -> None:
    _panel(draw, (MARGIN, BOTTOM_TOP, 685, BOTTOM_BOTTOM))
    draw.text((MARGIN + 30, BOTTOM_TOP + 26), "СРАВНЕНИЕ С ПРОШЛОЙ НЕДЕЛЕЙ",
              font=_font(17, True), fill=TEXT)

    legend_font = _font(11)
    w = _chip(draw, 655, BOTTOM_TOP + 34, "Прошлая", legend_font, MUTED, "#1b2534")
    _chip(draw, 655 - w - 8, BOTTOM_TOP + 34, "Эта неделя", legend_font, MUTED, "#1b2534")

    cur, prev = snapshot.week.stats, snapshot.prev_week
    rows = [
        ("ОНЛАЙН", cur.online_seconds, prev.online_seconds,
         format_duration, format_signed_duration),
        ("ОБРАЩЕНИЯ", cur.reports, prev.reports, str, format_signed_int),
    ]
    max_w = 330
    for index, (label, now_v, prev_v, fmt, fmt_delta) in enumerate(rows):
        y = BOTTOM_TOP + 92 + index * 96
        top_v = max(now_v, prev_v, 1)
        delta = now_v - prev_v
        draw.text((MARGIN + 30, y), label, font=_font(12, True), fill=MUTED)

        fg, bg = _delta_colors(delta)
        change = format_percent_change(now_v, prev_v)
        chip_text = fmt_delta(delta) if change == "\u2014" else f"{fmt_delta(delta)}  {change}"
        _chip(draw, 655, y + 8, chip_text, _font(13, True), fg, bg)

        for offset, value, color in ((24, now_v, ACCENT), (54, prev_v, BAR_PREV)):
            width = int(value / top_v * max_w) if value > 0 else 0
            if width:
                draw.rounded_rectangle(
                    (MARGIN + 30, y + offset, MARGIN + 30 + width, y + offset + 14),
                    radius=5, fill=color,
                )
            draw.text((MARGIN + 40 + width, y + offset + 7), fmt(value),
                      font=_font(12), fill=TEXT, anchor="lm")


# --- итог за месяц -------------------------------------------------------

def _month_panel(draw, snapshot: Snapshot) -> None:
    _panel(draw, (715, BOTTOM_TOP, 1355, BOTTOM_BOTTOM))
    title = (f"ИТОГ ЗА МЕСЯЦ  •  "
             f"{MONTHS_RU[snapshot.month_start.month - 1].upper()} {snapshot.month_start.year}")
    draw.text((745, BOTTOM_TOP + 26), title, font=_font(17, True), fill=TEXT)

    next_month = (snapshot.month_start.replace(day=1) + timedelta(days=32)).replace(day=1)
    days_in_month = (next_month - snapshot.month_start).days
    today = datetime.fromtimestamp(snapshot.generated_at).date()
    days_left = max(0, (next_month - today).days)

    month = snapshot.month
    rows = [
        ("ОНЛАЙН", format_duration(month.online_seconds), month.online_hours,
         snapshot.month_hours_norm, f"норма ≈ {snapshot.month_hours_norm:.0f} ч"),
        ("ОБРАЩЕНИЯ", str(month.reports), month.reports,
         snapshot.month_reports_norm, f"норма ≈ {snapshot.month_reports_norm:.0f}"),
    ]
    for index, (label, text, value, norm, norm_text) in enumerate(rows):
        y = BOTTOM_TOP + 84 + index * 96
        pct = _percent(value, norm)
        color = OK if pct >= 1 else ACCENT
        draw.text((745, y), label, font=_font(12, True), fill=MUTED)
        draw.text((745, y + 18), text, font=_font(26, True), fill=TEXT)
        draw.text((1325, y + 30), f"{norm_text}  •  {pct * 100:.0f}%",
                  font=_font(13, True), fill=color, anchor="ra")
        _progress(draw, 745, y + 62, 580, 10, pct, color)
        draw.text((745, y + 80),
                  f"{days_in_month - days_left} из {days_in_month} дн.  •  "
                  f"{_days_left_text(days_left)}",
                  font=_font(11), fill=MUTED)


# --- подвал --------------------------------------------------------------

def _footer(draw, snapshot: Snapshot) -> None:
    week = snapshot.week
    draw.line((MARGIN, 1030, 1355, 1030), fill=BORDER, width=1)
    draw.text(
        (MARGIN, 1054),
        f"План в день: {week.hours_norm / 7:g} ч • "
        f"{round(week.reports_norm / 7)} обращений  •  "
        f"Дежурство F10, обращения F9 / Ctrl+F9",
        font=_font(12), fill=MUTED, anchor="lm",
    )
    draw.text((1355, 1054), "SKY HELPER • данные из локальной базы",
              font=_font(12), fill=MUTED, anchor="rm")


def build_report_image(snapshot: Snapshot, path: Path) -> None:
    """Сохраняет готовый PNG; сначала пишет временный файл, затем заменяет основной."""
    width, height = 1400, 1080
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)

    by_day = {item.day: item for item in snapshot.days}
    days = []
    for i in range(7):
        day = snapshot.week_start + timedelta(days=i)
        item = by_day.get(day)
        days.append((day, item.online_seconds if item else 0, item.reports if item else 0))

    _header(draw, snapshot, width)
    _kpi_row(draw, snapshot)
    _daily_chart(draw, snapshot, days)
    _compare_panel(draw, snapshot)
    _month_panel(draw, snapshot)
    _footer(draw, snapshot)

    path = Path(path)
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(tmp, "PNG")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
