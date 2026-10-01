# -*- coding: utf-8 -*-
"""Вкладка «Online-STAFF»: живой онлайн серверов и свои данные администратора."""
from __future__ import annotations

import json

import pytest

from app.staff import data as staff_data

#: Ответ публичного счётчика rmrp.ru — ровно такой, каким он бывает.
_ONLINE = {"total": 2417, "servers": {"prod3": 399, "prod4": 481, "prod1": 479}}


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


@pytest.fixture(autouse=True)
def clean_cache():
    """Каждый тест начинается с пустого кэша онлайна."""
    staff_data._cache.update(at=0.0, data=None)
    yield
    staff_data._cache.update(at=0.0, data=None)


def test_fetch_reads_public_counter_and_caches(monkeypatch):
    calls: list[int] = []

    def fake_urlopen(request, timeout=0):
        calls.append(timeout)
        assert request.full_url == staff_data.ONLINE_URL
        assert timeout == staff_data.TIMEOUT_SEC
        return _FakeResponse(json.dumps(_ONLINE).encode("utf-8"))

    monkeypatch.setattr(staff_data.urllib.request, "urlopen", fake_urlopen)

    data = staff_data.fetch()
    assert data["found"] is True
    assert data["total"] == 2417
    assert list(data["servers"]) == ["prod1", "prod3", "prod4"]   # по номеру сервера
    assert data["updated"]
    assert len(calls) == 1

    staff_data.fetch()                       # кэш — сеть не трогаем
    assert len(calls) == 1
    staff_data.fetch(force=True)             # кнопка «Обновить» — снова запрос
    assert len(calls) == 2


def test_fetch_never_invents_numbers_when_network_is_down(monkeypatch):
    def boom(*exc, **kwargs):
        raise OSError("нет сети")

    monkeypatch.setattr(staff_data.urllib.request, "urlopen", boom)
    data = staff_data.fetch()
    assert data["found"] is False
    assert data["total"] == 0 and data["servers"] == {}
    assert "нет сети" in data["error"]

    html = staff_data.panel_html({}, network=True)     # кэш уже с этой ошибкой
    assert "нет данных" in html
    assert ">0<" not in html                            # выдуманных нулей нет


def test_admin_card_comes_from_own_game_log():
    """Карточка администратора — статик, имя и админ-ранг из своих логов."""
    person = staff_data.admin()
    assert set(person) == {
        "found", "static_id", "name", "staff", "level", "online", "updated",
        "source",
    }
    if person["found"]:
        assert person["static_id"] == "958726"
        assert person["name"] == "Артур Соколов"
        assert person["staff"] == "admin_plus"


def test_panel_html_shows_online_and_admin(monkeypatch):
    monkeypatch.setattr(staff_data, "fetch", lambda force=False: {
        "found": True, "error": "", "total": 2417,
        "servers": {"prod4": 481, "prod1": 479},
        "updated": "30.09.2026 00:15",
    })
    html = staff_data.panel_html({}, ids=True, network=True)
    assert "ОНЛАЙН СЕРВЕРА RMRP" in html
    assert 'id="staff-total"' in html and ">2417<" in html
    assert 'id="staff-servers"' in html and "Тверской" in html and ">481<" in html
    assert "Рублёвка" in html and ">479<" in html   # имена серверов, а не prod1… (баг №7)
    assert 'id="staff-updated"' in html and "30.09.2026 00:15" in html
    assert "АДМИНИСТРАТОР" in html
    assert 'href="staff:refresh"' in html

    # страница сайта рисуется без сети — цифры докачает JS
    offline = staff_data.panel_html({}, ids=True, network=False)
    assert 'id="staff-total"' in offline


def test_payload_carries_online_and_admin_for_the_site(monkeypatch):
    monkeypatch.setattr(staff_data, "fetch", lambda force=False: {
        "found": True, "error": "", "total": 100,
        "servers": {"prod4": 40}, "updated": "30.09.2026 00:15",
    })
    payload = json.loads(staff_data.payload())
    assert payload["online"]["total"] == 100
    assert payload["online"]["servers"] == {"prod4": 40}
    assert "staff" in payload["admin"] and "static_id" in payload["admin"]


def test_site_page_has_staff_tab_and_panel():
    from app.web import page as web_page

    html = web_page.dashboard_page({})
    assert 'data-view="staff">Online-STAFF</button>' in html
    assert 'id="view-staff"' in html
    assert 'id="staff-total"' in html and 'id="staff-servers"' in html
    assert "staffRefresh" in html and "/api/online?refresh=1" in html
    assert "статик" in html.lower()
