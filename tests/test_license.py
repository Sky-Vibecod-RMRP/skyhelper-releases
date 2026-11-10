# -*- coding: utf-8 -*-
"""Лицензия: подпись, привязка к ПК, срок, отзыв, откат часов.

Все тесты работают на одноразовых ключах Ed25519 и во временной папке —
приватный ключ администратора и %APPDATA% здесь не участвуют.
"""
import datetime as dt
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import license as lic
from app import license_public

PC = "RM-7F3A-9K2D-4M1P-8ZR7"
OTHER_PC = "RM-AAAA-BBBB-CCCC-DDDD"


@pytest.fixture()
def pair():
    """Свежая пара ключей + PEM публичного для передачи в verify()."""
    private = Ed25519PrivateKey.generate()
    pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private, pem


def issue(private, *, hwid=PC, days=30, who="Nick",
          today=None, issued="2026-10-01T00:00:00Z"):
    base = today or dt.date(2026, 10, 1)
    payload = lic.build_payload(
        hwid, issued, base + dt.timedelta(days=days), who,
    )
    return lic.sign_payload(payload, private), payload


# --- подпись и разбор -------------------------------------------------------

def test_roundtrip_ok(pair):
    private, pem = pair
    text, _payload = issue(private)
    result = lic.verify(text, hwid=PC, today=dt.date(2026, 10, 5), public_pem=pem)
    assert result.hwid == PC
    assert result.who == "Nick"
    assert result.expires == dt.date(2026, 10, 31)
    assert result.raw == text


def test_key_id_short_and_stable(pair):
    private, pem = pair
    text, payload = issue(private)
    kid = lic.key_id(payload)
    assert len(kid) == 9 and kid[4] == "-"          # вид ABCD-EFGH
    _payload2, kid2 = lic.parse_and_verify(text, public_pem=pem)
    assert kid2 == kid


def test_key_id_differs_for_different_issues(pair):
    private, pem = pair
    first, _ = issue(private, who="Nick", issued="2026-10-01T10:00:00Z")
    second, _ = issue(private, who="Nick", issued="2026-10-01T11:00:00Z")
    assert (lic.parse_and_verify(first, public_pem=pem)[1]
            != lic.parse_and_verify(second, public_pem=pem)[1])


def test_tampered_payload_rejected(pair):
    private, pem = pair
    text, payload = issue(private, days=30)
    # меняем дату срока в payload, подпись не переподписываем
    longer = payload.replace("2026-10-31", "2027-10-31")
    forged = f"{lic._b64e(longer.encode())}.{text.split('.', 1)[1]}"
    with pytest.raises(lic.LicenseError) as err:
        lic.verify(forged, hwid=PC, public_pem=pem)
    assert err.value.code == "bad_signature"


def test_foreign_key_rejected(pair):
    _priv, pem = pair
    stranger = Ed25519PrivateKey.generate()
    text, _payload = issue(stranger)
    with pytest.raises(lic.LicenseError) as err:
        lic.verify(text, hwid=PC, public_pem=pem)
    assert err.value.code == "bad_signature"


def test_malformed_variants(pair):
    private, pem = pair
    _text, _payload = issue(private)
    for broken, code in (
        ("", "missing"),
        ("no-dot-here", "malformed"),
        ("@@@.+++", "malformed"),
    ):
        with pytest.raises(lic.LicenseError) as err:
            lic.verify(broken, hwid=PC, public_pem=pem)
        assert err.value.code == code


def test_wrong_pc(pair):
    private, pem = pair
    text, _payload = issue(private, hwid=OTHER_PC)
    with pytest.raises(lic.LicenseError) as err:
        lic.verify(text, hwid=PC, public_pem=pem)
    assert err.value.code == "wrong_pc"
    # код этого ПК показан в сообщении — пользователь увидит свой код
    assert PC in err.value.message


def test_hwid_written_messy_still_matches(pair):
    # администратор мог записать код, скопированный из чата с пробелами
    private, pem = pair
    text, _payload = issue(private, hwid="rm-7f3a 9k2d-4m1p 8zr7")
    result = lic.verify(text, hwid=PC, today=dt.date(2026, 10, 5), public_pem=pem)
    assert result.hwid == "RM-7F3A 9K2D-4M1P 8ZR7"   # как записали — так и храним
    # а сравнивается «голыми» символами, поэтому ПК всё равно подходит
    lic.verify(text, hwid="rm7f3a9k2d4m1p8zr7", today=dt.date(2026, 10, 5), public_pem=pem)


def test_expired(pair):
    private, pem = pair
    text, _payload = issue(private, days=10)
    with pytest.raises(lic.LicenseError) as err:
        lic.verify(text, hwid=PC, today=dt.date(2026, 10, 12), public_pem=pem)
    assert err.value.code == "expired"
    # в последний день ещё работает
    lic.verify(text, hwid=PC, today=dt.date(2026, 10, 11), public_pem=pem)


def test_bad_format_version(pair):
    private, pem = pair
    payload = lic.build_payload(PC, "2026-10-01T00:00:00Z", dt.date(2027, 1, 1), "x")
    v99 = "99" + payload[1:]
    text = lic.sign_payload(v99, private)
    with pytest.raises(lic.LicenseError) as err:
        lic.verify(text, hwid=PC, public_pem=pem)
    assert err.value.code == "malformed"


def test_no_public_key_configured(pair):
    private, _pem = pair
    text, _payload = issue(private)
    with pytest.raises(lic.LicenseError) as err:
        lic.verify(text, hwid=PC, public_pem="")
    assert err.value.code == "no_public_key"


def test_committed_public_key_is_real():
    # защита от сборки exe «без проверки»: модуль license_public заполнен
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    key = lic.load_public_key()
    assert isinstance(key, Ed25519PublicKey)
    assert "BEGIN PUBLIC KEY" in key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


def test_private_key_lives_outside_project():
    # приватный ключ не должен лежать в проекте — его увозит архив раздачи
    from pathlib import Path

    project = Path(__file__).resolve().parent.parent
    home_key = lic.default_private_key_path()
    assert home_key.parent != project
    assert home_key.name == ".rmrp_signing_key.pem"


# --- список отзывов ---------------------------------------------------------

def test_revocations_sign_and_verify(pair):
    private, pem = pair
    text = lic.sign_revocations(["ABCD-EFGH", "abcd-efgh"], private_key=private)
    kids = lic.verify_revocations(text, public_pem=pem)
    assert kids == {"ABCD-EFGH"}   # дубликат в другом регистре схлопывается


def test_revocations_tamper_rejected(pair):
    _private, pem = pair
    text = lic.sign_revocations([], private_key=Ed25519PrivateKey.generate())
    with pytest.raises(lic.LicenseError) as err:
        lic.verify_revocations(text, public_pem=pem)
    assert err.value.code == "bad_signature"


def test_revocations_garbage_is_malformed(pair):
    _private, pem = pair
    for junk in ("not json", '{"body":"x"}', '{"body":"@@@","sig":"+++"}'):
        with pytest.raises(lic.LicenseError) as err:
            lic.verify_revocations(junk, public_pem=pem)
        assert err.value.code in {"malformed", "bad_signature"}


def test_revocations_empty_is_empty_set(pair):
    _private, pem = pair
    assert lic.verify_revocations("", public_pem=pem) == set()


def test_key_id_format_matches_revocation_entry(pair):
    private, pem = pair
    text, payload = issue(private)
    kid = lic.key_id(payload)
    signed = lic.sign_revocations([kid], private_key=private)
    assert kid in lic.verify_revocations(signed, public_pem=pem)


# --- часы -------------------------------------------------------------------

def test_clock_ok_without_state():
    assert lic.clock_ok({})


def test_clock_rollback_detected():
    seen = dt.datetime(2026, 10, 1, 12, 0, tzinfo=dt.timezone.utc)
    state = {"last_seen": seen.isoformat()}
    assert lic.clock_ok(state, now=seen + dt.timedelta(hours=1))
    assert lic.clock_ok(state, now=seen + dt.timedelta(hours=5))   # дрейф/NTP
    # откат на сутки — попытка продлить истёкший ключ
    assert not lic.clock_ok(state, now=seen - dt.timedelta(days=1))


def test_clock_garbage_state_not_blocking():
    assert lic.clock_ok({"last_seen": "вчера"})


# --- маршрут «всё разом» ----------------------------------------------------

@pytest.fixture()
def appdata(tmp_path, monkeypatch):
    """Подменяем папку %APPDATA% приложения на временную."""
    monkeypatch.setattr(lic, "app_dir", lambda: tmp_path)
    return tmp_path


def test_check_full_route(pair, appdata, monkeypatch):
    private, pem = pair
    text, _payload = issue(private, days=30)
    lic.save_license_text(text)
    lic.save_cached_revocations(
        lic.sign_revocations(["OTHERS-KEY"], private_key=private)
    )
    monkeypatch.setattr(license_public, "PUBLIC_KEY_PEM", pem)

    result = lic.check(hwid_value=PC, today=dt.date(2026, 10, 5))
    assert result.key_id not in lic.load_cached_revocations()
    assert result.who == "Nick"


def test_check_missing_key(appdata):
    with pytest.raises(lic.LicenseError) as err:
        lic.check(hwid_value=PC)
    assert err.value.code == "missing"


def test_check_revoked(pair, appdata, monkeypatch):
    private, pem = pair
    text, payload = issue(private, days=30)
    lic.save_license_text(text)
    lic.save_cached_revocations(
        lic.sign_revocations([lic.key_id(payload)], private_key=private)
    )
    monkeypatch.setattr(license_public, "PUBLIC_KEY_PEM", pem)

    with pytest.raises(lic.LicenseError) as err:
        lic.check(hwid_value=PC, today=dt.date(2026, 10, 5))
    assert err.value.code == "revoked"
    assert lic.key_id(payload) in err.value.message


def test_check_clock_rollback(pair, appdata, monkeypatch):
    private, pem = pair
    text, _payload = issue(private, days=30)
    lic.save_license_text(text)
    lic.save_cached_revocations(lic.sign_revocations([], private_key=private))
    monkeypatch.setattr(license_public, "PUBLIC_KEY_PEM", pem)

    # прошлый запуск был давно — всё чисто
    lic.state_path().write_text(
        json.dumps({"last_seen": "2020-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    assert lic.check(hwid_value=PC, today=dt.date(2026, 10, 5))

    # «прошлый запуск» из будущего = часы откатили — отказ
    future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    lic.state_path().write_text(
        json.dumps({"last_seen": future.isoformat()}), encoding="utf-8",
    )
    with pytest.raises(lic.LicenseError) as err:
        lic.check(hwid_value=PC, today=dt.date(2026, 10, 5))
    assert err.value.code == "clock"


def test_cache_read_survives_tampering(pair, appdata):
    _private, _pem = pair
    assert lic.load_cached_revocations() == set()       # файла нет
    lic.revocation_cache_path().write_text("мусор", encoding="utf-8")
    assert lic.load_cached_revocations() == set()       # битый файл = пусто
    lic.save_cached_revocations(
        lic.sign_revocations([], private_key=Ed25519PrivateKey.generate())
    )
    assert lic.load_cached_revocations() == set()       # чужая подпись = пусто


def test_state_roundtrip(pair, appdata):
    private, pem = pair
    text, _payload = issue(private)
    result = lic.verify(text, hwid=PC, today=dt.date(2026, 10, 1), public_pem=pem)
    lic.save_state(result, now=dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc))
    state = lic.load_state()
    assert state["key_id"] == result.key_id
    assert state["expires"] == "2026-10-31"
    assert state["last_seen"].startswith("2026-10-01T00:00:00")


def test_enforcement_rules(tmp_path, monkeypatch):
    # в исходниках без ключа — не блокируем (разработка и тесты)
    monkeypatch.setattr(lic, "app_dir", lambda: tmp_path)
    monkeypatch.setattr(lic.sys, "frozen", False, raising=False)
    assert not lic.enforcement_required()
    # а активированный ключ в исходниках — уже блокируем
    lic.save_license_text("whatever")
    assert lic.enforcement_required()
    # в собранном exe — всегда
    monkeypatch.setattr(lic.sys, "frozen", True, raising=False)
    assert lic.enforcement_required()


def test_save_and_read_license_text(appdata):
    lic.save_license_text("  ABC.DEF  \n")
    assert lic.read_license_text() == "ABC.DEF"
    appdata.joinpath("license.key").unlink()
    assert lic.read_license_text() == ""


def test_no_private_keys_inside_project():
    # приватный ключ живёт в домашней папке; в проекте (и в архиве
    # раздачи) его быть не должно — ни файлом, ни в тексте кода
    from pathlib import Path

    project = Path(__file__).resolve().parent.parent
    pem_files = [
        p for p in project.rglob("*.pem")
        if not {"__pycache__", "build", ".pytest_cache"} & set(p.parts)
    ]
    assert pem_files == [], f"в проекте лежат ключи: {pem_files}"
    marker = "PRIVATE" + " KEY-----"      # маркер собираем из кусков: иначе
    for path in project.rglob("*.py"):     # проверка нашла бы саму себя
        if {"__pycache__", "build", ".pytest_cache"} & set(path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert marker not in text, f"приватный PEM в {path}"


def test_build_payload_keeps_pipe_out_of_who():
    payload = lic.build_payload(PC, "2026-10-01T00:00:00Z", dt.date(2027, 1, 1),
                                "Nick|root")
    assert payload.count("|") == 4          # ровно 4 разделителя, 5 полей
    assert payload.endswith("Nick/root")
