from datetime import datetime

import pytest

from app.config import Config
from app.export.gsheets import GoogleSheetsError, build_tables, upload_tables
from app.export.service import ExportService
from app.export.snapshot import build_snapshot
from app.stats.service import StatsService
from app.storage.db import Database


def ts(*args) -> int:
    return int(datetime(*args).timestamp())


NOW = ts(2026, 9, 30, 15, 0)


@pytest.fixture
def env(tmp_path):
    config = Config(output_dir=str(tmp_path / "out"))
    db = Database(tmp_path / "g.db")
    sid = db.open_session(ts(2026, 9, 22, 10, 0))
    db.close_session(sid, ts(2026, 9, 22, 13, 0))
    for _ in range(5):
        db.add_report_event(ts(2026, 9, 22, 11, 0), 1)
    sid = db.open_session(ts(2026, 9, 29, 10, 0))
    db.close_session(sid, ts(2026, 9, 29, 12, 30))
    for _ in range(3):
        db.add_report_event(ts(2026, 9, 29, 11, 0), 1)
    stats = StatsService(db, config)
    yield config, db, stats
    db.close()


class FakeSheet:
    def __init__(self, title, rows=50, cols=6):
        self.title = title
        self.row_count = rows
        self.col_count = cols
        self.values = None
        self.cleared = 0
        self.bold = []
        self.frozen = 0

    def resize(self, rows=None, cols=None):
        if rows:
            self.row_count = rows
        if cols:
            self.col_count = cols

    def clear(self):
        self.cleared += 1

    def update(self, values=None, range_name=None):
        self.values = values

    def format(self, rng, fmt):
        self.bold.append(rng)

    def freeze(self, rows=0):
        self.frozen = rows


class FakeSpreadsheet:
    def __init__(self, titles=()):
        self.sheets = {t: FakeSheet(t) for t in titles}

    def worksheets(self):
        return list(self.sheets.values())

    def add_worksheet(self, title, rows, cols):
        self.sheets[title] = FakeSheet(title, rows=rows, cols=cols)
        return self.sheets[title]


class FakeClient:
    def __init__(self, spreadsheet):
        self.spreadsheet = spreadsheet
        self.opened = None

    def open_by_key(self, key):
        self.opened = key
        return self.spreadsheet


def test_tables_match_excel_layout(env):
    config, db, stats = env
    tables = build_tables(build_snapshot(stats, db, config, NOW))
    rows = tables["Неделя"].rows
    assert rows[4] == ["Показатель", "Факт", "Норма", "Выполнено"]
    assert rows[5][:3] == ["Онлайн (ч:мм)", "2:30", "70:00"]
    assert rows[6][:3] == ["Обращения", 3, 600]
    assert rows[8] == ["Сегодня: план на день и факт"]
    assert rows[9] == ["Показатель", "План в день", "Факт сегодня", "Выполнено"]
    assert rows[10] == ["Онлайн (ч:мм)", "10:00", "0:00", "0%"]
    assert rows[11] == ["Обращения", 86, 0, "0%"]
    assert rows[13] == ["Сравнение с прошлой неделей"]
    assert rows[15] == ["Онлайн (ч:мм)", "2:30", "3:00", "\u22120 ч 30 мин", "\u221217%"]
    assert rows[16] == ["Обращения", 3, 5, "\u22122", "\u221240%"]
    assert rows[18] == ["Прогноз к концу недели при текущем темпе"]
    assert rows[20] == ["Онлайн (ч:мм)", "5:50", "70:00", "8%"]
    assert rows[21] == ["Обращения", 7, 600, "1%"]
    assert rows[23] == ["Итог за месяц: Сентябрь 2026"]
    assert rows[25][:2] == ["Онлайн (ч:мм)", "5:30"]
    assert rows[26][:2] == ["Обращения", 8]
    days = tables["По дням"].rows
    assert days[0] == ["Дата", "День", "Онлайн (ч:мм)", "Часы", "Обращения"]
    assert days[1] == ["22.09.2026", "Вт", "3:00", 3.0, 5]   # от раннего дня к позднему
    assert days[2] == ["29.09.2026", "Вт", "2:30", 2.5, 3]
    assert days[3] == ["30.09.2026", "Ср", "0:00", 0.0, 0]    # последняя строка — сегодня


def test_upload_creates_missing_sheets_and_overwrites_existing(env):
    config, db, stats = env
    tables = build_tables(build_snapshot(stats, db, config, NOW))
    spreadsheet = FakeSpreadsheet(titles=["Неделя"])       # «По дням» ещё нет
    client = FakeClient(spreadsheet)
    upload_tables(tables, "SHEET_ID", "key.json", client_factory=lambda path: client)
    assert client.opened == "SHEET_ID"
    assert set(spreadsheet.sheets) == {"Неделя", "По дням"}
    for sheet in spreadsheet.sheets.values():
        assert sheet.cleared == 1 and sheet.values
    assert spreadsheet.sheets["По дням"].frozen == 1
    assert "1:1" in spreadsheet.sheets["По дням"].bold


def test_upload_maps_network_and_key_errors_to_readable_message():

    def no_key(path):
        raise FileNotFoundError(path)

    with pytest.raises(GoogleSheetsError) as info:
        upload_tables({}, "id", "nokey.json", client_factory=no_key)
    assert "Не найден ключ" in str(info.value)

    def offline(path):
        raise ConnectionError("dns")

    with pytest.raises(GoogleSheetsError) as info:
        upload_tables({}, "id", "key.json", client_factory=offline)
    assert "Не удалось связаться" in str(info.value)


def test_service_uploads_to_google_when_configured(env, tmp_path, monkeypatch):
    config, db, stats = env
    config.gsheet_id = "ABC123"
    key = tmp_path / "key.json"
    key.write_text("{}")
    config.gsheet_credentials = str(key)
    calls = []
    monkeypatch.setattr(
        "app.export.service.upload_tables",
        lambda tables, sheet_id, cred: calls.append((sorted(tables), sheet_id, cred)),
    )
    result = ExportService(stats, db, config, clock=lambda: NOW).run()
    assert result.ok and not result.warning and "Google" in result.message
    assert calls == [(["Неделя", "По дням"], "ABC123", str(key))]


def test_google_failure_keeps_local_export_and_shows_warning(env, tmp_path, monkeypatch):
    config, db, stats = env
    config.gsheet_id = "ABC123"
    key = tmp_path / "key.json"
    key.write_text("{}")
    config.gsheet_credentials = str(key)

    def boom(*args):
        raise GoogleSheetsError("Не удалось связаться с Google: offline")

    monkeypatch.setattr("app.export.service.upload_tables", boom)
    result = ExportService(stats, db, config, clock=lambda: NOW).run()
    assert result.ok and "offline" in result.warning
    assert (tmp_path / "out" / "SKYHELPER_stats.xlsx").exists()


def test_missing_google_key_is_reported(env, tmp_path):
    config, db, stats = env
    config.gsheet_id = "ABC123"
    config.gsheet_credentials = str(tmp_path / "missing.json")
    result = ExportService(stats, db, config, clock=lambda: NOW).run()
    assert result.ok and "нет ключа" in result.warning


def test_google_disabled_by_default(env):
    config, db, stats = env
    service = ExportService(stats, db, config, clock=lambda: NOW)
    assert not service.google_enabled
    assert service.run().warning == ""
