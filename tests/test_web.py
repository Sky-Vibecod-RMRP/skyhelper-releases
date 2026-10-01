"""Тесты изолированного модуля app/web: сервер, вход по коду, страницы.

Только стандартная библиотека (urllib, cookiejar, json) + pytest.
Сервер в каждом тесте поднимается на порту 0 — фактический читаем
из свойства ``dashboard.port``.
"""
from __future__ import annotations

import json
import re
import urllib.request
from contextlib import contextmanager
from http.cookiejar import CookieJar
from urllib.parse import urlencode

from app.web.page import LOGIN_PAGE, dashboard_page
from app.web.pin import hash_pin, verify_pin
from app.web.server import WebDashboard


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    """Оставляет 3xx/4xx/5xx как есть: нужен сам статус и заголовки.

    Заодно кука из 302 успевает попасть в CookieJar до следующего запроса.
    """

    def http_response(self, request, response):
        return response

    https_response = http_response


def _payload() -> dict:
    """Один и тот же статус для всех тестов."""
    return {
        "date": "29.09.2026",
        "weekday": "Пн",
        "week": "29.09 — 05.10",
        "today": {"seconds": 5400, "reports": 12, "plan_seconds": 10285},
        "week_stats": {
            "seconds": 250000,
            "reports": 321,
            "hours_percent": 62.0,
            "reports_percent": 55.0,
        },
        "streak": {"days": 6, "today_done": True},
        "flags": {"duty": True, "game": False, "counting": True},
        "days": [
            {"label": "29.09 Пн", "seconds": 7200, "reports": 50},
            {"label": "28.09 Вс", "seconds": 0, "reports": 0},
        ],
    }


def _payload_provider() -> dict:
    return _payload()


def _form(pin: str) -> bytes:
    """Тело POST /login (application/x-www-form-urlencoded)."""
    return urlencode({"pin": pin}).encode("utf-8")


def _url(dash: WebDashboard, path: str) -> str:
    return dash.url.rstrip("/") + path


def _request(jar: CookieJar, url: str, data: bytes | None = None):
    """(код, тело, заголовки). jar общий — куки переживают между запросами."""
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar), _NoRedirect()
    )
    with opener.open(urllib.request.Request(url, data=data), timeout=5) as response:
        return response.status, response.read(), response.headers


@contextmanager
def _running(dash: WebDashboard):
    dash.start()
    try:
        yield dash
    finally:
        dash.stop()


# --- 1. без кода доступа ---------------------------------------------------


def test_api_status_without_pin_returns_provider_payload():
    calls: list[int] = []

    def provider() -> dict:
        calls.append(1)
        return _payload()

    with _running(WebDashboard(provider, port=0)) as dash:
        assert dash.running
        assert dash.port > 0
        assert dash.url == f"http://127.0.0.1:{dash.port}/"

        code, body, headers = _request(CookieJar(), _url(dash, "/api/status"))
        assert code == 200
        assert json.loads(body.decode("utf-8")) == _payload()
        assert calls, "provider должен быть вызван"
        assert headers["Content-Type"].startswith("application/json")
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"

        # без кода доступа главная сразу отдаёт дашборд, а не страницу входа
        code, page, _ = _request(CookieJar(), _url(dash, "/"))
        assert code == 200
        text = page.decode("utf-8")
        assert "SKY-GRAFANA.RMRP" in text
        assert "Код доступа" not in text


# --- 2. вход по коду -------------------------------------------------------


def test_login_flow_with_pin_hash():
    dash = WebDashboard(_payload_provider, port=0, pin_hash=hash_pin("1234"))
    jar = CookieJar()
    with _running(dash):
        # API без куки закрыт
        code, body, _ = _request(jar, _url(dash, "/api/status"))
        assert code == 401
        assert json.loads(body.decode("utf-8")) == {"error": "unauthorized"}

        # главная отдаёт страницу входа
        code, page, _ = _request(jar, _url(dash, "/"))
        assert code == 200
        text = page.decode("utf-8")
        assert "Код доступа" in text
        assert 'method="post"' in text
        assert 'autocomplete="off"' in text

        # неверный код → 403 и сообщение об ошибке
        code, body, _ = _request(jar, _url(dash, "/login"), data=_form("9999"))
        assert code == 403
        assert "Неверный код доступа" in body.decode("utf-8")

        # верный код → 302, кука установлена
        code, _, headers = _request(jar, _url(dash, "/login"), data=_form("1234"))
        assert code == 302
        assert headers["Location"] == "/"
        set_cookie = headers["Set-Cookie"]
        assert "HttpOnly" in set_cookie
        assert "SameSite=Lax" in set_cookie
        assert "Path=/" in set_cookie
        assert any(cookie.name == "rmrp_auth" for cookie in jar)

        # с кукой API доступен
        code, body, _ = _request(jar, _url(dash, "/api/status"))
        assert code == 200
        assert json.loads(body.decode("utf-8")) == _payload()

        # выход удаляет сессию
        code, _, headers = _request(jar, _url(dash, "/logout"))
        assert code == 302
        assert not any(cookie.name == "rmrp_auth" for cookie in jar)
        code, _, _ = _request(jar, _url(dash, "/api/status"))
        assert code == 401


# --- 3. rate limit ---------------------------------------------------------


def test_five_failures_then_rate_limit():
    dash = WebDashboard(_payload_provider, port=0, pin_hash=hash_pin("secret"))
    jar = CookieJar()
    with _running(dash):
        for _ in range(5):
            code, _, _ = _request(jar, _url(dash, "/login"), data=_form("wrong"))
            assert code == 403

        code, body, _ = _request(jar, _url(dash, "/login"), data=_form("wrong"))
        assert code == 429
        assert "Слишком много попыток, подожди минуту" in body.decode("utf-8")

        # лимит действует и на верный код — это всё ещё попытка входа
        code, _, _ = _request(jar, _url(dash, "/login"), data=_form("secret"))
        assert code == 429


# --- 4. мусорный pin_hash --------------------------------------------------


def test_garbage_pin_hash_keeps_server_alive():
    dash = WebDashboard(_payload_provider, port=0, pin_hash="мусор")
    jar = CookieJar()
    with _running(dash):
        # страница входа отдаётся без падений
        code, page, _ = _request(jar, _url(dash, "/"))
        assert code == 200
        text = page.decode("utf-8")
        assert "Код доступа" in text
        assert "SKY-GRAFANA.RMRP" in text
        assert "{{error}}" in LOGIN_PAGE          # плейсхолдер есть в константе
        assert "{{error}}" not in text            # но в выдаче уже подставлен

        # войти невозможно: хэш не разобрать → всегда ошибка
        code, body, _ = _request(jar, _url(dash, "/login"), data=_form("1234"))
        assert code == 403
        assert "Неверный код доступа" in body.decode("utf-8")

        # API без куки закрыт, сервер жив
        code, _, _ = _request(jar, _url(dash, "/api/status"))
        assert code == 401
        assert dash.running


# --- 5. stop() идемпотентен ------------------------------------------------


def test_stop_is_idempotent_and_frees_port():
    first = WebDashboard(_payload_provider, port=0)
    first.start()
    port = first.port
    assert port > 0

    first.stop()
    first.stop()  # повторный вызов без ошибок
    assert not first.running

    # порт освобождён — можно поднять новый сервер на том же порту
    second = WebDashboard(_payload_provider, port=port)
    second.start()
    try:
        assert second.running
        assert second.port == port
        code, body, _ = _request(CookieJar(), _url(second, "/api/status"))
        assert code == 200
        assert json.loads(body.decode("utf-8")) == _payload()
    finally:
        second.stop()

    # stop() на остановленном сервере тоже безопасен
    second.stop()


# --- 6. hash_pin / verify_pin ----------------------------------------------


def test_hash_pin_roundtrip():
    pin_hash = hash_pin("1234")
    assert pin_hash.startswith("pbkdf2_sha256$")
    assert pin_hash.count("$") == 3
    assert "1234" not in pin_hash                # PIN не лежит открытым текстом

    assert verify_pin("1234", pin_hash)
    assert not verify_pin("1235", pin_hash)      # чужой код
    assert not verify_pin("", pin_hash)

    # пустой и мусорный хэш — всегда False, без исключений
    assert not verify_pin("1234", "")
    assert not verify_pin("1234", "мусор")
    assert not verify_pin("1234", "pbkdf2_sha256$abc$zz$zz")
    assert not verify_pin("1234", "sha1$1000$00$00")

    # одна и та же строка при повторном хэшировании даёт другой хэш (своя соль)
    assert hash_pin("1234") != hash_pin("1234")


# --- 7. страница дашборда --------------------------------------------------


def test_dashboard_page_markers_and_no_external_resources():
    page = dashboard_page(_payload()).lower()

    for marker in ("сегодня", "стрик", "/api/status"):
        assert marker in page, f"нет маркера {marker!r}"

    # Страница обязана работать офлайн: ни одного внешнего ресурса —
    # ни скриптов, ни стилей, ни картинок. Гиперссылки на форум
    # (вкладка «Правила RMRP») открываются только по клику пользователя
    # и ресурсами не являются.
    assert not re.search(
        r"<(script|link|img|iframe|embed|object|source|video|audio)\b[^>]*"
        r"\b(?:src|href)\s*=\s*[\"'](?:https?:)?//", page
    ), "внешний ресурс на странице"
    assert not re.search(r"@import|url\(\s*[\"']?(?:https?:)?//", page), "внешний url() в CSS"
    for forbidden in ("cdn", "googleapis", "jsdelivr", "unpkg"):
        assert forbidden not in page, f"внешний хост: {forbidden!r}"

    # ключевые подписи и данные на месте
    text = dashboard_page(_payload())
    assert "SKY-GRAFANA.RMRP" in text
    assert "НЕДЕЛЯ" in text
    assert "СТАТУС" in text
    assert "29.09.2026" in text
    assert "выполнено" in text
    assert "нет связи с трекером" in text      # текст ошибки связи в JS

    # пустой статус тоже не должен ломать разметку
    empty = dashboard_page({})
    assert "СЕГОДНЯ" in empty
    assert "нет данных за последние дни" in empty
