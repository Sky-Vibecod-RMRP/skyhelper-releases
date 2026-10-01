from datetime import datetime

from app.stats.weeks import day_bounds, overlap_seconds, week_bounds


def ts(*args) -> int:
    return int(datetime(*args).timestamp())


def test_week_starts_on_monday_midnight():
    wednesday = ts(2026, 9, 30, 15, 0)
    start, end = week_bounds(wednesday)
    assert start == ts(2026, 9, 28)
    assert end == ts(2026, 10, 5)


def test_monday_itself_belongs_to_new_week():
    start, _ = week_bounds(ts(2026, 9, 28, 0, 0))
    assert start == ts(2026, 9, 28)


def test_sunday_belongs_to_week_that_started_monday():
    start, _ = week_bounds(ts(2026, 10, 4, 23, 59))
    assert start == ts(2026, 9, 28)


def test_day_bounds():
    start, end = day_bounds(ts(2026, 9, 30, 15, 0))
    assert (start, end) == (ts(2026, 9, 30), ts(2026, 10, 1))


def test_session_over_week_boundary_is_clipped():
    start, end = week_bounds(ts(2026, 10, 5, 12, 0))  # неделя с 5 октября
    session = (ts(2026, 10, 4, 23, 0), ts(2026, 10, 5, 1, 0))
    assert overlap_seconds([session], start, end, now=ts(2026, 10, 5, 12, 0)) == 3600


def test_open_session_counts_until_now():
    now = ts(2026, 9, 30, 12, 0)
    start, end = week_bounds(now)
    session = (ts(2026, 9, 30, 10, 0), None)
    assert overlap_seconds([session], start, end, now) == 7200
