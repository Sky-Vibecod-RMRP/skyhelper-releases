# -*- coding: utf-8 -*-
"""Вкладка «Online-STAFF»: живой онлайн серверов RMRP и данные администратора.

Две половины, обе честные по источникам:

* **онлайн серверов** — открытый счётчик ``https://rmrp.ru/api/online``
  (общая цифра и разбивка по серверам), с коротким кэшем, чтобы не дёргать
  сеть на каждый рендер;
* **администратор** — свои же данные из логов RAGE:MP (см. ``app.player``):
  статик, имя и ранг в стаффе. Чужих игроков здесь нет и быть не может:
  читерских ридеров памяти в программе нет.

Секунды онлайна не выдумываются — при недоступности сети показывается
явное «нет данных», а не придуманные числа.
"""
from __future__ import annotations

import datetime as _dt
import json
import time
import urllib.request
from pathlib import Path

from app.player import data as player_data

#: Открытый счётчик онлайна RMRP.
ONLINE_URL = "https://rmrp.ru/api/online"

#: Сколько секунд одна и та же цифра считается свежей.
CACHE_SEC = 60

#: Таймаут запроса: сеть может быть недоступной — не подвешиваем окно.
TIMEOUT_SEC = 5

#: Поля администратора во вкладке (только свои данные из лога).
#: Имя — в шапке карточки, поэтому здесь его нет, чтобы не дублировать.
ADMIN_FIELDS = (
    ("static_id", "Статик"),
    ("staff", "Админ-ранг"),
    ("level", "Уровень"),
)

#: Имена серверов RMRP: идентификатор счётчика → название (как в лаунчере).
#: Источник — список серверов на rmrp.ru и избранное в лаунчере RAGE:MP.
SERVER_NAMES = {
    "prod1": "Рублёвка",
    "prod2": "Арбат",
    "prod3": "Патрики",
    "prod4": "Тверской",
    "prod5": "Кутузовский",
}


def server_name(key: object) -> str:
    """Название сервера для идентификатора счётчика (``prod1`` → «Рублёвка»)."""
    return SERVER_NAMES.get(str(key), str(key))


def _server_sort_key(item: tuple[str, int]) -> tuple[int, str]:
    """Сортировка серверов: по номеру (prod1, prod2, …), а не по онлайну."""
    digits = "".join(ch for ch in item[0] if ch.isdigit())
    return (int(digits) if digits else 999, item[0])

_cache: dict = {"at": 0.0, "data": None}


def _empty(error: str = "") -> dict:
    return {
        "found": False,
        "error": error,
        "total": 0,
        "servers": {},
        "updated": "",
    }


def peek() -> dict:
    """То, что уже известно про онлайн, без обращения к сети."""
    return _cache.get("data") or _empty("цифры ещё не запрашивались")


def fetch(force: bool = False) -> dict:
    """Живой онлайн серверов (кэш на ``CACHE_SEC`` секунд).

    ``force=True`` — обновить принудительно (кнопка «Обновить»).
    """
    now = time.time()
    cached = _cache.get("data")
    if not force and cached is not None and now - _cache["at"] < CACHE_SEC:
        return cached
    data = _empty()
    try:
        request = urllib.request.Request(
            ONLINE_URL, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
            raw = json.loads(response.read().decode("utf-8"))
        servers = {
            str(key): int(value)
            for key, value in (raw.get("servers") or {}).items()
            if str(value).lstrip("-").isdigit()
        }
        total = int(raw.get("total") or 0) or sum(servers.values())
        data = {
            "found": True,
            "error": "",
            "total": total,
            "servers": dict(sorted(servers.items(), key=_server_sort_key)),
            "updated": _dt.datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        }
    except Exception as exc:                     # noqa: BLE001 — сеть любит падать
        data = _empty("не удалось получить онлайн: %s" % str(exc)[:80])
    _cache.update(at=now, data=data)
    return data


def admin() -> dict:
    """Свои данные администратора из логов RAGE:MP (статик, имя, ранг)."""
    parsed = player_data.parse()
    return {
        "found": parsed["found"],
        "static_id": str(parsed["static_id"] or ""),
        "name": parsed["name"],
        "staff": parsed["staff"],
        "level": parsed["level"],
        "online": parsed["online"],
        "updated": parsed["updated"],
        "source": str(parsed["source"]),
    }


def payload(force: bool = False) -> str:
    """JSON для сайта: онлайн серверов + данные администратора."""
    data = {
        "online": fetch(force=force),
        "admin": admin(),
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _esc(text: object) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _admin_value(key: str, value: object) -> str:
    """Значение поля администратора: ранг — названием, остальное — как есть."""
    if key == "staff":
        return player_data.staff_name(value)
    return str(value or "—")


def _row(label: str, value: str, palette: dict[str, str], bold: bool = False) -> str:
    border = palette.get("border", "#30363d")
    muted = palette.get("muted", "#8a8c94")
    style = "font-weight:700;" if bold else ""
    return (
        '<div style="display:flex;gap:10px;padding:6px 0;'
        'border-bottom:1px solid %s;">'
        '<span style="color:%s;min-width:170px;">%s</span>'
        '<span style="%s">%s</span></div>'
        % (border, muted, _esc(label), style, _esc(value))
    )


def _online_card_html(palette: dict[str, str], *, ids: bool = False,
                      network: bool = True, force: bool = False) -> str:
    """Карточка онлайна серверов — общая для вкладки и объединённой панели."""
    muted = palette.get("muted", "#8a8c94")
    border = palette.get("border", "#30363d")
    card = palette.get("card", "#161b22")
    accent = palette.get("accent", "#38bdf8")

    online = fetch(force=force) if network else peek()

    total_id = ' id="staff-total"' if ids else ""
    servers_id = ' id="staff-servers"' if ids else ""
    updated_id = ' id="staff-updated"' if ids else ""
    note_id = ' id="staff-note"' if ids else ""

    if online["found"]:
        servers = "".join(
            '<div style="display:flex;gap:10px;justify-content:space-between;'
            'padding:5px 0;border-bottom:1px solid %s;">'
            "<span style=\"font-family:Consolas,monospace;\">%s</span>"
            "<span style=\"font-weight:700;\">%d</span></div>"
            % (border, _esc(server_name(name)), online["servers"][name])
            for name in online["servers"]
        )
        big = (
            '<div style="color:%s;font-size:34px;font-weight:800;"%s>%s</div>'
            % (accent, total_id, online["total"])
        )
        note = (
            '<div style="color:%s;font-size:12.5px;"%s>'
            "всего игроков на всех серверах</div>" % (muted, note_id)
        )
        updated = "Обновлено: %s" % online["updated"]
        source = ONLINE_URL
    else:
        servers = ""
        big = (
            '<div style="color:%s;font-size:20px;font-weight:700;"%s>нет данных</div>'
            % (muted, total_id)
        )
        note = '<div style="color:%s;font-size:12.5px;"%s>%s</div>' % (
            muted, note_id, _esc(online["error"] or "сеть недоступна"),
        )
        updated = "Онлайн не получен"
        source = ONLINE_URL
    servers = '<div%s>%s</div>' % (servers_id, servers) if ids else servers
    updated_html = (
        '<span%s>%s</span>' % (updated_id, _esc(updated))
        if ids else _esc(updated)
    )
    return (
        '<div style="background:%s;border:1px solid %s;border-radius:10px;'
        'padding:14px 16px;">'
        '<div style="color:%s;font-size:12px;font-weight:700;letter-spacing:1px;">'
        "ОНЛАЙН СЕРВЕРА RMRP</div>"
        "%s%s"
        '<div style="margin-top:8px;">%s</div>'
        '<div style="color:%s;font-size:12px;margin-top:8px;">%s • %s</div>'
        "</div>"
        % (card, border, muted, big, note, servers, muted, updated_html, _esc(source))
    )


def combined_html(palette: dict[str, str] | None = None, *, ids: bool = False,
                  network: bool = True, force: bool = False) -> str:
    """Объединённая вкладка: онлайн серверов + все данные игрока (без дубля).

    Админ-карточка из обычной вкладки здесь не нужна: она есть в полной
    карточке игрока (app.player).
    """
    palette = palette or {}
    return (
        _online_card_html(palette, ids=ids, network=network, force=force)
        + player_data.panel_html(palette)
    )


def panel_html(palette: dict[str, str] | None = None, *, ids: bool = False,
               network: bool = True, force: bool = False) -> str:
    """HTML вкладки: живой онлайн серверов и карточка администратора.

    ``ids=True`` — добавить ``id`` на обновляемые места (для сайта, где
    цифры докачиваются из ``/api/online``); ``network=False`` — не ходить
    в сеть, а показать то, что уже в кэше (страница не должна ждать сети).
    """
    palette = palette or {}
    muted = palette.get("muted", "#8a8c94")
    border = palette.get("border", "#30363d")
    accent = palette.get("accent", "#38bdf8")

    person = admin()
    card = palette.get("card", "#161b22")

    # --- администратор -----------------------------------------------------
    if person["found"]:
        status_color = "#2ea043" if person["online"] else muted
        status_text = "в игре" if person["online"] else "не в игре"
        # статик и остальные поля — в строках ниже, здесь только имя и статус
        head = (
            '<div style="display:flex;gap:10px;align-items:baseline;'
            'flex-wrap:wrap;">'
            '<span style="color:%s;font-size:17px;font-weight:700;">%s</span>'
            '<span style="color:%s;border:1px solid %s;border-radius:10px;'
            'padding:2px 9px;font-size:12.5px;">%s</span></div>'
            % (accent, _esc(person["name"] or "без имени"),
               status_color, status_color, _esc(status_text))
        )
        rows = "".join(
            _row(title, _admin_value(key, person.get(key)), palette)
            for key, title in ADMIN_FIELDS
        )
        note_admin = '<div style="color:%s;font-size:12px;margin-top:8px;">%s</div>' % (
            muted, "источник: %s • обновлено: %s" % (
                _esc(Path(person["source"]).name),
                _esc(person["updated"] or "—"),
            )
        )
    else:
        head = (
            '<div style="color:%s;font-weight:700;">Данных администратора пока нет'
            "</div>" % muted
        )
        rows = ""
        note_admin = (
            '<div style="color:%s;font-size:12px;margin-top:8px;">'
            "Игра ещё не запускалась — файл логов не найден.</div>" % muted
        )

    return (
        _online_card_html(palette, ids=ids, network=network, force=force)
        + (
            '<div style="background:%s;border:1px solid %s;border-radius:10px;'
            'padding:14px 16px;">'
            '<div style="color:%s;font-size:12px;font-weight:700;letter-spacing:1px;">'
            "АДМИНИСТРАТОР</div>"
            "%s<div style=\"margin-top:6px;\">%s</div>%s"
            '<p style="margin:12px 0 0 0;"><a href="staff:refresh" '
            'style="color:%s;">Обновить онлайн</a></p>'
            "</div>"
            % (card, border, muted, head, rows, note_admin, accent)
        )
    )
