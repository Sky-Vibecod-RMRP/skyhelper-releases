# -*- coding: utf-8 -*-
"""Лицензия exe: подписанный ключ с привязкой к ПК, сроком и отзывом.

Схема (решена 01.10.2026): ключи выдаёт администратор проекта вручную,
исходники остаются у него; exe пускает только при валидном ключе.

**Что такое ключ.** Строка ``<payload>.<подпись>``: внутри payload —
версия формата, код ПК, дата выдачи, срок действия и метка (ник админа).
Подпись — Ed25519, приватный ключ живёт у администратора
(``~/.rmrp_signing_key.pem``) и в репозиторий не попадает; в программу
встроен только публичный (:mod:`app.license_public`), поэтому
распаковка exe никому не даёт права выдавать ключи.

**Проверки при старте** (по порядку, каждая даёт свой ``code``):

``missing``       ключа нет; ``no_public_key`` — в сборку не вложен
                  публичный ключ (нужно ``tools/gen_key.py init``);
``malformed``     строка битая / скопирована не до конца;
``bad_signature`` подпись не проходит — ключ выпущен не этой программой;
``wrong_pc``      код ПК внутри ключа не совпадает с этой машиной;
``expired``       срок действия истёк;
``revoked``       key_id есть в подписанном списке отзывов;
``clock``         системное время раньше, чем при прошлом запуске
                  (попытка откатить дату, чтобы продлить ключ).

**Отзыв без сервера.** Администратор дописывает key_id в подписанный
файл и публикует его на статическом URL (публичная gist-запись).
Программа при наличии сети качает список, сверяет и кладёт в кэш;
без сети работает по кэшу — так решено для админов: пускать, опираясь
на кэш, а не блокировать офлайн-запуск.
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import json
import sys
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.paths import app_dir

#: Версия формата payload (внутри подписи) и списка отзывов.
FORMAT = 1

#: Разрешённый откат часов между запусками (часы/NTP поправляют сами).
CLOCK_TOLERANCE = _dt.timedelta(hours=2)

#: Адрес подписанного списка отзывов. Пусто = адрес задаётся в настройках
#: (администратор создаст gist-запись и впишет ссылку — пересборка не нужна).
DEFAULT_REVOCATION_URL = ""

#: Адрес по умолчанию для кэша списка отзывов при пустом URL — не используется,
#: но держим константу, чтобы код проверки нигде не разрастался.
_REVOKED_FILE = "revocations.json"


class LicenseError(Exception):
    """Причина, по которой ключ не принят (``code`` — машинный идентификатор)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class License:
    """Раскодированный и проверенный ключ."""

    key_id: str
    hwid: str
    issued: str            # ISO-время выдачи (информативно)
    expires: _dt.date      # последний день действия включительно
    who: str               # метка: кому выдан (ник админа)
    raw: str               # исходная строка ключа


# --- файлы ------------------------------------------------------------------

def license_path() -> Path:
    """Где лежит активированный ключ (рядом с config.json)."""
    return app_dir() / "license.key"


def state_path() -> Path:
    """Состояние проверки: когда ключ видели в последний раз."""
    return app_dir() / "license_state.json"


def revocation_cache_path() -> Path:
    """Кэш подписанного списка отзывов (подпись хранится целиком)."""
    return app_dir() / _REVOKED_FILE


def read_license_text() -> str:
    """Текст ключа из файла; нет файла → пустая строка."""
    try:
        return license_path().read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def save_license_text(text: str) -> Path:
    """Сохранить ключ (из окна активации)."""
    path = license_path()
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


# --- низкоуровневые: кодирование и подписи ----------------------------------

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def build_payload(hwid: str, issued: str, expires: _dt.date, who: str) -> str:
    """Собрать строку payload. Разделитель ``|``; в метке ``|`` запрещён."""
    safe_who = (who or "").replace("|", "/").strip()
    return "|".join((
        str(FORMAT),
        hwid.strip().upper(),
        issued.strip(),
        expires.isoformat(),
        safe_who,
    ))


def key_id(payload: str) -> str:
    """Короткий идентификатор ключа: отпечаток payload (для списка отзывов)."""
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    code = base64.b32encode(digest).decode("ascii").rstrip("=")[:8]
    return f"{code[:4]}-{code[4:]}"


def load_public_key(pem: str | None = None) -> Ed25519PublicKey:
    """Публичный ключ проверки: из модуля license_public (или явный PEM)."""
    from app import license_public

    text = (pem if pem is not None else license_public.PUBLIC_KEY_PEM).strip()
    if not text:
        raise LicenseError(
            "no_public_key",
            "В программу не вложен ключ проверки лицензий — "
            "нужно выполнить tools/gen_key.py init и пересобрать exe",
        )
    try:
        key = serialization.load_pem_public_key(text.encode("utf-8"))
    except (ValueError, TypeError) as exc:                      # noqa: PERF203
        raise LicenseError("no_public_key", f"Публичный ключ не читается: {exc}")
    if not isinstance(key, Ed25519PublicKey):
        raise LicenseError("no_public_key", "Ожидался ключ Ed25519")
    return key


def load_private_key(path: Path | str | None = None) -> Ed25519PrivateKey:
    """Приватный ключ подписи (нужен только tools/gen_key.py)."""
    target = Path(path) if path else default_private_key_path()
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise LicenseError("missing", f"Приватный ключ не найден: {target} ({exc})")
    key = serialization.load_pem_private_key(raw, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise LicenseError("no_public_key", "Ожидался приватный ключ Ed25519")
    return key


def default_private_key_path() -> Path:
    """Где хранится приватный ключ — ДОМА, не в проекте.

    Проект целиком уезжает в архив раздачи (в нём есть ``tools/``), поэтому
    ключ подписанная лежит в домашней папке: ``~/.rmrp_signing_key.pem``.
    """
    return Path.home() / ".rmrp_signing_key.pem"


def sign_payload(payload: str, private_key: Ed25519PrivateKey) -> str:
    """Подписать payload → строка ключа ``<payload-b64>.<sig-b64>``."""
    signature = private_key.sign(payload.encode("utf-8"))
    return f"{_b64e(payload.encode('utf-8'))}.{_b64e(signature)}"


# --- проверка ключа ---------------------------------------------------------

def parse_and_verify(
    text: str,
    *,
    public_pem: str | None = None,
) -> tuple[str, str]:
    """Проверить подпись и вернуть ``(payload, key_id)``. Только криптография."""
    raw = (text or "").strip()
    if not raw:
        raise LicenseError("missing", "Ключ активации не указан")
    if "." not in raw:
        raise LicenseError(
            "malformed", "Ключ скопирован не полностью — нет разделителя «.»",
        )
    payload_b64, signature_b64 = raw.split(".", 1)
    try:
        payload = _b64d(payload_b64).decode("utf-8")
        signature = _b64d(signature_b64)
    except (ValueError, UnicodeDecodeError) as exc:
        raise LicenseError("malformed", f"Ключ повреждён: {exc}")
    if not payload or not signature:
        raise LicenseError(
            "malformed", "Ключ повреждён — пустые данные подписи",
        )
    try:
        key = load_public_key(public_pem)
    except LicenseError:
        raise
    try:
        key.verify(signature, payload.encode("utf-8"))
    except InvalidSignature:
        raise LicenseError(
            "bad_signature",
            "Подпись не проходит: ключ выпущен не этой программой "
            "или был изменён",
        )
    return payload, key_id(payload)


def verify(
    text: str,
    *,
    hwid: str | None = None,
    today: _dt.date | None = None,
    public_pem: str | None = None,
) -> License:
    """Полная проверка: подпись → разбор → ПК → срок."""
    payload, kid = parse_and_verify(text, public_pem=public_pem)
    parts = payload.split("|")
    if len(parts) < 5 or parts[0] != str(FORMAT):
        raise LicenseError(
            "malformed",
            f"Формат ключа не распознан (ожидается v{FORMAT} со служебными полями)",
        )
    _version, raw_hwid, issued, raw_expires, who = parts[:5]
    try:
        expires = _dt.date.fromisoformat(raw_expires)
    except ValueError:
        raise LicenseError("malformed", "Срок действия в ключе записан неверно")

    if hwid is not None and not _same_hwid(raw_hwid, hwid):
        raise LicenseError(
            "wrong_pc",
            "Ключ выдан для другого компьютера: этот ПК имеет код "
            f"{hwid}, а ключ — {raw_hwid}",
        )

    day = today or _dt.date.today()
    if day > expires:
        raise LicenseError(
            "expired",
            f"Срок действия ключа истёк {expires.strftime('%d.%m.%Y')}",
        )
    return License(
        key_id=kid, hwid=raw_hwid, issued=issued, expires=expires,
        who=who, raw=text.strip(),
    )


def _same_hwid(expected: str, actual: str) -> bool:
    from app import hwid as hwid_mod

    return hwid_mod.matches(expected, actual)


# --- список отзывов ---------------------------------------------------------

def _revocations_body(kids: list[str], now: _dt.datetime) -> bytes:
    """Канонический JSON списка отзывов (подписывается целиком)."""
    body = {
        "v": FORMAT,
        "ts": now.replace(microsecond=0, tzinfo=None).isoformat() + "Z",
        "revoked": sorted({kid.strip().upper() for kid in kids if kid.strip()}),
    }
    return json.dumps(body, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def sign_revocations(
    kids: list[str],
    *,
    private_key: Ed25519PrivateKey,
    now: _dt.datetime | None = None,
) -> str:
    """Собрать подписанный файл списка отзывов (его и публикуют в gist)."""
    moment = now or _dt.datetime.now(_dt.timezone.utc)
    body = _revocations_body(kids, moment)
    signature = private_key.sign(body)
    return json.dumps(
        {"v": FORMAT, "body": _b64e(body), "sig": _b64e(signature)},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )


def verify_revocations(
    text: str,
    *,
    public_pem: str | None = None,
) -> set[str]:
    """Проверить подписанный список отзывов → множество отозванных key_id."""
    if not (text or "").strip():
        return set()
    try:
        envelope = json.loads(text)
        body = _b64d(str(envelope["body"]))
        signature = _b64d(str(envelope["sig"]))
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise LicenseError("malformed", f"Список отзывов повреждён: {exc}")
    try:
        load_public_key(public_pem).verify(signature, body)
    except InvalidSignature:
        raise LicenseError("bad_signature", "Список отзывов не подписан этой программой")
    try:
        data = json.loads(body)
        kids = data["revoked"]
    except (ValueError, KeyError, TypeError) as exc:
        raise LicenseError("malformed", f"Список отзывов повреждён: {exc}")
    return {str(kid).strip().upper() for kid in kids}


def download_revocations(url: str, *, timeout: float = 5.0) -> str:
    """Скачать подписанный список отзывов (обычный HTTP GET)."""
    if not url.strip():
        raise LicenseError("missing", "Адрес списка отзывов не задан")
    request = urllib.request.Request(          # noqa: S310 (намеренный URL)
        url, headers={"User-Agent": "SKYHELPER/license"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read().decode("utf-8", "replace")


def load_cached_revocations() -> set[str]:
    """Кэш списка отзывов: битый файл считаем пустым (пользователь мог править)."""
    try:
        text = revocation_cache_path().read_text(encoding="utf-8")
    except OSError:
        return set()
    try:
        return verify_revocations(text)
    except LicenseError:
        return set()


def save_cached_revocations(text: str) -> None:
    """Положить свежий (проверенный снаружи) список в кэш."""
    revocation_cache_path().write_text(text, encoding="utf-8")


def refresh_revocations(url: str, *, timeout: float = 5.0) -> int:
    """Скачать список отзывов, проверить подпись и обновить кэш.

    Возвращает число отозванных ключей. Подпись проверяется **до** записи
    в кэш — случайный или подделанный файл никогда не попадёт на диск.
    Скачивание неудачное — кэш не трогаем (старый список продолжает
    работать, офлайн-запуск не страдает).
    """
    text = download_revocations(url, timeout=timeout)
    kids = verify_revocations(text)
    save_cached_revocations(text)
    return len(kids)


def start_revocation_refresh(url: str) -> bool:
    """Обновить кэш списка отзывов в фоне (daemon-поток, старт не тормозит).

    Свежий список применится **на следующем запуске** — так и задумано:
    отзыв не должен подвешивать программу ради одного HTTP-запроса.
    Возвращает False, если обновлять нечего.
    """
    if not url.strip():
        return False

    def worker() -> None:
        try:
            refresh_revocations(url)
        except Exception:                       # noqa: BLE001 — фон, молчим
            pass

    threading.Thread(target=worker, daemon=True, name="license-revocations").start()
    return True


# --- часы и состояние -------------------------------------------------------

def load_state() -> dict:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(license_obj: License, *, now: _dt.datetime | None = None) -> None:
    """Запомнить успешный запуск: время и ключ, которым он был достигнут."""
    moment = now or _dt.datetime.now(_dt.timezone.utc)
    state_path().write_text(
        json.dumps(
            {
                "last_seen": moment.replace(microsecond=0).isoformat(),
                "key_id": license_obj.key_id,
                "expires": license_obj.expires.isoformat(),
            },
            ensure_ascii=False, sort_keys=True,
        ),
        encoding="utf-8",
    )


def clock_ok(
    state: dict | None = None,
    *,
    now: _dt.datetime | None = None,
) -> bool:
    """Не откатил ли пользователь часы назад (с допуском на NTP и дрейф)."""
    data = state if state is not None else load_state()
    raw = data.get("last_seen")
    if not raw:
        return True
    try:
        seen = _dt.datetime.fromisoformat(str(raw))
    except ValueError:
        return True                      # непонятное значение не блокируем
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=_dt.timezone.utc)
    moment = now or _dt.datetime.now(_dt.timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=_dt.timezone.utc)
    return moment >= seen - CLOCK_TOLERANCE


# --- одна проверка «всё разом» ----------------------------------------------

def check(
    *,
    hwid_value: str | None = None,
    today: _dt.date | None = None,
    public_pem: str | None = None,
) -> License:
    """Полный маршрут при старте: файл → подпись → ПК → срок → отзыв → часы.

    Возвращает валидный :class:`License` или бросает :class:`LicenseError`
    с внятным текстом для окна активации.
    """
    text = read_license_text()
    if not text:
        raise LicenseError(
            "missing",
            "Ключ активации не найден — вставьте ключ, полученный у администратора",
        )
    if hwid_value is None:
        from app import hwid as hwid_mod

        try:
            hwid_value = hwid_mod.current()
        except hwid_mod.HwidError as exc:
            raise LicenseError("no_hwid", str(exc)) from exc
    license_obj = verify(text, hwid=hwid_value, today=today, public_pem=public_pem)

    if license_obj.key_id in load_cached_revocations():
        raise LicenseError(
            "revoked",
            f"Ключ {license_obj.key_id} отозван администратором проекта",
        )
    if not clock_ok():
        raise LicenseError(
            "clock",
            "Системное время раньше, чем при прошлом запуске программы. "
            "Верните корректную дату — иначе срок ключа невозможно проверить",
        )
    return license_obj


def enforcement_required() -> bool:
    """Нужно ли блокировать запуск без валидного ключа.

    В собранном ``exe`` — всегда (это и есть смысл раздачи по ключам).
    В исходниках — только если ключ уже активирован: разработка и тесты
    должны работать без ключа, а исходники всё равно не раздаются.
    """
    if getattr(sys, "frozen", False):
        return True
    return license_path().exists()
