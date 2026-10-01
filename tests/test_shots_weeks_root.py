"""Корень отчётов: выбор папки, права на запись, отсутствие гонок.

``resolve_root`` зовут сразу несколько потоков (сайт, служба недели,
сохранение настроек) — здесь проверяется, что они не сбивают друг другу.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from app.config import Config
from app.shots import weeks


def test_configured_root_wins(tmp_path):
    config = Config()
    configured = tmp_path / "мои скриншоты"
    config.shots_root = str(configured)

    assert weeks.resolve_root(config) == configured
    assert configured.is_dir(), "папка создаётся сразу при выборе"


def test_empty_setting_falls_back_to_program_folder(tmp_path, monkeypatch):
    config = Config()
    config.shots_root = ""
    home = tmp_path / "program"
    home.mkdir()

    monkeypatch.setattr(weeks, "program_dir", lambda: home)
    assert weeks.resolve_root(config) == home


def test_unwritable_configured_root_falls_back(tmp_path, monkeypatch):
    config = Config()
    blocked = tmp_path / "забит"
    blocked.write_text("это файл, а не папка", encoding="utf-8")
    config.shots_root = str(blocked)
    home = tmp_path / "program"
    home.mkdir()

    monkeypatch.setattr(weeks, "program_dir", lambda: home)
    assert weeks.resolve_root(config) == home


def test_resolve_root_survives_parallel_calls(tmp_path, caplog):
    """200 параллельных проверок: пробный файл не должен «съедаться»."""
    config = Config()
    config.shots_root = str(tmp_path / "root")

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda _i: weeks.resolve_root(config), range(200)))

    assert all(r == tmp_path / "root" for r in results), (
        "потоки поссорились из-за общего пробного файла"
    )
    assert not [r for r in caplog.records if "недоступн" in r.getMessage()]
    assert not list((tmp_path / "root").glob(".rmrp_shots_write_test*")), (
        "пробный файл должен убираться за собой"
    )


def test_no_probe_file_is_left_behind(tmp_path):
    config = Config()
    config.shots_root = str(tmp_path / "clean")
    weeks.resolve_root(config)
    weeks.resolve_root(config)
    assert [p.name for p in (tmp_path / "clean").iterdir()] == []


def test_week_title_uses_the_character_windows_allows():
    start, end = weeks.week_bounds(date(2026, 9, 30), 0)
    title = weeks.week_title(start, end)

    assert weeks.ROOT_TITLE in title
    assert "¦" in title and "|" not in title
    assert "–" in title, "разделитель дат — длинный дефис U+2013"
