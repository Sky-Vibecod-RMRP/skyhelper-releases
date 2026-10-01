"""Запуск с окном и треем:  python -m app.gui_main [--minimized]"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from app.config import Config
from app.core import Core, setup_logging
from app.paths import config_path, migrate_legacy_dirs
from app.services.report_counter import (
    REASON_GAME_NOT_RUNNING,
    REASON_NOT_ON_DUTY,
    REASON_NOTHING_TO_UNDO,
    ReportResult,
)
from app.export.service import ExportResult
from app.stats.pace import pace_message
from app.stats.streak import current_streak
from app.ui import sounds, theme
from app.ui.app_icon import apply_window_icon
from app.ui.helper_window import HelperWindow
from app.ui.settings_dialog import SettingsDialog
from app.ui.toast import ToastOverlay
from app.ui.tray import create_tray
from app.util import format_duration

PACE_INTERVAL_MS = 2 * 60 * 60 * 1000  # напоминание о темпе раз в 2 часа


def _log_uncaught(exc_type, exc_value, exc_tb) -> None:
    """Необработанная ошибка — пишем в лог, а не роняем программу молча."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    try:
        from app.ui import theme
        import logging
        logging.getLogger("sky").error(
            "Необработанная ошибка:\n%s",
            "".join(__import__("traceback").format_exception(exc_type, exc_value, exc_tb)),
        )
    except Exception:
        sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _log_uncaught


class Bridge(QObject):
    """Передаёт события из фоновых потоков в главный поток интерфейса."""

    report_result = Signal(object)
    game_state = Signal(bool)
    export_done = Signal(object)
    duty_changed = Signal(bool)
    shot_result = Signal(object)   # результат нажатия клавиши категории
    # Прятание окон на мгновение снимка: слушатель клавиш живёт в своём
    # потоке, поэтому окна трогаем только здесь, в главном, и через
    # threading.Event ждём, пока они реально спрячутся.
    hide_request = Signal(object)
    show_request = Signal(object)


def describe(result: ReportResult, norm: int, duty_key: str = "F10") -> tuple[str, bool]:
    if result.ok:
        sign = "+1" if result.delta > 0 else "−1"
        return f"{sign} обращение  ·  {result.week_total} из {norm}", True
    if result.reason == REASON_GAME_NOT_RUNNING:
        return "Не засчитано: игра не запущена", False
    if result.reason == REASON_NOT_ON_DUTY:
        return f"Не засчитано: начни дежурство ({duty_key})", False
    if result.reason == REASON_NOTHING_TO_UNDO:
        return "Нечего отменять: 0 обращений за неделю", False
    return "Не засчитано", False


def apply_window_effects(window, config, theme_name: str) -> None:
    """Дождь и курсор окна — те же настройки, что и на сайте.

    Баг-репорт №2 (дождя в приложении не было) и №4 + предложение №1
    (курсор со временем становился стандартным): рисунок курсора берётся не
    из PNG рядом с exe, а рисуется в коде (``app.ui.cursor``), дождь — свой
    слой поверх окна (``app.ui.rain``). Оба живут на одной настройке с сайтом,
    поэтому окно и сайт всегда выглядят одинаково.

    ``set_custom_cursor`` принимает и None («Системный» в настройках) —
    тогда окно просто возвращается к штатной стрелке.
    """
    from app.ui.cursor import cursor_for

    accent = theme.THEMES.get(theme_name, {}).get("accent", theme.ACCENT)
    # Не setCursor(): рамка окна сама ставит курсоры и возвращала бы
    # системную стрелку после ухода мыши из окна.
    window.set_custom_cursor(cursor_for(
        getattr(config, "cursor_style", "white"), accent))
    window.set_rain(bool(getattr(config, "rain_enabled", True)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minimized", action="store_true", help="запуск сразу в трей")
    args = parser.parse_args()

    # Ребрендинг: данные из старых папок (RMRP Admin Tracker) переезжают
    # в новые (SKY HELPER) до первого чтения конфига.
    migrate_legacy_dirs()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    # Иконка окна: без неё панель задач берёт иконку exe из кэша Windows
    # и после автообновления показывает иконку прошлой версии.
    apply_window_icon(app)

    # Экран входа (вариант B): логин + пароль из настроек.
    # Тему применяем ДО показа окна входа — иначе оно рисуется системным стилем.
    config = Config.load(config_path())
    app.setStyleSheet(theme.apply(config.ui_theme))

    # Журнал настраиваем сразу: отказ по лицензии тоже должен в него попасть
    # (иначе он теряется — Core(), который включает логи, мы ещё не создавали).
    setup_logging()

    # Лицензия: в собранный exe пускаем только с валидным ключом (привязка
    # к ПК, срок, список отзывов). В исходниках проверка выключена, пока
    # ключ не активирован локально.
    from app.ui.activation_dialog import ensure_licensed

    if not ensure_licensed(config):
        return          # ключ не введён — выходим

    # Локальный сайт: адрес http://sky-grafana.rmrp/ работает через запись
    # в hosts. Программа идёт от администратора (RUNASADMIN), поэтому
    # дописываем её молча — после активации сайт открывается сразу; без
    # прав остаётся http://127.0.0.1/ и батник install-sky-grafana.bat.
    from app.hosts import ensure_local_domain

    ensure_local_domain()

    # Обновления: сверяем версию с манифестом (раз в несколько часов).
    # Новая есть — предлагаем обновиться в течение дня; срок прошёл —
    # старая версия не пускается, только обновление или выход.
    from app.ui.update_dialog import run_update_gate

    if not run_update_gate(config):
        return          # обновление запущено (программа перезапустится) или выход

    if config.login and config.password_hash and not config.remember_me:
        from app.ui.login_dialog import LoginDialog
        dialog = LoginDialog(config.login, config.password_hash)
        if not dialog.exec():
            return          # вход не пройден — выходим
        if dialog.remember_checked():
            config.remember_me = True
            config.save(config_path())

    core = Core()
    toast = ToastOverlay()
    bridge = Bridge()

    def signal(event: str) -> None:
        sounds.play(core.config.sound_theme, event)

    def open_report() -> None:
        path = core.exporter.report_image_path
        if path.exists() and hasattr(os, "startfile"):
            os.startfile(path)
        else:
            toast.show_message("PNG-отчёт ещё не создан", ok=False)

    def open_table() -> None:
        path = core.exporter.excel_path
        if path.exists() and hasattr(os, "startfile"):
            os.startfile(path)  # только Windows
        else:
            toast.show_message("Файл таблицы ещё не создан", ok=False)

    def open_folder() -> None:
        folder = core.exporter.output_dir
        folder.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(folder)

    def open_week_report() -> None:
        """Пункт трея: открыть папку текущей недели (без подменю и счётчиков)."""
        folder = core.shots.open_week()
        if folder is None:
            toast.show_message("Не удалось создать папку недели", ok=False, duration_ms=4000)
        elif hasattr(os, "startfile"):
            os.startfile(folder)

    def open_google() -> None:
        if core.exporter.google_enabled:
            webbrowser.open(core.exporter.google_url)
        else:
            toast.show_message(
                "Google Таблица не настроена: укажи ID в настройках",
                ok=False, duration_ms=4000,
            )

    def open_site() -> None:
        if core.site_url:
            webbrowser.open(core.site_url)
        elif core.web_error:
            toast.show_message(f"Сайт не запустился: {core.web_error}", ok=False, duration_ms=5000)
        else:
            toast.show_message("Сайт выключен: включи его в настройках", ok=False, duration_ms=4000)

    def tray_status() -> str:
        """Строка с живыми цифрами в меню трея."""
        now = int(time.time())
        today = core.stats.today(now)
        streak = current_streak(core.stats, core.config, now)
        return (f"Сегодня: {format_duration(today.online_seconds)} · "
                f"{today.reports} обр. · стрик {streak.days}")

    def apply_on_top(widget) -> None:
        """Окно поверх других окон — если это включено в настройках."""
        widget.setWindowFlag(
            Qt.WindowType.WindowStaysOnTopHint, bool(core.config.window_on_top)
        )

    def _show_on_top(widget) -> None:
        """Показать окно поверх игры: флаг, показ, поднять (баг №8).

        Игра в полноэкранном режиме может перехватывать фокус, поэтому окно
        поднимаем дважды — сразу и чуть позже.
        """
        apply_on_top(widget)
        if widget.isMinimized():
            widget.showNormal()
        else:
            widget.show()
        widget.raise_()
        widget.activateWindow()
        QTimer.singleShot(150, lambda: (widget.raise_(), widget.activateWindow()))

    def toggle_window() -> None:
        """Insert: спрятать окно или показать его поверх игры."""
        if window.isVisible():
            window.hide()
            return
        _show_on_top(window)

    core.toggle_window = toggle_window  # так горячая клавиша достучится до окна

    def open_helper() -> None:
        window.apply_theme(core.config.ui_theme)
        window.set_output_dir(str(core.exporter.output_dir))
        _show_on_top(window)

    def open_settings() -> None:
        dialog = SettingsDialog(core, window)
        if dialog.exec():
            app.setStyleSheet(theme.apply(core.config.ui_theme))
            window.apply_theme(core.config.ui_theme)
            apply_on_top(window)      # «поверх игры» могло включиться/выключиться
            # Дождь и курсор настраиваются там же, что и на сайте, — окно
            # должно перерисоваться с новым выбором сразу.
            apply_window_effects(window, core.config, core.config.ui_theme)
            if window.isVisible():
                window.show()         # перерисовать окно уже с новым флагом
            window.refresh()
            toast.show_message("Настройки сохранены", ok=True)

    duty_key = core.config.hotkey_duty.upper()
    # Одно окно на всё (предложение №1 из баг-репорта): статистика, справочник,
    # правила и помощь живут разделами в одном SKY HELPER. Закрытие = свернуть.
    window = HelperWindow(
        theme_name=core.config.ui_theme,
        output_dir=str(core.exporter.output_dir),
        core=core,
        actions=[
            ("Отчёт сейчас", core.export_scheduler.trigger),
            ("Открыть сайт", open_site),
            ("Настройки", open_settings),
        ],
    )
    # Дождь и курсор — по настройкам (баг-репорты №2 и №4): рисунок курсора
    # рисуется в коде, а не берётся из PNG рядом с exe, — он больше не может
    # «пропасть» и превратиться в стандартный.
    apply_window_effects(window, core.config, core.config.ui_theme)
    tray = create_tray(
        app,
        window,
        [
            ("Обновить таблицу сейчас", core.export_scheduler.trigger),
            ("Открыть папку с отчётом", open_folder),
            ("Открыть таблицу Excel", open_table),
            ("Открыть PNG-отчёт", open_report),
            ("Открыть Google Таблицу", open_google),
        ],
        on_duty_toggle=core.session.set_duty if core.config.require_duty else None,
        duty_title=f"Я на дежурстве ({duty_key})",
        status_provider=tray_status,
        site_provider=lambda: core.site_url,
        on_settings=open_settings,
        on_helper=open_helper,
        on_week_report=open_week_report,
    )

    norm = core.config.weekly_reports_norm
    bridge.game_state.connect(lambda _running: window.refresh())

    def on_duty_changed(on: bool) -> None:
        action = getattr(tray, "duty_action", None)
        if action is not None:
            action.setChecked(on)
        window.refresh()
        signal("duty_on" if on else "duty_off")
        if on:
            toast.show_message("Дежурство начато, онлайн считается", ok=True)
        else:
            toast.show_message("Дежурство закончено", ok=False)

    def on_report(result: ReportResult) -> None:
        toast.show_message(*describe(result, norm, duty_key))
        if result.ok:
            signal("report_add" if result.delta > 0 else "report_undo")
        else:
            signal("error")

    def on_export(result: ExportResult) -> None:
        window.set_export_status(result)
        signal("success" if result.ok else "error")

    bridge.duty_changed.connect(on_duty_changed)
    core.session.on_duty_change = bridge.duty_changed.emit
    bridge.export_done.connect(on_export)
    core.exporter.on_result = bridge.export_done.emit
    bridge.report_result.connect(on_report)
    core.counter.on_result = bridge.report_result.emit  # иначе плашка F9 не покажется
    core.session.on_state_change = bridge.game_state.emit

    # --- Скриншоты для недельного отчёта ---------------------------------
    # Свои окна прячем только на момент снимка (по ТЗ — 0,2 с) и возвращаем
    # ровно те, что были показаны. Всё это выполняется в главном потоке:
    # слушатель клавиш категории живёт в отдельном потоке и не имеет права
    # трогать виджеты напрямую.
    _shot_hidden: dict[str, bool] = {}

    def _apply_hide(done) -> None:
        _shot_hidden.clear()
        if window.isVisible():
            _shot_hidden["window"] = True
            window.hide()
        if toast.isVisible():
            _shot_hidden["toast"] = True
            toast.hide()
        done.set()

    def _apply_show(done) -> None:
        if _shot_hidden.pop("toast", False):
            toast.show()
        if _shot_hidden.pop("window", False):
            window.show()
        _shot_hidden.clear()
        done.set()

    def _sync(signal_) -> None:
        """Спросить главный поток и дождаться ответа (с потолком по времени)."""
        done = threading.Event()
        signal_.emit(done)
        done.wait(1.0)

    def hide_for_shot() -> None:
        _sync(bridge.hide_request)

    def show_after_shot() -> None:
        _sync(bridge.show_request)

    def on_shot(result) -> None:
        """Плашка и звук: свой переключатель звука, тема общей не мешает."""
        if result.message:
            text = result.message
            if result.warning:
                text = f"{text}\n⚠ {result.warning}"
            toast.show_message(text, ok=result.ok, duration_ms=5000)
        # Звучим только настоящие исходы: у «ещё снимается» и «создана папка
        # новой недели» звука нет, иначе радостный аккорд звучал бы на отказе.
        if core.config.shots_sound and result.kind in (
            "saved", "blocked", "black", "write_fail"
        ):
            sounds.play_shot(result.kind)

    bridge.hide_request.connect(_apply_hide)
    bridge.show_request.connect(_apply_show)
    bridge.shot_result.connect(on_shot)
    core.shots.hide_windows = hide_for_shot
    core.shots.show_windows = show_after_shot
    core.shots.on_result = bridge.shot_result.emit

    def show_pace() -> None:
        if core.session.is_counting:
            today = core.stats.today(int(time.time()))
            toast.show_message(pace_message(today, core.config), ok=True, duration_ms=7000)

    pace_timer = QTimer()
    pace_timer.timeout.connect(show_pace)
    pace_timer.start(PACE_INTERVAL_MS)

    app.aboutToQuit.connect(core.stop)
    core.start()
    if core.web_error:
        toast.show_message(f"Сайт не запустился: {core.web_error}", ok=False, duration_ms=6000)

    if not args.minimized or not QSystemTrayIcon.isSystemTrayAvailable():
        apply_on_top(window)
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
