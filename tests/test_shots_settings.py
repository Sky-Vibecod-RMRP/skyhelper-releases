"""Тесты вкладки «Скриншоты» экрана настроек."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # без экрана и без окон

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QTabWidget  # noqa: E402

from app.config import Config  # noqa: E402
from app.ui.settings_dialog import HotkeyEdit, SettingsDialog  # noqa: E402


class FakeCore:
    """Ядро-заглушка: экран настроек трогает только config и apply_config."""

    def __init__(self) -> None:
        self.config = Config()
        self.web_running = False
        self.web_error = ""
        self.site_url = None
        self.apply_calls = 0

    def apply_config(self) -> None:
        self.apply_calls += 1


@pytest.fixture(scope="session")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def core():
    return FakeCore()


@pytest.fixture
def warnings(monkeypatch):
    """Перехватываем QMessageBox.warning: без этого тест зависнет в диалоге."""
    captured: list[str] = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: captured.append(str(args[-1]))
    )
    return captured


@pytest.fixture
def dialog(qapp, core, warnings):
    box = SettingsDialog(core)
    yield box
    box.close()


def _press(edit: HotkeyEdit, key, modifiers=Qt.KeyboardModifier.NoModifier, text=""):
    edit.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text))


# --- наличие вкладки и строк категорий -------------------------------------


def test_dialog_has_shots_tab(dialog):
    tabs = dialog.findChild(QTabWidget)
    assert tabs is not None
    labels = [tabs.tabText(i) for i in range(tabs.count())]
    assert "Скриншоты" in labels


def test_eight_default_categories_are_shown(dialog):
    assert len(dialog._shot_rows) == 8
    assert dialog._shot_rows[0]["name"].text() == "Захват/налёт (День)"
    assert dialog._shot_rows[0]["hotkey"].text() == "f6"
    assert dialog._shot_rows[7]["name"].text() == "Помощь в проведении МП"
    assert dialog._shot_rows[7]["hotkey"].text() == "shift+f8"


def test_add_and_remove_category_rows(dialog):
    dialog._add_shot_row("Новая категория", "f5", False)
    assert len(dialog._shot_rows) == 9
    assert dialog._shot_rows[-1]["name"].text() == "Новая категория"

    dialog._remove_shot_row(1)          # убираем первую
    assert len(dialog._shot_rows) == 8
    assert dialog._shot_rows[0]["name"].text() == "Захват/налёт (Ночь)"


def test_delete_button_targets_its_own_row_after_renumbering(dialog):
    names = [row["name"].text() for row in dialog._shot_rows]
    dialog._remove_shot_row(1)                       # ушли «Захват/налёт (День)»
    dialog._shot_rows[1]["remove"].click()           # после перенумерации это names[2]
    left = [row["name"].text() for row in dialog._shot_rows]
    assert left == [n for n in names if n not in (names[0], names[2])]


# --- сохранение и конфликты -------------------------------------------------


def test_reserved_hotkey_blocks_save_and_says_what_it_means(dialog, core, warnings):
    dialog._shot_rows[0]["hotkey"].setText("f10")     # это дежурство
    assert dialog._collect() is False
    assert warnings, "пользователь должен увидеть причину"
    assert "f10" in warnings[-1] and "дежурство" in warnings[-1]
    # apply_config вызывается только после успешной проверки
    assert core.apply_calls == 0


def test_duplicate_hotkey_blocks_save(dialog, warnings):
    dialog._shot_rows[1]["hotkey"].setText("f6")      # уже у первой строки
    assert dialog._collect() is False
    assert "используется" in warnings[-1]


def test_new_category_without_hotkey_blocks_save(dialog, warnings):
    dialog._add_shot_row("Без клавиши", "", False)
    assert dialog._collect() is False
    assert "не назначена клавиша" in warnings[-1]


def test_valid_categories_are_written_to_config(dialog, core):
    dialog._shot_rows[2]["hotkey"].setText("ctrl+f6")
    dialog._shot_rows[3]["in_game"].setChecked(True)
    assert dialog._collect() is True
    assert core.config.shots_categories[2]["hotkey"] == "ctrl+f6"
    assert core.config.shots_categories[3]["in_game"] is True
    assert len(core.config.shots_categories) == 8


def test_shots_options_roundtrip(dialog, core, tmp_path):
    dialog._shots_root.setText(str(tmp_path / "pic"))
    dialog._shots_no_duty.setChecked(True)
    dialog._shots_sound.setChecked(False)
    assert dialog._collect() is True
    assert core.config.shots_root == str(tmp_path / "pic")
    assert core.config.shots_allow_no_duty is True
    assert core.config.shots_sound is False


def test_collect_without_validation_never_blocks(dialog):
    """«Открыть сайт» сохраняет молча — проверка включается только по «Сохранить»."""
    dialog._shot_rows[0]["hotkey"].setText("f9")
    assert dialog._collect(validate=False) is True


# --- поле назначения клавиши -----------------------------------------------


def test_hotkey_edit_captures_function_key_with_modifier(qapp):
    edit = HotkeyEdit()
    _press(edit, Qt.Key.Key_F6, Qt.KeyboardModifier.ShiftModifier)
    assert edit.text() == "shift+f6"


def test_hotkey_edit_captures_plain_letter(qapp):
    edit = HotkeyEdit()
    _press(edit, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier, "r")
    assert edit.text() == "ctrl+r"


def test_hotkey_edit_ignores_bare_modifier(qapp):
    edit = HotkeyEdit()
    _press(edit, Qt.Key.Key_Shift, Qt.KeyboardModifier.ShiftModifier)
    assert edit.text() == ""


def test_hotkey_edit_backspace_clears(qapp):
    edit = HotkeyEdit()
    _press(edit, Qt.Key.Key_F6)
    assert edit.text() == "f6"
    _press(edit, Qt.Key.Key_Backspace)
    assert edit.text() == ""


def test_hotkey_edit_ignores_unmapped_key(qapp):
    edit = HotkeyEdit()
    edit.setText("f6")
    _press(edit, Qt.Key.Key_F13)
    assert edit.text() == "f6", "нераспознанная клавиша не должна затирать бинд"


def test_hotkey_edit_uses_physical_key_not_layout(qapp):
    """Русская раскладка: клавиша «ф» должна дать бинд f, а не «ф»."""
    edit = HotkeyEdit()
    _press(edit, Qt.Key.Key_F, Qt.KeyboardModifier.ShiftModifier, "А")
    assert edit.text() == "shift+f"


def test_hotkey_edit_accepts_digits(qapp):
    edit = HotkeyEdit()
    _press(edit, Qt.Key.Key_7, Qt.KeyboardModifier.ControlModifier, "7")
    assert edit.text() == "ctrl+7"
