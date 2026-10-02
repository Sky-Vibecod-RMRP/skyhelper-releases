"""Сборка всех сервисов в одном месте (общая часть для окна и консоли)."""
from __future__ import annotations

import logging

from app.config import Config
from app.export.scheduler import ExportScheduler, wait_for_exports
from app.export.service import ExportService
from app.hotkeys.listener import HotkeyListener
from app.paths import config_path, db_path, logs_dir, program_logs_dir
from app.services.live_status import build_status
from app.services.report_counter import ReportCounter
from app.shots.service import ShotsService
from app.stats.service import StatsService
from app.storage.db import Database
from app.tracker.game_watcher import GameWatcher
from app.tracker.session_service import SessionService

# Сайт — второстепенная функция: если его модуль не загрузился (не дописан,
# сломан или вырезан), трекер обязан работать, а об этом написать в ошибке.
try:
    from app.web.server import WebDashboard, WebError
except ImportError as _web_exc:  # pragma: no cover - только при сломанном пакете
    WebDashboard = None  # type: ignore[assignment]

    class WebError(Exception):  # type: ignore[no-redef]
        pass

    WEB_IMPORT_ERROR: str | None = str(_web_exc)
else:
    WEB_IMPORT_ERROR = None

log = logging.getLogger(__name__)


def setup_logging() -> None:
    """Логи и в папке пользователя, и рядом с программой (предложение №1)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(logs_dir() / "app.log", encoding="utf-8"),
            logging.FileHandler(program_logs_dir() / "app.log", encoding="utf-8"),
        ],
    )


class Core:
    def __init__(self) -> None:
        setup_logging()
        self.config = Config.load(config_path())
        self.db = Database(db_path())
        self.session = SessionService(self.db, self.config)
        self.recovered_sessions = self.session.recover()
        self.stats = StatsService(self.db, self.config)
        self.counter = ReportCounter(self.db, self.stats, self.session, self.config)
        self.watcher = self._make_watcher()
        self.exporter = ExportService(self.stats, self.db, self.config)
        self.export_scheduler = self._make_scheduler()
        self.hotkeys = self._make_hotkeys()
        self.shots = self._make_shots()
        self.web = self._make_web()
        self.web_error = WEB_IMPORT_ERROR or ""  # текст ошибки, если сайт не поднялся
        self._running = False

    # --- сборка компонентов, которые зависят от настроек ---

    def _make_watcher(self) -> GameWatcher:
        return GameWatcher(
            self.session, self.config.game_processes, self.config.poll_interval_sec
        )

    def _make_scheduler(self) -> ExportScheduler:
        return ExportScheduler(self.exporter.run, self.config.export_interval_min * 60)

    def _make_hotkeys(self) -> HotkeyListener:
        duty_key = self.config.hotkey_duty

        def toggle_duty() -> object:
            # Причина с именем клавиши — в логе видно, что дежурство
            # выключено хоткеем, а не авто-выключением по закрытию игры.
            return self.session.toggle_duty(f"клавиша {str(duty_key).upper()}")

        return HotkeyListener(
            self.config.hotkey_add, self.config.hotkey_remove,
            self.counter.add, self.counter.undo,
            duty_key, toggle_duty,
            self.config.hotkey_toggle or None,
            self.on_toggle_window,
        )

    def on_toggle_window(self) -> None:
        """Клавиша показа окна: сюда GUI подставляет свой обработчик.

        Без окна (консольный запуск) клавиша просто ничего не делает —
        слушатель об этом не знает и не падает.
        """
        handler = getattr(self, "toggle_window", None)
        if handler is not None:
            handler()

    def _make_shots(self) -> ShotsService:
        """Скриншоты для недельного отчёта: сервис без Qt, результат — колбэк.

        ``on_result`` GUI назначает сам (как ``toggle_window``), поэтому
        консольный запуск спокойно живёт без уведомлений и звука.
        """
        return ShotsService(self.config, self.session)

    def _make_web(self) -> WebDashboard | None:
        if WebDashboard is None:  # пакет сайта не загрузился — работаем без него
            return None
        return WebDashboard(
            lambda: build_status(self.stats, self.session, self.config),
            host=self.config.web_host,
            port=self.config.web_port,
            pin_hash=self.config.web_pin_hash,
            shots=self.shots,
            config=self.config,
        )

    # --- жизненный цикл ---

    def start(self) -> None:
        self._running = True
        self.watcher.start()
        self.hotkeys.start()
        self.export_scheduler.start()
        conflicts = self.shots.start()
        if conflicts:
            log.warning("Клавиши скриншотов не повесились: %s", "; ".join(conflicts))
        self._start_web()

    def stop(self) -> None:
        self._running = False
        self._stop_web()
        self.shots.stop()
        self.export_scheduler.stop()
        if self.export_scheduler.is_alive():
            self.export_scheduler.join(timeout=5)
        # Экспорт читает базу в своём потоке — ждём его, прежде чем закрыть соединение.
        if not wait_for_exports(timeout=15):
            log.warning("Идущий экспорт не завершился к выходу — закрываю базу")
        self.hotkeys.stop()
        self.watcher.stop()
        if self.watcher.is_alive():
            self.watcher.join(timeout=5)  # последний tick не должен работать с закрытой базой
        self.session.shutdown()
        self.db.close()

    def apply_config(self) -> None:
        """Сохранить настройки и перезапустить то, что от них зависит.

        Потоки Python нельзя перезапустить заново, поэтому компоненты
        создаём заново. Вызывается из окна настроек после сохранения.
        """
        self.config.save(config_path())
        if not self._running:
            self.web = self._make_web()
            return

        self.hotkeys.stop()
        self.hotkeys = self._make_hotkeys()
        self.hotkeys.start()

        conflicts = self.shots.reload()
        if conflicts:
            log.warning("Клавиши скриншотов не повесились: %s", "; ".join(conflicts))

        self.watcher.stop()
        if self.watcher.is_alive():
            # Старый поток не должен сделать последнюю проверку уже после замены:
            # иначе он может выключить дежурство по «игре закрыли».
            self.watcher.join(timeout=5)
        self.watcher = self._make_watcher()
        self.watcher.start()

        self.export_scheduler.stop()
        if self.export_scheduler.is_alive():
            self.export_scheduler.join(timeout=5)
        self.export_scheduler = self._make_scheduler()
        self.export_scheduler.start()

        self._stop_web()
        self.web = self._make_web()
        self._start_web()

    # --- локальный сайт ---

    def _start_web(self) -> None:
        if self.web is None:
            self.web_error = WEB_IMPORT_ERROR or "модуль сайта недоступен"
            return
        if not self.config.web_enabled:
            return
        try:
            self.web.start()
            self.web_error = ""
            log.info("Сайт запущен: %s", self.web.url)
        except WebError as exc:
            self.web_error = str(exc)
            log.error("Сайт не запустился: %s", exc)

    def _stop_web(self) -> None:
        if self.web is None:
            return
        try:
            self.web.stop()
        except Exception:
            log.exception("Ошибка при остановке сайта")

    @property
    def web_running(self) -> bool:
        return bool(self.web and self.web.running)

    @property
    def site_url(self) -> str | None:
        return self.web.url if self.web_running else None
