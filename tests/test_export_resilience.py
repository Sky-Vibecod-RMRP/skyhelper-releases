"""Устойчивость экспорта: заблокированные файлы, параллельные запуски, остановка.

Здесь закреплено правило «занятый файл не должен валить остальные отчёты»
(раньше оно соблюдалось только для Excel) и общая блокировка экспорта.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime

import pytest

from app.config import Config
from app.export.scheduler import ExportScheduler, wait_for_exports
from app.export.service import ExportService
from app.stats.service import StatsService
from app.storage.db import Database


def ts(*args) -> int:
    return int(datetime(*args).timestamp())


NOW = ts(2026, 9, 30, 15, 0)


@pytest.fixture
def env(tmp_path):
    config = Config(output_dir=str(tmp_path / "out_dir"))
    db = Database(tmp_path / "t.db")
    sid = db.open_session(ts(2026, 9, 30, 13, 0))
    db.close_session(sid, ts(2026, 9, 30, 14, 0))
    db.add_report_event(ts(2026, 9, 30, 13, 30), 1)
    stats = StatsService(db, config)
    yield config, db, stats
    db.close()


def _lock_png(*args, **kwargs):
    raise PermissionError(13, "Файл занят другим процессом")


def test_locked_png_does_not_block_excel(env, tmp_path, monkeypatch):
    """PNG открыт в просмотрщике — Excel всё равно пишется, а ошибка видна."""
    config, db, stats = env
    monkeypatch.setattr("app.export.service.build_report_image", _lock_png)

    result = ExportService(stats, db, config, clock=lambda: NOW).run()

    assert not result.ok
    assert "PNG" in result.message
    assert (tmp_path / "out_dir" / "SKYHELPER_stats.xlsx").exists()


def test_locked_png_skips_archive_and_still_uploads_google(env, tmp_path, monkeypatch):
    """Копию с заблокированного PNG не делаем, но Google Таблица обновляется."""
    config, db, stats = env
    key = tmp_path / "key.json"
    key.write_text("{}", encoding="utf-8")
    config.gsheet_id = "sheet-id"
    config.gsheet_credentials = str(key)
    uploaded = []
    monkeypatch.setattr("app.export.service.build_report_image", _lock_png)
    monkeypatch.setattr(
        "app.export.service.upload_tables", lambda *a, **k: uploaded.append(a)
    )

    result = ExportService(stats, db, config, clock=lambda: NOW).run()

    assert uploaded, "Google-выгрузка должна пройти даже при заблокированном PNG"
    assert not result.ok
    assert not (tmp_path / "out_dir" / "История").exists()


def test_two_schedulers_never_export_at_once():
    """Замок общий: новый ExportScheduler не стартует, пока работает старый."""
    state = {"active": 0, "peak": 0}
    guard = threading.Lock()

    def job():
        with guard:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.2)
        with guard:
            state["active"] -= 1

    threads = [
        threading.Thread(target=ExportScheduler(job, interval_sec=3600).run_now)
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert state["peak"] == 1


def test_wait_for_exports_waits_for_triggered_job():
    """«Обновить сейчас» — фоновый поток: перед закрытием базы нужно дождаться."""
    finished = threading.Event()
    scheduler = ExportScheduler(
        lambda: (time.sleep(0.3), finished.set()), interval_sec=3600
    )
    scheduler.trigger()

    assert wait_for_exports(timeout=10) is True
    assert finished.is_set()


def test_upload_grows_grid_when_table_outgrows_sheet():
    """Лист «По дням» растёт каждый день — сетку надо расширять, а не упираться в 400."""
    from app.export.gsheets import Table, upload_tables

    class Sheet:
        title = "По дням"

        def __init__(self, rows, cols):
            self.row_count = rows
            self.col_count = cols
            self.resized = None
            self.values = None

        def resize(self, rows=None, cols=None):
            self.resized = (rows, cols)
            self.row_count, self.col_count = rows, cols

        def clear(self):
            pass

        def update(self, values=None, range_name=None):
            self.values = values

        def format(self, rng, fmt):
            pass

        def freeze(self, rows=0):
            pass

    sheet = Sheet(rows=50, cols=6)

    class Spreadsheet:
        def worksheets(self):
            return [sheet]

        def add_worksheet(self, title, rows, cols):
            raise AssertionError("лист уже есть — создавать не нужно")

    class Client:
        def open_by_key(self, key):
            return Spreadsheet()

    big = [[f"строка {i}"] for i in range(80)]  # 80 строк при сетке в 50
    upload_tables(
        {"По дням": Table(big, freeze_rows=1)},
        "sheet-id",
        "key.json",
        client_factory=lambda path: Client(),
    )

    assert sheet.resized == (100, 6)  # 80 строк + запас 20
    assert sheet.values == big
