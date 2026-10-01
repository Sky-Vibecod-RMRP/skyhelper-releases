"""Локальный HTTP-сервер дашборда: страница, вход по коду доступа, JSON-статус.

Только стандартная библиотека. Сервер поднимается в daemon-потоке
(ThreadingHTTPServer), ошибка bind превращается в :class:`WebError` с русским
текстом. Никогда не логируем сам PIN и не отдаём pin_hash в ответах.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import threading
import time
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

from app.paths import resource_dir
from app.staff import data as staff_data
from app.web.page import LOGIN_PAGE, dashboard_page
from app.web.pin import verify_pin

log = logging.getLogger("app.web.server")

COOKIE_NAME = "rmrp_auth"
LOGIN_FAIL_LIMIT = 5       # не больше 5 неудач...
LOGIN_FAIL_WINDOW = 60.0   # ...за 60 секунд на один IP
TOKEN_MAX_AGE = 60 * 60 * 24 * 365   # кука на год
MAX_BODY = 64 * 1024       # потолок размера тела POST-запроса

#: Только «безопасные» имена: путь внутри /img/ собирается из кусков вида a.jpg.
_IMAGE_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$")
_IMAGE_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}

_NOT_FOUND_PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>404 — не найдено</title>
<style>
body { background: #0b0c0e; color: #edeef1; font-family: "Segoe UI", sans-serif;
       padding: 48px 32px; }
a { color: #4ec3f0; }
</style>
</head>
<body>
<h1>404 — страница не найдена</h1>
<p><a href="/">На главную</a></p>
</body>
</html>
"""


class WebError(Exception):
    """Ошибка запуска/работы веб-сервера; сообщение уже по-русски."""


def _set_cookie(token: str) -> str:
    """Кука сессии: HttpOnly, SameSite=Lax, Path=/, на год."""
    return (
        f"{COOKIE_NAME}={token}; Max-Age={TOKEN_MAX_AGE}; "
        "Path=/; HttpOnly; SameSite=Lax"
    )


def _clear_cookie() -> str:
    """Сброс куки (Max-Age=0)."""
    return f"{COOKIE_NAME}=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax"


class WebDashboard:
    """Локальный сайт с живыми цифрами трекера.

    ``provider`` — callable без аргументов, возвращающий dict для
    ``GET /api/status``. Пустой ``pin_hash`` означает «код не задан»:
    вход не требуется, дашборд открыт для всех на localhost.
    """

    def __init__(
        self,
        provider: Callable[[], dict],
        *,
        host: str = "127.0.0.1",
        port: int = 80,
        pin_hash: str = "",
        shots=None,
        config=None,
    ) -> None:
        self.provider = provider
        # Настройки оформления нужны странице: дождь и вид курсора.
        self.config = config
        # Сервис скриншотов нужен, чтобы отдать /api/shots и сами картинки.
        # None — модуль недоступен (например, в тестах или старой конфигурации).
        self.shots = shots
        self._host = host
        self._port = port               # запрошенный; фактический — свойство port
        self._pin_hash = pin_hash or ""
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._tokens: set[str] = set()  # активные сессии (живут до рестарта)
        self._failures: dict[str, list[float]] = {}  # ip → моменты неудач
        self._lock = threading.Lock()

    # --- жизненный цикл ----------------------------------------------------

    def start(self) -> None:
        """Поднимает сервер в daemon-потоке; при занятом порте — WebError."""
        if self._server is not None:
            return
        handler = _make_handler(self)
        try:
            server = ThreadingHTTPServer((self._host, self._port), handler)
        except OSError as exc:
            raise WebError(
                f"Не удалось запустить веб-сервер на {self._host}:{self._port} "
                f"({exc}). Порт {self._port} занят, смени его в настройках."
            ) from exc

        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever, name="rmrp-web", daemon=True
        )
        self._thread.start()
        log.info("Веб-дашборд запущен: %s", self.url)

    def stop(self) -> None:
        """Останавливает сервер; повторный вызов безопасен (идемпотентно)."""
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is None:
            return
        server.shutdown()      # дождаться выхода serve_forever
        server.server_close()  # освободить порт
        if thread is not None:
            thread.join(timeout=5)
        with self._lock:
            self._tokens.clear()
            self._failures.clear()
        log.info("Веб-дашборд остановлен")

    @property
    def running(self) -> bool:
        """Сервер сейчас поднят."""
        return self._server is not None

    @property
    def port(self) -> int:
        """Фактический порт (важен при port=0 — система даёт свой)."""
        if self._server is not None:
            return int(self._server.server_address[1])
        return self._port

    @property
    def url(self) -> str:
        """Адрес для открытия у себя; для 0.0.0.0 всё равно пишем 127.0.0.1."""
        return f"http://127.0.0.1:{self.port}/"

    def status(self) -> dict | None:
        """Статус от provider; None, если тот упал или вернул не dict."""
        try:
            status = self.provider()
        except Exception:
            log.exception("Провайдер статуса выбросил исключение")
            return None
        return status if isinstance(status, dict) else None

    # --- авторизация -------------------------------------------------------

    def _token_valid(self, token: str) -> bool:
        """True, если сессия валидна (или код доступа вообще не задан)."""
        if not self._pin_hash:
            return True
        if not token:
            return False
        with self._lock:
            return token in self._tokens

    def check_pin(self, pin: str) -> bool:
        """Сверяет присланный код; при пустом pin_hash код не нужен.

        Сам код здесь и в логах никогда не сохраняется и не выводится.
        """
        if not self._pin_hash:
            return True
        return verify_pin(pin, self._pin_hash)

    def _new_token(self) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._tokens.add(token)
        return token

    def _revoke_token(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            self._tokens.discard(token)

    # --- rate limit неудачных входов ---------------------------------------

    def login_limited(self, ip: str) -> bool:
        """True, если IP сделал слишком много неудач за последнюю минуту."""
        now = time.monotonic()
        with self._lock:
            fails = [
                t for t in self._failures.get(ip, ()) if now - t < LOGIN_FAIL_WINDOW
            ]
            if fails:
                self._failures[ip] = fails
            else:
                self._failures.pop(ip, None)
            return len(fails) >= LOGIN_FAIL_LIMIT

    def note_login_failure(self, ip: str) -> None:
        """Записывает неудачную попытку (успешные не учитываются)."""
        now = time.monotonic()
        with self._lock:
            fails = [
                t for t in self._failures.get(ip, ()) if now - t < LOGIN_FAIL_WINDOW
            ]
            fails.append(now)
            self._failures[ip] = fails
            if len(self._failures) > 128:
                # чистим протухшие ip, чтобы словарь не рос бесконечно
                self._failures = {
                    addr: times
                    for addr, times in self._failures.items()
                    if any(now - t < LOGIN_FAIL_WINDOW for t in times)
                }


def _make_handler(dash: WebDashboard) -> type[BaseHTTPRequestHandler]:
    """Создаёт класс обработчика, привязанный к конкретному дашборду."""

    class Handler(BaseHTTPRequestHandler):
        # Версию в заголовке Server не раскрываем — зачем помогать сканерам.
        server_version = "SKY HELPER"
        sys_version = ""

        # --- служебное -----------------------------------------------------

        def log_message(self, fmt: str, *args: object) -> None:
            """Тихий лог вместо печати в stderr (шум в тестах не нужен)."""
            log.debug("%s %s", self.client_address[0], fmt % args)

        def _send(
            self,
            code: int,
            body: bytes,
            content_type: str,
            extra: tuple[tuple[str, str], ...] = (),
        ) -> None:
            """Ответ с обязательными заголовками no-store/nosniff."""
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for name, value in extra:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, code: int, page: str) -> None:
            self._send(code, page.encode("utf-8"), "text/html; charset=utf-8")

        def _send_json(self, code: int, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(code, body, "application/json; charset=utf-8")

        def _send_text(self, code: int, text: str) -> None:
            self._send(code, text.encode("utf-8"), "text/plain; charset=utf-8")

        def _redirect(self, extra: tuple[tuple[str, str], ...] = ()) -> None:
            self._send(302, b"", "text/plain; charset=utf-8", (("Location", "/"),) + extra)

        def _cookie_token(self) -> str:
            """Токен из заголовка Cookie; при любой ошибке — пустая строка."""
            raw = self.headers.get("Cookie") or ""
            if not raw:
                return ""
            cookie = SimpleCookie()
            try:
                cookie.load(raw)
            except CookieError:
                return ""
            morsel = cookie.get(COOKIE_NAME)
            return morsel.value if morsel else ""

        # --- маршруты ------------------------------------------------------

        def do_GET(self) -> None:  # noqa: N802 (имена из BaseHTTPRequestHandler)
            path = urlparse(self.path).path
            if path == "/":
                self._handle_index()
            elif path == "/api/status":
                self._handle_status()
            elif path == "/api/online":
                self._handle_online()
            elif path == "/api/shots":
                self._handle_shots()
            elif path.startswith("/shots/"):
                self._handle_shot_file(path)
            elif path.startswith("/img/"):
                self._handle_image(path)
            elif path == "/logout":
                self._handle_logout()
            else:
                self._handle_not_found()

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/login":
                self._handle_login()
            else:
                self._handle_not_found()

        def _handle_index(self) -> None:
            """GET /: дашборд, а без валидной куки — страница входа."""
            if not dash._token_valid(self._cookie_token()):
                self._send_html(200, LOGIN_PAGE.replace("{{error}}", ""))
                return
            # Первую отрисовку делаем сразу с цифрами; сбой провайдера
            # не должен ломать страницу — JS доберёт данные сам.
            try:
                status = dash.provider()
            except Exception:
                log.exception("Провайдер статуса выбросил исключение при рендере")
                status = {}
            self._send_html(200, dashboard_page(
                status if isinstance(status, dict) else {},
                self._page_options(),
            ))

        def _page_options(self) -> dict:
            """Настройки оформления для страницы: дождь и вид курсора."""
            cfg = dash.config
            return {
                "rain": bool(getattr(cfg, "rain_enabled", True)),
                "cursor": str(getattr(cfg, "cursor_style", "white")),
            }

        def _handle_status(self) -> None:
            """GET /api/status: JSON от provider, без куки — 401."""
            if not dash._token_valid(self._cookie_token()):
                self._send_json(401, {"error": "unauthorized"})
                return
            try:
                status = dash.provider()
                body = json.dumps(status, ensure_ascii=False).encode("utf-8")
            except Exception:
                log.exception("Провайдер статуса выбросил исключение")
                self._send_json(500, {"error": "provider failed"})
                return
            self._send(200, body, "application/json; charset=utf-8")

        def _handle_online(self) -> None:
            """GET /api/online: живой онлайн серверов RMRP (кэш 60 с).

            ``?refresh=1`` — обновить вопреки кэшу (кнопка «Обновить»).
            Сеть может быть недоступной: тогда приходит ``found:false``
            и страница остаётся с прежними цифрами.
            """
            if not dash._token_valid(self._cookie_token()):
                self._send_json(401, {"error": "unauthorized"})
                return
            force = "refresh=1" in (urlparse(self.path).query or "")
            try:
                data = staff_data.fetch(force=force)
            except Exception:                     # noqa: BLE001 — не роняем сайт
                log.exception("Не удалось получить онлайн серверов")
                data = {"found": False, "error": "online failed",
                        "total": 0, "servers": {}, "updated": ""}
            self._send_json(200, data)

        def _handle_shots(self) -> None:
            """GET /api/shots?week=…: дерево «неделя → категории → файлы».

            Пустая структура вместо ошибки, если модуль скриншотов
            недоступен — вкладка просто покажет «скриншотов пока нет».
            """
            if not dash._token_valid(self._cookie_token()):
                self._send_json(401, {"error": "unauthorized"})
                return
            empty = {"weeks": [], "selected": "", "current": "",
                     "categories": [], "total": 0}
            if dash.shots is None:
                self._send_json(200, empty)
                return
            query = parse_qs(urlparse(self.path).query or "")
            week = (query.get("week") or [""])[0]
            try:
                data = dash.shots.report_tree(week or None)
            except Exception:
                log.exception("Не удалось собрать дерево скриншотов")
                self._send_json(500, {"error": "shots failed"})
                return
            self._send_json(200, data)

        def _handle_shot_file(self, path: str) -> None:
            """GET /shots/<неделя>/<категория>/<файл.jpg>: сама картинка недели."""
            if not dash._token_valid(self._cookie_token()):
                self._send_text(401, "Требуется вход")
                return
            if dash.shots is None:
                self._handle_not_found()
                return
            parts = [unquote(piece) for piece in path[len("/shots/"):].split("/")]
            if len(parts) != 3:
                self._handle_not_found()
                return
            target = dash.shots.resolve_file(*parts)
            if target is None:
                self._handle_not_found()
                return
            try:
                blob = target.read_bytes()
            except OSError:
                self._handle_not_found()
                return
            self._send(200, blob, "image/jpeg")

        def _handle_image(self, path: str) -> None:
            """GET /img/...: скриншоты событий из папки приложения.

            Тот же вход, что и на саму страницу; путь собирается только из
            «безопасных» имён, поэтому выйти за папку картинок нельзя.
            """
            if not dash._token_valid(self._cookie_token()):
                self._send_text(401, "Требуется вход")
                return
            rel = path[len("/img/"):]
            if not _IMAGE_PATH_RE.match(rel):
                self._handle_not_found()
                return
            root = (resource_dir("web", "static") / "img").resolve()
            target = (root / rel).resolve()
            if target.parent != root and root not in target.parents:
                self._handle_not_found()
                return
            kind = _IMAGE_TYPES.get(target.suffix.lower())
            if kind is None or not target.is_file():
                self._handle_not_found()
                return
            try:
                blob = target.read_bytes()
            except OSError:
                self._handle_not_found()
                return
            self._send(200, blob, kind)

        def _handle_login(self) -> None:
            """POST /login: form-поле pin, кука + 302 либо 403 со страницей."""
            ip = self.client_address[0]
            if dash.login_limited(ip):
                log.warning("Слишком много неудачных попыток входа с %s", ip)
                self._send_text(429, "Слишком много попыток, подожди минуту")
                return

            length_text = self.headers.get("Content-Length") or "0"
            try:
                length = max(0, min(int(length_text), MAX_BODY))
            except ValueError:
                length = 0
            raw = self.rfile.read(length) if length else b""
            fields = parse_qs(raw.decode("utf-8", errors="replace"),
                              keep_blank_values=True)
            pin = (fields.get("pin") or [""])[0]

            if dash.check_pin(pin):
                token = dash._new_token()
                log.info("Успешный вход по коду доступа: ip=%s", ip)
                self._redirect((("Set-Cookie", _set_cookie(token)),))
            else:
                # В лог уходит только факт неудачи, сам код — никогда.
                dash.note_login_failure(ip)
                log.warning("Неудачная попытка входа: ip=%s", ip)
                page = LOGIN_PAGE.replace("{{error}}", "Неверный код доступа")
                self._send_html(403, page)

        def _handle_logout(self) -> None:
            """GET /logout: закрываем сессию и сбрасываем куку."""
            dash._revoke_token(self._cookie_token())
            log.info("Выход из веб-дашборда: ip=%s", self.client_address[0])
            self._redirect((("Set-Cookie", _clear_cookie()),))

        def _handle_not_found(self) -> None:
            self._send_html(404, _NOT_FOUND_PAGE)

    return Handler
