"""Тесты правок по баг-репорту SKY HELPER UPDATE.

Каждый тест подписан номером бага из отчёта — чтобы было видно, что именно
 закрыто, и ничего не «починилось случайно».
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.hotkeys.listener import HotkeyListener
from app.player import data as player_data
from app.web.page import dashboard_page

#: Лог, повторяющий настоящий cef_game_logs.txt (все нужные куски).
_PHONE = {
    "id": 958726, "rank": 70, "factionId": "belozerski",
    "firstName": "Артур", "lastName": "Соколов", "staff": "admin_plus",
    "socialClubId": "272398236", "familyFactionId": "family20332",
    "familyRank": 1, "playtime": 3100835, "health": 15, "armour": 0,
    "posX": 1573.27, "posY": 2192.65, "posZ": 165.699,
    "createdAt": "2025-06-28T11:16:40.000Z", "registredAt": "2025-06-28T11:19:07.000Z",
}
_CHAT = {
    "user": {"id": 958726, "factionId": "belozerski", "staff": "admin_plus",
             "familyFactionId": "family20332"},
    "userFactionGameObjectId": "Белозерские",
    "number": 79153338684,
    "familyProfessions": [
        {"rank": 1, "name": "Администратор", "group": "family20332"},
        {"rank": 2, "name": "ГА", "group": "family20332"},
        {"rank": 5, "name": "ПГК НР", "group": "family20332"},
    ],
}


def _write_log(tmp_path) -> str:
    path = tmp_path / "cef_game_logs.txt"
    path.write_text(
        "[0929/092722.123:45] Phone start with: " + json.dumps(_PHONE, ensure_ascii=False) + "\n"
        "[0929/092722.124:00] Start opening chat: " + json.dumps(_CHAT, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return str(path)


# --- баг №5: ранг в семье словом, а не цифрой ------------------------------


def test_family_rank_is_shown_as_name_not_number(tmp_path):
    data = player_data.parse(_write_log(tmp_path))
    assert data["family_rank"] == 1                      # номер в логе не изменился
    assert data["family_rank_name"] == "Администратор"  # а показываем слово


def test_family_rank_name_handles_missing_and_broken_data():
    assert player_data.family_rank_name({}, 3) == ""
    assert player_data.family_rank_name({"familyProfessions": []}, 0) == ""
    broken = {"familyProfessions": [{"rank": "не число", "name": "x"}]}
    assert player_data.family_rank_name(broken, 1) == ""


def test_player_panel_shows_rank_name_and_uses_table(tmp_path, monkeypatch):
    monkeypatch.setattr(player_data, "LOG_PATH", Path(_write_log(tmp_path)))
    html = player_data.panel_html()
    # подпись и значение не могут наехать друг на друга только в таблице
    assert "<table" in html and "<tr><td" in html
    # строки полей больше не на flex — именно он наезжал на подпись
    assert "display:flex;gap:14px" not in html
    assert "min-width:170px" not in html


def test_display_value_prefers_name_but_keeps_id():
    data = {"family": "family20332", "family_name": "",
            "family_rank": 1, "family_rank_name": "ГА"}
    assert player_data._display_value("family_rank", data) == "ГА"
    assert player_data._display_value("family", data) == "family20332"
    data["family_name"] = "ПГК НР"
    assert player_data._display_value("family", data) == "ПГК НР"


# --- баг №3: заголовок окна -------------------------------------------------


def test_main_window_is_titled_sky_helper():
    """После объединения окон главное окно одно — и называется SKY HELPER."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from app.ui.helper_window import HelperWindow

    app = QApplication.instance() or QApplication([])
    window = HelperWindow()
    try:
        assert window.windowTitle().startswith("SKY HELPER")
    finally:
        window.close()


# --- предложение №1: одно окно вместо двух --------------------------------


def test_second_window_module_is_gone():
    """Главного окна больше нет: статистика стала разделом «Главная»."""
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.ui.main_window")


def test_single_window_has_home_section_and_duty_in_menu():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from app.ui.helper_window import HelperWindow

    app = QApplication.instance() or QApplication([])
    window = HelperWindow()          # без ядра — «Главная» не строится
    try:
        assert hasattr(window, "_show_home")
        assert window.home_row is None, "без ядра раздела «Главная» быть не должно"
        assert window._duty is not None
        assert not window._duty.isVisible(), "без ядра кнопка дежурства скрыта"
    finally:
        window.close()


def test_gui_main_creates_exactly_one_window():
    import inspect

    import app.gui_main as gui_main

    source = inspect.getsource(gui_main.main)
    assert "MainWindow" not in source, "второе окно не должно создаваться"
    assert "HelperWindow" in source
    assert "core=core" in source, "окно должно получать ядро для раздела «Главная»"


# --- баг №4: Insert не должен доходить до игры ------------------------------


class _FakeKeyboard:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def add_hotkey(self, key, callback, suppress=False, **_kwargs):
        self.calls.append((key, suppress))
        return f"h-{key}"

    def remove_hotkey(self, handle) -> None:
        pass


def test_window_toggle_hotkey_is_suppressed_but_others_are_not(monkeypatch):
    fake = _FakeKeyboard()
    monkeypatch.setitem(sys.modules, "keyboard", fake)
    listener = HotkeyListener(
        "f9", "ctrl+f9", lambda: None, lambda: None, "f10", lambda: None,
        toggle_key="insert", on_toggle=lambda: None,
    )
    listener.start()
    listener.stop()

    by_key = dict(fake.calls)
    assert by_key["insert"] is True, "Insert не должен доходить до игры/лаунчера"
    assert by_key["f9"] is False, "+1 игра должна видеть"
    assert by_key["f10"] is False, "дежурство игра должна видеть"


# --- баг №2: белая рамка Windows вокруг окна -------------------------------


def test_frameless_windows_are_translucent():
    """FramelessWindowHint сам по себе оставляет белую полосу по краю."""
    pytest.importorskip("PySide6")
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QWidget

    from app.ui.frameless import FramelessMixin

    app = QApplication.instance() or QApplication([])

    class _Win(FramelessMixin, QWidget):
        def __init__(self) -> None:
            QWidget.__init__(self)
            self.init_frameless("проверка")

    win = _Win()
    try:
        assert win.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground) is True
        assert win.windowFlags() & Qt.WindowType.FramelessWindowHint
    finally:
        win.close()


# --- баг №6: один курсор, а не два ------------------------------------------


def test_page_has_no_bitmap_cursor_and_hides_native_one():
    page = dashboard_page({})
    # битмап-курсор больше не подмешивается к нарисованному
    assert "cursors/cursor.png" not in page
    # системный курсор прячется только когда скрипт точно загрузился
    assert "sky-cursor-on" in page
    assert "document.documentElement.classList.add('sky-cursor-on')" in page


# --- баг №1: карточки правил не слипаются в окне ----------------------------


def test_rules_html_for_window_has_no_flexbox():
    from app.help import data as help_data

    html = help_data.rules_html({}, "")
    assert "display:flex" not in html, "QTextBrowser игнорирует flex — карточки слипались"
    assert html.count("margin:0 0 8px 0") >= 1, "у карточек должен быть отступ снизу"
