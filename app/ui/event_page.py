"""Карточка серверного события в окне программы.

Название, дополнительная информация, координаты и кнопка
«Телепортироваться на событие». Команда берётся из базы
``app.events.data`` ровно в том виде, в каком она опубликована
в документации RMRP Study, и копируется в буфер — в игру ничего
не внедряется.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout,
    QWidget,
)

from app.events import data as ev_data

_MONO = "Consolas, 'Courier New', monospace"

#: Ширина скриншота события в карточке (файлы — 800 px по ширине).
_SHOT_WIDTH = 620


class EventPage(QWidget):
    """Одна карточка события: назад — к списку, главное — кнопка телепорта."""

    back_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._event: dict | None = None
        self._palette: dict[str, str] = {}

        self._back = QPushButton("← К списку событий")
        self._back.setObjectName("back")
        # Курсор одинаков во всём окне (белый кружок, как на сайте) — см.
        # app.ui.cursor и баг-репорт №4.
        self._back.clicked.connect(self.back_clicked.emit)

        self._name = QLabel()
        self._name.setObjectName("evt-name")
        self._name.setWordWrap(True)
        self._name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self._chips = QLabel()
        self._chips.setObjectName("evt-chips")
        self._chips.setWordWrap(True)
        self._chips.setTextFormat(Qt.TextFormat.RichText)
        self._chips.setOpenExternalLinks(True)
        #: Блоки над карточкой (категория, раздел, скриншот) — без стилей.
        self._chip_bits: list[dict] = []

        #: Скриншот события из документации RMRP Study (скрыт, если файла нет).
        self._shot = QLabel()
        self._shot.setObjectName("evt-shot")
        self._shot.setVisible(False)
        self._shot.setWordWrap(True)
        self._shot.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self._back)
        top.addStretch(1)

        self._body = QVBoxLayout()
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(10)
        self._body.addLayout(top)
        self._body.addWidget(self._name)
        self._body.addWidget(self._chips)
        self._body.addWidget(self._shot)

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

    # --- сборка карточки ---------------------------------------------------

    def show_event(self, event: dict, palette: dict[str, str] | None = None) -> None:
        """Показать событие: категория, координаты, кнопка телепорта."""
        self._event = event
        self._palette = palette or self._palette

        while self._body.count() > 4:
            item = self._body.takeAt(4)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                _clear_layout(item.layout())

        self._name.setText(event["name"])

        cat = ev_data.category(event["cat"])
        self._chip_bits = []
        if cat:
            self._chip_bits.append({"kind": "chip", "text": cat["name"]})
        if event.get("group"):
            self._chip_bits.append({"kind": "chip-alt", "text": event["group"]})
        self._render_chips()
        self._render_shot(event)

        self._body.addWidget(self._coords_box(event))
        self._body.addWidget(self._teleport_box(event))
        self._body.addStretch(1)
        self._apply_palette()

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("cmd-section")
        return label

    def _render_chips(self) -> None:
        """Полоска над карточкой: категория, раздел, ссылка на скриншот."""
        p = self._palette or {}
        border = p.get("border", "#30363d")
        card = p.get("card", "#161b22")
        accent = p.get("accent", "#38bdf8")
        muted = p.get("muted", "#8a8c94")
        parts = []
        for bit in self._chip_bits:
            text = _esc(bit["text"])
            if bit["kind"] == "link":
                parts.append('<a href="%s">%s</a>' % (_esc(bit["href"]), text))
                continue
            color = accent if bit["kind"] == "chip-alt" else muted
            parts.append(
                '<span style="background:%s;border:1px solid %s;border-radius:9px;'
                'padding:2px 9px;margin-right:6px;color:%s;">%s</span>'
                % (card, border, color, text)
            )
        self._chips.setText(" ".join(parts) or "&nbsp;")

    def _render_shot(self, event: dict) -> None:
        """Скриншот события из папки приложения (файл лежит рядом с сайтом)."""
        path = ev_data.image_file(event)
        pixmap = QPixmap(str(path)) if path is not None else QPixmap()
        if pixmap.isNull():
            self._shot.clear()
            self._shot.setVisible(False)
            return
        width = min(_SHOT_WIDTH, pixmap.width())
        self._shot.setPixmap(
            pixmap.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
        )
        self._shot.setVisible(True)

    def _coords_box(self, event: dict) -> QWidget:
        box = QWidget()
        box.setObjectName("cmd-box")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        layout.addWidget(self._section_title("КООРДИНАТЫ СОБЫТИЯ"))

        code = QLabel(", ".join(_fmt(v) for v in event["coords"]))
        code.setObjectName("evt-coords")
        code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        code.setWordWrap(True)

        cmd = QLabel(event["cmd"])
        cmd.setObjectName("cmd-preview")
        cmd.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cmd.setWordWrap(True)

        note = QLabel(
            "Координаты взяты из документации RMRP Study как есть — "
            "кнопка ниже копирует эту же команду без изменений."
        )
        note.setObjectName("cmd-hint")
        note.setWordWrap(True)

        layout.addWidget(code)
        layout.addWidget(cmd)
        layout.addWidget(note)
        return box

    def _teleport_box(self, event: dict) -> QWidget:
        box = QWidget()
        box.setObjectName("cmd-box")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        layout.addWidget(self._section_title("ТЕЛЕПОРТАЦИЯ"))

        row = QHBoxLayout()
        row.setSpacing(8)
        button = QPushButton("Телепортироваться на событие")
        button.setObjectName("evt-tp")
        button.clicked.connect(self._teleport)
        self._tp_btn = button
        row.addWidget(button)
        row.addStretch(1)

        self._tp_hint = QLabel(
            "Команда скопирована — открой чат в игре и вставь её."
        )
        self._tp_hint.setObjectName("cmd-hint")
        self._tp_hint.setWordWrap(True)
        self._tp_hint.setVisible(False)

        layout.addLayout(row)
        layout.addWidget(self._tp_hint)
        return box

    # --- действия ----------------------------------------------------------

    def _teleport(self) -> None:
        """Скопировать команду события в буфер обмена."""
        if self._event is None:
            return
        QGuiApplication.clipboard().setText(self._event["cmd"])
        self._tp_btn.setText("Скопировано ✓")
        self._tp_hint.setVisible(True)
        QTimer.singleShot(
            2200,
            lambda: self._tp_btn.setText("Телепортироваться на событие"),
        )

    def current_event(self) -> dict | None:
        """Событие, которое страница показывает сейчас."""
        return self._event

    # --- тема --------------------------------------------------------------

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
            QLabel#evt-name { color: %s; font-size: 21px; font-weight: 700; }
            QLabel#evt-chips { color: %s; font-size: 13px; }
            QLabel#evt-shot { border: 1px solid %s; border-radius: 8px; }
            QLabel#cmd-section {
                color: %s; font-size: 12px; font-weight: 700; letter-spacing: 1px;
            }
            QWidget#cmd-box {
                background: %s; border: 1px solid %s; border-radius: 10px;
            }
            QLabel#cmd-hint { color: %s; font-size: 12.5px; }
            QLabel#evt-coords {
                color: %s; font-family: %s; font-size: 15px; font-weight: 700;
                background: %s; border: 1px solid %s; border-radius: 8px; padding: 9px 11px;
            }
            QLabel#cmd-preview {
                color: %s; font-family: %s; font-size: 15px; font-weight: 700;
                background: %s; border: 1px dashed %s; border-radius: 8px; padding: 9px 11px;
            }
            QPushButton#evt-tp {
                color: #06281c; background: %s; border: 1px solid %s;
                border-radius: 8px; padding: 10px 16px; font-size: 14px; font-weight: 700;
            }
            QPushButton#evt-tp:hover { background: %s; }
            QPushButton#back {
                color: %s; background: %s; border: 1px solid %s;
                border-radius: 8px; padding: 7px 13px; font-size: 13px;
            }
            QPushButton#back:hover { border-color: %s; }
            """
            % (
                card, accent, muted, border,
                accent, card, border,
                muted,
                accent, _MONO, field, border,
                accent, _MONO, field, accent,
                accent, accent, accent,
                text, field, border, accent,
            )
        )
        self._render_chips()


def _fmt(value: float) -> str:
    """580.0 → «580», 155.21 → «155.21» — только для показа."""
    text = ("%f" % value).rstrip("0").rstrip(".")
    return text or "0"


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())
