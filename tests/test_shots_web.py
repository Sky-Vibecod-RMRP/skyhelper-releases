"""Тесты сайта: вкладка «Недельный отчёт», её JSON и отдача картинок."""
from __future__ import annotations

import http.client
import json
from datetime import datetime
from urllib.parse import quote

import pytest
from PIL import Image

from app.config import Config
from app.shots.service import ShotsService
from app.web.page import dashboard_page
from app.web.pin import hash_pin
from app.web.server import WebDashboard


class FakeSession:
    is_on_duty = True
    is_game_running = True


class FakeWindow:
    minimized = False
    monitor = (0, 0, 8, 6)


def fetch(port: int, path: str) -> tuple[int, bytes, dict[str, str]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, data, {k.lower(): v for k, v in resp.getheaders()}
    finally:
        conn.close()


def _service(root) -> ShotsService:
    config = Config()
    config.shots_root = str(root)
    return ShotsService(
        config,
        FakeSession(),
        window_finder=lambda _names: FakeWindow(),
        grabber=lambda _monitor: Image.new("RGB", (8, 6), (12, 40, 90)),
        clock=lambda: datetime(2026, 9, 30, 16, 42, 15),
    )


@pytest.fixture
def shots(tmp_path) -> ShotsService:
    """Сервис с одной уже снятой картинкой во временной папке."""
    service = _service(tmp_path / "shots")
    result = service.shoot("Наказания (День)")
    assert result.ok, result.message
    return service


@pytest.fixture
def dash(shots, request):
    pin_hash = getattr(request, "param", "")
    server = WebDashboard(
        lambda: {"ok": True}, host="127.0.0.1", port=0, pin_hash=pin_hash, shots=shots
    )
    server.start()
    try:
        yield server
    finally:
        server.stop()


# --- страница ---------------------------------------------------------------


def test_page_has_weekly_report_tab_and_view():
    page = dashboard_page({})
    assert 'data-view="shots">Недельный отчёт</button>' in page
    assert 'id="view-shots"' in page
    assert "НЕДЕЛЬНЫЙ ОТЧЁТ" in page
    assert "shotsLoad(" in page, "переключение на вкладку должно грузить дерево"
    assert "setInterval" in page, "вкладка должна обновляться сама"


def test_page_has_no_external_resources_with_shots_tab():
    from test_web_dashboard import _CSS_EXTERNAL, _EXTERNAL_RESOURCE

    page = dashboard_page({})
    assert not _EXTERNAL_RESOURCE.search(page)
    assert not _CSS_EXTERNAL.search(page)


# --- JSON -------------------------------------------------------------------


def test_api_shots_returns_week_tree(dash, shots):
    status, body, headers = fetch(dash.port, "/api/shots")
    assert status == 200
    assert headers["content-type"].startswith("application/json")
    data = json.loads(body)
    assert len(data["weeks"]) == 1
    assert data["selected"] == data["current"]
    assert data["total"] == 1
    category = next(c for c in data["categories"] if c["folder"] == "Наказания (День)")
    assert category["files"][0]["name"] == "2026-09-30_16-42-15_Наказания-День.jpg"
    assert category["files"][0]["size"] > 0
    assert category["files"][0]["url"].startswith("/shots/")


def test_api_shots_unknown_week_falls_back_to_current(dash):
    status, body, _ = fetch(dash.port, "/api/shots?week=%D0%BD%D0%B5%D1%82")
    assert status == 200
    data = json.loads(body)
    assert data["selected"] == data["current"]


def test_api_shots_without_module_returns_empty_structure(tmp_path):
    server = WebDashboard(lambda: {}, host="127.0.0.1", port=0)   # shots=None
    server.start()
    try:
        status, body, _ = fetch(server.port, "/api/shots")
    finally:
        server.stop()
    assert status == 200
    assert json.loads(body) == {
        "weeks": [], "selected": "", "current": "", "categories": [], "total": 0,
    }


def test_shot_route_without_module_is_404(tmp_path):
    server = WebDashboard(lambda: {}, host="127.0.0.1", port=0)
    server.start()
    try:
        status, _, _ = fetch(server.port, "/shots/a/b/c.jpg")
    finally:
        server.stop()
    assert status == 404


# --- картинки ----------------------------------------------------------------


def test_shot_file_is_served_as_jpeg(dash, shots):
    week = shots.report_tree()["selected"]
    url = "/shots/{}/{}/{}".format(
        quote(week),
        quote("Наказания (День)"),
        quote("2026-09-30_16-42-15_Наказания-День.jpg"),
    )
    status, body, headers = fetch(dash.port, url)
    assert status == 200, body
    assert headers["content-type"] == "image/jpeg"
    assert body.startswith(b"\xff\xd8"), "должен отдаваться настоящий JPG"


@pytest.mark.parametrize(
    "path",
    [
        "/shots/../../config.json",
        "/shots/x/../../app/config.py",
        "/shots/x/y/../../../secrets.jpg",
        "/shots/x/y/not-a-jpg.png",
        "/shots/x/y",
        "/shots/x/y/z.jpg/extra",
    ],
)
def test_shot_file_rejects_traversal(dash, path):
    status, _, _ = fetch(dash.port, path)
    assert status == 404, path


# --- вход по коду ------------------------------------------------------------


def test_shots_endpoints_respect_pin(tmp_path):
    server = WebDashboard(
        lambda: {}, host="127.0.0.1", port=0,
        pin_hash=hash_pin("1234"), shots=_service(tmp_path / "shots"),
    )
    server.start()
    try:
        assert fetch(server.port, "/api/shots")[0] == 401
        assert fetch(server.port, "/shots/a/b/c.jpg")[0] == 401
        status, page, _ = fetch(server.port, "/")
        assert status == 200
        assert b"data-view" not in page, "без входа дашборд не показываем"
    finally:
        server.stop()
