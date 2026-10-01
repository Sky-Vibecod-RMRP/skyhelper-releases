"""Тесты модуля скриншотов: имена, папка недели, проверки и сервис.

Захват экрана и системная корзина в тестах подменяются — реальный монитор
и реальный `SHFileOperationW` тестировать нельзя.
"""
from __future__ import annotations

import threading
from datetime import date, datetime
from pathlib import Path

import pytest

from app.config import Config
from app.shots import trash, weeks
from app.shots.listener import category_problems, normalize
from app.shots.names import file_name, sanitize, unique_path
from app.shots.service import ShotsService


@pytest.fixture
def cfg(tmp_path) -> Config:
    """Конфигурация с корнем во временной папке (в проект не пишем)."""
    config = Config()
    config.shots_root = str(tmp_path / "shots")
    return config


class FakeSession:
    def __init__(self, duty: bool = True, game: bool = True) -> None:
        self.is_on_duty = duty
        self.is_game_running = game


class FakeWindow:
    def __init__(self, minimized: bool = False) -> None:
        self.minimized = minimized
        self.monitor = (0, 0, 100, 60)


def _image(color=(40, 90, 160), size=(100, 60)):
    from PIL import Image

    return Image.new("RGB", size, color)


# --- имена -----------------------------------------------------------------


def test_sanitize_replaces_only_forbidden_characters():
    # «/» мешает, пробелы и скобки — нет: папка должна читаться как на Диске
    assert sanitize("Захват/налёт (День)") == "Захват-налёт (День)"
    assert sanitize("Ограбы/поставки/КРАЗ/AirDrop (День)") == (
        "Ограбы-поставки-КРАЗ-AirDrop (День)"
    )


def test_sanitize_drops_trailing_dots_and_spaces():
    assert sanitize("  Наказания.  ") == "Наказания"


@pytest.mark.parametrize("name", ["CON", "con", "COM1", "LPT9", "NUL", "NUL.txt"])
def test_sanitize_survives_names_reserved_by_windows(name):
    # Без префикса mkdir на таких именах падает, и категория молча уезжала
    # бы в запасную папку с невнятным «нет прав».
    assert sanitize(name).startswith("_"), name
    assert sanitize(name) != name


def test_sanitize_leaves_ordinary_names_untouched():
    for name in ("Наказания (День)", "Ограбы-поставки-КРАЗ-AirDrop (День)"):
        assert sanitize(name) == name


def test_file_name_matches_the_agreed_format():
    assert (
        file_name(datetime(2026, 9, 30, 16, 42, 15), "Наказания (День)")
        == "2026-09-30_16-42-15_Наказания-День.jpg"
    )


def test_file_name_flattens_slashes():
    name = file_name(datetime(2026, 9, 30, 16, 42, 15), "Ограбы/поставки/КРАЗ/AirDrop (День)")
    assert "/" not in name and "\\" not in name
    assert name.endswith("Ограбы-поставки-КРАЗ-AirDrop-День.jpg")


def test_unique_path_never_overwrites(tmp_path):
    first = unique_path(tmp_path, "a.jpg")
    first.write_bytes(b"1")
    second = unique_path(tmp_path, "a.jpg")
    assert second != first and second.name == "a_1.jpg"
    second.write_bytes(b"2")
    assert first.read_bytes() == b"1", "старый файл должен остаться нетронутым"


# --- папка недели ----------------------------------------------------------


def test_week_is_monday_to_sunday():
    start, end = weeks.week_bounds(date(2026, 9, 30), 0)   # среда
    assert (start, end) == (date(2026, 9, 28), date(2026, 10, 4))
    assert start.weekday() == 0 and end.weekday() == 6


def test_week_respects_configurable_first_day():
    start, end = weeks.week_bounds(date(2026, 9, 30), 6)   # неделя с воскресенья
    assert start.weekday() == 6
    assert (end - start).days == 6


def test_week_title_matches_google_drive_format():
    title = weeks.week_title(date(2026, 9, 28), date(2026, 10, 4))
    assert title == "Отчёты ¦ Администратор ¦ 28.09.2026–04.10.2026"
    assert "\u2013" in title, "нужен длинный дефис, как на Google Диске"
    assert "|" not in title, "вертикальная черта запрещена в именах папок Windows"


def test_ensure_week_creates_all_category_folders_and_trash(cfg):
    made = weeks.ensure_week(cfg, cfg.shots_categories)
    assert made.is_dir()
    assert (made / weeks.TRASH_TITLE).is_dir()
    for cat in cfg.shots_categories:
        assert (made / sanitize(cat["name"])).is_dir(), cat["name"]
    assert len(list(made.iterdir())) == len(cfg.shots_categories) + 1


def test_ensure_week_is_idempotent(cfg):
    first = weeks.ensure_week(cfg, cfg.shots_categories)
    second = weeks.ensure_week(cfg, cfg.shots_categories)
    assert first == second
    assert len([p for p in first.parent.iterdir() if p.is_dir()]) == 1


def test_list_weeks_sorted_newest_first(cfg):
    weeks.ensure_week(cfg, cfg.shots_categories)
    assert weeks.list_weeks(cfg) == [weeks.week_folder(cfg).name]


# --- проверки списка категорий ---------------------------------------------

def test_default_categories_have_no_conflicts(cfg):
    reserved = [cfg.hotkey_add, cfg.hotkey_remove, cfg.hotkey_duty, cfg.hotkey_toggle]
    assert category_problems(cfg, cfg.shots_categories, reserved) == []
    assert len(cfg.shots_categories) == 8


def test_reserved_key_reports_what_it_is_bound_to(cfg):
    cats = [{"name": "Наказания (День)", "hotkey": "f9", "in_game": False}]
    problems = category_problems(cfg, cats, ["f9", "ctrl+f9", "f10", "insert"])
    assert len(problems) == 1
    assert "f9" in problems[0] and "+1 обращение" in problems[0]


def test_duplicate_key_names_the_other_category(cfg):
    cats = [
        {"name": "Первая", "hotkey": "f6", "in_game": False},
        {"name": "Вторая", "hotkey": "shift+f6", "in_game": False},
        {"name": "Третья", "hotkey": "F6", "in_game": False},
    ]
    problems = category_problems(cfg, cats, [])
    assert len(problems) == 1
    assert "Первая" in problems[0] and "Третья" in problems[0]


def test_missing_name_or_hotkey_is_reported(cfg):
    problems = category_problems(
        cfg, [{"name": "", "hotkey": "f6"}, {"name": "X", "hotkey": ""}], []
    )
    assert len(problems) == 2
    assert "не задано название" in problems[0]
    assert "не назначена клавиша" in problems[1]


def test_normalize_lowercases_and_trims():
    assert normalize("  Shift+F6 ") == "shift+f6"
    assert normalize("") == ""


def test_categories_that_share_a_folder_are_rejected(cfg):
    """«Захват/налёт (День)» и «Захват-налёт (День)» — одна папка на диске."""
    cats = [
        {"name": "Захват/налёт (День)", "hotkey": "f6"},
        {"name": "Захват-налёт (День)", "hotkey": "f7"},
    ]
    problems = category_problems(cfg, cats, [])
    assert len(problems) == 1
    assert "Захват-налёт (День)" in problems[0]


def test_name_that_becomes_nothing_is_rejected(cfg):
    problems = category_problems(cfg, [{"name": "..", "hotkey": "f6"}], [])
    assert len(problems) == 1
    assert "не получится папка" in problems[0]


# --- сервис: блокировки ----------------------------------------------------


def _service(cfg, session, *, window=None, grab=None, **kw) -> ShotsService:
    """Сервис с подставленным окном и захватом.

    ``grab`` — либо готовая «картинка», либо функция от монитора: так
    тесты пишут читаемо, а сервис всегда получает функцию.
    """
    options = dict(kw)
    options["window_finder"] = lambda _names: window
    if grab is not None:
        options["grabber"] = (
            (lambda _monitor, image=grab: image)
            if hasattr(grab, "convert")      # PIL-изображение
            else grab                        # уже функция монитора
        )
    return ShotsService(cfg, session, **options)


def test_shot_is_blocked_without_duty(cfg):
    results = []
    svc = _service(cfg, FakeSession(duty=False), window=FakeWindow(), grab=_image())
    svc.on_result = results.append
    result = svc.shoot("Наказания (День)")
    assert result.kind == "blocked" and not result.ok
    assert "дежурстве" in result.message
    assert results and results[0] is result


def test_shot_allowed_without_duty_when_toggle_is_on(cfg):
    cfg.shots_allow_no_duty = True
    svc = _service(cfg, FakeSession(duty=False), window=FakeWindow(), grab=_image())
    assert svc.shoot("Наказания (День)").kind == "saved"


def test_shot_is_blocked_when_game_is_closed(cfg):
    svc = _service(cfg, FakeSession(game=False), window=FakeWindow(), grab=_image())
    assert svc.shoot("Наказания (День)").message.endswith("игра не запущена")


def test_shot_is_blocked_when_window_is_minimized(cfg):
    svc = _service(cfg, FakeSession(), window=FakeWindow(minimized=True), grab=_image())
    assert "свёрнута" in svc.shoot("Наказания (День)").message


def test_shot_is_blocked_when_window_is_missing(cfg):
    svc = _service(cfg, FakeSession(), window=None, grab=_image())
    assert "окно игры не найдено" in svc.shoot("Наказания (День)").message


# --- сервис: удачный снимок -------------------------------------------------


def test_successful_shot_writes_named_file_into_week_folder(cfg, tmp_path):
    svc = _service(
        cfg, FakeSession(), window=FakeWindow(), grab=_image(),
        clock=lambda: datetime(2026, 9, 30, 16, 42, 15),
    )
    result = svc.shoot("Наказания (День)")
    assert result.kind == "saved" and result.ok
    expected = tmp_path / "shots" / weeks.week_title(
        date(2026, 9, 28), date(2026, 10, 4)
    ) / "Наказания (День)" / "2026-09-30_16-42-15_Наказания-День.jpg"
    assert expected.exists(), expected
    assert result.path == str(expected)


def test_second_shot_in_same_second_gets_suffix(cfg, tmp_path):
    clock = lambda: datetime(2026, 9, 30, 16, 42, 15)  # noqa: E731
    svc = _service(cfg, FakeSession(), window=FakeWindow(), grab=_image(), clock=clock)
    first = svc.shoot("Наказания (День)")
    second = svc.shoot("Наказания (День)")
    assert first.path != second.path
    assert second.path.endswith("_1.jpg")


def test_own_windows_are_hidden_only_around_the_grab(cfg):
    events: list[str] = []

    def grab(_monitor):
        events.append("grab")
        return _image()

    svc = _service(
        cfg, FakeSession(), window=FakeWindow(), grab=grab,
        hide_windows=lambda: events.append("hide"),
        show_windows=lambda: events.append("show"),
    )
    assert svc.shoot("Наказания (День)").ok
    assert events == ["hide", "grab", "show"]


def test_windows_returned_even_if_grab_fails(cfg):
    events: list[str] = []

    def boom(_monitor):
        raise RuntimeError("нет захвата")

    svc = _service(
        cfg, FakeSession(), window=FakeWindow(), grab=boom,
        hide_windows=lambda: events.append("hide"),
        show_windows=lambda: events.append("show"),
    )
    assert svc.shoot("Наказания (День)").kind == "blocked"
    assert events == ["hide", "show"], "окна обязаны вернуться в любом случае"


def test_black_frame_is_retried_then_reported(cfg):
    sleeps: list[float] = []
    svc = _service(
        cfg, FakeSession(), window=FakeWindow(),
        grab=lambda _m: _image(color=(0, 0, 0)),
        sleeper=sleeps.append,
    )
    result = svc.shoot("Наказания (День)")
    assert result.kind == "black"
    assert "чёрный" in result.message
    assert sleeps == [1.0], "ровно один повтор через секунду"


def test_black_frame_recovers_on_retry(cfg):
    frames = [_image(color=(0, 0, 0)), _image(color=(200, 120, 30))]
    svc = _service(
        cfg, FakeSession(), window=FakeWindow(),
        grab=lambda _m: frames.pop(0),
        sleeper=lambda _s: None,
    )
    assert svc.shoot("Наказания (День)").kind == "saved"


def test_in_game_key_adds_warning_but_saves(cfg):
    cfg.shots_categories[3]["in_game"] = True   # «Наказания (Ночь)»
    svc = _service(cfg, FakeSession(), window=FakeWindow(), grab=_image())
    result = svc.shoot("Наказания (Ночь)")
    assert result.ok, "снимок всё равно сохраняется"
    assert "занята в игре" in result.warning


def test_fallback_and_in_game_warnings_are_both_shown(cfg, tmp_path, monkeypatch):
    """Раньше второе предупреждение затирало первое — терялась половина причины."""
    def refuse(*_args, **_kwargs):
        raise OSError("нет прав")

    def spare(_config, name, now=None):
        folder = tmp_path / "Документы" / sanitize(name)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    monkeypatch.setattr(weeks, "category_folder", refuse)
    monkeypatch.setattr(weeks, "fallback_folder", spare)
    cfg.shots_categories[2]["in_game"] = True          # «Наказания (День)»

    svc = _service(cfg, FakeSession(), window=FakeWindow(), grab=_image())
    result = svc.shoot("Наказания (День)")

    assert result.ok and result.fallback
    assert "Документы" in result.warning
    assert "занята в игре" in result.warning


def test_press_while_previous_shot_is_running_is_not_silent(cfg):
    """Нажал вторую категорию во время съёмки — должен быть ответ, а не тишина."""
    started = threading.Event()
    gate = threading.Event()

    def slow_grab(_monitor):
        started.set()
        gate.wait(5)
        return _image()

    svc = _service(cfg, FakeSession(), window=FakeWindow(), grab=slow_grab)
    results: list = []
    svc.on_result = results.append

    worker = threading.Thread(
        target=lambda: svc.shoot("Наказания (День)"), daemon=True
    )
    worker.start()
    assert started.wait(5), "захват так и не начался"

    second = svc.shoot("Захват/налёт (День)")
    gate.set()
    worker.join(5)

    assert second.kind == "ignored"
    assert "ещё снимается" in second.message
    assert [r.kind for r in results] == ["ignored", "saved"]


def test_write_failure_falls_back_to_documents(cfg, monkeypatch, tmp_path):
    def refuse(*_args, **_kw):
        raise OSError("нет прав")

    monkeypatch.setattr(weeks, "category_folder", refuse)
    monkeypatch.setattr(weeks, "fallback_folder", refuse)
    svc = _service(cfg, FakeSession(), window=FakeWindow(), grab=_image())
    result = svc.shoot("Наказания (День)")
    assert result.kind == "write_fail" and not result.ok
    assert "не сохранён" in result.message


def test_new_week_folder_is_announced_once(cfg, monkeypatch):
    notices: list = []
    svc = _service(cfg, FakeSession(), window=FakeWindow(), grab=_image())
    svc.on_result = notices.append

    svc._ensure_week()
    assert notices == [], "самый первый запуск на чистой папке молчит"

    # Неделя переехала: подменяем «сегодня» так, чтобы папка стала новой.
    root = weeks.resolve_root(cfg)
    monkeypatch.setattr(
        weeks, "week_folder",
        lambda _cfg, now=None: root / "Отчёты ¦ Администратор ¦ 01.01.2099–07.01.2099",
    )
    svc._ensure_week()
    assert len(notices) == 1 and notices[0].kind == "week"
    assert "новой недели" in notices[0].message

    svc._ensure_week()
    assert len(notices) == 1, "повторно не досаждаем"


def test_startup_announces_week_that_changed_while_app_was_closed(cfg, monkeypatch):
    """Неделя сменилась, пока программу не было, — плашка и на старте."""
    weeks.ensure_week(cfg, cfg.shots_categories)          # прошлая неделя на диске
    root = weeks.resolve_root(cfg)
    monkeypatch.setattr(
        weeks, "week_folder",
        lambda _cfg, now=None: root / "Отчёты ¦ Администратор ¦ 01.01.2099–07.01.2099",
    )
    svc = _service(cfg, FakeSession(), window=FakeWindow(), grab=_image())
    notices: list = []
    svc.on_result = notices.append

    svc._ensure_week()                                    # так делает start()
    assert len(notices) == 1
    assert notices[0].kind == "week"
    assert notices[0].message.startswith("Создана папка новой недели")


# --- сайт: дерево и путь к картинке ---------------------------------------


def test_report_tree_lists_categories_and_files(cfg):
    svc = _service(cfg, FakeSession(), window=FakeWindow(), grab=_image(),
                   clock=lambda: datetime(2026, 9, 30, 16, 42, 15))
    svc.shoot("Наказания (День)")
    tree = svc.report_tree()
    assert tree["weeks"] and tree["selected"] == tree["current"]
    assert tree["total"] == 1
    entry = next(c for c in tree["categories"] if c["folder"] == "Наказания (День)")
    assert entry["name"] == "Наказания (День)"
    assert entry["files"][0]["name"] == "2026-09-30_16-42-15_Наказания-День.jpg"
    assert entry["files"][0]["url"].startswith("/shots/")
    assert "%D0%9D" in entry["files"][0]["url"] or "Наказания" in entry["files"][0]["url"]


def test_report_tree_of_unknown_week_falls_back_to_current(cfg):
    svc = _service(cfg, FakeSession(), window=FakeWindow(), grab=_image())
    svc._ensure_week(silent=True)
    tree = svc.report_tree("нет такой недели")
    assert tree["selected"] == tree["current"]


def test_resolve_file_accepts_real_picture_and_rejects_traversal(cfg):
    svc = _service(
        cfg, FakeSession(), window=FakeWindow(), grab=_image(),
        clock=lambda: datetime(2026, 9, 30, 16, 42, 15),
    )
    svc.shoot("Наказания (День)")
    week = svc.report_tree()["selected"]
    name = "2026-09-30_16-42-15_Наказания-День.jpg"

    assert svc.resolve_file(week, "Наказания (День)", name) is not None
    assert svc.resolve_file("..", "x", name) is None
    assert svc.resolve_file(week, "../..", name) is None
    assert svc.resolve_file(week, "Наказания (День)", "..\\..\\config.json") is None
    assert svc.resolve_file(week, "Наказания (День)", "shot.png") is None
    assert svc.resolve_file(week, "Наказания (День)", "нет.jpg") is None


# --- корзина ---------------------------------------------------------------


def test_removed_category_is_copied_to_trash_then_deleted(tmp_path, monkeypatch):
    source = tmp_path / "Наказания (День)"
    source.mkdir()
    (source / "a.jpg").write_bytes(b"jpeg")
    trash_dir = tmp_path / weeks.TRASH_TITLE

    monkeypatch.setattr(trash, "to_recycle_bin", lambda _path: False)
    backup = trash.remove_category(source, trash_dir)

    assert backup is not None and backup.is_dir()
    assert (backup / "a.jpg").read_bytes() == b"jpeg"
    assert not source.exists(), "оригинал должен уехать из недели"


def test_trash_backup_does_not_overwrite_previous_copy(tmp_path, monkeypatch):
    source = tmp_path / "Категория"
    source.mkdir()
    monkeypatch.setattr(trash, "to_recycle_bin", lambda _path: False)
    trash_dir = tmp_path / weeks.TRASH_TITLE

    first = trash.remove_category(source, trash_dir)
    source.mkdir()
    second = trash.remove_category(source, trash_dir)

    assert first != second and first.exists() and second.exists()


def test_remove_missing_folder_is_a_noop(tmp_path):
    assert trash.remove_category(tmp_path / "нет", tmp_path / "Корзина") is None
