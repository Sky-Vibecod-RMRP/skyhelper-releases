"""Окно «Хелпер»: цветное меню разделов слева, текст и поиск справа.

Контент общий с сайтом (``app.help.data``): одни и те же разделы инструкций
и тот же список правил RMRP с поиском выглядят одинаково и в программе,
и на sky-grafana.rmrp. Ссылки на правила открываются в браузере.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QGuiApplication, QIcon, QPainter, QPalette, QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QLineEdit, QPushButton, QStackedWidget, QVBoxLayout,
)

from app.catalog import data as cat_data
from app.commands import data as cmd_data
from app.events import data as ev_data
from app.help import data as help_data
from app.player import data as player_data
from app.staff import data as staff_data
from app.ui import theme
from app.ui.command_page import CommandPage
from app.ui.dashboard import DashboardPanel
from app.ui.event_page import EventPage
from app.ui.frameless import FramelessMixin
from app.ui.rich_text import ImageBrowser

#: Насколько затемнять яркие цвета разделов на светлой теме.
_LIGHT_DARKEN = 0.62

#: Заголовки групп в левом меню (не кликаются).
_GROUP_HOME = "ОСНОВНОЕ"
_GROUP_SECTIONS = "РАЗДЕЛЫ"
_GROUP_REFERENCE = "СПРАВОЧНИК"

#: Первый пункт меню — статистика (бывшее главное окно).
_HOME_ITEM = "Главная"

#: Пункты справочника. «Online-STAFF» и «Данные игрока» объединены в одну
#: вкладку (Online-STAFF показывает и онлайн серверов, и карточку игрока).
_REFERENCE_ITEMS = (
    "Команды", "Серверные события", "Транспорт", "Оружие",
    "Транспорт (Google)", "Online-STAFF", "Правила RMRP",
)

log = logging.getLogger(__name__)


def _log_render(section: str, exc: Exception) -> None:
    """Ошибка рендера — в лог, чтобы не искать вслепую (баг №1, предложение №1)."""
    import logging
    logging.getLogger("sky").error(
        "Ошибка рендера «%s»: %s", section, exc, exc_info=True
    )

#: Метки групп в левом меню — как категории в меню MIDNIGHT.
GROUP_SECTIONS = "ИНСТРУКЦИИ"
GROUP_REFERENCE = "СПРАВОЧНИК"

#: Подсказки в строке поиска для справочников из документации Study.
_CATALOG_HINTS = {
    "transport": "Поиск по транспорту — Adder, полиция, /spawnvehicle…",
    "weapon": "Поиск по оружию — винтовка, weapon_pistol, /givegun…",
    "gt": "Поиск по Google-Таблице — название, ID, категория, спавн…",
}


def _luminance(color: str) -> float:
    """Яркость hex-цвета (0..255) по формуле WS. Плохой ввод → 0."""
    raw = color.lstrip("#")
    if len(raw) != 6:
        return 0.0
    try:
        red, green, blue = (int(raw[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return 0.0
    return 0.299 * red + 0.587 * green + 0.114 * blue


def _darken(color: str, factor: float = _LIGHT_DARKEN) -> str:
    """Затемнить hex-цвет — для светлых тем, где яркий бирюзовый не читается."""
    raw = color.lstrip("#")
    if len(raw) != 6:
        return color
    try:
        parts = [int(raw[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return color
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(p * factor))) for p in parts)


def readable(color: str, palette: dict[str, str]) -> str:
    """Цвет раздела: на светлом фоне — затемнённый вариант."""
    return _darken(color) if _luminance(palette.get("bg", "#0b0c0e")) > 150 else color


def section_icon(color: str, kind: str, size: int = 20) -> QIcon:
    """Иконка пункта меню: цветной квадрат раздела и белый знак внутри."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(0, 0, size, size, 5, 5)

    pen = QPen(QColor("#ffffff"), 1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    m = 5  # отступ знака от края квадрата
    if kind == "excel":            # сетка таблицы
        painter.drawRect(m + 1, m + 1, size - 2 * m - 2, size - 2 * m - 2)
        painter.drawLine(size // 2, m + 1, size // 2, size - m - 1)
        painter.drawLine(m + 1, size // 2, size - m - 1, size // 2)
    elif kind == "png":            # картинка
        painter.drawRect(m, m + 2, size - 2 * m, size - 2 * m - 4)
        painter.drawLine(m + 2, size - m - 3, m + 6, size // 2 - 1)
        painter.drawLine(m + 6, size // 2 - 1, m + 10, size - m - 5)
        painter.drawEllipse(size - m - 5, m + 5, 3, 3)
    elif kind == "site":           # глобус
        cx = cy = size // 2
        painter.drawEllipse(m, m, size - 2 * m, size - 2 * m)
        painter.drawEllipse(cx - 3, m, 6, size - 2 * m)
        painter.drawLine(m + 1, cy, size - m - 1, cy)
    elif kind == "duty":           # часы
        cx = cy = size // 2
        painter.drawEllipse(m, m, size - 2 * m, size - 2 * m)
        painter.drawLine(cx, cy, cx, m + 4)
        painter.drawLine(cx, cy, cx + 4, cy + 3)
    elif kind == "trouble":        # восклицание
        cx = size // 2
        painter.drawLine(cx, m, cx, size - m - 5)
        painter.drawEllipse(cx - 1, size - m - 4, 2, 2)
    elif kind == "paths":          # папка
        painter.drawRoundedRect(m, m + 3, size - 2 * m, size - 2 * m - 3, 2, 2)
        painter.drawLine(m, m + 4, m + 4, m)
        painter.drawLine(m + 4, m, size - 2 * m, m)
    else:                          # книга правил
        cx = size // 2
        painter.drawRoundedRect(m, m, size - 2 * m, size - 2 * m, 3, 3)
        painter.drawLine(cx, m + 2, cx, size - m - 2)
    painter.end()
    return QIcon(pixmap)


class HelperWindow(FramelessMixin, QDialog):
    """Слева меню разделов (цветные пункты), справа контент, у правил — поиск.

    Окно без системной рамки: своя шапка вместо белой плашки Windows и
    растягивание мышью за края (баг-репорт №2 и №3). Закрытие крестиком не
    завершает программу — она остаётся в трее.
    """

    def __init__(
        self,
        theme_name: str = theme.DEFAULT_THEME,
        output_dir: str = "",
        core=None,
        actions=(),
        parent=None,
    ) -> None:
        super().__init__(parent)
        # Своя шапка вместо системной белой плашки + растягивание за края.
        title_bar = self.init_frameless(
            "SKY HELPER", closable=True, minimizable=True, resizable=True
        )
        self.setWindowTitle("SKY HELPER — sky-grafana.rmrp")
        self.setMinimumSize(940, 620)
        self._theme_name = theme_name
        self._output_dir = output_dir
        self._core = core
        self._palette = self._build_palette(theme_name)
        #: Что показывает правая часть: раздел, правила, список команд, страницу.
        self._view = "section"
        self._current_command: str | None = None
        #: Открытое событие (id) и выбранная категория (None — все пять).
        self._current_event: str | None = None
        self._events_category: str | None = None
        #: Справочники «Транспорт»/«Оружие»: ключ и открытый раздел (None — все).
        self._catalog_kind: str | None = None
        self._catalog_section: int | None = None

        self._nav = QListWidget()
        self._nav.setObjectName("nav")
        # Пункты длиннее сайдбара не должны давать горизонтальную полосу.
        self._nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav.setTextElideMode(Qt.TextElideMode.ElideRight)
        self._nav.currentRowChanged.connect(self._on_row)

        # Шапка сайдбара — как логотип слева в меню MIDNIGHT.
        self._brand = QLabel("SKY HELPER")
        self._brand.setObjectName("brand")
        brand_font = self._brand.font()
        brand_font.setPointSize(13)
        brand_font.setBold(True)
        brand_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        self._brand.setFont(brand_font)
        self._brand_sub = QLabel("sky-grafana.rmrp")
        self._brand_sub.setObjectName("brand-sub")
        brand_rule = QFrame()
        brand_rule.setObjectName("brand-rule")
        brand_rule.setFixedHeight(2)
        brand_rule.setFixedWidth(36)

        side_layout = QVBoxLayout()
        side_layout.setContentsMargins(14, 16, 12, 12)
        side_layout.setSpacing(4)
        side_layout.addWidget(self._brand)
        side_layout.addWidget(self._brand_sub)
        side_layout.addSpacing(4)
        side_layout.addWidget(brand_rule)
        side_layout.addSpacing(8)

        # Дежурство живёт в меню, а не в отдельном окне: кнопка на виду из
        # любого раздела (предложение №1 — одно окно вместо двух).
        self._duty = QPushButton()
        self._duty.setObjectName("duty")
        self._duty.setCheckable(True)
        if core is not None:
            self._duty.clicked.connect(
                lambda checked: core.session.set_duty(checked, "кнопка в меню")
            )
            # Пульсирующее циановое свечение, пока дежурство включено.
            # Эффект вешаем ТОЛЬКО на время дежурства: когда он выключен,
            # но уже навешен, Qt рисует синюю рамку вокруг кнопки (баг-репорт).
            self._create_duty_glow()
        else:
            self._duty.setVisible(False)
        side_layout.addWidget(self._duty)
        side_layout.addSpacing(8)

        side_layout.addWidget(self._nav, 1)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(264)
        sidebar.setLayout(side_layout)

        self._heading = QLabel()
        self._heading.setObjectName("heading")
        #: Акцентная черта под заголовком — как подчёркивание активной вкладки.
        self._heading_rule = QFrame()
        self._heading_rule.setObjectName("brand-rule")
        self._heading_rule.setFixedHeight(2)
        self._heading_rule.setFixedWidth(56)

        self._search = QLineEdit()
        self._search.setObjectName("search")
        self._search.setPlaceholderText("Поиск по правилам — допросы, война, семьи…")
        self._search.setClearButtonEnabled(True)
        # Не перерисовываем на каждую букву: сборка правил и подсветка по
        # 236К символов заметно подтормаживали на длинных запросах.
        self._query_timer = QTimer(self)
        self._query_timer.setSingleShot(True)
        self._query_timer.setInterval(180)
        self._query_timer.timeout.connect(
            lambda: self._on_query(self._search.text())
        )
        self._search.textChanged.connect(lambda _text: self._query_timer.start())

        self._count = QLabel()
        self._count.setObjectName("caption")

        self._body = ImageBrowser()
        self._body.setObjectName("body")
        self._body.setOpenExternalLinks(False)
        self._body.setOpenLinks(False)  # ссылки разбираем сами: cmd: — внутри окна
        self._body.anchorClicked.connect(self._on_anchor)
        # Над ссылками Qt сам ставит системную «руку» — держим курсор окна
        # (белый кружок, как на сайте; баг-репорт №4).
        self.keep_custom_cursor(self._body)

        self._command_page = CommandPage()
        self._command_page.back_clicked.connect(self._back_to_list)

        self._event_page = EventPage()
        self._event_page.back_clicked.connect(self._back_to_events)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._body)
        self._stack.addWidget(self._command_page)
        self._stack.addWidget(self._event_page)
        # «Главная» — бывшее отдельное окно со статистикой, теперь раздел.
        self._home = DashboardPanel(core, actions) if core is not None else None
        if self._home is not None:
            self._stack.addWidget(self._home)
            # Цифры и кнопка дежурства должны быть живыми всегда, как было
            # в отдельном окне: раз в секунду.
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.refresh)
            self._timer.start(1000)

        search_row = QHBoxLayout()
        search_row.addWidget(self._search, 1)
        search_row.addWidget(self._count)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        right.addWidget(self._heading)
        right.addWidget(self._heading_rule, 0, Qt.AlignLeft)
        right.addSpacing(2)
        right.addLayout(search_row)
        right.addWidget(self._stack, 1)

        layout = QHBoxLayout()
        layout.setContentsMargins(16, 10, 16, 14)
        layout.setSpacing(14)
        layout.addWidget(sidebar)
        layout.addLayout(right, 1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(title_bar)
        outer.addLayout(layout, 1)

        self.apply_theme(self._theme_name)
        if self._home is not None:
            self._show_home()          # открываемся на статистике
        else:
            self._show_commands()      # окно без ядра — инструкции убраны

    # --- тема ---------------------------------------------------------------

    @staticmethod
    def _build_palette(theme_name: str) -> dict[str, str]:
        """Цвета темы программы поверх палитры хелпера (нет нужного ключа → свой)."""
        return {**help_data.PALETTE, **theme.theme_colors(theme_name)}

    def apply_theme(self, theme_name: str) -> None:
        """Перекрасить окно под выбранную тему (вызывается и после настроек)."""
        self._theme_name = theme_name
        self._palette = self._build_palette(theme_name)
        c = self._palette
        self.setStyleSheet(
            """
            QDialog {
                background: %s; border: 1px solid %s; border-radius: 12px;
            }
            QFrame#titlebar {
                background: %s; border: none; border-top-left-radius: 11px;
                border-top-right-radius: 11px;
            }
            QFrame#titlebar QLabel {
                color: %s; font-size: 13px; font-weight: 600;
            }
            QFrame#titlebar QPushButton {
                background: transparent; border: none; border-radius: 6px;
                color: %s; font-size: 15px; font-weight: 700;
            }
            QFrame#titlebar QPushButton:hover { background: %s; }
            QFrame#sidebar {
                background: %s; border: 1px solid %s; border-radius: 12px;
            }
            QLabel#brand-sub { color: %s; }
            QFrame#brand-rule { background: %s; }
            QListWidget#nav {
                background: transparent; border: none;
                padding: 0; outline: 0; font-size: 13.5px;
            }
            QListWidget#nav::item { padding: 7px 9px; border-radius: 7px; }
            QListWidget#nav::item:selected { background: %s; color: %s; }
            QListWidget#nav::item:hover { background: %s; }
            QLabel#heading { font-size: 17px; font-weight: 700; }
            QLabel#caption { color: %s; font-size: 12px; }
            QLineEdit#search {
                background: %s; border: 1px solid %s; border-radius: 8px;
                padding: 9px 12px; font-size: 14px;
            }
            QLineEdit#search:focus { border-color: %s; }
            QTextBrowser#body {
                background: %s; border: 1px solid %s; border-radius: 12px;
                padding: 4px; font-size: 14px;
            }
            /* --- раздел «Главная»: карточки и кнопка дежурства --- */
            QFrame#card {
                background: %s; border: 1px solid %s; border-radius: 10px;
            }
            QLabel#value { font-size: 22px; font-weight: 600; color: %s; }
            QLabel#percent { color: %s; font-size: 13px; }
            QLabel#percent[done="true"] { color: %s; }
            QProgressBar {
                background: %s; border: none; border-radius: 4px; height: 8px;
            }
            QProgressBar::chunk {
                background: %s; border: none; border-radius: 4px;
            }
            QProgressBar[done="true"]::chunk { background: %s; }
            QPushButton#duty {
                background: %s; border: 1px solid %s; border-radius: 9px;
                padding: 8px 9px; font-size: 12.5px; color: %s;
            }
            QPushButton#duty:hover { background: %s; }
            QPushButton#duty:checked {
                background: %s; color: %s; border-color: %s;
            }
            QPushButton#duty:disabled { background: %s; color: %s; }
            /* Полосы прокрутки: свои, а не системные (жалоба на «уродливый
               бегунок»). Тонкие, тёмные, без стрелок и без рамки. */
            QScrollBar:vertical {
                background: transparent; width: 10px; margin: 2px 4px 2px 0;
            }
            QScrollBar::handle:vertical {
                background: %s; border-radius: 5px; min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: %s; }
            QScrollBar:horizontal {
                background: transparent; height: 10px; margin: 0 2px 4px 2px;
            }
            QScrollBar::handle:horizontal {
                background: %s; border-radius: 5px; min-width: 30px;
            }
            QScrollBar::handle:horizontal:hover { background: %s; }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
            QScrollBar::add-page, QScrollBar::sub-page { background: none; }
            """
            % (
                # окно и своя шапка
                c["bg"], c["border"], c["card"], c["text"], c["muted"],
                c["card"],
                # сайдбар, меню, поиск, текст
                c["field"], c["border"], c["muted"], c["accent"],
                c["card"], c["accent"], c["card"], c["muted"],
                c["field"], c["border"], c["accent"], c["card"], c["border"],
                # раздел «Главная»
                c["card"], c["border"], c["text"], c["muted"], c["ok"],
                c.get("bar_bg", c["border"]), c["accent"], c["ok"],
                c["field"], c["border"], c["text"],
                c["card"], c["ok"], c.get("ok_text", c["bg"]), c["ok"],
                c["field"], c["muted"],
                # полосы прокрутки
                c["border"], c["accent"], c["border"], c["accent"],
            )
        )

        pal = QPalette()
        pal.setColor(QPalette.ColorRole.Window, QColor(c["card"]))
        pal.setColor(QPalette.ColorRole.Base, QColor(c["card"]))
        pal.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
        pal.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
        pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["muted"]))
        pal.setColor(QPalette.ColorRole.Link, QColor(c["accent"]))
        self._body.setPalette(pal)
        self._search.setPalette(pal)
        self._command_page.apply_theme(c)
        self._event_page.apply_theme(c)

        row = self._nav.currentRow()
        self._fill_nav()
        if row >= 0:
            self._nav.setCurrentRow(row)
        self._render_current()

    def closeEvent(self, event) -> None:  # noqa: N802 (имя задано Qt)
        # Крестик не завершает программу — она остаётся в трее (Insert
        # возвращает окно). Это же касается и рамки, если её тянуть за угол.
        event.ignore()
        self.hide()

    # --- левое меню ---------------------------------------------------------

    def _fill_nav(self) -> None:
        """Пересобрать меню: «Главная» и справочник (инструкции — на сайте)."""
        current = self._nav.currentRow()
        self._nav.blockSignals(True)
        self._nav.clear()
        if self._home is not None:
            self._nav.addItem(self._nav_label(_GROUP_HOME))
            self._nav.addItem(self._nav_item(_HOME_ITEM))
        self._nav.addItem(self._nav_label(_GROUP_REFERENCE))
        for title in _REFERENCE_ITEMS:
            self._nav.addItem(self._nav_item(title))
        if current >= 0:
            self._nav.setCurrentRow(current)   # пока сигналы заблокированы
        self._nav.blockSignals(False)

    @property
    def home_row(self) -> int | None:
        """Строка меню «Главная» (None — раздела нет, окно без ядра)."""
        return self._row_of(_HOME_ITEM)

    def _nav_label(self, text: str) -> QListWidgetItem:
        """Некликабельная метка группы — как «Combat», «Visuals» в MIDNIGHT."""
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)      # не кликается, не выбирается
        font = item.font()
        font.setPointSize(8)
        font.setBold(True)
        item.setFont(font)
        item.setForeground(QColor(self._palette["muted"]))
        item.setSizeHint(QSize(0, 28))
        return item

    def _nav_item(self, text: str) -> QListWidgetItem:
        """Обычный пункт меню: сплошной светлый текст, активный — цианом."""
        item = QListWidgetItem(text)
        item.setForeground(QColor(self._palette["text"]))
        return item

    def _section_row(self, index: int) -> int:
        """Строка меню раздела: сверху метка-группа, поэтому со сдвигом."""
        return self._sections_first_row() + index

    def _section_index(self, row: int) -> int | None:
        """Какой раздел открывает строка меню (None — строка не про разделы)."""
        first = self._sections_first_row()
        if first <= row < first + len(help_data.SECTIONS):
            return row - first
        return None

    def _sections_first_row(self) -> int:
        """Первая строка разделов инструкций (после метки группы)."""
        if not help_data.SECTIONS:
            return 0
        found = self._row_of(str(help_data.SECTIONS[0]["title"]))
        return 0 if found is None else found

    def _row_of(self, title: str) -> int | None:
        """Строка меню с таким текстом (разделы инструкций не трогаем)."""
        for row in range(self._nav.count()):
            item = self._nav.item(row)
            if item is not None and item.text() == title:
                return row
        return None

    @property
    def commands_row(self) -> int | None:
        """Строка «Команды»."""
        return self._row_of("Команды")

    @property
    def events_row(self) -> int | None:
        """Строка «Серверные события»."""
        return self._row_of("Серверные события")

    @property
    def transport_row(self) -> int | None:
        """Строка «Транспорт»."""
        return self._row_of("Транспорт")

    @property
    def weapon_row(self) -> int | None:
        """Строка «Оружие»."""
        return self._row_of("Оружие")

    @property
    def gt_row(self) -> int | None:
        """Строка «Транспорт (Google)»."""
        return self._row_of("Транспорт (Google)")

    def _catalog_menu_row(self, kind: str) -> int | None:
        """Строка меню для вида справочника («transport» → «Транспорт» …)."""
        names = {"transport": "Транспорт", "weapon": "Оружие",
                 "gt": "Транспорт (Google)"}
        title = names.get(kind)
        return self._row_of(title) if title else None

    @property
    def staff_row(self) -> int | None:
        """Строка «Online-STAFF»."""
        return self._row_of("Online-STAFF")

    @property
    def player_row(self) -> int | None:
        """Строка «Данные игрока»."""
        return self._row_of("Данные игрока")

    @property
    def rules_row(self) -> int | None:
        """Строка «Правила RMRP»."""
        return self._row_of("Правила RMRP")

    def _on_row(self, row: int) -> None:
        if row < 0:
            return
        if self._home is not None and row == self.home_row:
            self._show_home()
        elif row == self.rules_row:
            self._show_rules()
        elif row == self.commands_row:
            self._show_commands()
        elif row == self.events_row:
            self._show_events()
        elif row == self.transport_row:
            self._show_catalog("transport")
        elif row == self.weapon_row:
            self._show_catalog("weapon")
        elif row == self.gt_row:
            self._show_catalog("gt")
        elif row == self.staff_row:
            self._show_staff()
        elif row == self.player_row:
            self._show_player()
        else:
            index = self._section_index(row)
            if index is not None:
                self._show_section(index)

    def _render_current(self) -> None:
        """Показать то, что выбрано сейчас (после смены темы или данных)."""
        if self._view == "home":
            self._show_home()
        elif self._view == "command" and self._current_command:
            self._open_command(self._current_command, keep_selection=True)
        elif self._view == "event" and self._current_event:
            self._open_event(self._current_event, keep_selection=True)
        elif self._view == "catalog" and self._catalog_kind:
            self._show_catalog(self._catalog_kind, self._catalog_section)
        else:
            self._on_row(self._nav.currentRow())

    def _select_row(self, row: int) -> None:
        """Поставить выделение без лишнего сигнала (рендер вызовет сам)."""
        if self._nav.currentRow() == row:
            return
        self._nav.blockSignals(True)
        self._nav.setCurrentRow(row)
        self._nav.blockSignals(False)

    def _select_item(self, title: str) -> None:
        """Подсветить пункт меню с таким текстом (нужно и при вызове из кода)."""
        row = self._row_of(title)
        if row is not None:
            self._select_row(row)

    # --- правая часть -------------------------------------------------------

    def set_output_dir(self, output_dir: str) -> None:
        """Папка с отчётами — подставляется в раздел «Где что лежит»."""
        self._output_dir = str(output_dir)
        self._render_current()

    def show_section(self, index: int) -> None:
        """Открыть раздел инструкций по индексу в SECTIONS."""
        if not 0 <= index < len(help_data.SECTIONS):
            return
        self._show_section(index)

    def show_rules(self) -> None:
        """Открыть вкладку правил RMRP (с поиском)."""
        row = self.rules_row
        if row is None:
            return
        self._select_row(row)
        self._show_rules()

    def show_commands(self) -> None:
        """Открыть список команд администрации (с поиском)."""
        row = self.commands_row
        if row is None:
            return
        self._select_row(row)
        self._show_commands()

    def show_events(self) -> None:
        """Открыть раздел «Серверные события» (с поиском)."""
        row = self.events_row
        if row is None:
            return
        self._select_row(row)
        self._show_events()

    def show_catalog(self, kind: str) -> None:
        """Открыть справочник «Транспорт», «Оружие» или Google-Таблицу."""
        row = self._catalog_menu_row(kind)
        if row is None:
            return
        self._select_row(row)
        self._show_catalog(kind)

    def open_command(self, name: str) -> None:
        """Открыть страницу команды, не трогая левое меню."""
        self._open_command(name)

    def open_event(self, event_id: str) -> None:
        """Открыть карточку события, не трогая левое меню."""
        self._open_event(event_id)

    def _show_section(self, index: int) -> None:
        self._select_row(self._section_row(index))
        self._view = "section"
        self._current_command = None
        self._current_event = None
        self._stack.setCurrentWidget(self._body)
        section = help_data.SECTIONS[index]
        color = readable(str(section.get("color", self._palette["accent"])), self._palette)
        styled = {**section, "color": color}
        self._search.setVisible(False)
        self._count.setVisible(False)
        self._heading.setText(str(section.get("title", "")))
        self._heading.setStyleSheet("color: %s;" % color)
        self._body.setHtml(
            self._wrap(
                help_data.section_page_html(styled, self._palette, self._output_dir)
            )
        )

    def _show_rules(self) -> None:
        self._select_item("Правила RMRP")
        self._view = "rules"
        self._current_command = None
        self._current_event = None
        self._stack.setCurrentWidget(self._body)
        self._search.setVisible(True)
        self._count.setVisible(True)
        self._search.setPlaceholderText("Поиск по правилам — допросы, война, семьи…")
        self._heading.setText("Правила RMRP")
        self._heading.setStyleSheet("color: %s;" % self._palette["accent"])
        self._render_rules(self._search.text())

    def _show_home(self) -> None:
        """Раздел «Главная»: статистика, стрик и действия (бывшее окно)."""
        self._view = "home"
        self._search.setVisible(False)
        self._heading.setText(_HOME_ITEM)
        if self._home is not None:
            self._stack.setCurrentWidget(self._home)
            self._home.refresh()
        self._sync_duty()

    def _create_duty_glow(self) -> None:
        """(Пере)создать свечение и пульс кнопки дежурства.

        ``setGraphicsEffect(None)`` при выключении дежурства забирает владение
        эффектом у Qt и удаляет C++-объект — Python-ссылка остаётся, но
        мёртвая. Повторное использование такой ссылки даёт RuntimeError
        «Internal C++ object already deleted» (в логе сотрудника — 1555 раз,
        волна на каждую секунду, пока дежурство включено).
        """
        pulse = getattr(self, "_duty_pulse", None)
        if pulse is not None:
            try:
                pulse.stop()
                pulse.setTargetObject(None)
            except RuntimeError:
                pass
        self._duty_glow = QGraphicsDropShadowEffect(self._duty)
        self._duty_glow.setColor(QColor("#4ec3f0"))
        self._duty_glow.setBlurRadius(18)
        self._duty_glow.setOffset(0, 0)
        self._duty_pulse = QPropertyAnimation(self._duty_glow, b"blurRadius", self)
        self._duty_pulse.setDuration(1400)
        self._duty_pulse.setStartValue(8)
        self._duty_pulse.setEndValue(28)
        self._duty_pulse.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._duty_pulse.setLoopCount(-1)

    def _duty_glow_alive(self) -> bool:
        """Жива ли C++-ссылка на эффект (мёртвая бросает RuntimeError)."""
        try:
            self._duty_glow.blurRadius()
        except RuntimeError:
            return False
        return True

    def _sync_duty(self) -> None:
        """Кнопка дежурства в меню: состояние и подсказка с клавишей."""
        if self._core is None or self._duty is None:
            return
        cfg = self._core.config
        on = bool(self._core.session.is_on_duty)
        key = str(cfg.hotkey_duty).upper()
        self._duty.setVisible(bool(cfg.require_duty))
        self._duty.blockSignals(True)
        self._duty.setChecked(on)
        self._duty.blockSignals(False)
        # Две строки: в меню 264 пикселя, длинный текст туда не влезает.
        self._duty.setText(
            f"● На дежурстве\n{key} — закончить" if on
            else f"Начать дежурство\n{key} — начать"
        )
        pulse = getattr(self, "_duty_pulse", None)
        if pulse is None:
            return
        # Defensive: крах свечения не должен ронять обновление окна (та же
        # волна RuntimeError раз в секунду съедала тост «Дежурство начато»).
        try:
            if on:
                if not self._duty_glow_alive():
                    self._create_duty_glow()
                    pulse = self._duty_pulse
                if self._duty.graphicsEffect() is None:
                    self._duty.setGraphicsEffect(self._duty_glow)
                if pulse.state() != QPropertyAnimation.State.Running:
                    pulse.start()
            else:
                pulse.stop()
                if self._duty.graphicsEffect() is not None:
                    self._duty.setGraphicsEffect(None)
        except RuntimeError:
            log.exception("Свечение дежурства не обновилось")

    def refresh(self) -> None:
        """Обновить цифры и кнопку дежурства (окно живёт всё время работы)."""
        if self._home is not None:
            self._home.refresh()
        self._sync_duty()

    @property
    def stats_snapshot(self) -> tuple | None:
        """Последний снимок статистики с «Главной» — без чтения базы."""
        home = getattr(self, "_home", None)
        return home.stats_snapshot if home is not None else None

    def stop_updates(self) -> None:
        """Остановить фоновые таймеры окна.

        Вызывается из aboutToQuit ДО остановки ядра: иначе секундный таймер
        успевает прочитать уже закрытую базу (sqlite3.ProgrammingError
        «Cannot operate on a closed database» на выходе).
        """
        timer = getattr(self, "_timer", None)
        if timer is not None:
            timer.stop()
        home = getattr(self, "_home", None)
        if home is not None:
            home.stop_stats()
        query = getattr(self, "_query_timer", None)
        if query is not None:
            query.stop()
        pulse = getattr(self, "_duty_pulse", None)
        if pulse is not None:
            try:
                pulse.stop()
            except RuntimeError:
                pass

    def set_export_status(self, result) -> None:
        """Строка выгрузки — в разделе «Главная»."""
        if self._home is not None:
            self._home.set_export_status(result)

    def _show_commands(self) -> None:
        self._select_item("Команды")
        self._view = "commands"
        self._current_command = None
        self._current_event = None
        self._stack.setCurrentWidget(self._body)
        self._search.setVisible(True)
        self._count.setVisible(True)
        self._search.setPlaceholderText("Поиск по командам — /ban, kick, предупреждение…")
        self._heading.setText("Команды")
        self._heading.setStyleSheet("color: %s;" % self._palette["accent"])
        self._render_commands(self._search.text())

    def _render_commands(self, query: str) -> None:
        try:
            found = len(cmd_data.search(query))
            if query.strip():
                self._count.setText("Найдено: %d из %d" % (found, len(cmd_data.COMMANDS)))
            else:
                self._count.setText("%d команд" % len(cmd_data.COMMANDS))
            self._body.setHtml(self._wrap(cmd_data.list_html(query, self._palette)))
        except Exception as exc:                     # noqa: BLE001 — рендер не должен ронять окно
            _log_render("Команды", exc)
            self._render_error("Команды", exc)

    # --- серверные события -------------------------------------------------

    def _show_events(self) -> None:
        """Список пяти категорий событий (или одна категория, если открыта)."""
        self._select_item("Серверные события")
        self._view = "events"
        self._current_command = None
        self._current_event = None
        self._stack.setCurrentWidget(self._body)
        self._search.setVisible(True)
        self._count.setVisible(True)
        self._search.setPlaceholderText(
            "Поиск по событиям — налёт, склад, захват, КрАЗ…"
        )
        self._heading.setText("Серверные события")
        self._heading.setStyleSheet("color: %s;" % self._palette["accent"])
        self._render_events(self._search.text())

    def _render_events(self, query: str) -> None:
        """Счётчик и HTML: категории, события категории или результат поиска."""
        try:
            want = (query or "").strip()
            if want:
                found = len(ev_data.search(want))
                self._count.setText(
                    "Найдено: %d из %d" % (found, len(ev_data.EVENTS))
                )
            elif self._events_category:
                self._count.setText(
                    "%d событий" % len(ev_data.events_of(self._events_category))
                )
            else:
                self._count.setText(ev_data.summary())
            self._body.setHtml(
                self._wrap(
                    ev_data.list_html(want, self._events_category, self._palette)
                )
            )
        except Exception as exc:                     # noqa: BLE001
            _log_render("Серверные события", exc)
            self._render_error("Серверные события", exc)

    def _open_event_category(self, slug: str) -> None:
        """Открыть одну категорию со списком её событий."""
        if slug and ev_data.category(slug) is None:
            return
        self._events_category = slug or None
        if self._view != "events":
            self._show_events()
            return
        self._render_events(self._search.text())

    def _open_event(self, event_id: str, keep_selection: bool = False) -> None:
        """Карточка события: координаты и кнопка телепорта."""
        event = ev_data.get(event_id)
        if event is None:
            return
        if not keep_selection:
            row = self.events_row
            if row is not None and self._nav.currentRow() != row:
                self._select_row(row)
        self._view = "event"
        self._current_command = None
        self._current_event = event["id"]
        self._search.setVisible(False)
        self._count.setVisible(False)
        self._heading.setText("Серверные события")
        self._heading.setStyleSheet("color: %s;" % self._palette["accent"])
        self._event_page.show_event(event, self._palette)
        self._stack.setCurrentWidget(self._event_page)

    def _teleport_event(self, event_id: str) -> None:
        """Кнопка «Телепортироваться на событие» — команда в буфер (баг №4)."""
        event = ev_data.get(event_id)
        if event is None:
            return
        QGuiApplication.clipboard().setText(event["cmd"])
        self._flash_count("Скопировано ✓ " + event["cmd"])

    def _back_to_events(self) -> None:
        """Вернуться к списку событий (с текущей категорией и поиском)."""
        row = self.events_row
        if row is not None and self._nav.currentRow() != row:
            self._select_row(row)
        self._show_events()

    # --- транспорт и оружие -------------------------------------------------

    def _show_catalog(self, kind: str, section: int | None = None) -> None:
        """Справочник из документации Study: разделы, строки, поиск."""
        if kind not in cat_data.TITLES:
            return
        row = self._catalog_menu_row(kind)
        if row is not None and self._nav.currentRow() != row:
            self._select_row(row)
        self._view = "catalog"
        self._catalog_kind = kind
        self._catalog_section = section
        self._current_command = None
        self._current_event = None
        self._stack.setCurrentWidget(self._body)
        self._search.setVisible(True)
        self._count.setVisible(True)
        self._search.setPlaceholderText(_CATALOG_HINTS[kind])
        self._heading.setText(cat_data.TITLES[kind])
        self._heading.setStyleSheet("color: %s;" % self._palette["accent"])
        self._render_catalog(self._search.text())

    def _render_catalog(self, query: str) -> None:
        """Счётчик и HTML: разделы, строки открытого раздела или поиск."""
        try:
            kind = self._catalog_kind or "transport"
            want = (query or "").strip()
            if want:
                found = len(cat_data.search(kind, want))
                self._count.setText("Найдено: %d из %d" % (found, cat_data.count(kind)))
            elif self._catalog_section is not None:
                self._count.setText(
                    "%d строк" % len(cat_data.rows_of(kind, self._catalog_section))
                )
            else:
                self._count.setText(cat_data.summary(kind))
            self._body.setHtml(
                self._wrap(
                    cat_data.list_html(kind, self._palette, want, self._catalog_section)
                )
            )
        except Exception as exc:                     # noqa: BLE001
            _log_render("Справочник", exc)
            self._render_error("Справочник", exc)

    def _open_catalog_section(self, index: int) -> None:
        """Открыть один раздел справочника («Спорткары», «Пистолеты» …)."""
        kind = self._catalog_kind or "transport"
        if not 0 <= index < len(cat_data.sections(kind)):
            return
        if self._view != "catalog":
            self._show_catalog(kind, index)
            return
        self._catalog_section = index
        self._render_catalog(self._search.text())

    def _back_to_catalog(self) -> None:
        """Список разделов справочника — поиск и выделение сохраняются."""
        self._catalog_section = None
        self._render_catalog(self._search.text())

    def _copy_catalog_command(self, href: str) -> None:
        """Клик по команде справочника — в буфер обмена и короткая подсказка."""
        parts = href.split(":")            # catcopy:kind:раздел:строка
        if len(parts) != 4:
            return
        try:
            row = cat_data.get(parts[1], int(parts[2]), int(parts[3]))
        except ValueError:
            return
        if not row:
            return
        # Команда спавна собирается и для тех строк, где в таблице она
        # пустая (запрет спавна убран по просьбе пользователя).
        command = (cat_data.spawn_command(row) if parts[1] == "gt"
                   else str(row[2] or ""))
        if not command:
            return
        QGuiApplication.clipboard().setText(command)
        self._flash_count("Скопировано ✓ " + command)

    def _flash_count(self, text: str) -> None:
        """Показать сообщение в шапке и через пару секунд вернуть счётчик."""
        self._count.setText(text)
        QTimer.singleShot(2500, self._restore_count)

    def _restore_count(self) -> None:
        """Вернуть нормальный счётчик справочника после подсказки."""
        if self._view != "catalog" or not self._catalog_kind:
            return
        kind = self._catalog_kind
        want = (self._search.text() or "").strip()
        if want:
            self._count.setText(
                "Найдено: %d из %d" % (len(cat_data.search(kind, want)),
                                       cat_data.count(kind))
            )
        elif self._catalog_section is not None:
            self._count.setText(
                "%d строк" % len(cat_data.rows_of(kind, self._catalog_section))
            )
        else:
            self._count.setText(cat_data.summary(kind))

    # --- данные игрока ------------------------------------------------------

    def _show_player(self) -> None:
        """Свои данные из логов RAGE:MP — без поиска, с обновлением по клику."""
        self._select_item("Данные игрока")
        self._view = "player"
        self._current_command = None
        self._current_event = None
        self._stack.setCurrentWidget(self._body)
        self._search.setVisible(False)
        self._count.setVisible(False)
        self._heading.setText("Данные игрока")
        self._heading.setStyleSheet("color: %s;" % self._palette["accent"])
        self._render_player()

    def _render_player(self) -> None:
        try:
            panel = player_data.panel_html(self._palette)
            refresh = (
                '<p style="margin:10px 2px 2px 0;"><a href="player:refresh" '
                'style="color:%s;">Обновить данные</a></p>'
                % self._palette["accent"]
            )
            self._body.setHtml(self._wrap(panel + refresh))
        except Exception as exc:                     # noqa: BLE001
            _log_render("Данные игрока", exc)
            self._render_error("Данные игрока", exc)

    # --- online-staff -------------------------------------------------------

    def show_staff(self) -> None:
        """Открыть вкладку «Online-STAFF» (онлайн серверов + свои данные)."""
        row = self.staff_row
        if row is None:
            return
        self._select_row(row)
        self._show_staff()

    def _show_staff(self, force: bool = False) -> None:
        """Живой онлайн RMRP + все данные игрока (объединённая вкладка)."""
        self._select_item("Online-STAFF")
        self._view = "staff"
        self._current_command = None
        self._current_event = None
        self._stack.setCurrentWidget(self._body)
        self._search.setVisible(False)
        self._count.setVisible(False)
        self._heading.setText("Online-STAFF")
        self._heading.setStyleSheet("color: %s;" % self._palette["accent"])
        self._body.setHtml(
            self._wrap(staff_data.combined_html(self._palette, force=force))
        )

    def _open_command(self, name: str, keep_selection: bool = False) -> None:
        """Страница команды: форма параметров, предпросмотр, права."""
        command = cmd_data.get(name)
        if command is None:
            return
        if not keep_selection:
            row = self.commands_row
            if row is not None and self._nav.currentRow() != row:
                self._select_row(row)
        self._view = "command"
        self._current_command = command["name"]
        self._current_event = None
        self._search.setVisible(False)
        self._count.setVisible(False)
        self._heading.setText("Команды")
        self._heading.setStyleSheet("color: %s;" % self._palette["accent"])
        self._command_page.show_command(command, self._palette)
        self._stack.setCurrentWidget(self._command_page)

    def _back_to_list(self) -> None:
        """Вернуться к списку команд с текущим поиском."""
        row = self.commands_row
        if row is not None and self._nav.currentRow() != row:
            self._select_row(row)
        self._show_commands()

    def _on_anchor(self, url: QUrl) -> None:
        """Внутри окна — страница команды или события, остальное — в браузере."""
        href = str(url.toString() or "")
        if href.startswith("player:"):
            if href == "player:refresh":
                self._render_player()
            return
        if href.startswith("staff:"):
            if href == "staff:refresh":
                self._show_staff(force=True)      # живой онлайн — по кнопке
            return
        if href.startswith("evtcat:"):
            self._open_event_category(href[len("evtcat:"):])
            return
        if href.startswith("evt:"):
            self._open_event(href[len("evt:"):])
            return
        if href.startswith("evttp:"):
            self._teleport_event(href[len("evttp:"):])
            return
        if href.startswith("catcopy:"):
            self._copy_catalog_command(href)
            return
        if href.startswith("catsec:"):
            rest = href[len("catsec:"):]
            kind, _, index = rest.partition(":")
            if kind not in cat_data.TITLES:
                return
            try:
                section = int(index)
            except ValueError:
                return
            if kind != self._catalog_kind:
                self._show_catalog(kind, section)
            else:
                self._open_catalog_section(section)
            return
        if href.startswith("cat:"):
            kind = href[len("cat:"):]
            if kind not in cat_data.TITLES:
                return
            if kind != self._catalog_kind or self._view != "catalog":
                self._show_catalog(kind)
            else:
                self._back_to_catalog()
            return
        if href.startswith("cmd:"):
            self._open_command(href[4:])
            return
        QDesktopServices.openUrl(url)

    def _render_rules(self, query: str) -> None:
        try:
            total = help_data.total_rules()
            found = sum(len(cat["items"]) for cat in help_data.filter_rules(query))
            if query.strip():
                self._count.setText("Найдено: %d из %d" % (found, total))
            else:
                self._count.setText(
                    "%d правил в %d разделах" % (total, len(help_data.RULES))
                )
            if found:
                inner = help_data.rules_html(self._palette, query)
            else:
                inner = (
                    '<p style="color:%s;margin:14px 2px;">Ничего не нашлось — '
                    "попробуй другое слово.</p>" % self._palette["muted"]
                )
            self._body.setHtml(self._wrap(inner))
        except Exception as exc:                     # noqa: BLE001
            _log_render("Правила RMRP", exc)
            self._render_error("Правила RMRP", exc)

    def set_query(self, text: str) -> None:
        """Поставить запрос и сразу перерисовать.

        Поле ввода connected через задержку (:attr:`_query_timer`), чтобы не
        перерисовывать на каждую букву. Всё, что меняет запрос не из
        пользовательского ввода, идёт через этот метод.
        """
        self._query_timer.stop()
        self._search.setText(text)
        self._on_query(text)

    def _on_query(self, text: str) -> None:
        if self._view == "rules":
            self._render_rules(text)
        elif self._view == "commands":
            self._render_commands(text)
        elif self._view == "events":
            self._render_events(text)
        elif self._view == "catalog":
            self._render_catalog(text)

    def _wrap(self, inner: str) -> str:
        """Готовый документ для QTextBrowser."""
        return (
            '<html><body style="font-family:Segoe UI;font-size:14px;color:%s;">'
            "%s</body></html>" % (self._palette["text"], inner)
        )

    def _render_error(self, section: str, exc: Exception) -> None:
        """Показать ошибку рендера вместо вылета (баг №1)."""
        self._count.setText("Ошибка")
        self._body.setHtml(self._wrap(
            '<p style="color:%s;font-weight:700;">Не удалось отрисовать «%s».</p>'
            '<p style="color:%s;font-size:12.5px;">%s</p>'
            '<p style="color:%s;font-size:12.5px;">Подробности — в logs/app.log '
            "рядом с программой.</p>"
            % (self._palette.get("danger", "#f85149"), section,
               self._palette.get("muted", "#8a8c94"), str(exc)[:200],
               self._palette.get("muted", "#8a8c94"))
        ))

    # --- жизненный цикл -----------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 (имя задано Qt)
        # Окно прячется, а не уничтожается: следующее открытие — мгновенно.
        event.ignore()
        self.hide()
