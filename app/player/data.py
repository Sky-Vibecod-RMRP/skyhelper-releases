# -*- coding: utf-8 -*-
"""Свои данные персонажа из логов RAGE:MP (``cef_game_logs.txt``).

Лог пишет сам клиент игры, поэтому здесь видны только данные своего
персонажа: статик, имя, ранг, фракция, семья, SocialClub, телефон,
уровень, плейтайм и координаты. Никаких инъекций в процесс игры и
чтения памяти других игроков нет — только чтение текстового файла.

Источники полей:
  * строка ``Phone start with: {...}`` — карточка персонажа;
  * строка ``Start opening chat: {...}`` — телефон и название фракции.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

#: Лог клиентской части RAGE:MP.
LOG_PATH = Path(r"C:\RAGEMP\clientdata\cef_game_logs.txt")

#: Если последняя запись в логе свежее этого количества секунд — «в игре».
ONLINE_WINDOW_SEC = 900

#: Названия админ-рангов: идентификатор из лога → как пишется в игре.
#: Источник — значения поля ``staff`` в логе RAGE:MP (баг №2).
STAFF_NAMES = {
    "admin": "Админ",
    "admin_plus": "Админ+",
    "admin_pro": "Админ PRO",
    "admin_ultra": "Админ ULTRA",
    "admin_max": "Админ MAX",
    "admin_god": "Админ GOD",
    "admin_legend": "Админ LEGEND",
}


def staff_name(value: object) -> str:
    """Название админ-ранга (``admin_plus`` → «Админ+»); неизвестный — как есть."""
    text = str(value or "")
    return STAFF_NAMES.get(text, text)


def family_rank_name(chat: dict, rank: int) -> str:
    """Название ранга в семье по ``familyProfessions`` из лога.

    В карточке телефона лежит только номер (``familyRank: 1``), а рядом, в
    записи открытия чата, — весь список рангов семьи с названиями
    («Администратор», «ГА», «ГК НР»…). Поэтому цифру превращаем в слово
    (баг-репорт №5); если такого ранга в списке нет — пустая строка.
    """
    if not rank:
        return ""
    for entry in chat.get("familyProfessions") or ():
        if not isinstance(entry, dict):
            continue
        try:
            number = int(entry.get("rank") or 0)
        except (TypeError, ValueError):
            continue
        if number == rank:
            return str(entry.get("name") or "").strip()
    return ""

#: Время в строке лога: ``[0930/213544.123:INFO:...]`` → месяц, день, часы.
#: Года в логе нет — его подставляет :func:`_last_stamp`.
_TIME_RE = re.compile(r"\[(\d{2})(\d{2})/(\d{2})(\d{2})(\d{2})\.")


def _balanced(line: str) -> str:
    """Первый сбалансированный блок ``{...}`` в строке лога."""
    start = line.find("{")
    if start < 0:
        return ""
    depth = 0
    in_str = False
    esc = False
    for index in range(start, len(line)):
        char = line[index]
        if in_str:
            if esc:
                esc = False
            elif char == "\\":
                esc = True
            elif char == '"':
                in_str = False
            continue
        if char == '"':
            in_str = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return line[start:index + 1]
    return ""


def _last_json(lines: list[str], marker: str) -> dict | None:
    """Последний JSON в строках с нужной подписью (данные свежей сессии)."""
    for line in reversed(lines):
        if marker in line:
            raw = _balanced(line)
            if raw:
                try:
                    return json.loads(raw)
                except ValueError:
                    continue
    return None


def _last_stamp(lines: list[str], year: int | None = None) -> str | None:
    """Метка времени последней записи вида ``[0930/213544.123:...]``.

    В логе RAGE:MP года нет — только месяц, день и время, поэтому год
    берётся параметром (обычно из года последней записи самого файла).
    Раньше здесь стоял формат ``[ГГГГ/ММ/ДД/…`` с лишним слэшем: он не
    совпадал ни с одной строкой настоящего лога, и метка всегда подменялась
    временем файла.
    """
    if year is None:
        year = _dt.datetime.now().year
    for line in reversed(lines):
        match = _TIME_RE.search(line)
        if match:
            month, day, hour, minute, second = (int(g) for g in match.groups())
            try:
                moment = _dt.datetime(year, month, day, hour, minute, second)
            except ValueError:
                continue
            return moment.strftime("%d.%m.%Y %H:%M:%S")
    return None


def _playtime_text(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return "%d ч %d мин" % (hours, minutes)


def _date_text(value: str | None) -> str:
    if not value:
        return ""
    return str(value)[:10]


def parse(path: Path | str | None = None) -> dict:
    """Прочитать лог и вернуть карточку своего персонажа.

    Пустой ``{...}`` с ``found=False`` — файла нет или данных ещё нет.
    """
    source = Path(path) if path else LOG_PATH
    out = {
        "found": False,
        "source": str(source),
        "exists": False,
        "updated": "",
        "online": False,
        "name": "",
        "static_id": "",
        "staff": "",
        "level": 0,
        "faction": "",
        "faction_name": "",
        "family": "",
        "family_name": "",
        "family_rank": 0,
        "family_rank_name": "",
        "social": "",
        "phone": "",
        "playtime": "",
        "playtime_sec": 0,
        "balance": 0,
        "health": 0,
        "armour": 0,
        "registered": "",
        "created": "",
        "pos": [],
        "stamp": "",
    }
    if not source.exists():
        return out
    out["exists"] = True

    try:
        text = source.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    lines = text.splitlines()
    phone = _last_json(lines, "Phone start with")
    chat = _last_json(lines, "Start opening chat")
    if not phone and not chat:
        return out

    out["found"] = True
    year = _dt.datetime.now().year
    try:
        moment = _dt.datetime.fromtimestamp(source.stat().st_mtime)
        out["updated"] = moment.strftime("%d.%m.%Y %H:%M:%S")
        year = moment.year          # в логе года нет — берём год самого файла
    except (OSError, OverflowError, ValueError):
        out["updated"] = ""

    stamp = _last_stamp(lines, year)
    out["stamp"] = stamp or out["updated"]
    if out["updated"]:
        try:
            moment = _dt.datetime.strptime(out["updated"], "%d.%m.%Y %H:%M:%S")
            age = (_dt.datetime.now() - moment).total_seconds()
            out["online"] = 0 <= age <= ONLINE_WINDOW_SEC
        except ValueError:
            out["online"] = False

    phone = phone or {}
    chat = chat or {}
    user = chat.get("user") or {}

    out["static_id"] = phone.get("id") or user.get("id") or ""
    first = str(phone.get("firstName") or "")
    last = str(phone.get("lastName") or "")
    out["name"] = (" ".join(part for part in (first, last) if part)).strip()
    out["staff"] = str(phone.get("staff") or user.get("staff") or "")
    out["level"] = int(phone.get("rank") or 0)
    out["faction"] = str(phone.get("factionId") or user.get("factionId") or "")
    out["faction_name"] = str(chat.get("userFactionGameObjectId") or "")
    out["family"] = str(
        phone.get("familyFactionId") or user.get("familyFactionId") or ""
    )
    out["family_rank"] = int(phone.get("familyRank") or 0)
    out["family_rank_name"] = family_rank_name(chat, out["family_rank"])
    out["social"] = str(phone.get("socialClubId") or "")
    out["phone"] = str(chat.get("number") or "")
    out["playtime_sec"] = int(phone.get("playtime") or 0)
    out["playtime"] = _playtime_text(out["playtime_sec"])
    out["balance"] = int(phone.get("balance") or 0)
    out["health"] = int(phone.get("health") or 0)
    out["armour"] = int(phone.get("armour") or 0)
    out["created"] = _date_text(phone.get("createdAt"))
    out["registered"] = _date_text(phone.get("registredAt"))
    out["pos"] = [
        phone.get("posX"), phone.get("posY"), phone.get("posZ")
    ]
    if not all(isinstance(v, (int, float)) for v in out["pos"]):
        out["pos"] = []
    return out


#: Подписи полей в панели (в том порядке, в каком они идут).
#: Баланс убран по просьбе пользователя: в логе сумма в рублях неверная.
FIELDS = (
    ("static_id", "Статик"),
    ("name", "Никнейм в игре"),
    ("staff", "Ранг в стаффе"),
    ("level", "Ранг персонажа во фракции"),
    ("faction_name", "Фракция"),
    ("family", "Семья (ID)"),
    ("family_rank", "Ранг в семье"),
    ("social", "SocialClub"),
    ("phone", "Телефон"),
    ("playtime", "Наиграно"),
    ("health", "Здоровье"),
    ("armour", "Броня"),
    ("created", "Создан"),
    ("registered", "Зарегистрирован"),
)


def _display_value(key: str, data: dict) -> object:
    """Чем показывать поле: где в логе есть название — показываем его.

    В карточке телефона лежат «сырые» значения (номер ранга, ID семьи), а
    названия есть в других кусках того же лога. Подменяем где возможно,
    иначе отдаём честно как есть (баг-репорт №5).
    """
    if key == "family":
        return data.get("family_name") or data.get("family") or ""
    if key == "family_rank":
        return data.get("family_rank_name") or data.get("family_rank") or ""
    return data.get(key)


def payload() -> str:
    """JSON для сайта (вкладка Online-STAFF) — те же данные, что в окне."""
    return json.dumps(parse(), ensure_ascii=False, separators=(",", ":"))


def _esc(text: object) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def panel_html(palette: dict[str, str] | None = None) -> str:
    """HTML карточки персонажа для окна программы и для сайта."""
    palette = palette or {}
    accent = palette.get("accent", "#38bdf8")
    muted = palette.get("muted", "#8a8c94")
    border = palette.get("border", "#30363d")
    card = palette.get("card", "#161b22")

    data = parse()
    if not data["found"]:
        return (
            '<div style="background:%s;border:1px solid %s;border-radius:10px;'
            'padding:14px 16px;color:%s;">'
            "Данных пока нет: файл логов не найден или игра ещё не запускалась.<br>"
            "<span style=\"color:%s;font-size:13px;\">Ищи: %s</span></div>"
            % (card, border, muted, muted, _esc(data["source"]))
        )

    status_color = "#2ea043" if data["online"] else muted
    status_text = "в игре" if data["online"] else "не в игре"

    # Строки — таблицей, а не flex-ом: Qt не понимает display:flex, и
    # длинное значение (например, ID семьи) наезжало на подпись (баг-репорт №5).
    rows = []
    for key, title in FIELDS:
        value = _display_value(key, data)
        if value in ("", None, 0) and key not in ("health", "armour"):
            continue
        if key == "staff":
            value = staff_name(value)
        rows.append(
            '<tr><td style="padding:7px 14px 7px 0;border-bottom:1px solid %s;'
            'color:%s;vertical-align:top;">%s</td>'
            '<td style="padding:7px 0;border-bottom:1px solid %s;'
            'font-weight:600;">%s</td></tr>'
            % (border, muted, _esc(title), border, _esc(value))
        )
    table = (
        '<table width="100%%" cellspacing="0" cellpadding="0">%s</table>'
        % "".join(rows)
    )

    pos = ""
    if data["pos"]:
        pos = (
            '<div style="color:%s;font-size:13px;margin-top:8px;">'
            "Координаты: <code>%s</code></div>"
            % (muted, _esc(", ".join("%.2f" % v for v in data["pos"])))
        )

    return (
        '<div style="background:%s;border:1px solid %s;border-radius:10px;'
        'padding:16px 18px;">'
        '<div style="display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;">'
        '<span style="color:%s;font-size:18px;font-weight:700;">%s</span>'
        '<span style="color:%s;border:1px solid %s;border-radius:10px;'
        'padding:2px 9px;font-size:12.5px;">%s</span>'
        "</div>"
        '<div style="margin-top:14px;">%s</div>%s'
        '<div style="color:%s;font-size:12px;margin-top:10px;">'
        "Обновлено: %s • источник: %s</div>"
        "</div>"
        % (
            card, border,
            accent, _esc(data["name"] or "без имени"),
            status_color, status_color, _esc(status_text),
            table,
            pos,
            muted, _esc(data["updated"] or "—"), _esc(Path(data["source"]).name),
        )
    )
