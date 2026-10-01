from datetime import datetime

import pytest

from app.config import Config
from app.services.report_counter import (
    REASON_GAME_NOT_RUNNING,
    REASON_NOT_ON_DUTY,
    REASON_NOTHING_TO_UNDO,
    ReportCounter,
)
from app.stats.service import StatsService
from app.storage.db import Database
from app.tracker.session_service import SessionService

T0 = int(datetime(2026, 9, 30, 12, 0).timestamp())


class FakeClock:
    def __init__(self, t: int = T0):
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def env(tmp_path):
    config = Config(require_duty=False)  # старые тесты: считаем всё время в игре
    db = Database(tmp_path / "test.db")
    clock = FakeClock()
    session = SessionService(db, config, clock)
    stats = StatsService(db, config)
    counter = ReportCounter(db, stats, session, config, clock)
    yield config, db, clock, session, stats, counter
    db.close()


def test_online_time_is_counted_between_start_and_stop(env):
    config, _, clock, session, stats, _ = env
    config.max_gap_sec = 10**9  # тест перематывает время, защита от сна не нужна
    session.tick(True)
    clock.t += 3600
    session.tick(True)
    clock.t += 1800
    session.tick(False)
    assert stats.week(clock.t).online_seconds == 5400
    assert not session.is_game_running


def test_open_session_is_counted_live(env):
    _, _, clock, session, stats, _ = env
    session.tick(True)
    clock.t += 600
    assert stats.week(clock.t).online_seconds == 600


def test_gap_between_ticks_closes_session_at_last_tick(env):
    _, _, clock, session, stats, _ = env
    session.tick(True)
    clock.t += 3
    session.tick(True)          # последняя нормальная проверка: T0+3
    clock.t += 5000             # ПК спал
    session.tick(True)
    assert stats.week(clock.t).online_seconds == 3 + 0  # сон не засчитан


def test_orphan_session_is_closed_by_last_heartbeat(tmp_path):
    config = Config()
    path = tmp_path / "crash.db"
    db = Database(path)
    session_id = db.open_session(T0)
    db.touch_session(session_id, T0 + 120)
    db.close()  # «вылет»: сессия осталась без ended_at

    db = Database(path)
    assert db.close_orphan_sessions() == 1
    stats = StatsService(db, config)
    assert stats.week(T0 + 9999).online_seconds == 120
    db.close()


def test_session_service_reports_state_changes(env):
    _, _, clock, session, _, _ = env
    events = []
    session.on_state_change = events.append
    session.tick(True)
    session.tick(True)
    session.tick(False)
    assert events == [True, False]


def test_report_rejected_when_game_not_running(env):
    _, _, _, _, _, counter = env
    result = counter.add()
    assert not result.ok and result.reason == REASON_GAME_NOT_RUNNING


def test_report_add_and_undo(env):
    _, _, _, session, _, counter = env
    session.tick(True)
    assert counter.add().week_total == 1
    assert counter.add().week_total == 2
    assert counter.undo().week_total == 1
    assert counter.undo().week_total == 0
    result = counter.undo()
    assert not result.ok and result.reason == REASON_NOTHING_TO_UNDO


def test_reports_are_counted_per_week(env):
    _, _, clock, session, stats, counter = env
    session.tick(True)
    counter.add()
    clock.t += 7 * 24 * 3600
    session.tick(True)
    assert stats.week_reports(clock.t) == 0


def test_count_only_in_game_can_be_disabled(env):
    config, _, _, _, _, counter = env
    config.count_only_in_game = False
    assert counter.add().ok


def test_progress_percent(env):
    config, _, clock, session, stats, counter = env
    config.max_gap_sec = 10**9
    session.tick(True)
    counter.add()
    clock.t += 7 * 3600
    session.tick(True)
    progress = stats.week_progress(clock.t)
    assert round(progress.hours_percent) == 10   # 7 из 70
    assert round(progress.reports_percent, 2) == round(1 / 600 * 100, 2)


# ---------- дежурство ----------

@pytest.fixture
def duty_env(tmp_path):
    config = Config()  # require_duty=True по умолчанию
    config.max_gap_sec = 10**9
    db = Database(tmp_path / "duty.db")
    clock = FakeClock()
    session = SessionService(db, config, clock)
    stats = StatsService(db, config)
    counter = ReportCounter(db, stats, session, config, clock)
    yield config, clock, session, stats, counter
    db.close()


def test_online_not_counted_without_duty(duty_env):
    _, clock, session, stats, _ = duty_env
    session.tick(True)
    clock.t += 1200
    session.tick(True)
    assert session.is_game_running and not session.is_counting
    assert stats.week(clock.t).online_seconds == 0


def test_duty_starts_and_stops_counting_immediately(duty_env):
    _, clock, session, stats, _ = duty_env
    session.tick(True)
    clock.t += 600            # 10 минут без дежурства
    session.set_duty(True)
    clock.t += 1800           # 30 минут на дежурстве
    session.set_duty(False)
    clock.t += 900            # ещё 15 минут не на дежурстве
    session.tick(True)
    assert stats.week(clock.t).online_seconds == 1800


def test_reports_need_duty(duty_env):
    _, _, session, _, counter = duty_env
    session.tick(True)
    result = counter.add()
    assert not result.ok and result.reason == REASON_NOT_ON_DUTY
    session.set_duty(True)
    assert counter.add().ok


def test_duty_turns_off_when_game_closes(duty_env):
    _, clock, session, stats, _ = duty_env
    events = []
    session.on_duty_change = events.append
    session.tick(True)
    session.set_duty(True)
    clock.t += 300
    session.tick(False)       # игру закрыли
    assert not session.is_on_duty and not session.is_counting
    assert events == [True, False]
    assert stats.week(clock.t).online_seconds == 300


def test_duty_set_before_game_start_waits_for_game(duty_env):
    _, clock, session, stats, _ = duty_env
    session.tick(False)
    session.set_duty(True)
    session.tick(False)       # игры всё ещё нет: дежурство не сбрасывается
    assert session.is_on_duty and not session.is_counting
    session.tick(True)
    clock.t += 120
    assert session.is_counting
    assert stats.week(clock.t).online_seconds == 120


def test_toggle_duty_and_state_events(duty_env):
    _, _, session, _, _ = duty_env
    counting = []
    session.on_state_change = counting.append
    session.tick(True)
    assert session.toggle_duty() is True
    assert session.toggle_duty() is False
    assert counting == [True, False]


def test_duty_auto_off_can_be_disabled(duty_env):
    config, _, session, _, _ = duty_env
    config.duty_auto_off_on_game_close = False
    session.tick(True)
    session.set_duty(True)
    session.tick(False)
    assert session.is_on_duty
