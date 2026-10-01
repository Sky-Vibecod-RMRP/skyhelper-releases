"""Безрамочные окна: своя шапка вместо системной полосы заголовка.

Окно без рамки теряет системные кнопки и изменение размера, поэтому всё
сделано руками:

* :class:`TitleBar` — заголовок, кнопки «свернуть»/«закрыть», перетаскивание
  окна мышью (двойной клик по шапке — свернуть), верхний и боковые края
  шапки отдают окну для изменения размера;
* :class:`FramelessMixin` — зона захвата по краям окна и курсоры-стрелки,
  как у обычного окна Windows.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QCursor, QMouseEvent, QPainter, QPalette, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from app.ui import theme
from app.ui.rain import RainOverlay

#: Ширина зоны захвата края окна (в пикселях).
EDGE = 6

#: Скругление собственной рамки окна.
CORNER = 12

# Направления изменения размера: комбинация сторон окна.
_LEFT, _RIGHT, _TOP, _BOTTOM = 1, 2, 4, 8

_CURSORS = {
    _LEFT | _TOP: Qt.CursorShape.SizeFDiagCursor,
    _RIGHT | _BOTTOM: Qt.CursorShape.SizeFDiagCursor,
    _RIGHT | _TOP: Qt.CursorShape.SizeBDiagCursor,
    _LEFT | _BOTTOM: Qt.CursorShape.SizeBDiagCursor,
    _LEFT: Qt.CursorShape.SizeHorCursor,
    _RIGHT: Qt.CursorShape.SizeHorCursor,
    _TOP: Qt.CursorShape.SizeVerCursor,
    _BOTTOM: Qt.CursorShape.SizeVerCursor,
}


class TitleBar(QFrame):
    """Шапка окна: перетаскивание, название, кнопки свернуть/закрыть."""

    def __init__(
        self,
        window: QWidget,
        title: str = "",
        closable: bool = True,
        minimizable: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName("titlebar")
        self._window = window
        self._dragging = False
        self._drag_offset: QPoint | None = None

        self._label = QLabel(title, self)
        self._label.setObjectName("titlebar-label")

        buttons = QHBoxLayout()
        buttons.setSpacing(2)
        buttons.setContentsMargins(0, 0, 0, 0)

        if minimizable:
            min_btn = self._button("min", "–")
            min_btn.clicked.connect(window.showMinimized)
            buttons.addWidget(min_btn)
        if closable:
            close_btn = self._button("close", "✕")
            close_btn.clicked.connect(window.close)
            buttons.addWidget(close_btn)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 6, 0)
        layout.setSpacing(8)
        layout.addWidget(self._label)
        layout.addStretch(1)
        layout.addLayout(buttons)
        self.setFixedHeight(38)

    def _button(self, name: str, text: str) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setObjectName("titlebar-btn")
        btn.setProperty("role", name)
        btn.setFixedSize(30, 26)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    def set_title(self, text: str) -> None:
        self._label.setText(text)

    # --- края шапки = края окна ---

    def _edge_at(self, pos: QPoint) -> int:
        direction = 0
        if pos.x() <= EDGE:
            direction |= _LEFT
        elif pos.x() >= self.width() - EDGE:
            direction |= _RIGHT
        if pos.y() <= EDGE:
            direction |= _TOP
        return direction

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            direction = self._edge_at(event.position().toPoint())
            if direction and hasattr(self._window, "_begin_resize"):
                self._window._begin_resize(direction, event.globalPosition().toPoint())
                return
            self._dragging = True
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self._window.frameGeometry().topLeft()
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if getattr(self._window, "_edge_dir", 0):
            self._window._resize_to(event.globalPosition().toPoint())
            return
        if self._dragging and self._drag_offset is not None:
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if getattr(self._window, "_edge_dir", 0):
            self._window._end_resize()
        self._dragging = False
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._window.isMinimized():
                self._window.showNormal()
            else:
                self._window.showMinimized()
        super().mouseDoubleClickEvent(event)


class _ViewportCursorFilter(QObject):
    """Держит курсор окна над ссылками в тексте.

    QTextBrowser сам ставит системную «руку», как только мышь попадает на
    ссылку, — и окно снова показывало стандартный курсор (баг-репорт №4).
    На сайте та же роль у ``html.sky-cursor-on * { cursor: none }``: курсор
    одинаков везде. При виде «Системный» в настройках фильтр ничего не делает.
    """

    def __init__(self, window) -> None:
        super().__init__(window)
        self._window = window
        self._busy = False

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if (event.type() == QEvent.Type.CursorChange
                and not self._busy and watched is not None):
            custom = getattr(self._window, "_custom_cursor", None)
            if custom is not None:
                self._busy = True
                try:
                    watched.setCursor(custom)
                finally:
                    self._busy = False
        return False


class FramelessMixin:
    """Перетаскивание и изменение размера для окна без системной рамки.

    Окно вызывает :meth:`init_frameless` после создания виджетов и вставляет
    возвращённую шапку первой в свой layout.
    """

    _edge_dir = 0
    _resize_start: QPoint | None = None
    _resize_geo: QRect | None = None
    _resizable = True

    def init_frameless(
        self,
        title: str = "",
        closable: bool = True,
        minimizable: bool = False,
        resizable: bool = True,
    ) -> TitleBar:
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        # Баг-репорт №2: одного FramelessWindowHint мало — Windows 10/11
        # рисует по краю окна служебную полоску цветом системной темы, и на
        # светлой это «белая рамка». Убирается прозрачным фоном окна.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # …но с прозрачным фоном Windows больше НЕ заливает окно сам, и если
        # фон не нарисовать своим paintEvent, окно получается совсем
        # прозрачным (срочный баг-репорт 30.09.2026). Поэтому красим его
        # здесь: собственная скруглённая рамка цветом темы, а не надеемся
        # на системную кисть.
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(theme.BG))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(theme.TEXT))
        self.setPalette(palette)
        self.setAutoFillBackground(False)
        self._resizable = bool(resizable)
        self._edge_dir = 0
        self._resize_start = None
        self._resize_geo = None
        #: Свой курсор окна (картинка); край всегда системный, а после
        #: ухода мыши из окна курсор возвращается сюда, а не к стрелке.
        self._custom_cursor: QCursor | None = None
        self._title_bar = TitleBar(self, title, closable=closable,
                                   minimizable=minimizable)
        # Дождь в окне (баг-репорт №2): слой поверх контента, как капли на
        # стекле. Слой создаётся сейчас, а дети окна — позже, поэтому
        # resizeEvent/showEvent поднимают его наверх каждый раз.
        self._rain_overlay = RainOverlay(self)
        self._rain_overlay.setGeometry(self.rect())
        return self._title_bar

    def set_custom_cursor(self, cursor: QCursor | None) -> None:
        """Поставить свой курсор на всё окно (его же возвращает :meth:`leaveEvent`).

        ``None`` — как в настройках «Системный»: окно возвращается к
        штатной стрелке, а рамка по-прежнему возвращает её после ухода мыши.
        """
        self._custom_cursor = cursor
        fallback = cursor if cursor is not None else QCursor(
            Qt.CursorShape.ArrowCursor)
        self.setCursor(fallback)
        # Виджеты с фильтром (текст со ссылками) тоже обновляются сразу,
        # а не ждут, пока мышь впервые наведётся.
        for widget in getattr(self, "_cursor_widgets", ()):
            target = widget.viewport() if hasattr(widget, "viewport") else widget
            target.setCursor(fallback)

    def keep_custom_cursor(self, widget: QWidget) -> None:
        """Не давать ``widget`` ставить системный курсор вместо курсора окна.

        Нужно для текстовых полей со ссылками: Qt показывает над ними «руку»,
        и окно выглядело так, будто кастомный курсор пропал (баг-репорт №4).
        """
        widgets = getattr(self, "_cursor_widgets", None)
        if widgets is None:
            widgets = []
            self._cursor_widgets = widgets
        if widget in widgets:
            return
        widgets.append(widget)
        target = widget.viewport() if hasattr(widget, "viewport") else widget
        target.installEventFilter(_ViewportCursorFilter(self))

    def set_rain(self, enabled: bool) -> None:
        """Дождь в окне — та же настройка «Дождь на фоне», что и на сайте."""
        overlay = getattr(self, "_rain_overlay", None)
        if overlay is not None:
            overlay.set_enabled(bool(enabled))

    def resizeEvent(self, event) -> None:  # noqa: N802 (имя задано Qt)
        """Слой дождя повторяет размер окна и всегда остаётся поверх детей."""
        super().resizeEvent(event)
        overlay = getattr(self, "_rain_overlay", None)
        if overlay is not None:
            overlay.setGeometry(self.rect())
            overlay.raise_()

    def showEvent(self, event) -> None:  # noqa: N802 (имя задано Qt)
        """Показать дождь поверх: дети создаются позже слоя и перекрывают бы его."""
        super().showEvent(event)
        overlay = getattr(self, "_rain_overlay", None)
        if overlay is not None:
            overlay.setGeometry(self.rect())
            overlay.raise_()

    def _apply_cursor(self, direction: int) -> None:
        """Край окна — стрелка изменения размера, остальное — свой курсор.

        Раньше здесь всегда ставилась системная стрелка, и свой курсор
        пропадал навсегда, как только мышь покидала окно или пользователь
        нажимал кнопку где-нибудь внутри.
        """
        if direction:
            self.setCursor(QCursor(self._cursor_for(direction)))
        elif self._custom_cursor is not None:
            self.setCursor(self._custom_cursor)
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    # --- изменение размера по краям ---

    def _edge_at(self, pos: QPoint) -> int:
        if not self._resizable:
            return 0
        rect = self.rect()
        direction = 0
        if pos.x() <= EDGE:
            direction |= _LEFT
        elif pos.x() >= rect.width() - EDGE:
            direction |= _RIGHT
        if pos.y() <= EDGE:
            direction |= _TOP
        elif pos.y() >= rect.height() - EDGE:
            direction |= _BOTTOM
        return direction

    @staticmethod
    def _cursor_for(direction: int) -> Qt.CursorShape:
        return _CURSORS.get(direction, Qt.CursorShape.ArrowCursor)

    def _begin_resize(self, direction: int, global_pos: QPoint) -> None:
        self._edge_dir = direction
        self._resize_start = global_pos
        self._resize_geo = self.geometry()

    def _resize_to(self, global_pos: QPoint) -> None:
        if self._resize_start is None or self._resize_geo is None:
            return
        delta = global_pos - self._resize_start
        geo = QRect(self._resize_geo)
        min_w, min_h = self.minimumWidth(), self.minimumHeight()
        if self._edge_dir & _LEFT:
            geo.setLeft(geo.right() - max(min_w, geo.width() - delta.x()) + 1)
        if self._edge_dir & _RIGHT:
            geo.setWidth(max(min_w, geo.width() + delta.x()))
        if self._edge_dir & _TOP:
            geo.setTop(geo.bottom() - max(min_h, geo.height() - delta.y()) + 1)
        if self._edge_dir & _BOTTOM:
            geo.setHeight(max(min_h, geo.height() + delta.y()))
        self.setGeometry(geo)

    def _end_resize(self) -> None:
        self._edge_dir = 0
        self._resize_start = None
        self._resize_geo = None

    def paintEvent(self, event) -> None:  # noqa: N802 (имя задано Qt)
        """Собственный фон окна — обязателен при прозрачном фоне.

        Без него Qt не заливает окно системной кистью, и оно просвечивает
        насквозь (окно было полностью прозрачным — срочный баг-репорт).
        Рисуем скруглённый прямоугольник цветом темы: заодно уходят
        углы Windows 11 и та самая «белая рамка» по краю.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = self.rect().adjusted(0, 0, -1, -1)
        painter.setBrush(QColor(theme.BG))
        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.drawRoundedRect(box, CORNER, CORNER)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            direction = self._edge_at(event.position().toPoint())
            if direction:
                self._begin_resize(direction, event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._edge_dir:
            self._resize_to(event.globalPosition().toPoint())
            return
        self._apply_cursor(self._edge_at(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._end_resize()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._apply_cursor(0)      # свой курсор, а не системная стрелка
        super().leaveEvent(event)
