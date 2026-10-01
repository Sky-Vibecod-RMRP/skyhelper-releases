# -*- coding: utf-8 -*-
"""Единая база команд: состав, поиск, синтаксис и права доступа.

Названия и порядок заморожены здесь намеренно: команды менять нельзя —
переименование, перестановка или новая команда ломают этот тест.
"""
from __future__ import annotations

import json

from app.commands import data

#: Ровно тот список, что дал пользователь (порядок сохранён).
EXPECTED = [
    "/adminbase", "/getwarns", "/infoban", "/godmode", "/uncuff",
    "/dimensionstat", "/adminmode", "/esp", "/goto", "/tp", "/return",
    "/spectate", "/callcar", "/teleportcar", "/flipcar", "/freeze",
    "/unfreeze", "/noclip", "/respawn", "/pacifist", "/unpacifist",
    "/setpos", "/kick", "/ban", "/mutechat", "/mutevoice", "/mutereport",
    "/unmute", "/deafness", "/numbness", "/unicon", "/unrk", "/warn",
    "/unarrest", "/unban", "/pred", "/spawnvehicle", "/fixcar",
    "/vehiclerows", "/clearvehicles", "/sethealth", "/sethealthall",
    "/setarmor", "/setarmorall", "/freezeall", "/unfreezeall", "/givegun",
    "/givegunall", "/model", "/modelall", "/muteall", "/unmuteall",
    "/killall", "/dimension", "/dimension_close", "/gomp", "/gomp_stop",
    "/unwarn", "/cheatcheck", "/setleader", "/unsetleader",
    "/setfactionrank", "/setfaction", "/getfactioninfo",
    "/forbid_buy_chips", "/unforbid_buy_chips", "/greenzoneoff",
    "/greenzoneon", "/setstaff", "/prolongedban", "/strictban",
    "/giveitem", "/changename", "/wipestorage", "/addcredits", "/addmoney",
    "/givecase", "/perma",
]

#: Коды прав, прочитанные со скриншотов (9 рангов: moderator → staff_leader).
RIGHTS_SAMPLES = {
    "/adminbase": "GGGGGGGGG",
    "/godmode":   "YYYYYYYYY",
    "/kick":      "YYYYYGGGG",
    "/warn":      "RYYYYGGGG",
    "/unban":     "RRYYYGGGG",
    "/killall":   "RRYYYYYYY",
    "/setleader": "RRRRRGGGG",
    "/giveitem":  "RRRRRRRGG",
    "/perma":     "RRRRRRRGG",
}


def test_command_list_is_exact():
    assert [c["name"] for c in data.COMMANDS] == EXPECTED
    assert len(data.RANKS) == 9
    assert [r["level"] for r in data.RANKS] == list(range(9))


def test_every_command_has_page_data():
    for command in data.COMMANDS:
        assert command["desc"], command["name"]
        assert command["syntax"].startswith(command["head"]), command["name"]
        assert set(command["rights"]) == {r["id"] for r in data.RANKS}
        assert set(command["rights"].values()) <= {"always", "duty", "never"}
        # параметры идут ровно в том порядке, в каком стоят в синтаксисе
        # (имя с фамилией в /changename — один параметр, поэтому склеиваем)
        tokens = command["syntax"].split()
        assert tokens[0] == command["head"], command["name"]
        assert " ".join(p["t"] for p in command["params"]) == " ".join(tokens[1:]), \
            command["name"]
        for param in command["params"]:
            assert param["ti"] and param["h"], (command["name"], param)


def test_syntax_and_descriptions_match_the_source():
    """Синтаксис и формулировки — дословно из списка пользователя."""
    by_name = {c["name"]: c for c in data.COMMANDS}
    assert by_name["/adminbase"]["desc"] == "Телепортирует на базу администрации."
    assert by_name["/adminbase"]["syntax"] == "/adminbase"
    assert by_name["/pred"]["desc"] == "Выдать устное предупреждение"
    assert by_name["/pred"]["syntax"] == "/pred 123456 4.12 ПП"
    assert by_name["/changename"]["desc"] == "Сменить имя."
    assert by_name["/changename"]["syntax"] == "/changename 123456 Иван Петухов"
    assert by_name["/perma"]["syntax"] == "/perma id"
    # примеры с псевдонимом не переписываем — показываем как есть
    assert by_name["/godmode"]["syntax"] == "/gm"
    assert by_name["/godmode"]["alias"] == "/gm"
    assert by_name["/vehiclerows"]["syntax"].startswith("/rveh 5 3 gemera")
    assert "P.S." in by_name["/vehiclerows"]["note"]


def test_search_is_case_insensitive_and_slash_optional():
    assert [c["name"] for c in data.search("")] == EXPECTED
    assert [c["name"] for c in data.search("KICK")] == ["/kick"]
    assert [c["name"] for c in data.search("/kick")] == ["/kick"]
    assert [c["name"] for c in data.search("kick")] == ["/kick"]
    assert [c["name"] for c in data.search("БАН")][:1] == ["/ban"]
    assert data.search("абракадабра") == []
    # точное название важнее совпадения внутри другого
    names = [c["name"] for c in data.search("ban")]
    assert names[0] == "/ban"
    assert "/infoban" in names and "/unban" in names


def test_search_finds_russian_words_and_drops_substring_garbage():
    """Баг-репорт №1: «поиск работает криво».

    Русский запрос находит латинскую команду, короткие слова не ловят
    мусор из середины слов, описание сравнивается по целым словам.
    """
    # «кик»/«мут» раньше давали 0 — команда есть, слова в описании нет
    assert [c["name"] for c in data.search("кик")] == ["/kick"]
    assert data.search("мут")[0]["name"] == "/mutechat"
    # «тп» раньше находило /ban и /killall: подстрока внутри «Отправить»
    tp = [c["name"] for c in data.search("тп")]
    assert set(tp) == {"/goto", "/tp", "/teleportcar"}
    # «id» раньше находило forbid_buy_chips: «id» внутри названия
    assert data.search("id") == []
    # описание по основам: «блокировка» находит «Снять блокировку чата»
    blocked = [c["name"] for c in data.search("блокировка")]
    assert "/unmute" in blocked and "/ban" in blocked
    # слово запроса остаётся первым в вариантах — /pred не пропадает
    assert data.search("предупреждение")[0]["name"] == "/warn"
    assert "/pred" in [c["name"] for c in data.search("предупреждение")]
    # мусора нет
    assert data.search("абракадабра") == []
    assert data.search("зарплата") == []


def test_synonyms_stay_in_sync_with_the_site():
    """Зеркало V_CMD_SYNONYMS в app.web.page держит поиск одинаковым."""
    import app.web.page as page

    site = page.V_CMD_SYNONYMS
    assert set(site) == set(data.SYNONYMS)
    for word, variants in data.SYNONYMS.items():
        assert tuple(site[word]) == variants, word


def test_rights_codes_from_the_spreadsheet():
    for name, code in RIGHTS_SAMPLES.items():
        command = data.get(name)
        assert command is not None, name
        assert command["code"] == code, name
        for rank, letter in zip(data.RANKS, code):
            expected = {"G": "always", "Y": "duty", "R": "never"}[letter]
            assert command["rights"][rank["id"]] == expected, (name, rank["id"])


def test_first_available_rank():
    assert data.first_available(data.get("/adminbase"))["id"] == "moderator"
    assert data.first_available(data.get("/setleader"))["id"] == "globaladmin"
    rows = data.rights_rows(data.get("/kick"))
    assert [r["state"] for r in rows] == [
        "duty", "duty", "duty", "duty", "duty", "always", "always", "always",
        "always",
    ]


def test_get_and_payload():
    assert data.get("kick")["name"] == "/kick"
    assert data.get("/KICK")["name"] == "/kick"
    assert data.get("нет_такой") is None
    payload = json.loads(data.payload())
    assert len(payload["commands"]) == len(EXPECTED)
    assert payload["commands"][0]["n"] == "/adminbase"
    assert payload["commands"][0]["r"] == "GGGGGGGGG"
    assert payload["ranks"][8]["id"] == "staff_leader"
