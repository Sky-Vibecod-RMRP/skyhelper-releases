# -*- coding: utf-8 -*-
"""Справочники «Транспорт» и «Оружие» — таблицы из документации RMRP Study."""
from __future__ import annotations

import json

from app.catalog import data as cat_data

PALETTE = {
    "accent": "#38bdf8",
    "muted": "#8b98a9",
    "border": "#30363d",
    "card": "#161b22",
    "text": "#e6edf3",
}


def test_sections_and_counts_come_from_study_documents():
    """19 разделов транспорта и 6 разделов оружия — как в документах Study."""
    assert [sec["title"] for sec in cat_data.sections("transport")] == [
        "🚤 Водный транспорт", "🚛 Грузовой транспорт", "🚓 Спецслужбы",
        "🚔 Полиция", "🚗 Мини машины", "🚘 Легковые", "🚴 Велосипеды",
        "🚁 Вертолёты", "⚔️ Военная техника", "🏍️ Мотоциклы",
        "🚜 Промышленная техника", "✈️ Самолёты", "🚎 Автобусы",
        "🚗 Классические авто", "🚙 Внедорожники", "🏎️ Спорткары",
        "🚙 SUV / Джипы", "🚐 Фургоны", "🚛 Прицепы",
    ]
    assert [sec["title"] for sec in cat_data.sections("weapon")] == [
        "🔪 Холодное оружие", "🔫 Пистолеты", "🔫 ПП (SMG)", "🔫 Дробовики",
        "🔫 Винтовки", "🔫 Прочее",
    ]
    assert cat_data.count("transport") == 542
    assert cat_data.count("weapon") == 60
    assert cat_data.summary("transport") == "542 строк в 19 разделах"
    assert cat_data.summary("weapon") == "60 строк в 6 разделах"


def test_every_row_has_name_id_and_source_command():
    """Каждая строка: наименование, ID и ровно та команда, что в документе."""
    for kind, prefix in (("transport", "/spawnvehicle "), ("weapon", "/givegun ")):
        for section in cat_data.sections(kind):
            assert section["rows"], section["title"]
            for row in section["rows"]:
                assert len(row) == 3
                assert row[0], row                     # наименование не пустое
                assert row[1], row                     # ID не пустой
                assert row[2].startswith(prefix), row   # команда источника


def test_rows_match_the_source_document_word_for_word():
    """Проверка на выдумки: строки лежат в том же порядке, что и в Study."""
    assert cat_data.get("transport", 15, 0) == [
        "Adder", "adder", "/spawnvehicle adder",
    ]
    assert cat_data.get("weapon", 1, 0) == [
        "Пистолет", "weapon_pistol", "/givegun id weapon_pistol 999",
    ]
    assert cat_data.get("weapon", 5, 0)[1] == "weapon_mg"
    assert cat_data.get("transport", 99, 0) == []      # за пределами — пусто


def test_search_is_case_insensitive_with_optional_slash():
    """Регистр не важен, ё = е, слэш можно не писать (как у остальных разделов)."""
    assert len(cat_data.search("transport", "Adder")) == 1
    assert len(cat_data.search("transport", "adder")) == 1
    assert cat_data.search("transport", "spawnvehicle adder")
    assert cat_data.search("transport", "/spawnvehicle adder")
    assert len(cat_data.search("weapon", "ВИНТОВКА")) >= 4
    assert cat_data.search("weapon", "weapon_pistol")
    assert cat_data.search("weapon", "пистолет")        # ё/е не мешает
    assert cat_data.search("transport", "аддер") == []  # транслита нет — это ок
    assert cat_data.search("transport", "") == []


def test_section_html_lists_rows_and_copy_links():
    """Открытый раздел: заголовок, счётчик строк и команды с копированием."""
    html = cat_data.section_html("transport", 15, PALETTE)   # «Спорткары»
    assert "Спорткары" in html
    assert "cat:transport" in html                        # «← Все разделы»
    assert 'href="catcopy:transport:15:0"' in html
    assert "/spawnvehicle adder" in html
    assert html.count("catcopy:transport:15:") == 51       # строк раздела


def test_sections_html_and_search_rendering():
    assert cat_data.list_html("transport", PALETTE).count("catsec:transport:") == 19
    assert cat_data.list_html("weapon", PALETTE).count("catsec:weapon:") == 6

    found = cat_data.list_html("weapon", PALETTE, "дробовик")
    assert "Найдено" in found and "catcopy:weapon:" in found
    assert "Ничего не нашлось" in cat_data.list_html("weapon", PALETTE, "бла-бла")

    # поиск важнее открытого раздела — раздел перекрывается результатами
    merged = cat_data.list_html("weapon", PALETTE, "пистолет", section=4)
    assert "Винтовки" not in merged.split("Найдено", 1)[1]


def test_payload_gives_the_site_the_same_rows():
    """Сайт получает те же данные: заголовки, разделы и строки."""
    payload = json.loads(cat_data.payload())
    assert payload["titles"] == {"transport": "Транспорт", "weapon": "Оружие",
                                 "gt": "Транспорт (Google)"}
    assert len(payload["sections"]["transport"]) == 19
    assert len(payload["sections"]["weapon"]) == 6
    assert len(payload["items"]["transport"]) == 542
    assert len(payload["items"]["weapon"]) == 60

    first = payload["items"]["transport"][0]
    assert first == {"s": 0, "r": 0, "n": "Субмарина Avisa", "i": "avisa",
                     "c": "/spawnvehicle avisa"}
    assert payload["items"]["weapon"][0]["i"] == "weapon_dagger"
    # у каждой строки известны раздел и позиция внутри него — без дублей
    keys = [(it["s"], it["r"]) for it in payload["items"]["transport"]]
    assert len(keys) == len(set(keys)) == 542


def test_documents_have_no_images_so_cards_are_text_only():
    """В документах Study нет картинок — значит, и в карточках их нет."""
    for kind in ("transport", "weapon"):
        assert "<img" not in cat_data.list_html(kind, PALETTE)
        assert "<img" not in cat_data.section_html(kind, 0, PALETTE)
    assert cat_data.notes("transport")[1].endswith("только таблицы.")
    assert "«Автомобили RMRP», 542 строк" in cat_data.notes("transport")[0]
    assert "«Оружие RMRP», 60 строк" in cat_data.notes("weapon")[0]


def test_google_table_transport_has_photo_and_spawn():
    """Google-Таблица: 296 единиц, категории, фото и статус спавна — как есть."""
    assert cat_data.summary("gt") == "296 строк в 9 разделах"
    assert [sec["title"] for sec in cat_data.sections("gt")] == [
        "Велики/Мотоциклы", "Самолеты/вертолеты", "Фракционный",
        "Рабочий гражданский", "Автомобили", "Прочее", "Внедорожники",
        "Спорткары/суперкары", "Отечественные",
    ]
    for section in cat_data.sections("gt"):
        assert section["rows"]
        for row in section["rows"]:
            assert len(row) == 5
            assert row[0] and row[1]                  # название и ID
            assert row[3].endswith(".jpg")            # скачанное фото
            assert row[4] in ("Спавн разрешён", "Спавн невозможен")
            assert row[2].startswith("/spawnvehicle ") == (row[4] == "Спавн разрешён")

    # порядок строк — как в таблице: первая строка первой категории
    assert cat_data.get("gt", 0, 0)[:3] == ["Квадрик Банан", "kvadrobanan", ""]

    # поиск по названию, ID и категории; имя файла в поиск не попадает
    assert cat_data.search("gt", "kvadrobanan")
    assert cat_data.search("gt", "Спорткары/суперкары")
    assert len(cat_data.search("gt", "bmx")) == 1
    assert cat_data.search("gt", ".jpg") == []


def test_google_table_rows_render_photo_and_copy_link():
    """Карточка на сайте и в окне: фото, ID, статус спавна, копирование."""
    section = cat_data.section_html("gt", 0, PALETTE)
    assert section.count("<img") == len(cat_data.rows_of("gt", 0))
    assert 'src="/img/transport/' in section
    assert "catcopy:gt:0:" in section

    # Запрет спавна из самой таблицы убран по просьбе пользователя:
    # команда собирается из ID, и подпись честно предупреждает, что сервер
    # может отказать (предложение №2 из баг-репорта).
    banned = cat_data.row_html("gt", 0, 0, PALETTE)
    assert "catcopy:gt:0:0" in banned
    assert "/spawnvehicle " in banned
    assert "запрещён" in banned


def test_every_google_table_row_has_a_spawn_command():
    """Ни одна строка справочника не осталась без команды спавна."""
    rows = [row for sec in cat_data.sections("gt") for row in sec["rows"]]
    without = [row[0] for row in rows if not cat_data.spawn_command(row)]
    assert without == [], f"без команды: {without[:5]}"


def test_spawn_command_is_built_from_id_when_sheet_has_none():
    assert cat_data.spawn_command(["bmx", "bmx", "/spawnvehicle bmx"]) == "/spawnvehicle bmx"
    assert cat_data.spawn_command(["Квадрик", "kvadrobanan", ""]) == "/spawnvehicle kvadrobanan"
    assert cat_data.spawn_command(["Без ID", "", ""]) == ""
    assert cat_data.spawn_command(None) == ""

    # фото лежат в папке, которую раздаёт и окно, и сайт
    from pathlib import Path
    from app.paths import resource_dir
    root = resource_dir("web", "static", "img", "transport")
    for section_rows in cat_data.sections("gt"):
        for row in section_rows["rows"]:
            assert (root / row[3]).is_file(), row[3]
    assert len(list(Path(root).glob("*.jpg"))) == 290   # 296 строк, 6 повторов ID


def test_google_table_notes_name_the_source():
    """Сноска честно называет источник и подтверждает работу без сети."""
    notes = cat_data.notes("gt")
    assert "Google-Таблица RMRP — 296 строк" in notes[0]
    assert "без сети" in notes[1]


def test_site_page_has_transport_and_weapon_tabs():
    """На сайте свои вкладки: «Транспорт» 542 и «Оружие» 60 — с теми же данными."""
    from app.web import page as web_page

    html = web_page.dashboard_page({})
    assert 'data-view="transport">Транспорт<span class="tab-n">542</span>' in html
    assert 'data-view="weapon">Оружие<span class="tab-n">60</span>' in html
    assert 'id="view-transport"' in html and 'id="view-weapon"' in html
    assert 'id="transport-list"' in html and 'id="weapon-list"' in html
    assert "window.SKY_CATALOG = " in html
    assert '"i":"adder","c":"/spawnvehicle adder"' in html
    assert "applyCatalog('transport')" in html and "applyCatalog('weapon')" in html
    # данные попали в страницу одним куском — список рисуется из них
    assert 'id="transport-count">542 строк в 19 разделах' in html
    assert 'id="weapon-count">60 строк в 6 разделах' in html


def test_site_page_has_google_transport_tab():
    """На сайте вкладка «Транспорт (Google)»: 296 строк, фото и спавн."""
    from app.web import page as web_page

    html = web_page.dashboard_page({})
    assert 'data-view="gt">Транспорт (Google)<span class="tab-n">296</span>' in html
    assert 'id="view-gt"' in html and 'id="gt-list"' in html
    assert 'id="gt-count">296 строк в 9 разделах' in html
    assert "applyCatalog('gt')" in html
    assert "/img/transport/kvadrobanan.jpg" in html      # данные несут фото
    assert '"sp":"Спавн невозможен"' in html             # и статус спавна


# --- баг-репорт №3: слипшийся текст и нечитаемые цвета ----------------------


def test_gt_card_keeps_a_gap_before_copy_hint():
    """QTextBrowser не умеет margin-left — команда и подпись склеивались.

    На скриншоте из репорта: «/spawnvehicle kvadrobananклик — скопировать».
    """
    html = cat_data.row_html("gt", 0, 0, PALETTE)
    assert "</a> <span" in html
    assert "</a><span" not in html


def test_catalog_text_is_readable_on_every_theme():
    """Цвета карточек проходят норму контраста 4.5:1 (WCAG AA).

    Тёмная тема читалась и раньше — она должна остаться ровно такой же;
    «midnight» (акцент 3.99:1, красный 4.44:1, чип 3.62:1) и «light»
    (акцент 3.65:1) чинятся. Ровно про это баг-репорт: «цвет символов
    не соответствует фону».
    """
    from app.ui import theme

    for name, palette in theme.THEMES.items():
        card, field = palette["card"], palette["field"]
        chip_bg = cat_data._mix(card, "#ffffff", 0.04)
        pairs = [
            ("акцент на карточке", palette["accent"], card),
            ("акцент в чипе ID", palette["accent"], chip_bg),
            ("красный статус спавна", palette["danger"], card),
            ("зелёный статус спавна", palette["ok"], card),
            ("серый текст на карточке", palette["muted"], card),
            ("заглушка «Нет фото»", palette["muted"], field),
        ]
        for label, fg, bg in pairs:
            ink = cat_data.readable_on(fg, bg)
            assert cat_data._contrast(ink, bg) >= cat_data._MIN_CONTRAST, \
                f"{name}: {label}: {ink} на {bg}"
        if name == "dark":
            # тёмная тема не перекрашивается — там контраст и так был нормой
            assert cat_data.readable_on(palette["accent"], card) == palette["accent"]
            assert cat_data.readable_on(palette["danger"], card) == palette["danger"]