"""Тесты окна «Хелпер»: цветное меню, контент разделов, поиск по правилам.

Как и экран настроек, рисуемся без экрана (QT_QPA_PLATFORM=offscreen).
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # без экрана и без окон

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.catalog import data as cat_data  # noqa: E402
from app.commands import data as cmd_data  # noqa: E402
from app.events import data as ev_data  # noqa: E402
from app.help import data  # noqa: E402
from app.player import data as player_data  # noqa: E402
from app.ui import helper_window as helper  # noqa: E402
from app.ui.helper_window import HelperWindow, readable  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp):
    win = HelperWindow(theme_name="dark", output_dir=r"C:\Отчёты")
    win.show()
    qapp.processEvents()
    yield win
    win.hide()


def test_nav_has_reference_group_only(window):
    """В меню только справочник — инструкции убраны (они на сайте)."""
    assert window._nav.count() == len(helper._REFERENCE_ITEMS) + 1   # + метка
    titles = [window._nav.item(i).text() for i in range(window._nav.count())]
    assert titles[0] == helper.GROUP_REFERENCE
    assert titles[1] == "Команды"
    assert titles[2] == "Серверные события"
    assert titles[3] == "Транспорт"
    assert titles[4] == "Оружие"
    assert titles[5] == "Транспорт (Google)"
    assert titles[6] == "Online-STAFF"
    assert titles[7] == "Правила RMRP"
    assert window._nav.currentRow() == 1             # «Команды» — первый пункт
    assert window._heading.text() == "Команды"
    assert window._search.isVisible()               # у команд есть поиск

    # метка группы не выбирается и не кликается
    item = window._nav.item(0)
    assert not (item.flags() & Qt.ItemFlag.ItemIsSelectable)
    assert not (item.flags() & Qt.ItemFlag.ItemIsEnabled)


def test_instructions_are_not_in_window_nav(window):
    """Разделы инструкций из меню окна убраны — они остались на сайте."""
    titles = [window._nav.item(i).text() for i in range(window._nav.count())]
    for section in data.SECTIONS:
        assert str(section["title"]) not in titles


def test_rules_search_filters_counts_and_empty_state(window):
    window.show_rules()
    assert window._search.isVisible()
    assert window._heading.text() == "Правила RMRP"
    assert window._count.text() == "28 правил в 3 разделах"
    assert window._body.toHtml().count("forum.rmrp.ru") == 28

    window.set_query("допросы")
    html = window._body.toHtml()
    assert "pravila-doprosov" in html
    # Совпадение в заголовке идёт выше совпадений «только в тексте».
    assert html.index("pravila-doprosov") < html.index("pravila-semej")
    # Количество найденных считает тот же фильтр, что и рендер.
    found = sum(len(c["items"]) for c in data.filter_rules("допросы"))
    assert window._count.text() == "Найдено: %d из 28" % found
    assert found > 1  # поиск идёт и по тексту правил

    window.set_query("абракадабра")
    assert "Ничего не нашлось" in window._body.toPlainText()
    assert window._count.text() == "Найдено: 0 из 28"

    window.set_query("")
    assert window._count.text() == "28 правил в 3 разделах"


def test_theme_change_keeps_selection_and_content(window, qapp):
    window.show_rules()
    window.apply_theme("light")
    qapp.processEvents()
    assert window._nav.currentRow() == window.rules_row
    assert window._count.text() == "28 правил в 3 разделах"


def test_readable_darkens_bright_colors_on_light_theme():
    light = {"bg": "#f4f6fa"}
    dark = {"bg": "#0d1117"}
    assert readable("#00d1ff", dark) == "#00d1ff"
    assert readable("#00d1ff", light) != "#00d1ff"
    assert readable("мусор", light) == "мусор"   # плохой ввод не роняет


def test_commands_list_search_and_open_page(window):
    """Раздел «Команды»: список, регистронезависимый поиск, страница команды."""
    window.show_commands()
    assert window._search.isVisible()
    assert window._heading.text() == "Команды"
    assert window._count.text() == "%d команд" % len(cmd_data.COMMANDS)
    assert "/kick" in window._body.toHtml()

    window.set_query("KICK")           # регистр не важен
    assert window._count.text() == "Найдено: 1 из %d" % len(cmd_data.COMMANDS)
    html = window._body.toHtml()
    assert "/kick" in html
    assert "/kickkey" not in html

    window.open_command("/kick")
    assert window._stack.currentWidget() is window._command_page
    assert window._heading.text() == "Команды"
    assert not window._search.isVisible()     # на странице команды поиск не нужен
    page = window._command_page
    assert page.command()["name"] == "/kick"
    assert page._name.text() == "/kick"
    # форма подставлена значениями из примера → предпросмотр = исходный синтаксис
    assert [f.text() for f in page._fields] == ["1234", "Причина"]
    assert page._preview.text() == "/kick 1234 Причина"

    page._fields[0].setText("958726")          # собрали свою команду
    assert page._preview.text() == "/kick 958726 Причина"

    window._back_to_list()
    assert window._stack.currentWidget() is window._body
    assert window._view == "commands"
    assert window._search.text() == "KICK"     # поиск сохранился


def test_theme_change_keeps_command_page(window, qapp):
    window.open_command("/ban")
    window.apply_theme("light")
    qapp.processEvents()
    assert window._stack.currentWidget() is window._command_page
    assert window._command_page.command()["name"] == "/ban"
    assert window._nav.currentRow() == window.commands_row


def test_events_categories_open_and_show_cards(window):
    """Раздел событий: пять категорий → список событий → карточка."""
    window.show_events()
    assert window._view == "events"
    assert window._heading.text() == "Серверные события"
    assert window._search.isVisible()
    assert window._count.text() == ev_data.summary()
    html = window._body.toHtml()
    for cat in ev_data.CATEGORIES:
        assert 'href="evtcat:%s"' % cat["slug"] in html
    # на первом экране только заголовки категорий, без карточек событий
    assert 'href="evt:' not in html

    window._open_event_category("nalyoty")
    html = window._body.toHtml()
    assert window._count.text() == "%d событий" % len(ev_data.events_of("nalyoty"))
    assert 'href="evtcat:"' in html          # «← Все категории»
    assert html.count('href="evt:nalyoty-') == len(ev_data.events_of("nalyoty"))

    window._open_event("nalyoty-1")
    assert window._stack.currentWidget() is window._event_page
    page = window._event_page
    event = ev_data.get("nalyoty-1")
    assert page.current_event()["id"] == "nalyoty-1"
    assert page._name.text() == event["name"]
    assert page._tp_btn.text() == "Телепортироваться на событие"

    page._back.click()
    assert window._stack.currentWidget() is window._body
    assert window._view == "events"
    assert window._events_category == "nalyoty"   # категория сохранилась


def test_events_search_by_name_and_category(window):
    window.show_events()
    window.set_query("захват")
    found = len(ev_data.search("захват"))
    assert window._count.text() == "Найдено: %d из %d" % (found, len(ev_data.EVENTS))
    assert "Семейные захваты территорий" in window._body.toHtml()

    window.set_query("Поставки")            # поиск и по названию категории
    assert len(ev_data.search("Поставки")) == len(ev_data.events_of("postavki"))

    window.set_query("абракадабра")
    assert "Событий не нашлось" in window._body.toPlainText()


def test_event_page_teleport_copies_source_command(window, qapp):
    """Кнопка телепорта копирует ровно ту команду, что в документации."""
    from PySide6.QtGui import QGuiApplication

    event = ev_data.get("fraktsionnye-2")
    window.open_event(event["id"])
    page = window._event_page
    page._tp_btn.click()
    assert QGuiApplication.clipboard().text() == event["cmd"]
    assert page._tp_btn.text() == "Скопировано ✓"
    assert page._tp_hint.isVisible()
    assert event["cmd"] == "/setpos -912.78, 4497.64, 133.75"


def test_event_screenshots_show_in_list_and_on_card(window):
    """Скачанные со Study скриншоты видны и в списке, и в карточке события."""
    from app.ui.rich_text import resolve_image

    window.show_events()
    window._open_event_category("nalyoty")
    html = window._body.toHtml()
    assert html.count('<img src="/img/events/nalyoty-') == len(
        ev_data.events_of("nalyoty")
    )

    page = window._event_page
    window._open_event("nalyoty-1")
    assert page._shot.isVisible()
    pixmap = page._shot.pixmap()
    assert not pixmap.isNull()
    assert pixmap.width() == 620          # картинка 800 px подогнана под карточку

    # ссылки разбираются только внутри папки картинок приложения
    assert resolve_image("/img/events/nalyoty-1.jpg") is not None
    assert resolve_image("/img/../config.json") is None
    assert resolve_image("/img/events/../../app/paths.py") is None
    assert resolve_image("https://rmrp-study.ru/uploads/x.png") is None
    assert resolve_image("file:///C:/nope/x.jpg") is None


def test_player_data_is_inside_staff_view(window):
    """Данные игрока теперь внутри объединённой вкладки Online-STAFF."""
    window.show_staff()
    text = window._body.toPlainText()
    data = player_data.parse()
    if data["found"]:
        assert str(data["static_id"]) in text
        assert data["name"] in text
        assert player_data.staff_name(data["staff"]) in text
    # отдельной вкладки «Данные игрока» в меню больше нет
    assert window._row_of("Данные игрока") is None


def test_transport_catalog_sections_search_and_copy(window):
    """«Транспорт»: разделы Study, поиск и копирование команды кликом."""
    window.show_catalog("transport")
    assert window._view == "catalog"
    assert window._heading.text() == "Транспорт"
    assert window._count.text() == "542 строк в 19 разделах"
    assert window._search.isVisible()
    assert window._body.toHtml().count('href="catsec:transport:') == 19

    window._on_anchor(QUrl("catsec:transport:15"))       # «Спорткары»
    assert window._catalog_section == 15
    assert window._count.text() == "51 строк"
    assert 'href="catcopy:transport:15:0"' in window._body.toHtml()

    window.set_query("Adder")
    assert window._count.text() == "Найдено: 1 из 542"
    window._on_anchor(QUrl("catcopy:transport:15:0"))
    assert QApplication.clipboard().text() == "/spawnvehicle adder"
    assert window._count.text().startswith("Скопировано ✓")

    window.set_query("")
    window._on_anchor(QUrl("cat:transport"))             # «← Все разделы»
    assert window._catalog_section is None
    assert window._count.text() == "542 строк в 19 разделах"

    window.set_query("бла-бла")
    assert window._count.text() == "Найдено: 0 из 542"
    assert "Ничего не нашлось" in window._body.toPlainText()


def test_weapon_catalog_from_menu_and_theme_change(window, qapp):
    """«Оружие» из меню; смена темы не сбрасывает открытый раздел."""
    assert window.weapon_row is not None
    window._on_row(window.weapon_row)
    assert window._view == "catalog"
    assert window._heading.text() == "Оружие"
    assert window._count.text() == "60 строк в 6 разделах"
    assert window._nav.currentRow() == window.weapon_row

    window._on_anchor(QUrl("catsec:weapon:4"))           # «Винтовки»
    html = window._body.toHtml()
    assert "Винтовки" in html and "weapon_assaultrifle" in html

    window.apply_theme("light")
    qapp.processEvents()
    assert window._view == "catalog"
    assert window._catalog_kind == "weapon"
    assert window._catalog_section == 4
    assert window._count.text() == "11 строк"
    assert "weapon_assaultrifle" in window._body.toHtml()


def test_staff_view_shows_online_and_full_player(window, monkeypatch):
    """Объединённая вкладка: живой онлайн серверов + все данные игрока."""
    from app.staff import data as staff_data

    monkeypatch.setattr(staff_data, "fetch", lambda force=False: {
        "found": True, "error": "", "total": 2417,
        "servers": {"prod4": 481, "prod1": 479},
        "updated": "30.09.2026 00:15",
    })
    window.show_staff()
    assert window._view == "staff"
    assert window._heading.text() == "Online-STAFF"
    assert window._nav.currentRow() == window.staff_row
    assert not window._search.isVisible()

    text = window._body.toPlainText()
    assert "ОНЛАЙН СЕРВЕРА RMRP" in text
    assert "2417" in text and "Тверской" in text and "481" in text   # имя, не prod4 (баг №7)
    assert "Рублёвка" in text and "479" in text
    # полная карточка игрока (не отдельная админ-карточка)
    assert "АДМИНИСТРАТОР" not in text
    player = player_data.parse()
    if player["found"]:
        assert str(player["static_id"]) in text
        assert player["name"] in text
        assert player_data.staff_name(player["staff"]) in text   # название ранга (баг №2)
        assert "Фракция" in text and "Семья" in text              # полные данные игрока

    calls: list[bool] = []

    def fake_fetch(force=False):
        calls.append(force)
        return {"found": True, "error": "", "total": 1,
                "servers": {"prod4": 1}, "updated": "now"}

    monkeypatch.setattr(staff_data, "fetch", fake_fetch)
    window._on_anchor(QUrl("staff:refresh"))
    assert calls == [True]                             # кнопка форсирует запрос
    assert window._view == "staff"
    assert "1" in window._body.toPlainText()
