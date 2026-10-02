"""Экран настроек: всё важное в одном окне, без правки config.json руками."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from app.config import CURSOR_STYLES
from app.core import Core
from app.hotkeys.listener import bind_problem
from app.paths import default_google_key_path, default_output_dir, program_dir
from app.shots.listener import category_problems
from app.ui import sounds, theme
from app.ui.frameless import FramelessMixin

_WEEKDAYS_RU = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
_PLACEHOLDER = "•" * 8

# Что считать «не клавишей» в поле назначения бинда.
_MODIFIER_KEYS = {
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
}
_F_FIRST = Qt.Key.Key_F1
_F_LAST = Qt.Key.Key_F12
_A_FIRST = Qt.Key.Key_A
_A_LAST = Qt.Key.Key_Z
_0_FIRST = Qt.Key.Key_0
_9_LAST = Qt.Key.Key_9
_KEY_BACKSPACE = Qt.Key.Key_Backspace
_KEY_DELETE = Qt.Key.Key_Delete


def _field() -> QLineEdit:
    edit = QLineEdit()
    edit.setMinimumWidth(260)
    return edit


# Специальные клавиши, которые понимает слушатель keyboard.
_QT_KEY_NAMES = {
    "Insert": "insert", "Delete": "delete", "Home": "home", "End": "end",
    "PageUp": "pageup", "PageDown": "pagedown", "Esc": "esc", "Tab": "tab",
    "Space": "space", "Up": "up", "Down": "down", "Left": "left", "Right": "right",
}


class HotkeyEdit(QLineEdit):
    """Поле, куда не печатают, а **нажимают** клавишу.

    Клик — и ждём: следующее нажатие (с модификатором) становится значением,
    например «shift+f6». Backspace/Delete чистят поле.
    """

    def keyPressEvent(self, event) -> None:  # noqa: N802 (имя из Qt)
        key = event.key()
        if key in _MODIFIER_KEYS:
            return                              # модификатор сам по себе — не клавиша
        if key in (_KEY_BACKSPACE, _KEY_DELETE):
            self.clear()
            event.accept()
            return
        name = self._key_name(event)
        if not name:
            event.ignore()
            return
        mods = []
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            mods.append("ctrl")
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            mods.append("alt")
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            mods.append("shift")
        self.setText("+".join(mods + [name]).lower())
        event.accept()

    @staticmethod
    def _key_name(event) -> str:
        key = event.key()
        if _F_FIRST <= key <= _F_LAST:
            return f"f{key - _F_FIRST + 1}"
        for attr, name in _QT_KEY_NAMES.items():
            if key == getattr(Qt.Key, f"Key_{attr}", None):
                return name
        # Буквы и цифры — по коду клавиши, а не по event.text(): с русской
        # раскладкой text() вернёт «ф», а бинд должен быть «f».
        if _A_FIRST <= key <= _A_LAST:
            return chr(ord("a") + (key - _A_FIRST))
        if _0_FIRST <= key <= _9_LAST:
            return chr(ord("0") + (key - _0_FIRST))
        return ""


def _hotkey_field(value: str, placeholder: str = "нажми клавишу") -> HotkeyEdit:
    """Поле бинда в «Дежурство, клавиши и нормы»: только нажатие клавиши.

    Раньше здесь стояло обычное текстовое поле (жалоба 02.10.2026): в него
    набирали «zcsda»/«numpad0», и сохранение падало в keyboard.add_hotkey.
    """
    edit = HotkeyEdit()
    edit.setMinimumWidth(260)
    edit.setText(value)
    edit.setPlaceholderText(placeholder)
    # Контекстное меню отключено: вставить текст мышью нельзя,
    # бинд получается только настоящим нажатием клавиши.
    edit.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
    edit.setToolTip(
        "Нажми на поле, а затем на нужную клавишу. Backspace — очистить."
    )
    return edit


class SettingsDialog(FramelessMixin, QDialog):
    """Читает текущие значения из core.config, при сохранении пишет их обратно."""

    def __init__(self, core: Core, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._core = core
        cfg = core.config
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(560)

        tabs = QTabWidget()
        tabs.addTab(self._tab_general(), "Основное")
        tabs.addTab(self._tab_reports(), "Отчёты")
        tabs.addTab(self._tab_web(), "Сайт")
        tabs.addTab(self._tab_google(), "Google")
        tabs.addTab(self._tab_look(), "Вид и звуки")
        tabs.addTab(self._tab_shots(), "Скриншоты")
        tabs.addTab(self._tab_license(), "Лицензия")

        buttons = QDialogButtonBox()
        self._save = buttons.addButton("Сохранить", QDialogButtonBox.ButtonRole.AcceptRole)
        self._save.setObjectName("primary")
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 12)
        layout.setSpacing(12)
        layout.addWidget(self.init_frameless("Настройки"))
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # --- вкладки ---

    def _section(self, title: str, hint: str = "") -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(6)
        label = QLabel(title)
        label.setObjectName("section")
        box.addWidget(label)
        if hint:
            note = QLabel(hint)
            note.setObjectName("hint")
            note.setWordWrap(True)
            box.addWidget(note)
        return box

    def _tab_general(self) -> QWidget:
        cfg = self._core.config
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(self._section(
            "Дежурство, клавиши и нормы",
            "F10 включает и выключает дежурство; без него онлайн не считается. "
            "Клавиша показа окна сворачивает и разворачивает программу поверх игры.",
        ))
        form = QFormLayout()
        form.setSpacing(10)

        self._require_duty = QCheckBox(
            "Обязательное дежурство: онлайн считается только после F10"
        )
        self._require_duty.setChecked(cfg.require_duty)
        self._auto_off = QCheckBox("Выключать дежурство, когда игра закрыта")
        self._auto_off.setChecked(cfg.duty_auto_off_on_game_close)
        self._count_in_game = QCheckBox("Засчитывать нажатия только при запущенной игре")
        self._count_in_game.setChecked(cfg.count_only_in_game)

        self._key_add = _hotkey_field(cfg.hotkey_add)
        self._key_remove = _hotkey_field(cfg.hotkey_remove)
        self._key_duty = _hotkey_field(cfg.hotkey_duty)
        # Пусто = клавиша показа окна выключена.
        self._key_toggle = _hotkey_field(
            cfg.hotkey_toggle, "напр. insert (пусто = выключить)"
        )

        self._on_top = QCheckBox("Держать окно поверх игры (поверх других окон)")
        self._on_top.setChecked(cfg.window_on_top)

        self._hours_norm = QDoubleSpinBox()
        self._hours_norm.setRange(0, 1000)
        self._hours_norm.setSingleStep(0.5)
        self._hours_norm.setDecimals(1)
        self._hours_norm.setSuffix(" ч")
        self._hours_norm.setValue(cfg.weekly_hours_norm)

        self._reports_norm = QSpinBox()
        self._reports_norm.setRange(0, 100000)
        self._reports_norm.setValue(cfg.weekly_reports_norm)

        self._week_start = QComboBox()
        self._week_start.addItems(_WEEKDAYS_RU)
        self._week_start.setCurrentIndex(cfg.week_start_weekday)

        self._processes = _field()
        self._processes.setText(", ".join(cfg.game_processes))

        form.addRow(self._require_duty)
        form.addRow(self._auto_off)
        form.addRow(self._count_in_game)
        form.addRow("Клавиша +1 обращение", self._key_add)
        form.addRow("Клавиша −1 обращение", self._key_remove)
        form.addRow("Клавиша дежурства", self._key_duty)
        form.addRow("Клавиша показа окна", self._key_toggle)
        form.addRow(self._on_top)
        form.addRow("Норма часов в неделю", self._hours_norm)
        form.addRow("Норма обращений в неделю", self._reports_norm)
        form.addRow("Неделя начинается", self._week_start)
        form.addRow("Процесс игры (через запятую)", self._processes)

        layout.addLayout(form)
        layout.addStretch()
        return page

    def _tab_reports(self) -> QWidget:
        cfg = self._core.config
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(10)

        self._out_dir = _field()
        self._out_dir.setText(cfg.output_dir)
        self._out_dir.setPlaceholderText(str(default_output_dir()))
        browse_out = QPushButton("Обзор…")
        browse_out.clicked.connect(self._pick_output_dir)
        row_out = QHBoxLayout()
        row_out.addWidget(self._out_dir, 1)
        row_out.addWidget(browse_out)

        self._interval = QSpinBox()
        self._interval.setRange(1, 24 * 60)
        self._interval.setSuffix(" мин")
        self._interval.setValue(int(cfg.export_interval_min))

        self._archive = QCheckBox("Каждую неделю копировать PNG в папку «История»")
        self._archive.setChecked(cfg.archive_weekly)

        form.addRow("Папка отчётов", row_out)
        form.addRow("Обновлять отчёты раз в", self._interval)
        form.addRow(self._archive)

        note = QLabel("Пустое поле = папка «Документы\\SKY HELPER».")
        note.setObjectName("hint")
        note.setWordWrap(True)
        form.addRow(note)
        return page

    def _tab_web(self) -> QWidget:
        cfg = self._core.config
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(10)

        self._web_on = QCheckBox("Включить локальный сайт с живыми цифрами")
        self._web_on.setChecked(cfg.web_enabled)
        self._web_lan = QCheckBox("Разрешить доступ с телефона (та же Wi-Fi сеть)")
        self._web_lan.setChecked(cfg.web_host == "0.0.0.0")
        self._web_lan.setEnabled(cfg.web_enabled)
        self._web_on.toggled.connect(self._web_lan.setEnabled)

        self._web_port = QSpinBox()
        self._web_port.setRange(1, 65535)
        self._web_port.setValue(cfg.web_port)

        self._pin = _field()
        self._pin.setEchoMode(QLineEdit.EchoMode.Password)
        self._pin.setPlaceholderText(_PLACEHOLDER)
        self._pin.setMaxLength(32)
        self._pin_hint = QLabel()
        self._pin_hint.setObjectName("hint")
        self._pin_hint.setWordWrap(True)
        clear_pin = QPushButton("Снять код")
        clear_pin.clicked.connect(self._clear_pin)
        self._pin_cleared = False
        self._update_pin_hint()

        self._open_site = QPushButton("Открыть сайт")
        self._open_site.clicked.connect(self._open_site_now)
        self._site_state = QLabel()
        self._site_state.setObjectName("hint")
        self._site_state.setWordWrap(True)
        self._phone_hint = QLabel()
        self._phone_hint.setObjectName("section")
        self._phone_hint.setWordWrap(True)
        self._web_lan.toggled.connect(lambda _on: self._refresh_site_state())
        self._web_port.valueChanged.connect(lambda _value: self._refresh_site_state())

        form.addRow(self._web_on)
        form.addRow(self._web_lan)
        form.addRow("Порт", self._web_port)
        form.addRow("Код доступа", self._pin)
        form.addRow(self._pin_hint)
        row_pin = QHBoxLayout()
        row_pin.addWidget(clear_pin)
        row_pin.addStretch()
        form.addRow(row_pin)
        form.addRow(self._phone_hint)
        form.addRow(self._open_site)
        form.addRow(self._site_state)
        self._refresh_site_state()
        return page

    def _tab_google(self) -> QWidget:
        cfg = self._core.config
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(10)

        self._gsheet_id = _field()
        self._gsheet_id.setText(cfg.gsheet_id)
        self._gsheet_id.setPlaceholderText("пусто = выключено")
        self._gsheet_key = _field()
        self._gsheet_key.setText(cfg.gsheet_credentials)
        self._gsheet_key.setPlaceholderText(str(default_google_key_path()))
        browse_key = QPushButton("Обзор…")
        browse_key.clicked.connect(self._pick_google_key)
        row_key = QHBoxLayout()
        row_key.addWidget(self._gsheet_key, 1)
        row_key.addWidget(browse_key)

        form.addRow("ID Google Таблицы", self._gsheet_id)
        form.addRow("JSON-ключ сервисного аккаунта", row_key)
        note = QLabel(
            "ID берётся из адреса таблицы: docs.google.com/spreadsheets/d/<ID>/edit. "
            "Оставь пустым, чтобы Google Таблицу не обновлять."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        form.addRow(note)
        return page

    def _tab_look(self) -> QWidget:
        cfg = self._core.config
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(10)

        self._ui_theme = QComboBox()
        for key, meta in theme.THEMES.items():
            self._ui_theme.addItem(meta["label"], key)
        self._ui_theme.setCurrentIndex(
            max(0, list(theme.THEMES).index(cfg.ui_theme))
            if cfg.ui_theme in theme.THEMES else 0
        )

        self._sound_theme = QComboBox()
        for key, label in sounds.THEMES.items():
            self._sound_theme.addItem(label, key)
        self._sound_theme.setCurrentIndex(
            max(0, list(sounds.THEMES).index(cfg.sound_theme))
            if cfg.sound_theme in sounds.THEMES else 0
        )
        test_sound = QPushButton("Проверить звук")
        test_sound.clicked.connect(
            lambda: sounds.play(self._sound_theme.currentData(), "success")
        )
        row_sound = QHBoxLayout()
        row_sound.addWidget(self._sound_theme, 1)
        row_sound.addWidget(test_sound)

        streak_note = QLabel(
            "Стрик считается автоматически: день выполнен, если набраны и часы, "
            "и обращения по дневному плану (недельная норма / 7)."
        )
        streak_note.setObjectName("hint")
        streak_note.setWordWrap(True)

        # --- оформление сайта ---
        self._rain = QCheckBox("Дождь на фоне сайта и в окне")
        self._rain.setChecked(cfg.rain_enabled)
        self._rain.setToolTip(
            "Тонкие наклонные линии на фоне: на сайте и поверх окна программы. "
            "Если в системе включено «уменьшить анимацию», дождь всё равно не "
            "рисуется."
        )

        self._cursor = QComboBox()
        for key, label in CURSOR_STYLES.items():
            self._cursor.addItem(label, key)
        if cfg.cursor_style not in CURSOR_STYLES:
            cfg.cursor_style = "white"
        self._cursor.setCurrentIndex(
            max(0, list(CURSOR_STYLES).index(cfg.cursor_style))
        )

        site_note = QLabel(
            "Дождь и курсор одинаковы на сайте sky-grafana.rmrp и в окне "
            "программы: тот же рисунок и та же настройка."
        )
        site_note.setObjectName("hint")
        site_note.setWordWrap(True)

        form.addRow("Тема интерфейса", self._ui_theme)
        form.addRow("Звуки уведомлений", row_sound)
        form.addRow(streak_note)
        form.addRow("Дождь", self._rain)
        form.addRow("Курсор", self._cursor)
        form.addRow(site_note)
        return page

    def _tab_shots(self) -> QWidget:
        """Скриншоты для еженедельного отчёта: папка, категории, клавиши."""
        cfg = self._core.config
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addLayout(self._section(
            "Скриншоты недельного отчёта",
            "Папка недели создаётся сама: «Отчёты ¦ Администратор ¦ 28.09.2026–04.10.2026», "
            "внутри — по папке на каждую категорию. Клавиша категории работает только "
            "при развёрнутом окне игры (и, если не отмечено ниже, — только на дежурстве).",
        ))

        form = QFormLayout()
        form.setSpacing(10)

        self._shots_root = _field()
        self._shots_root.setText(cfg.shots_root)
        self._shots_root.setPlaceholderText(str(program_dir()))
        browse_root = QPushButton("Обзор…")
        browse_root.clicked.connect(self._pick_shots_root)
        row_root = QHBoxLayout()
        row_root.addWidget(self._shots_root, 1)
        row_root.addWidget(browse_root)

        self._shots_no_duty = QCheckBox("Разрешить скриншот без дежурства")
        self._shots_no_duty.setChecked(cfg.shots_allow_no_duty)
        self._shots_sound = QCheckBox("Звук при скриншоте")
        self._shots_sound.setChecked(cfg.shots_sound)
        test_shot_sound = QPushButton("Проверить звук")
        test_shot_sound.clicked.connect(lambda: sounds.play_shot("saved"))
        row_sound = QHBoxLayout()
        row_sound.addWidget(self._shots_sound, 1)
        row_sound.addWidget(test_shot_sound)

        form.addRow("Папка отчётов", row_root)
        form.addRow(self._shots_no_duty)
        form.addRow(row_sound)
        note = QLabel(
            "Пустое поле = папка с программой; если туда нельзя писать — "
            "«Документы\\SKY HELPER». Имя файла: "
            "2026-09-30_16-42-15_Наказания-День.jpg, качество 90 %."
        )
        note.setObjectName("hint")
        note.setWordWrap(True)
        form.addRow(note)
        layout.addLayout(form)

        layout.addSpacing(4)
        layout.addLayout(self._section(
            "Категории и клавиши",
            "Название — как на Google Диске («/» на диске станет «-»). "
            "Нажми на поле клавиши и потом саму клавишу. F9, Ctrl+F9, F10 и Insert "
            "заняты программой, поэтому назначить их нельзя — будет подсказка, "
            "на что они уже стоят.",
        ))

        grid = QGridLayout()
        grid.setSpacing(6)
        for column, title in enumerate(("Название", "Клавиша", "Занята в игре", "")):
            label = QLabel(title)
            label.setObjectName("hint")
            grid.addWidget(label, 0, column)
        self._shot_grid = grid
        self._shot_rows: list[dict] = []
        for cat in cfg.shots_categories or []:
            self._add_shot_row(
                str(cat.get("name", "")),
                str(cat.get("hotkey", "")),
                bool(cat.get("in_game", False)),
            )
        layout.addLayout(grid)

        add_button = QPushButton("Добавить категорию")
        add_button.clicked.connect(lambda: self._add_shot_row("", "", False))
        row_add = QHBoxLayout()
        row_add.addWidget(add_button)
        row_add.addStretch()
        layout.addLayout(row_add)

        layout.addStretch()
        return page

    def _add_shot_row(self, name: str, hotkey: str, in_game: bool) -> None:
        """Одна строка категории: имя, клавиша, «занята в игре», удаление."""
        row = len(self._shot_rows) + 1

        name_edit = _field()
        name_edit.setText(name)
        name_edit.setPlaceholderText("например, Наказания (День)")

        key_edit = HotkeyEdit()
        key_edit.setMinimumWidth(150)
        key_edit.setText(hotkey)
        key_edit.setPlaceholderText("нажми клавишу")
        # Контекстное меню отключено: вставить текст мышью нельзя,
        # бинд получается только настоящим нажатием клавиши.
        key_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        key_edit.setToolTip(
            "Нажми на поле, а затем на нужную клавишу. Backspace — очистить."
        )

        game_box = QCheckBox()
        game_box.setChecked(in_game)
        game_box.setToolTip(
            "Если клавиша дублирует бинд в игре: скриншот всё равно сохранится, "
            "но появится предупреждение «Клавиша занята в игре»."
        )

        remove = QPushButton("×")
        remove.setFixedWidth(28)
        remove.setToolTip("Удалить категорию (файлы уедут в «Корзину»)")
        remove.clicked.connect(lambda _on=False, r=row: self._remove_shot_row(r))

        self._shot_grid.addWidget(name_edit, row, 0)
        self._shot_grid.addWidget(key_edit, row, 1)
        self._shot_grid.addWidget(game_box, row, 2, alignment=Qt.AlignmentFlag.AlignCenter)
        self._shot_grid.addWidget(remove, row, 3, alignment=Qt.AlignmentFlag.AlignCenter)
        self._shot_rows.append({
            "name": name_edit, "hotkey": key_edit,
            "in_game": game_box, "remove": remove,
        })

    def _remove_shot_row(self, number: int) -> None:
        """Убирает строку по её номеру, остальные перенумеровываются."""
        index = number - 1
        if not 0 <= index < len(self._shot_rows):
            return
        row = self._shot_rows.pop(index)
        for widget in row.values():
            widget.deleteLater()
        self._renumber_shot_rows()

    def _renumber_shot_rows(self) -> None:
        """Чтобы кнопка «×» удаляла именно свою строку, и сетка без дырок."""
        for index, item in enumerate(self._shot_rows, start=1):
            button: QPushButton = item["remove"]
            try:
                button.clicked.disconnect()
            except (RuntimeError, TypeError):   # уже отключено
                pass
            button.clicked.connect(
                lambda _on=False, r=index: self._remove_shot_row(r)
            )
            for column, key in enumerate(("name", "hotkey", "in_game", "remove")):
                self._shot_grid.removeWidget(item[key])
                self._shot_grid.addWidget(
                    item[key], index, column,
                    alignment=(
                        Qt.AlignmentFlag.AlignCenter
                        if key in ("in_game", "remove")
                        else Qt.AlignmentFlag.AlignLeft
                    ),
                )

    def _pick_shots_root(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Папка для скриншотов", self._shots_root.text() or str(program_dir())
        )
        if path:
            self._shots_root.setText(path)

    # --- действия ---

    def _pick_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Папка для отчётов", self._out_dir.text())
        if path:
            self._out_dir.setText(path)

    def _pick_google_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "JSON-ключ Google", "", "JSON (*.json)"
        )
        if path:
            self._gsheet_key.setText(path)

    def _clear_pin(self) -> None:
        self._pin.clear()
        self._pin_cleared = True
        self._update_pin_hint()

    def _update_pin_hint(self) -> None:
        if self._pin_cleared:
            text = "Код доступа будет снят при сохранении."
        elif self._core.config.web_pin_hash:
            text = "Код доступа задан. Введи новый, чтобы сменить; сам код нигде не показывается."
        else:
            text = "Код доступа не задан: сайт смогут открыть все, кто в твоей сети."
        self._pin_hint.setText(text)

    def _open_site_now(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        if not self._web_on.isChecked():
            QMessageBox.information(
                self, "Сайт выключен",
                "Включи «Включить локальный сайт» и нажми «Сохранить».",
            )
            return
        self._collect(validate=False)   # подхватить текущие поля: порт, код, доступ по сети
        self._core.apply_config()       # сохранить и (пере)запустить сайт
        self._refresh_site_state()
        if self._core.site_url:
            import webbrowser

            webbrowser.open(self._core.site_url)
        elif self._core.web_error:
            QMessageBox.warning(self, "Сайт не запустился", self._core.web_error)

    def _refresh_site_state(self) -> None:
        from app.util import local_ip

        port = int(self._web_port.value())
        if self._core.web_running:
            self._site_state.setText(f"Сайт запущен: {self._core.site_url}")
        elif self._core.web_error:
            self._site_state.setText(f"Сайт не запустился: {self._core.web_error}")
        elif self._core.config.web_enabled:
            self._site_state.setText("Сайт пока не запущен: нажми «Открыть сайт».")
        else:
            self._site_state.setText("Сайт выключен.")

        if self._web_lan.isChecked():
            ip = local_ip()
            if ip:
                self._phone_hint.setText(
                    f"С телефона: http://{ip}:{port}/  (та же Wi-Fi сеть)"
                )
            else:
                self._phone_hint.setText("IP-адрес компьютера узнать не удалось — смотри в ipconfig.")
        else:
            self._phone_hint.setText("Доступ только с этого компьютера.")

    # --- сохранение ---

    # --- вкладка «Лицензия» -------------------------------------------------

    def _tab_license(self) -> QWidget:
        from app import hwid as hwid_mod

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(self._section(
            "Лицензия",
            "Ключ выдаётся под конкретный компьютер и действует ограниченный "
            "срок. Отозванный ключ перестаёт работать при следующем запуске "
            "программы с интернетом.",
        ))

        self._lic_status = QLabel()
        self._lic_status.setWordWrap(True)
        layout.addWidget(self._lic_status)

        form = QFormLayout()
        form.setSpacing(10)

        self._lic_code = QLineEdit()
        self._lic_code.setReadOnly(True)
        try:
            self._lic_code.setText(hwid_mod.current())
        except hwid_mod.HwidError as exc:
            self._lic_code.setText("—")
            self._lic_code.setToolTip(str(exc))
        copy = QPushButton("Копировать")
        copy.setToolTip("Код этого ПК — отправьте его администратору")
        copy.clicked.connect(self._copy_hwid)
        code_row = QHBoxLayout()
        code_row.setSpacing(8)
        code_row.addWidget(self._lic_code, 1)
        code_row.addWidget(copy)

        self._lic_key = _field()
        self._lic_key.setPlaceholderText("новый ключ (напр. для продления)")
        activate = QPushButton("Активировать")
        activate.clicked.connect(self._activate_license)
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_row.addWidget(self._lic_key, 1)
        key_row.addWidget(activate)

        self._revocation_url = _field()
        self._revocation_url.setText(self._core.config.revocation_url)
        self._revocation_url.setPlaceholderText(
            "https://gist.githubusercontent.com/…/raw/…"
        )

        form.addRow("Код этого ПК", code_row)
        form.addRow("Ключ", key_row)
        form.addRow("Список отзывов (адрес)", self._revocation_url)

        layout.addLayout(form)
        layout.addStretch()
        self._refresh_license_status()
        return page

    def _set_license_message(self, text: str, color: str) -> None:
        self._lic_status.setText(text)
        self._lic_status.setStyleSheet(f"color: {color}; font-size: 13px;")

    def _refresh_license_status(self) -> None:
        from app import license as lic

        try:
            result = lic.check()
        except lic.LicenseError as exc:
            if exc.code == "missing":
                self._set_license_message(
                    "Ключ не активирован: без него exe не запустится.",
                    "#d29922",
                )
            else:
                self._set_license_message(exc.message, "#e5484d")
            return
        text = (f"Ключ {result.key_id} действует до "
                f"{result.expires.strftime('%d.%m.%Y')}")
        if result.who:
            text += f" · выдан {result.who}"
        self._set_license_message(text, "#3fb950")

    def _copy_hwid(self) -> None:
        from PySide6.QtWidgets import QApplication

        code = self._lic_code.text().strip()
        if code and code != "—":
            QApplication.clipboard().setText(code)
            self._set_license_message("Код ПК скопирован — отправьте его "
                                      "администратору", "#3fb950")

    def _activate_license(self) -> None:
        from app import hwid as hwid_mod
        from app import license as lic

        text = self._lic_key.text().strip()
        if not text:
            self._set_license_message("Вставьте ключ в поле выше", "#e5484d")
            return
        try:
            code = hwid_mod.current()
        except hwid_mod.HwidError as exc:
            self._set_license_message(
                f"Не удалось получить код ПК: {exc}", "#e5484d",
            )
            return
        try:
            lic.verify(text, hwid=code)
        except lic.LicenseError as exc:
            self._set_license_message(exc.message, "#e5484d")
            return
        lic.save_license_text(text)
        try:
            lic.check(hwid_value=code)      # отзыв по кэшу + откат часов
        except lic.LicenseError as exc:
            self._set_license_message(exc.message, "#e5484d")
            return
        self._lic_key.clear()
        self._refresh_license_status()

    def _collect(self, validate: bool = True) -> bool:
        cfg = self._core.config
        errors: list[str] = []

        # Сначала читаем и проверяем клавиши, потом пишем в cfg: битое
        # значение не должно успеть попасть в config.json (жалоба
        # 02.10.2026: «zcsda» из текстового поля отравляло конфиг ещё до
        # падения apply_config — и тогда бинды умирали при каждом запуске).
        hotkeys = (
            ("hotkey_add", "клавиша +1 обращения", self._key_add, True),
            ("hotkey_remove", "клавиша −1 обращения", self._key_remove, True),
            ("hotkey_duty", "клавиша дежурства", self._key_duty, True),
            ("hotkey_toggle", "клавиша показа окна", self._key_toggle, False),
        )
        new_keys = {
            attr: edit.text().strip().lower()
            for attr, _title, edit, _required in hotkeys
        }
        categories = [
            {
                "name": row["name"].text().strip(),
                "hotkey": row["hotkey"].text().strip().lower(),
                "in_game": row["in_game"].isChecked(),
            }
            for row in self._shot_rows
        ]
        if validate:
            for attr, title, _edit, required in hotkeys:
                value = new_keys[attr]
                if required and not value:
                    errors.append(f"Не заполнена {title}")
                elif value and bind_problem(value):
                    errors.append(
                        f"Не распознана {title}: «{value}» — нажми клавишу "
                        f"в поле (Backspace — очистить)"
                    )
            # Резерв берём из полей этого же окна: их могли поменять прямо
            # сейчас, а не только в прошлый раз — иначе проверка врёт.
            reserved = [
                self._key_add.text(), self._key_remove.text(),
                self._key_duty.text(), self._key_toggle.text(),
            ]
            errors.extend(category_problems(cfg, categories, reserved))

        if errors and validate:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "Проверь настройки", "\n".join(errors))
            return False

        # Все проверки прошли — записываем значения в config.
        cfg.require_duty = self._require_duty.isChecked()
        cfg.duty_auto_off_on_game_close = self._auto_off.isChecked()
        cfg.count_only_in_game = self._count_in_game.isChecked()
        cfg.hotkey_add = new_keys["hotkey_add"]
        cfg.hotkey_remove = new_keys["hotkey_remove"]
        cfg.hotkey_duty = new_keys["hotkey_duty"]
        cfg.hotkey_toggle = new_keys["hotkey_toggle"]
        cfg.window_on_top = self._on_top.isChecked()
        cfg.weekly_hours_norm = float(self._hours_norm.value())
        cfg.weekly_reports_norm = int(self._reports_norm.value())
        cfg.week_start_weekday = int(self._week_start.currentIndex())
        cfg.game_processes = [p.strip() for p in self._processes.text().split(",") if p.strip()]

        cfg.output_dir = self._out_dir.text().strip()
        cfg.export_interval_min = float(self._interval.value())
        cfg.archive_weekly = self._archive.isChecked()

        cfg.web_enabled = self._web_on.isChecked()
        cfg.web_host = "0.0.0.0" if self._web_lan.isChecked() else "127.0.0.1"
        cfg.web_port = int(self._web_port.value())
        pin = self._pin.text().strip()
        if self._pin_cleared:
            cfg.web_pin_hash = ""
        elif pin:
            from app.web.pin import hash_pin

            cfg.web_pin_hash = hash_pin(pin)
        self._pin.clear()
        self._pin_cleared = False
        self._update_pin_hint()

        cfg.gsheet_id = self._gsheet_id.text().strip()
        cfg.gsheet_credentials = self._gsheet_key.text().strip()
        cfg.ui_theme = self._ui_theme.currentData()
        cfg.sound_theme = self._sound_theme.currentData()
        cfg.rain_enabled = self._rain.isChecked()
        cfg.cursor_style = self._cursor.currentData()
        cfg.revocation_url = self._revocation_url.text().strip()

        cfg.shots_root = self._shots_root.text().strip()
        cfg.shots_allow_no_duty = self._shots_no_duty.isChecked()
        cfg.shots_sound = self._shots_sound.isChecked()
        cfg.shots_categories = categories
        return True

    def accept(self) -> None:  # noqa: N802 (имя задано Qt)
        if not self._collect():
            return
        try:
            self._core.apply_config()
        except Exception as exc:  # noqa: BLE001 — окно не должно умирать молча
            # Жалоба 02.10.2026: «после ввода клавиши не работает
            # сохранение» — apply_config падал, окно висело без объяснений.
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(
                self,
                "Не удалось применить",
                f"Сохранение сорвалось: {exc}\n"
                r"Подробности — в журнале logs\app.log.",
            )
            return
        self.done(QDialog.DialogCode.Accepted)
