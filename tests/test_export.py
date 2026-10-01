from datetime import date, datetime, timedelta

import pytest

from app.config import Config
from app.export.excel_export import ExportError, write_excel
from app.export.scheduler import ExportScheduler
from app.export.service import ExportService
from app.export.snapshot import build_snapshot
from app.stats.service import StatsService
from app.storage.db import Database


def ts(*args) -> int:
    return int(datetime(*args).timestamp())


NOW = ts(2026, 9, 30, 15, 0)  # среда


@pytest.fixture
def env(tmp_path):
    config = Config(output_dir=str(tmp_path / "out_dir"))
    db = Database(tmp_path / "t.db")
    # вторник: 2 часа игры и 3 обращения; сегодня: час игры и 1 обращение
    sid = db.open_session(ts(2026, 9, 29, 10, 0))
    db.close_session(sid, ts(2026, 9, 29, 12, 0))
    for _ in range(3):
        db.add_report_event(ts(2026, 9, 29, 11, 0), 1)
    sid = db.open_session(ts(2026, 9, 30, 13, 0))
    db.close_session(sid, ts(2026, 9, 30, 14, 0))
    db.add_report_event(ts(2026, 9, 30, 13, 30), 1)
    stats = StatsService(db, config)
    yield config, db, stats
    db.close()


def test_first_activity(env):
    _, db, _ = env
    assert db.first_activity_ts() == ts(2026, 9, 29, 10, 0)


def test_snapshot_days_and_week(env):
    config, db, stats = env
    snap = build_snapshot(stats, db, config, NOW)
    assert snap.week_start == date(2026, 9, 28)
    assert snap.week_end == date(2026, 10, 4)
    assert [d.day for d in snap.days] == [date(2026, 9, 30), date(2026, 9, 29)]
    assert (snap.days[0].online_seconds, snap.days[0].reports) == (3600, 1)
    assert (snap.days[1].online_seconds, snap.days[1].reports) == (7200, 3)
    assert snap.week.stats.online_seconds == 10800
    assert snap.week.stats.reports == 4


def test_snapshot_without_data_has_today_row(tmp_path):
    db = Database(tmp_path / "e.db")
    config = Config()
    snap = build_snapshot(StatsService(db, config), db, config, NOW)
    assert len(snap.days) == 1 and snap.days[0].reports == 0
    db.close()


def as_days(value) -> float:
    """openpyxl отдаёт ячейки формата [h]:mm как timedelta."""
    return value.total_seconds() / 86400 if hasattr(value, "total_seconds") else value


def test_excel_file_content(env, tmp_path):
    from openpyxl import load_workbook

    config, db, stats = env
    path = tmp_path / "out" / "stats.xlsx"
    write_excel(build_snapshot(stats, db, config, NOW), path)

    wb = load_workbook(path)
    week = wb["Неделя"]
    assert as_days(week["B6"].value) == pytest.approx(10800 / 86400)
    assert as_days(week["C6"].value) == pytest.approx(70 / 24)
    assert week["B7"].value == 4 and week["C7"].value == 600
    # блок «Сегодня»: план на день и факт за 30.09
    assert as_days(week["B11"].value) == pytest.approx(70 / 7 / 24)
    assert as_days(week["C11"].value) == pytest.approx(1 / 24)

    days = wb["По дням"]
    assert days["A2"].value.date() == date(2026, 9, 29)  # по порядку: от раннего дня
    assert days["A3"].value.date() == date(2026, 9, 30)
    assert days["D2"].value == 2 and days["E2"].value == 3  # Часы, Обращения
    assert days["D3"].value == 1 and days["E3"].value == 1
    assert not list((tmp_path / "out").glob("*.tmp*"))  # временный файл убран


def test_export_service_reports_locked_file(env, tmp_path, monkeypatch):
    config, db, stats = env
    config.excel_path = str(tmp_path / "s.xlsx")
    service = ExportService(stats, db, config, clock=lambda: NOW)

    def locked(*args, **kwargs):
        raise ExportError("Файл Excel открыт в другой программе, закрой его")

    monkeypatch.setattr("app.export.service.write_excel", locked)
    results = []
    service.on_result = results.append
    result = service.run()
    assert not result.ok and "открыт" in result.message
    assert results == [result]


def test_export_service_success(env, tmp_path):
    config, db, stats = env
    config.excel_path = str(tmp_path / "ok.xlsx")
    result = ExportService(stats, db, config, clock=lambda: NOW).run()
    assert result.ok and (tmp_path / "ok.xlsx").exists()
    assert not result.warning


def test_scheduler_run_now_survives_job_errors():
    calls = []

    def job():
        calls.append(1)
        raise RuntimeError("boom")

    scheduler = ExportScheduler(job, interval_sec=3600)
    scheduler.run_now()
    scheduler.run_now()
    assert calls == [1, 1]


# ---------- прошлая неделя, месяц, папка, архив ----------

def _db_with_history(tmp_path):
    db = Database(tmp_path / "h.db")
    # прошлая неделя (21-27 сентября): 3 часа и 5 обращений во вторник 22-го
    sid = db.open_session(ts(2026, 9, 22, 10, 0))
    db.close_session(sid, ts(2026, 9, 22, 13, 0))
    for _ in range(5):
        db.add_report_event(ts(2026, 9, 22, 11, 0), 1)
    # эта неделя: 2 часа и 3 обращения во вторник 29-го
    sid = db.open_session(ts(2026, 9, 29, 10, 0))
    db.close_session(sid, ts(2026, 9, 29, 12, 0))
    for _ in range(3):
        db.add_report_event(ts(2026, 9, 29, 11, 0), 1)
    return db


def test_snapshot_previous_week_and_month(tmp_path):
    db = _db_with_history(tmp_path)
    config = Config()
    snap = build_snapshot(StatsService(db, config), db, config, NOW)
    assert (snap.prev_week.online_seconds, snap.prev_week.reports) == (3 * 3600, 5)
    assert (snap.week.stats.online_seconds, snap.week.stats.reports) == (2 * 3600, 3)
    assert snap.month_start == date(2026, 9, 1)
    assert (snap.month.online_seconds, snap.month.reports) == (5 * 3600, 8)
    assert snap.month_hours_norm == pytest.approx(70 * 30 / 7)      # 30 дней в сентябре
    assert snap.month_reports_norm == pytest.approx(600 * 30 / 7)
    db.close()


def test_excel_block_order_today_comparison_and_month(tmp_path):
    from openpyxl import load_workbook

    db = _db_with_history(tmp_path)
    config = Config()
    path = tmp_path / "cmp.xlsx"
    write_excel(build_snapshot(StatsService(db, config), db, config, NOW), path)
    ws = load_workbook(path)["Неделя"]
    # порядок блоков: неделя → сегодня → сравнение → прогноз → месяц
    assert ws["A5"].value == "Показатель" and ws["A6"].value == "Онлайн (ч:мм)"
    assert ws["A9"].value == "Сегодня: план на день и факт"
    assert ws["A14"].value == "Сравнение с прошлой неделей"
    assert as_days(ws["B16"].value) == pytest.approx(2 / 24)
    assert as_days(ws["C16"].value) == pytest.approx(3 / 24)
    assert ws["D16"].value == "\u22121 ч 00 мин"
    assert ws["B17"].value == 3 and ws["C17"].value == 5 and ws["D17"].value == -2
    assert ws["E17"].value == pytest.approx(-0.4)
    assert ws["A19"].value == "Прогноз к концу недели при текущем темпе"
    assert ws["A24"].value == "Итог за месяц: Сентябрь 2026"
    assert as_days(ws["B26"].value) == pytest.approx(5 / 24)
    assert ws["B27"].value == 8
    assert ws["D27"].value == pytest.approx(8 / (600 * 30 / 7))
    db.close()


def test_comparison_without_previous_week_shows_dash(tmp_path):
    from openpyxl import load_workbook

    db = Database(tmp_path / "n.db")
    sid = db.open_session(ts(2026, 9, 29, 10, 0))
    db.close_session(sid, ts(2026, 9, 29, 11, 0))
    config = Config()
    path = tmp_path / "n.xlsx"
    write_excel(build_snapshot(StatsService(db, config), db, config, NOW), path)
    ws = load_workbook(path)["Неделя"]
    assert ws["E16"].value == "\u2014"
    db.close()


def test_export_goes_to_output_dir_and_archives_weekly_png(env, tmp_path):
    config, db, stats = env
    result = ExportService(stats, db, config, clock=lambda: NOW).run()
    out = tmp_path / "out_dir"
    assert result.ok
    assert (out / "SKYHELPER_stats.xlsx").exists()
    assert (out / "SKYHELPER_report.png").exists()
    assert (out / "История" / "SKYHELPER_report_2026-09-28.png").exists()


def test_archive_can_be_disabled(env, tmp_path):
    config, db, stats = env
    config.archive_weekly = False
    ExportService(stats, db, config, clock=lambda: NOW).run()
    assert not (tmp_path / "out_dir" / "История").exists()


def test_locked_excel_does_not_stop_png(env, tmp_path, monkeypatch):
    config, db, stats = env

    def locked(*args, **kwargs):
        raise ExportError("Файл Excel открыт в другой программе, закрой его")

    monkeypatch.setattr("app.export.service.write_excel", locked)
    result = ExportService(stats, db, config, clock=lambda: NOW).run()
    assert not result.ok
    assert (tmp_path / "out_dir" / "SKYHELPER_report.png").exists()


# ---------- история недель и новые листы Excel ----------

def test_snapshot_history_covers_recent_weeks(tmp_path):
    from app.export.snapshot import HISTORY_WEEKS

    db = _db_with_history(tmp_path)
    config = Config()
    snap = build_snapshot(StatsService(db, config), db, config, NOW)
    assert len(snap.history) == HISTORY_WEEKS
    assert snap.history[0].week_start == date(2026, 9, 28)   # текущая неделя
    assert (snap.history[0].online_seconds, snap.history[0].reports) == (2 * 3600, 3)
    assert snap.history[1].week_start == date(2026, 9, 21)    # прошлая неделя
    assert (snap.history[1].online_seconds, snap.history[1].reports) == (3 * 3600, 5)
    assert all(w.week_start < w.week_start + timedelta(days=7) for w in snap.history)
    db.close()


def test_snapshot_tracks_today_and_elapsed_days(env):
    config, db, stats = env
    snap = build_snapshot(stats, db, config, NOW)
    assert snap.today.online_seconds == 3600   # сессия 13:00–14:00 сегодня
    assert snap.today.reports == 1
    assert snap.elapsed_days == 3              # 28, 29, 30 сентября


def test_excel_has_history_sheet_and_extra_columns(tmp_path):
    from openpyxl import load_workbook

    db = _db_with_history(tmp_path)
    config = Config()
    path = tmp_path / "hist.xlsx"
    write_excel(build_snapshot(StatsService(db, config), db, config, NOW), path)

    wb = load_workbook(path)
    assert wb.sheetnames == ["Неделя", "По дням", "Динамика"]

    history = wb["Динамика"]
    assert history["A1"].value == "Неделя"
    assert history["A2"].value == "28.09 — 04.10"
    assert history["D2"].value == 3 and history["D3"].value == 5

    days = wb["По дням"]
    assert days["G1"].value == "Онлайн к плану"
    assert days["H1"].value == "Обращения к плану"
    assert days.cell(row=days.max_row, column=1).value == "ИТОГО"
    db.close()
