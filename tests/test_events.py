"""Проверка раздела «Серверные события» (спецификация 9.7).

Данные берутся из документов RMRP Study и не должны искажаться:
названия и команды телепортации — дословно, координаты у каждого
события — свои, распределение по пяти категориям — как в источнике.
"""
from __future__ import annotations

import json
import re

from app.events import data as ev_data

#: Названия пять категорий — ровно как в документации RMRP Study.
CATEGORY_NAMES = [
    "Война за КрАЗ и AirDrop",
    "Налёты",
    "Поставки/ограбления",
    "Семейные захваты территорий",
    "Фракционные захваты",
]

#: Распределение событий по категориям (проверено на источнике).
DISTRIBUTION = {
    "kraz-airdrop": 8,
    "nalyoty": 30,
    "postavki": 9,
    "semeynye": 9,
    "fraktsionnye": 11,
}

#: Фрагменты дословно из документов: название → команда телепортации.
FROZEN = {
    "kraz-airdrop-1": ("ВЗК 1/3", "/setpos 580, 1570, 170, 155.21"),
    "kraz-airdrop-5": ("ВЗА 2/5", "/setpos -1332.15, 960, 165, 155.21"),
    "kraz-airdrop-8": ("ВЗА 5/5", "/setpos -80, 1265, 130, 155.21"),
    "nalyoty-1": ("Гараж самогонщика", "/setpos 160.15, 2710, 150, 155.21"),
    "nalyoty-30": ("Шахта №3", "/setpos -820.15, 10, 195, 155.21"),
    "postavki-9": ("Объект 7", "/setpos 600, 1800, 170, 155.21"),
    "semeynye-1": ("Топливное хранилище", "/setpos -2251.06, 4300.78, 144.69"),
    "semeynye-9": ("Строящийся мост", "/setpos -132, 513, 145.21"),
    "fraktsionnye-2": ("Порт Исаково", "/setpos -912.78, 4497.64, 133.75"),
    "fraktsionnye-11": ("Трасса Москва-Зарайск", "/setpos -8.51, 1960, 150.21"),
}


def test_five_categories_in_source_order():
    assert [cat["name"] for cat in ev_data.CATEGORIES] == CATEGORY_NAMES
    assert len(ev_data.CATEGORIES) == 5
    assert ev_data.NOTES == []          # данные полные, ничего не додумывали


def test_events_distributed_across_categories():
    assert len(ev_data.EVENTS) == sum(DISTRIBUTION.values()) == 67
    for slug, expected in DISTRIBUTION.items():
        found = ev_data.events_of(slug)
        assert len(found) == expected, slug
        assert ev_data.category_count(slug) == expected
    slugs = {cat["slug"] for cat in ev_data.CATEGORIES}
    assert {ev["cat"] for ev in ev_data.EVENTS} <= slugs


def test_names_and_commands_kept_verbatim():
    for event_id, (name, cmd) in FROZEN.items():
        event = ev_data.get(event_id)
        assert event is not None, event_id
        assert event["name"] == name
        assert event["cmd"] == cmd


def test_every_event_has_its_own_coordinates():
    for event in ev_data.EVENTS:
        assert event["name"], event["id"]
        assert event["cmd"].startswith("/setpos "), event["id"]
        assert len(event["coords"]) >= 3, event["id"]   # минимум x, y, z
        # координаты в команде = координаты в карточке (кнопка не подменяет их)
        numbers = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", event["cmd"])]
        assert numbers == event["coords"], event["id"]


def test_no_duplicates():
    ids = [event["id"] for event in ev_data.EVENTS]
    assert len(ids) == len(set(ids))
    pairs = [(event["cat"], event["name"]) for event in ev_data.EVENTS]
    assert len(pairs) == len(set(pairs))


def test_search_by_name_and_by_category():
    assert ev_data.search("Гараж самогонщика")[0]["id"] == "nalyoty-1"
    assert len(ev_data.search("налёт")) == DISTRIBUTION["nalyoty"]
    assert len(ev_data.search("Поставки")) == DISTRIBUTION["postavki"]
    # без учёта регистра и без слэша
    assert ev_data.search("ШАХТА №3")
    assert ev_data.search("захват")             # и по названию категории тоже
    assert ev_data.search("абракадабра") == []


def test_payload_matches_window_data():
    payload = json.loads(ev_data.payload())
    assert [cat["name"] for cat in payload["categories"]] == CATEGORY_NAMES
    assert payload["notes"] == ev_data.NOTES
    assert len(payload["events"]) == len(ev_data.EVENTS)
    by_id = {ev["i"]: ev for ev in payload["events"]}
    event = by_id["nalyoty-1"]
    assert event["n"] == "Гараж самогонщика"
    assert event["c"] == "nalyoty"
    assert event["m"] == "/setpos 160.15, 2710, 150, 155.21"
    assert event["x"] == [160.15, 2710, 150, 155.21]
    # скриншот лежит на сайте, оригинал — в документации RMRP Study
    assert event["s"] == "/img/events/nalyoty-1.jpg"
    assert event["u"].startswith("https://rmrp-study.ru/uploads/")
    assert event["w"] > 0 and event["h"] > 0


def test_every_event_has_a_downloadable_screenshot():
    """67 скриншотов скачаны из RMRP Study и лежат в папке приложения."""
    missing = [
        ev["id"]
        for ev in ev_data.EVENTS
        if not ev["img"].startswith("/img/events/") or ev_data.image_file(ev) is None
    ]
    assert missing == []
    assert ev_data.image_file(ev_data.get("nalyoty-1")).stat().st_size > 2000


def test_window_cards_show_screenshot():
    """В окне у каждого события виден скриншот (свой размер под свою картинку)."""
    palette = {"accent": "#38bdf8", "muted": "#8b98a9", "border": "#30363d",
               "card": "#161b22", "text": "#e6edf3"}
    html = ev_data.list_html("", "nalyoty", palette)
    assert html.count('<img src="/img/events/nalyoty-') == len(ev_data.events_of("nalyoty"))
    for event in ev_data.events_of("nalyoty")[:3]:
        height = max(1, round(400 * event["ih"] / max(1, event["iw"])))
        assert 'src="%s" width="400" height="%d"' % (event["img"], height) in html


def test_site_page_has_screenshots_and_teleport_button():
    """На сайте скриншоты есть, кнопка «Телепортироваться» — тоже (баг №4)."""
    from app.web import page as web_page

    html = web_page.dashboard_page({})
    assert "window.SKY_EVENTS" in html
    assert "Телепортироваться на событие" in html
    assert 'class="evt-tp"' in html
    assert "evt-shot" in html and 'loading="lazy"' in html
