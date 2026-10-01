"""Локальная база SQLite: сессии игры и события обращений.

Время хранится как целые секунды UTC (Unix timestamp).
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   INTEGER NOT NULL,
    ended_at     INTEGER,
    heartbeat_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS report_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    delta      INTEGER NOT NULL CHECK (delta IN (-1, 1))
);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_reports_created  ON report_events(created_at);
"""


class Database:
    def __init__(self, path: str | Path):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- сессии игры ---------------------------------------------------

    def open_session(self, ts: int) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO sessions (started_at, heartbeat_at) VALUES (?, ?)",
                (ts, ts),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def touch_session(self, session_id: int, ts: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET heartbeat_at = ? WHERE id = ?", (ts, session_id)
            )
            self._conn.commit()

    def close_session(self, session_id: int, ts: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET ended_at = ?, heartbeat_at = ? WHERE id = ?",
                (ts, ts, session_id),
            )
            self._conn.commit()

    def close_orphan_sessions(self) -> int:
        """Закрывает сессии, оставшиеся открытыми после вылета/выключения ПК.

        Концом считается последний «пульс», поэтому потеря не больше
        heartbeat_interval_sec.
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE sessions SET ended_at = heartbeat_at WHERE ended_at IS NULL"
            )
            self._conn.commit()
            return cur.rowcount

    def sessions_overlapping(self, start: int, end: int) -> list[tuple[int, int | None]]:
        """Сессии, пересекающие [start, end). У незакрытой сессии конец None."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT started_at, ended_at FROM sessions "
                "WHERE started_at < ? AND (ended_at IS NULL OR ended_at > ?)",
                (end, start),
            ).fetchall()
        return [(int(s), None if e is None else int(e)) for s, e in rows]

    def first_activity_ts(self) -> int | None:
        """Время самой ранней записи (сессия или обращение), None если данных нет."""
        with self._lock:
            row = self._conn.execute(
                "SELECT MIN(t) FROM ("
                "SELECT MIN(started_at) AS t FROM sessions "
                "UNION ALL SELECT MIN(created_at) FROM report_events)"
            ).fetchone()
        return None if row[0] is None else int(row[0])

    # --- обращения -----------------------------------------------------

    def add_report_event(self, ts: int, delta: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO report_events (created_at, delta) VALUES (?, ?)",
                (ts, delta),
            )
            self._conn.commit()

    def report_total(self, start: int, end: int) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(delta), 0) FROM report_events "
                "WHERE created_at >= ? AND created_at < ?",
                (start, end),
            ).fetchone()
        return int(row[0])
