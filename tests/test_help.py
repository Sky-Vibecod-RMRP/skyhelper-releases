"""Тесты общих данных хелпера: разделы инструкций и список правил RMRP.

Один и тот же контент показывают окно «Хелпер» в программе и вкладки
«Хелпер» / «Правила RMRP» на сайте — здесь проверяем сам источник.
"""
from __future__ import annotations

import json

from app.help import data


def _titles(query: str) -> list[str]:
    return [i["title"] for cat in data.filter_rules(query) for i in cat["items"]]


# --- правила ---------------------------------------------------------------


def test_rules_are_complete_and_real():
    """Ровно те 28 ссылок, что прислал пользователь, по трём категориям."""
    assert data.total_rules() == 28
    assert [c["category"] for c in data.RULES] == [
        "Общие правила проекта",
        "Правила криминальных организаций",
        "Правила государственных организаций",
    ]
    for cat in data.RULES:
        assert cat["items"], cat["category"]
        for item in cat["items"]:
            assert item["title"]
            assert item["url"].startswith("https://forum.rmrp.ru/threads/")


def test_search_finds_by_russian_word_forms():
    """«семьи» обязано найти «Правила семей» — ищем по основе слова."""
    assert _titles("допросы")[0] == "Правила допросов"      # совпадение в названии — первое
    assert _titles("семьи")[0] == "Правила семей"
    assert _titles("рынок")[0] == "Правила использования маркетплейса «Blueberries»"
    assert _titles("абракадабра") == []

    war = _titles("война")
    assert war[0] == "Правила войны за КрАЗ"  # категории отсортированы по лучшему совпадению
    assert {t for t in war if t.startswith("Правила войны")} == {
        "Правила войны", "Правила войны за КрАЗ", "Правила войны за бизнес",
        "Правила войны за AirDrop", "Правила войны за территории",
    }

    gov = _titles("государственных")
    assert gov[0] == "Основные правила государственных организаций"
    assert "Титульные районы государственных организаций" in gov


def test_search_reaches_into_rule_text():
    """Ищем и по тексту правила: «60 минут» и «не должен длиться» находят допросы."""
    assert "Правила допросов" in _titles("60 минут")
    assert _titles("не должен длиться")[0] in {
        "Правила допросов", "Правила рейдов", "Правила войны",
        "Правила криминальных событий", "Правила семей", "Правила и обязанности лидеров",
    }

    # Короткое «ко» в текст не лезет: иначе нашло бы всё подряд.
    assert "Правила ограблений игроков" not in _titles("ко")


def test_rank_puts_title_matches_before_text_matches():
    """Заголовок важнее текста: «допросы» — сначала «Правила допросов»."""
    titles = _titles("допросы")
    first_block = titles[: titles.index("Правила допросов") + 1]
    assert first_block[0] == "Правила допросов" or "Правила допросов" in first_block
    assert data.match_rank(
        {"title": "Правила допросов", "url": "x"}, "Категория", "допросы"
    ) == 1
    # Совпадение только в тексте — третий ранг, а не мимо.
    item = {"title": "Чужое правило", "url": "https://forum.rmrp.ru/threads/z.1/"}
    assert data.match_rank(item, "Категория", "60 минут") in (None, 3)


def test_short_query_matches_only_word_starts():
    """«ко» находит «ко организации», но не «игроков» (середина слова)."""
    found = _titles("ко")
    assert "Правила ограблений игроков" not in found
    assert "Основные правила криминальных организаций" in found


def test_highlight_escapes_html_and_marks_the_whole_word():
    marked = data.highlight("Правила войны за КрАЗ", "война")
    assert "<span" in marked and "войны" in marked   # подсвечено слово целиком
    assert data.highlight("Правила войны", "") == "Правила войны"

    evil = data.highlight("<script>alert(1)</script>", "alert")
    assert "<script>" not in evil and "&lt;script&gt;" in evil


def test_local_rules_file_replaces_builtin(tmp_path):
    """%APPDATA%\\SKYHELPER\\rules.json правится без пересборки."""
    good = tmp_path / "rules.json"
    good.write_text(json.dumps([
        {"category": "Свои правила",
         "items": [{"title": "Свое правило",
                    "url": "https://forum.rmrp.ru/threads/x.1/"}]},
    ]), encoding="utf-8")
    loaded = data.load_rules(good)
    assert data.total_rules(loaded) == 1
    assert loaded[0]["category"] == "Свои правила"

    broken = tmp_path / "broken.json"
    broken.write_text("это не json", encoding="utf-8")
    assert data.load_rules(broken) == data.RULES

    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    assert data.load_rules(empty) == data.RULES


# --- разделы ---------------------------------------------------------------


def test_every_section_has_content():
    assert len(data.SECTIONS) == 6
    ids = [s["id"] for s in data.SECTIONS]
    assert ids == ["excel", "png", "site", "duty", "trouble", "paths"]
    for section in data.SECTIONS:
        assert section["title"] and section["color"] and section["blocks"]
        assert data.section_html(section)


def test_output_dir_is_substituted_or_replaced_by_hint():
    paths = next(s for s in data.SECTIONS if s["id"] == "paths")

    filled = data.section_html(paths, output_dir=r"C:\Users\Арсюша\Desktop\Отчёты")
    assert r"C:\Users\Арсюша\Desktop\Отчёты" in filled
    assert data.OUTPUT_DIR_TOKEN not in filled

    fallback = data.section_html(paths, output_dir="")
    assert data.OUTPUT_DIR_FALLBACK in fallback


def test_texts_are_escaped():
    """Данные не могут сломать разметку ни в окне, ни на сайте."""
    section = {"title": "x", "color": "#00d1ff",
               "blocks": [{"t": "p", "text": "<b>жирный</b> & опасный"}]}
    out = data.section_html(section)
    assert "&lt;b&gt;" in out and "<b>жирный</b>" not in out


# --- рендер для сайта ------------------------------------------------------


def test_web_rules_markup_carries_search_data():
    markup = data.rules_html(web=True)
    assert markup.count('data-k="') == 28
    assert markup.count('data-t="') == 28
    assert markup.count('data-x="') == 28      # сырой текст правила для клиентского поиска
    assert markup.count("https://forum.rmrp.ru/threads/") == 28

    filtered = data.rules_html(query="допросы")
    assert "pravila-doprosov" in filtered
    # Совпадение в заголовке идёт выше совпадений «только в тексте».
    assert filtered.index("pravila-doprosov") < filtered.index("pravila-semej")
    # Сниппет показывает место совпадения в тексте правила.
    assert "допрос" in filtered.lower()
