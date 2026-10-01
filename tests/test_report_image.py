from datetime import datetime
from pathlib import Path

from PIL import Image

from app.config import Config
from app.export.report_image import build_report_image
from app.export.snapshot import build_snapshot
from app.stats.service import StatsService
from app.storage.db import Database


def ts(*args) -> int:
    return int(datetime(*args).timestamp())


def test_report_image_is_created(tmp_path):
    db = Database(tmp_path / "r.db")
    config = Config()
    now = ts(2026, 9, 30, 15, 0)
    sid = db.open_session(ts(2026, 9, 30, 10, 0))
    db.close_session(sid, ts(2026, 9, 30, 12, 0))
    db.add_report_event(ts(2026, 9, 30, 11, 0), 1)

    snapshot = build_snapshot(StatsService(db, config), db, config, now)
    path = tmp_path / "report.png"
    build_report_image(snapshot, path)

    assert path.exists()
    with Image.open(path) as image:
        assert image.size == (1400, 1080)
        assert image.format == "PNG"
    db.close()
