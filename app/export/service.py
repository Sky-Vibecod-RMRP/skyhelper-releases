"""Обновление отчётов: собирает снимок и пишет Excel, PNG и (если настроено) Google Таблицу."""
from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.config import Config
from app.export.excel_export import ExportError, write_excel
from app.export.gsheets import GoogleSheetsError, build_tables, upload_tables
from app.export.report_image import build_report_image
from app.export.snapshot import Snapshot, build_snapshot
from app.paths import default_google_key_path, default_output_dir
from app.stats.service import StatsService
from app.storage.db import Database

log = logging.getLogger(__name__)

ARCHIVE_DIR_NAME = "История"


@dataclass(frozen=True)
class ExportResult:
    ok: bool
    message: str
    at: int
    warning: str = ""  # локальные файлы обновлены, но что-то дополнительное не вышло (Google)


class ExportService:
    def __init__(
        self,
        stats: StatsService,
        db: Database,
        config: Config,
        clock: Callable[[], float] = time.time,
    ):
        self._stats = stats
        self._db = db
        self._config = config
        self._clock = clock
        self.on_result: Callable[[ExportResult], None] | None = None

    @property
    def output_dir(self) -> Path:
        return Path(self._config.output_dir) if self._config.output_dir else default_output_dir()

    @property
    def excel_path(self) -> Path:
        if self._config.excel_path:
            return Path(self._config.excel_path)
        return self.output_dir / "SKYHELPER_stats.xlsx"

    @property
    def report_image_path(self) -> Path:
        if self._config.report_image_path:
            return Path(self._config.report_image_path)
        return self.output_dir / "SKYHELPER_report.png"

    @property
    def google_enabled(self) -> bool:
        return bool(self._config.gsheet_id.strip())

    @property
    def google_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self._config.gsheet_id.strip()}"

    def _archive_image(self, snapshot: Snapshot) -> None:
        """Копия PNG с датой начала недели: к концу недели в архиве лежит итоговый отчёт."""
        if not self._config.archive_weekly:
            return
        folder = self.report_image_path.parent / ARCHIVE_DIR_NAME
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"SKYHELPER_report_{snapshot.week_start:%Y-%m-%d}.png"
        shutil.copyfile(self.report_image_path, target)

    def _upload_google(self, snapshot: Snapshot) -> str:
        """Возвращает текст предупреждения или пустую строку, если всё хорошо."""
        key = self._config.gsheet_credentials.strip() or str(default_google_key_path())
        if not Path(key).exists():
            return f"Google Таблица: нет ключа, положи его сюда: {key}"
        try:
            upload_tables(build_tables(snapshot), self._config.gsheet_id.strip(), key)
        except GoogleSheetsError as exc:
            log.warning("Google Таблица: %s", exc)
            return f"Google Таблица: {exc}"
        except Exception:
            log.exception("Непредвиденная ошибка выгрузки в Google")
            return "Google Таблица: не удалось обновить, подробности в журнале"
        return ""

    def run(self) -> ExportResult:
        now = int(self._clock())
        try:
            snapshot = build_snapshot(self._stats, self._db, self._config, now)
            # Занятый один файл не мешает остальным отчётам обновиться:
            # ошибка каждого формата собирается отдельно, а не роняет весь экспорт.
            excel_error = ""
            try:
                write_excel(snapshot, self.excel_path)
            except ExportError as exc:
                log.warning("Экспорт Excel: %s", exc)
                excel_error = str(exc)

            png_error = ""
            try:
                build_report_image(snapshot, self.report_image_path)
            except OSError as exc:
                # PNG открыт в просмотрщике/Paint или папка недоступна.
                log.warning("PNG-отчёт: %s", exc)
                png_error = (
                    "PNG-отчёт открыт в другой программе, закрой его"
                    if isinstance(exc, PermissionError)
                    else f"Не удалось записать PNG-отчёт: {exc.strerror or exc}"
                )
            else:
                try:
                    self._archive_image(snapshot)
                except OSError:
                    log.exception("Не удалось сохранить копию отчёта в архив")

            warning = self._upload_google(snapshot) if self.google_enabled else ""
            file_error = " ".join(part for part in (excel_error, png_error) if part)
            if file_error:
                result = ExportResult(False, file_error, now, warning)
            else:
                message = "Excel и PNG-отчёт обновлены"
                if self.google_enabled and not warning:
                    message += ", Google Таблица тоже"
                result = ExportResult(True, message, now, warning)
        except Exception:
            log.exception("Непредвиденная ошибка экспорта")
            result = ExportResult(False, "Не удалось обновить таблицу, подробности в журнале", now)
        if self.on_result:
            self.on_result(result)
        return result
