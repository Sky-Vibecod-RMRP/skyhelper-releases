"""Страница команды в окне программы: описание, форма параметров,
предпросмотр собранной команды и таблица прав доступа.

Данные приходят из ``app.commands.data`` — той же базы, что питает поиск
и вкладку «Команды» на сайте. Синтаксис и порядок параметров не меняются:
поля формы подставляют значения ровно в том порядке, в каком они идут
в примере из списка пользователя.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from app.commands import data as cmd_data

_MONO = "Consolas, 'Courier New', monospace"


class CommandPage(QWidget):
    """Одна страница команды: назад — к списку, вниз — таблица прав."""

    back_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._command: dict | None = None
        self._palette: dict[str, str] = {}
        self._fields: list[QLineEdit] = []

        self._back = QPushButton("← К списку команд")
        self._back.setObjectName("back")
        # Курсор кнопкам не ставим: в окне он одинаков везде — белый кружок,
        # как на сайте, а системная «рука» читалась как «стандартный курсор»
        # (баг-репорт №4).
        self._back.clicked.connect(self.back_clicked.emit)

        self._name = QLabel()
        self._name.setObjectName("cmd-name")
        self._name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._desc = QLabel()
        self._desc.setObjectName("cmd-desc")
        self._desc.setWordWrap(True)

        self._meta = QLabel()
        self._meta.setObjectName("cmd-meta")
        self._meta.setWordWrap(True)
        self._meta.setVisible(False)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self._back)
        top.addStretch(1)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(10)
        self._body.addLayout(top)
        self._body.addWidget(self._name)
        self._body.addWidget(self._desc)
        self._body.addWidget(self._meta)

        host = QWidget()
        host.setObjectName("cmd-scroll-body")
        host.setLayout(self._body)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(host)
        scroll.setObjectName("cmd-scroll")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    # --- сборка страницы ---------------------------------------------------

    def show_command(self, command: dict, palette: dict[str, str] | None = None) -> None:
        """Показать команду: форма параметров, предпросмотр, права."""
        self._command = command
        self._palette = palette or self._palette
        self._fields = []

        # старые блоки формы и прав — на свалку
        while self._body.count() > 4:
            item = self._body.takeAt(4)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                _clear_layout(item.layout())

        self._name.setText(command["name"])
        self._desc.setText(command["desc"])

        meta_bits = []
        if command["alias"]:
            meta_bits.append(
                "В примере используется запись <b>%s</b>" % command["alias"]
            )
        if command["note"]:
            meta_bits.append(command["note"])
        if meta_bits:
            self._meta.setText("<br>".join(meta_bits))
            self._meta.setVisible(True)
        else:
            self._meta.setVisible(False)

        self._body.addWidget(self._form_box(command))
        self._body.addWidget(self._preview_box(command))
        self._body.addWidget(self._rights_box(command))
        self._body.addStretch(1)
        self._apply_palette()

    # --- блоки -------------------------------------------------------------

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("cmd-section")
        return label

    def _form_box(self, command: dict) -> QWidget:
        box = QWidget()
        box.setObjectName("cmd-box")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        layout.addWidget(self._section_title("ФОРМА ПАРАМЕТРОВ"))

        params = command["params"]
        if not params:
            hint = QLabel(
                "Параметры не нужны — команда вызывается без аргументов."
                if not command["alias"]
                else "Параметры не нужны — просто введи <b>%s</b>."
                % command["head"]
            )
            hint.setWordWrap(True)
            hint.setObjectName("cmd-hint")
            layout.addWidget(hint)
            return box

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)
        grid.setColumnStretch(1, 1)
        for index, param in enumerate(params):
            token, title, hint = param["t"], param["ti"], param["h"]
            code = QLabel(token)
            code.setObjectName("cmd-token")
            title_label = QLabel(title)
            title_label.setObjectName("cmd-title")
            field = QLineEdit(token)
            field.setObjectName("cmd-field")
            field.setProperty("param-index", index)
            field.textChanged.connect(self._refresh_preview)
            expl = QLabel(hint)
            expl.setObjectName("cmd-hint")
            expl.setWordWrap(True)

            grid.addWidget(title_label, index * 2, 0, 1, 2)
            grid.addWidget(code, index * 2 + 1, 0)
            grid.addWidget(field, index * 2 + 1, 1)
            grid.addWidget(expl, index * 2 + 2, 0, 1, 2)
            self._fields.append(field)
        layout.addLayout(grid)
        return box

    def _preview_box(self, command: dict) -> QWidget:
        box = QWidget()
        box.setObjectName("cmd-box")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        layout.addWidget(self._section_title("ПРЕДПРОСМОТР СОБРАННОЙ КОМАНДЫ"))

        row = QHBoxLayout()
        row.setSpacing(8)
        preview = QLabel()
        preview.setObjectName("cmd-preview")
        preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        preview.setWordWrap(True)
        self._preview = preview

        copy = QPushButton("Скопировать")
        copy.setObjectName("cmd-copy")
        copy.clicked.connect(self._copy)
        self._copy_btn = copy

        row.addWidget(preview, 1)
        row.addWidget(copy)
        layout.addLayout(row)
        layout.addWidget(
            _hint("Значения подставляются в том порядке, в каком параметры идут "
                  "в синтаксисе — сам синтаксис не меняется.")
        )
        self._refresh_preview()
        return box

    def _rights_box(self, command: dict) -> QWidget:
        box = QWidget()
        box.setObjectName("cmd-box")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        layout.addWidget(self._section_title("ПРАВА ДОСТУПА ПО РАНГАМ"))

        first = cmd_data.first_available(command)
        if first is None:
            summary = "Ни один ранг не может использовать эту команду."
        else:
            state = command["rights"].get(first["id"], "never")
            summary = (
                "С <b>%s</b> (уровень %d) — %s."
                % (first["id"], first["level"],
                   cmd_data.STATE_TEXT[state].lower())
            )
        note = _hint("🟩 всегда (если есть ранг) • 🟨 только на смене • 🟥 недоступна. "
                     + summary)
        layout.addWidget(note)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)
        headers = ("Уровень", "Ранг", "Группа", "Доступ")
        for column, text in enumerate(headers):
            head = QLabel(text)
            head.setObjectName("cmd-head")
            grid.addWidget(head, 0, column)
        for row, rank in enumerate(cmd_data.rights_rows(command), start=1):
            level = QLabel(str(rank["level"]))
            level.setObjectName("cmd-level")
            ident = QLabel(rank["id"])
            ident.setObjectName("cmd-token")
            group = QLabel(rank["group"])
            group.setObjectName("cmd-group")
            state = QLabel(rank["label"])
            state.setObjectName("cmd-state")
            state.setProperty("state", rank["state"])
            grid.addWidget(level, row, 0)
            grid.addWidget(ident, row, 1)
            grid.addWidget(group, row, 2)
            grid.addWidget(state, row, 3)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)
        return box

    # --- обновления --------------------------------------------------------

    def _refresh_preview(self, *_args) -> None:
        command = self._command
        if command is None or not hasattr(self, "_preview"):
            return
        parts = [command["head"]]
        parts += [field.text().strip() for field in self._fields
                  if field.text().strip()]
        self._preview.setText(" ".join(parts))

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self._preview.text())
        self._copy_btn.setText("Скопировано")
        QTimer.singleShot(1400, lambda: self._copy_btn.setText("Скопировать"))

    def apply_theme(self, palette: dict[str, str]) -> None:
        self._palette = palette
        self._apply_palette()

    def _apply_palette(self) -> None:
        p = self._palette
        if not p:
            return
        accent = p.get("accent", "#38bdf8")
        text = p.get("text", "#edeef1")
        muted = p.get("muted", "#8a8c94")
        border = p.get("border", "#30363d")
        card = p.get("card", "#161b22")
        field = p.get("field", "#0b0c0e")
        self.setStyleSheet(
            """
            QScrollArea#cmd-scroll, QWidget#cmd-scroll-body { background: %s; border: none; }
            QLabel#cmd-name {
                color: %s; font-family: %s; font-size: 21px; font-weight: 700;
            }
            QLabel#cmd-desc { color: %s; font-size: 14px; }
            QLabel#cmd-meta {
                color: %s; font-size: 13px; background: %s;
                border-left: 4px solid %s; border-radius: 7px; padding: 7px 10px;
            }
            QLabel#cmd-section {
                color: %s; font-size: 12px; font-weight: 700; letter-spacing: 1px;
            }
            QWidget#cmd-box {
                background: %s; border: 1px solid %s; border-radius: 10px;
            }
            QLabel#cmd-title { color: %s; font-size: 13px; font-weight: 700; }
            QLabel#cmd-token {
                color: %s; font-family: %s; font-size: 13px;
                background: %s; border: 1px solid %s; border-radius: 6px;
                padding: 6px 8px;
            }
            QLabel#cmd-hint { color: %s; font-size: 12.5px; }
            QLabel#cmd-head {
                color: %s; font-size: 12px; font-weight: 700;
                border-bottom: 1px solid %s; padding-bottom: 4px;
            }
            QLabel#cmd-level, QLabel#cmd-group { color: %s; font-size: 13px; }
            QLabel#cmd-state { font-size: 13px; }
            QLabel#cmd-state[state="always"]  { color: #2ea043; }
            QLabel#cmd-state[state="duty"]    { color: #d29922; }
            QLabel#cmd-state[state="never"]   { color: #f85149; }
            QLabel#cmd-preview {
                color: %s; font-family: %s; font-size: 15px; font-weight: 700;
                background: %s; border: 1px dashed %s; border-radius: 8px;
                padding: 9px 11px;
            }
            QPushButton#cmd-copy, QPushButton#back {
                color: %s; background: %s; border: 1px solid %s;
                border-radius: 8px; padding: 7px 13px; font-size: 13px;
            }
            QPushButton#cmd-copy:hover, QPushButton#back:hover { border-color: %s; }
            QLineEdit#cmd-field {
                color: %s; background: %s; border: 1px solid %s;
                border-radius: 7px; padding: 7px 9px; font-family: %s; font-size: 13px;
            }
            QLineEdit#cmd-field:focus { border-color: %s; }
            """
            % (
                card, accent, _MONO, text, muted, card, accent,
                accent, card, border,
                text, accent, _MONO, field, border,
                muted, muted, border, muted,
                accent, _MONO, field, accent,
                text, field, border, accent,
                text, field, border, _MONO, accent,
            )
        )

    def command(self) -> dict | None:
        """Команда, которую страница показывает сейчас."""
        return self._command


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("cmd-hint")
    label.setWordWrap(True)
    return label


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        child = item.widget()
        if child is not None:
            child.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())
