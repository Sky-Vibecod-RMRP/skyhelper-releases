"""Локальный веб-дашборд трекера (только стандартная библиотека, офлайн)."""
from __future__ import annotations

from app.web.page import LOGIN_PAGE, dashboard_page
from app.web.pin import hash_pin, verify_pin
from app.web.server import WebDashboard, WebError

__all__ = [
    "LOGIN_PAGE",
    "WebDashboard",
    "WebError",
    "dashboard_page",
    "hash_pin",
    "verify_pin",
]
