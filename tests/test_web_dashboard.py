"""Интеграционные тесты локального сайта: сервер, вход по коду, JSON, страница."""
from __future__ import annotations

import http.client
import json
import re
import socket
import urllib.parse

import pytest

from app.services.live_status import build_status
from app.stats.service import StatsService
from app.storage.db import Database
from app.tracker.session_service import SessionService
from app.config import Config
from app.web.page import LOGIN_PAGE, dashboard_page
from app.web.pin import hash_pin, verify_pin
from app.web.server import WebDashboard, WebError

#: Внешний ресурс — то, что браузер грузит сам: скрипты, стили, картинки.
#: Ссылки-навигации <a href> на форум ресурсами не являются.
_EXTERNAL_RESOURCE = re.compile(
    r"<(script|link|img|iframe|embed|object|source|video|audio)\b[^>]*"
    r"\b(?:src|href)\s*=\s*[\"'](?:https?:)?//",
    re.I,
)
#: Внешние же стили внутри CSS (@import и url(http…)) — тоже ресурс.
_CSS_EXTERNAL = re.compile(r"@import|url\(\s*[\"']?(?:https?:)?//", re.I)


# --- маленький клиент -------------------------------------------------------


def fetch(port: int, method: str, path: str, *, form: dict | None = None,
          cookie: str = "") -> tuple[int, bytes, dict[str, str]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers: dict[str, str] = {}
    body = None
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if cookie:
        headers["Cookie"] = cookie
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        heads = {k.lower(): v for k, v in resp.getheaders()}
        return resp.status, data, heads
    finally:
        conn.close()


def json_status(port: int, cookie: str = "") -> dict:
    status, body, _ = fetch(port, "GET", "/api/status", cookie=cookie)
    assert status == 200, body
    return json.loads(body)


@pytest.fixture
def provider():
    payload = {"ok": True, "today": {"seconds": 3600, "reports": 7}}
    calls = []

    def call() -> dict:
        calls.append(1)
        return payload

    call.payload = payload       # type: ignore[attr-defined]
    call.calls = calls           # type: ignore[attr-defined]
    return call


@pytest.fixture
def dash(request, provider):
    """Сервер на свободном порту; закрывается даже при падении теста."""
    pin_hash = getattr(request, "param", "")
    server = WebDashboard(provider, host="127.0.0.1", port=0, pin_hash=pin_hash)
    server.start()
    try:
        yield server
    finally:
        server.stop()


# --- базовая работа ---------------------------------------------------------


def test_status_endpoint_returns_provider_json(dash, provider):
    assert json_status(dash.port) == provider.payload
    assert provider.calls, "провайдер должен вызываться на каждый запрос"


def test_index_renders_dashboard_without_pin(dash):
    status, body, heads = fetch(dash.port, "GET", "/")
    page = body.decode("utf-8")
    assert status == 200
    assert "SKY-GRAFANA.RMRP" in page
    assert "/api/status" in page
    assert heads.get("cache-control") == "no-store"
    assert heads.get("x-content-type-options") == "nosniff"


def test_unknown_path_is_404(dash):
    status, body, _ = fetch(dash.port, "GET", "/no-such-page")
    assert status == 404
    assert b"404" in body


def test_provider_crash_returns_500_and_server_survives(dash):
    def boom() -> dict:
        raise RuntimeError("база недоступна")

    dash.provider = boom
    status, body, _ = fetch(dash.port, "GET", "/api/status")
    assert status == 500
    assert b"provider failed" in body
    # Сервер жив, страницу всё равно отдаёт.
    assert fetch(dash.port, "GET", "/")[0] == 200


# --- вход по коду доступа ---------------------------------------------------


PIN_HASH = hash_pin("1234")


@pytest.fixture
def guarded(dash):  # noqa: ARG001 - dash уже поднят, дописываем ему код
    return dash


def test_pin_protects_api_and_page(request, provider):
    server = WebDashboard(provider, host="127.0.0.1", port=0, pin_hash=PIN_HASH)
    server.start()
    try:
        port = server.port
        # Без куки — ни данных, ни дашборда.
        assert fetch(port, "GET", "/api/status")[0] == 401
        status, body, _ = fetch(port, "GET", "/")
        assert status == 200
        assert "Код доступа" in body.decode("utf-8")

        # Не тот код — 403 и снова страница входа.
        status, body, _ = fetch(port, "POST", "/login", form={"pin": "0000"})
        assert status == 403
        assert "Неверный код доступа" in body.decode("utf-8")

        # Верный код — редирект с кукой, дальше данные открыты.
        status, _, heads = fetch(port, "POST", "/login", form={"pin": "1234"})
        assert status == 302
        cookie = heads["set-cookie"].split(";")[0]
        assert cookie.startswith("rmrp_auth=")
        assert json_status(port, cookie) == provider.payload
        assert fetch(port, "GET", "/", cookie=cookie)[0] == 200
    finally:
        server.stop()


def test_too_many_failures_are_rate_limited(provider):
    server = WebDashboard(provider, host="127.0.0.1", port=0, pin_hash=PIN_HASH)
    server.start()
    try:
        port = server.port
        codes = [fetch(port, "POST", "/login", form={"pin": "нет"})[0]
                 for _ in range(6)]
        assert codes[:5] == [403] * 5
        assert codes[5] == 429
        # После лимита сервер не умер и статус по-прежнему закрыт.
        assert fetch(port, "GET", "/api/status")[0] == 401
    finally:
        server.stop()


def test_broken_pin_hash_keeps_server_alive(provider):
    server = WebDashboard(provider, host="127.0.0.1", port=0, pin_hash="мусор-вместо-хэша")
    server.start()
    try:
        port = server.port
        assert fetch(port, "GET", "/")[0] == 200
        # Войти с мусорным хэшем нельзя, но и падения нет.
        assert fetch(port, "POST", "/login", form={"pin": "любой"})[0] == 403
        assert fetch(port, "GET", "/api/status")[0] == 401
    finally:
        server.stop()


def test_logout_closes_session(provider):
    server = WebDashboard(provider, host="127.0.0.1", port=0, pin_hash=PIN_HASH)
    server.start()
    try:
        port = server.port
        _, _, heads = fetch(port, "POST", "/login", form={"pin": "1234"})
        cookie = heads["set-cookie"].split(";")[0]
        assert fetch(port, "GET", "/api/status", cookie=cookie)[0] == 200

        _, _, logout_heads = fetch(port, "GET", "/logout", cookie=cookie)
        assert logout_heads["set-cookie"].split(";")[0].startswith("rmrp_auth=;") or \
            "Max-Age=0" in logout_heads["set-cookie"]
        # Тот же токен больше не работает.
        assert fetch(port, "GET", "/api/status", cookie=cookie)[0] == 401
    finally:
        server.stop()


# --- жизненный цикл ---------------------------------------------------------


def test_stop_is_idempotent_and_frees_port(dash):
    port = dash.port
    dash.stop()
    dash.stop()                      # повторный вызов — не ошибка
    assert not dash.running

    # Порт освободился: на нём поднимается новый сервер.
    second = WebDashboard(lambda: {}, host="127.0.0.1", port=port)
    second.start()
    try:
        assert second.running
    finally:
        second.stop()


def test_busy_port_raises_readable_error():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    busy_port = sock.getsockname()[1]
    try:
        server = WebDashboard(lambda: {}, host="127.0.0.1", port=busy_port)
        with pytest.raises(WebError) as exc:
            server.start()
        message = str(exc.value)
        assert str(busy_port) in message
        assert "порт" in message.lower()
        assert not server.running
    finally:
        sock.close()


def test_url_is_always_localhost(dash):
    assert dash.url == f"http://127.0.0.1:{dash.port}/"
    assert dash.running


# --- код доступа ------------------------------------------------------------


def test_pin_hash_roundtrip_and_no_plaintext():
    pin = "секрет-2026"
    stored = hash_pin(pin)
    assert stored.startswith("pbkdf2_sha256$")
    assert pin not in stored
    assert verify_pin(pin, stored)
    assert not verify_pin("другой", stored)
    assert not verify_pin(pin, "")
    assert not verify_pin(pin, "мусор")


def test_hash_uses_salt_different_every_time():
    assert hash_pin("1234") != hash_pin("1234")   # одинаковый код — разные хэши


# --- страница ---------------------------------------------------------------


def test_dashboard_page_has_no_external_resources():
    page = dashboard_page({"today": {"seconds": 3600}, "days": []})
    lowered = page.lower()
    # Наружу не грузится НИЧЕГО: ни скриптов, ни стилей, ни картинок.
    assert not _EXTERNAL_RESOURCE.search(lowered), "внешний ресурс на странице"
    assert not _CSS_EXTERNAL.search(lowered), "внешний url() / @import в CSS"
    for marker in ("googleapis", "unpkg", "jsdelivr", "cdn"):
        assert marker not in lowered, f"внешний хост: {marker!r}"
    for marker in ("СЕГОДНЯ", "НЕДЕЛЯ", "СТРИК", "СТАТУС", "ПОСЛЕДНИЕ ДНИ"):
        assert marker in page


def test_dashboard_page_has_helper_and_rules_tabs():
    """Три вкладки в шапке: дашборд, хелпер и правила RMRP с поиском."""
    page = dashboard_page({"today": {"seconds": 3600}, "days": []})
    for marker in ('data-view="dash"', 'data-view="helper"', 'data-view="rules"',
                   'id="rules-q"', "view-helper", "view-rules"):
        assert marker in page, f"нет {marker!r}"
    # Секции хелпера и ссылки на форум — на месте.
    assert "Открыть таблицу Excel" in page
    assert "install-sky-grafana.bat" in page
    assert page.count("https://forum.rmrp.ru/threads/") == 28
    # Поиск клиентский: JS есть, данные для фильтрации — в data-k.
    assert "applyRules" in page and 'data-k="' in page


def test_dashboard_page_renders_real_status(tmp_path):
    config = Config(weekly_hours_norm=70.0, weekly_reports_norm=600)
    db = Database(tmp_path / "web.db")
    try:
        session = SessionService(db, config)
        stats = StatsService(db, config)
        from datetime import datetime

        start = int(datetime(2026, 9, 29, 9, 0).timestamp())
        sid = db.open_session(start)
        db.close_session(sid, start + 3 * 3600 + 36 * 60)
        for i in range(12):
            db.add_report_event(start + 60 + i, 1)

        status = build_status(stats, session, config, int(datetime(2026, 9, 29, 21, 0).timestamp()))
        page = dashboard_page(status)
        assert "3:36" in page            # онлайн за сегодня
        assert "12 обр" in page
        assert "28.09" in page           # диапазон недели в подзаголовке
        assert "29.09" in page           # столбики дней
    finally:
        db.close()


def test_login_page_is_self_contained():
    page = LOGIN_PAGE.replace("{{error}}", "")
    assert "Код доступа" in page
    assert "/login" in page
    assert "https://" not in page


# --- картинки событий -------------------------------------------------------


def test_image_route_serves_event_screenshot(dash):
    """Скриншот события отдаётся локальным сервером как image/jpeg."""
    from app.events import data as ev_data

    event = ev_data.get("nalyoty-1")
    status, body, heads = fetch(dash.port, "GET", event["img"])
    assert status == 200, body
    assert heads.get("content-type") == "image/jpeg"
    assert body[:2] == b"\xff\xd8"              # сигнатура JPEG
    assert len(body) > 2000


def test_image_route_rejects_traversal_and_junk(dash):
    for path in (
        "/img/../config.json",
        "/img/events/../../config.json",
        "/img/events/..\\..\\config.json",
        "/img//etc/passwd",
        "/img/",
        "/img/%D0%BD%D0%B5%D1%82.jpg",
    ):
        status, _, _ = fetch(dash.port, "GET", path)
        assert status == 404, path


def test_image_route_respects_pin(provider):
    """Картинки закрыты тем же кодом доступа, что и страница."""
    server = WebDashboard(provider, host="127.0.0.1", port=0, pin_hash=PIN_HASH)
    server.start()
    try:
        port = server.port
        assert fetch(port, "GET", "/img/events/nalyoty-1.jpg")[0] == 401
        _, _, heads = fetch(port, "POST", "/login", form={"pin": "1234"})
        cookie = heads["set-cookie"].split(";")[0]
        assert fetch(port, "GET", "/img/events/nalyoty-1.jpg", cookie=cookie)[0] == 200
    finally:
        server.stop()


def test_online_route_serves_live_counter(dash, monkeypatch):
    """GET /api/online — живой онлайн серверов для вкладки Online-STAFF."""
    from app.staff import data as staff_data

    monkeypatch.setattr(staff_data, "fetch", lambda force=False: {
        "found": True, "error": "", "total": 2417,
        "servers": {"prod4": 481, "prod1": 479},
        "updated": "30.09.2026 00:15",
    })
    status, body, heads = fetch(dash.port, "GET", "/api/online?refresh=1")
    assert status == 200, body
    assert heads.get("content-type", "").startswith("application/json")
    payload = json.loads(body)
    assert payload["total"] == 2417
    assert payload["servers"] == {"prod4": 481, "prod1": 479}
    assert payload["updated"] == "30.09.2026 00:15"
