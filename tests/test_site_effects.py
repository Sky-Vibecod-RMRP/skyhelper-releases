"""Тесты новых фич: дождь, белый кружок-курсор, бегунок, умный поиск.

Всё, что тут проверяется, добавлено 30.09.2026 по просьбе: дождь с
переключателем в настройках, кастомный курсор «белый кружок», нормальный
ползунок прокрутки и «поиск ещё лучше» (стоп-слова + опечатки).
"""
from __future__ import annotations

import json
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.config import CURSOR_STYLES, Config
from app.help import data as help_data
from app.web import page as web_page

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


class FakeCore:
    """Подмена ядра: настоящее трогает файлы в %APPDATA%."""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.web_running = False
        self.web_error = ""
        self.site_url = None

    def apply_config(self) -> None:
        self.web_running = self.config.web_enabled


def _opts(html: str) -> dict:
    found = re.search(r"window\.SKY_OPTS = (\{.*?\});", html)
    assert found, "на странице нет window.SKY_OPTS"
    return json.loads(found.group(1))


# --- дождь ------------------------------------------------------------------


def test_page_defaults_to_rain_and_white_cursor():
    """Без настроек страница всё равно должна быть с дождём и белым кружком."""
    opts = _opts(web_page.dashboard_page({}))
    assert opts == {"rain": True, "cursor": "white"}


def test_page_options_reach_the_page():
    opts = _opts(web_page.dashboard_page({}, {"rain": False, "cursor": "ring"}))
    assert opts["rain"] is False
    assert opts["cursor"] == "ring"


def test_rain_is_a_canvas_behind_content():
    html = web_page.dashboard_page({})
    assert "#sky-rain" in html, "нет полотна дождя"
    assert "createElement('canvas')" in html
    # Дождь не должен перехватывать клики и не должен лежать поверх текста.
    block = re.search(r"#sky-rain \{[^}]*\}", html).group(0)
    assert "pointer-events: none" in block
    assert "z-index: -1" in block


def test_rain_respects_reduced_motion():
    """Если в системе включено «уменьшить анимацию» — дождя нет."""
    html = web_page.dashboard_page({})
    assert "prefers-reduced-motion" in html


def test_rain_can_be_switched_off_in_settings(qapp):
    from app.ui.settings_dialog import SettingsDialog

    cfg = Config()
    cfg.rain_enabled = False
    cfg.cursor_style = "ring"
    dialog = SettingsDialog(FakeCore(cfg))
    try:
        assert dialog._rain.isChecked() is False
        assert dialog._cursor.currentData() == "ring"
        dialog._rain.setChecked(True)
        dialog._cursor.setCurrentIndex(0)      # «Белый кружок»
        dialog._collect()
        assert cfg.rain_enabled is True
        assert cfg.cursor_style == "white"
    finally:
        dialog.deleteLater()


def test_config_round_trip_of_new_fields(tmp_path):
    """Новые настройки должны переживать перезапуск программы."""
    path = tmp_path / "cfg.json"
    cfg = Config()
    cfg.rain_enabled = False
    cfg.cursor_style = "ring"
    cfg.save(path)
    again = Config.load(path)
    assert again.rain_enabled is False
    assert again.cursor_style == "ring"


# --- курсор -----------------------------------------------------------------


def test_white_cursor_is_white_circle_with_outline():
    """Кружок должен быть виден и на светлом, и на тёмном фоне."""
    html = web_page.dashboard_page({})
    block = re.search(r"\.sky-cursor-dot\.white \{[^}]*\}", html).group(0)
    assert "background: #ffffff" in block
    assert "border-radius: 50%" in re.search(
        r"\.sky-cursor-dot \{[^}]*\}", html
    ).group(0)
    assert "box-shadow" in block


def test_cursor_is_pinned_to_the_corner():
    """Без top/left position:fixed ставит элемент в конце страницы, за экраном.

    Из-за этого курсор не было видно вообще, а системный уже был скрыт.
    """
    html = web_page.dashboard_page({})
    for name in (".sky-cursor-dot", ".sky-cursor-ring"):
        block = re.search(re.escape(name) + r" \{[^}]*\}", html).group(0)
        assert "position: fixed" in block
        assert "top: 0" in block and "left: 0" in block, f"{name} не закреплён"


def test_cursor_style_off_keeps_system_cursor():
    """При «Системный» нарисованный курсор не создаётся вовсе."""
    js = web_page._CURSOR_JS
    assert "if (style === 'off') { return; }" in js


def test_cursor_never_leaves_two_pointers():
    """Нарисованный курсор всегда гасит системный — иначе их видно два."""
    assert "sky-cursor-on" in web_page._CURSOR_JS


def test_cursor_styles_have_names_for_settings():
    assert set(CURSOR_STYLES) == {"white", "ring", "off"}
    assert all(label.strip() for label in CURSOR_STYLES.values())


# --- бегунок прокрутки ------------------------------------------------------


def test_helper_window_has_its_own_scrollbars(qapp):
    """Полосы прокрутки были системными — отсюда «уродливый бегунок»."""
    from app.ui.helper_window import HelperWindow

    window = HelperWindow()
    try:
        style = window.styleSheet()
        assert "QScrollBar:vertical" in style
        assert "QScrollBar::handle:vertical" in style
        assert "QScrollBar:horizontal" in style
        assert "QScrollBar::add-line" in style, "стрелки на бегунке лишние"
    finally:
        window.deleteLater()


def test_helper_window_sidebar_has_no_horizontal_scrollbar(qapp):
    from app.ui.helper_window import HelperWindow

    window = HelperWindow()
    try:
        from PySide6.QtCore import Qt

        window.resize(1000, 640)
        window.show()
        window._nav.setCurrentRow(window._row_of("Транспорт (Google)"))
        qapp.processEvents()
        assert not window._nav.horizontalScrollBar().isVisible()
    finally:
        window.deleteLater()


# --- поиск: стоп-слова ------------------------------------------------------


def test_stop_words_do_not_block_the_search():
    """«как наказать за спавн» раньше не находил ничего."""
    assert "как" in help_data.STOP_WORDS
    assert help_data.query_stems("как наказать за спавн") == ["нак", "спа"]
    assert help_data.query_stems("сколько минут длится допрос") == [
        "ско", "мин", "дли", "доп",
    ]


def test_query_of_stop_words_only_is_searched_as_is():
    """Если кроме служебных слов ничего нет — не выкидываем всё."""
    assert help_data.query_stems("как") == ["как"]


def test_stop_words_make_search_find_the_same_rules():
    rules = help_data.load_rules()

    def count(query: str) -> int:
        return sum(len(c.get("items", ())) for c in help_data.filter_rules(query, rules))

    assert count("наказать за спавн") == count("как наказать за спавн")
    assert count("наказать за спавн") > 0


# --- поиск: опечатки --------------------------------------------------------


@pytest.mark.parametrize("typo, word", [
    ("депрос", "допрос"),
    ("допрс", "допрос"),
    ("наказания", "наказание"),
    ("оружье", "оружие"),
])
def test_typo_still_finds_the_rules(typo, word):
    rules = help_data.load_rules()

    def count(query: str) -> int:
        return sum(len(c.get("items", ())) for c in help_data.filter_rules(query, rules))

    assert count(typo) > 0, f"«{typo}» не нашёл ничего, хотя «{word}» есть"
    assert count(typo) >= min(3, count(word))


@pytest.mark.parametrize("junk", [
    "ыыыы", "zxcvbn", "бмп", "пмж", "кое-что", "спвон",
])
def test_junk_does_not_open_the_whole_section(junk):
    """Опечатки не должны превращаться в «покажи всё»."""
    rules = help_data.load_rules()
    total = sum(len(c.get("items", ())) for c in rules)
    found = sum(len(c.get("items", ())) for c in help_data.filter_rules(junk, rules))
    assert found == 0, f"«{junk}» нашёл {found} из {total} правил"


def test_typo_hits_go_after_exact_ones():
    """Точное совпадение всегда выше ошибочного."""
    rules = help_data.load_rules()
    cats = help_data.filter_rules("депрос", rules)
    assert cats, "ничего не нашлось"
    first = cats[0]["items"][0]
    assert help_data.match_rank(first, cats[0]["category"], "депрос") is not None, \
        "первым пошло правило, найденное только с опечаткой"


def test_typo_ball_stays_inside_word_length():
    """Слишком короткие и слишком длинные слова опечатками не ловим."""
    assert help_data._typo_ball("бмп") == frozenset()
    assert help_data._typo_ball("аб") == frozenset()
    assert help_data._typo_ball("оченьдлинное") == frozenset()
    assert "допрос" in help_data._typo_ball("депрос")
    assert "допрос" not in help_data._typo_ball("допрос")


def test_search_stays_fast():
    """Поиск не должен тормозить: 236К символов правил."""
    import time

    rules = help_data.load_rules()
    start = time.perf_counter()
    for query in ("допрос", "спавн", "война", "зарплата", "наказание"):
        help_data.filter_rules(query, rules)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"пять запросов заняли {elapsed:.2f} с"


# --- поиск на сайте ---------------------------------------------------------


def test_site_js_has_the_same_stop_words():
    js = web_page._VIEW_JS
    for word in ("не", "как", "за", "для"):
        assert f"'{word}': 1" in js, f"«{word}» не выкидается на сайте"


def test_site_js_builds_the_same_typo_ball():
    """Лишняя буква вставляется перед word[i] — иначе получаются обрезки
    в одну букву, а такие есть в любом заголовке, и поиск находил всё."""
    js = web_page._VIEW_JS
    assert "head + ch + word.charAt(i) + tail" in js
    assert re.search(r"out\[head \+ ch\]", js) is None


def test_site_search_has_a_delay():
    """Перерисовка по 236К символов на каждую букву подтормаживала."""
    assert "queueRules" in web_page._VIEW_JS
    assert "}, 160);" in web_page._VIEW_JS


def test_site_and_program_show_the_same_rules():
    """Сайт и программа работают с одним и тем же набором правил."""
    rules = help_data.load_rules()
    expected = sum(len(cat.get("items", ())) for cat in rules)
    payload = web_page.dashboard_page({})
    assert payload.count('class="rule-card"') == expected