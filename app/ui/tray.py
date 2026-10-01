from __future__ import annotations

from typing import Callable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from app.ui import theme


def make_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(theme.ACCENT))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(6, 6, 52, 52)
    painter.end()
    return QIcon(pixmap)


def create_tray(
    app: QApplication,
    window: QWidget,
    actions: Sequence[tuple[str, Callable[[], None]]] = (),
    on_duty_toggle: Callable[[bool], None] | None = None,
    duty_title: str = "Я на дежурстве",
    status_provider: Callable[[], str] | None = None,
    site_provider: Callable[[], str | None] | None = None,
    on_settings: Callable[[], None] | None = None,
    on_helper: Callable[[], None] | None = None,
    on_week_report: Callable[[], None] | None = None,
) -> QSystemTrayIcon:
    """Собрать меню трея.

    status_provider  — строка с живыми цифрами сверху (обновляется при открытии меню);
    site_provider    — адрес сайта (None = пункт скрыт);
    on_settings      — открыть экран настроек;
    on_helper        — открыть окно «Хелпер» (разделы + правила RMRP);
    on_week_report   — открыть папку недельного отчёта (только этот пункт,
                       без подменю и счётчиков — как в ТЗ).
    """
    tray = QSystemTrayIcon(make_icon(), app)
    tray.setToolTip("SKY HELPER")

    menu = QMenu()

    status_action: QAction | None = None
    if status_provider is not None:
        status_action = QAction(status_provider(), menu)
        status_action.setEnabled(False)
        menu.addAction(status_action)
        menu.addSeparator()

    open_action = QAction("Открыть", menu)
    open_action.triggered.connect(lambda: _show(window))
    menu.addAction(open_action)

    if on_duty_toggle is not None:
        duty_action = QAction(duty_title, menu)
        duty_action.setCheckable(True)
        duty_action.triggered.connect(lambda checked=False: on_duty_toggle(bool(checked)))
        menu.addAction(duty_action)
        tray.duty_action = duty_action  # type: ignore[attr-defined]

    site_action: QAction | None = None
    if site_provider is not None:
        site_action = QAction("Открыть сайт", menu)
        menu.addAction(site_action)

    if on_helper is not None:
        helper_action = QAction("SKY HELPER…", menu)
        helper_action.triggered.connect(on_helper)
        menu.addAction(helper_action)

    if on_week_report is not None:
        week_action = QAction("Посмотреть недельный отчёт", menu)
        week_action.triggered.connect(lambda _checked=False: on_week_report())
        menu.addAction(week_action)

    settings_action: QAction | None = None
    if on_settings is not None:
        settings_action = QAction("Настройки…", menu)
        settings_action.triggered.connect(on_settings)
        menu.addAction(settings_action)

    if actions:
        menu.addSeparator()
    for title, callback in actions:
        action = QAction(title, menu)
        action.triggered.connect(lambda _checked=False, cb=callback: cb())
        menu.addAction(action)

    menu.addSeparator()
    quit_action = QAction("Выход", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)

    def refresh() -> None:
        """Данные подтягиваем в момент открытия меню — свежие и без лишних таймеров."""
        if status_action is not None and status_provider is not None:
            status_action.setText(status_provider())
        if site_action is not None and site_provider is not None:
            url = site_provider()
            site_action.setVisible(bool(url))
            if url:
                site_action.setText(f"Открыть сайт  {url}")

    menu.aboutToShow.connect(refresh)
    refresh()

    if site_action is not None:
        def open_site(_checked: bool = False, provider=site_provider) -> None:
            url = provider()
            if url:
                import webbrowser

                webbrowser.open(url)

        site_action.triggered.connect(open_site)

    tray.setContextMenu(menu)

    def on_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            _show(window)

    tray.activated.connect(on_activated)
    tray.show()
    return tray


def _show(window: QWidget) -> None:
    window.show()
    window.raise_()
    window.activateWindow()
