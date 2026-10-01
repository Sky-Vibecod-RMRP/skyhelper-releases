"""Хеширование кода доступа: PBKDF2-HMAC-SHA256, только стандартная библиотека.

Формат строки: ``pbkdf2_sha256$<итерации>$<соль_hex>$<хэш_hex>``.
Соль генерируется на каждый вызов, поэтому один и тот же код даёт разные хэши.
Пустой ``pin_hash`` вызывающая сторона трактует как «код не задан» (без
авторизации); здесь на пустой строке verify_pin просто возвращает False.
"""
from __future__ import annotations

import hashlib
import hmac
import os

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 120_000
SALT_BYTES = 16

# Защита от мусорного pin_hash с гигантским числом итераций (иначе можно
# подвесить сервер бессмысленным пересчётом).
MAX_ITERATIONS = 10_000_000


def hash_pin(pin: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    """Возвращает хэш кода доступа в формате pbkdf2_sha256$итерации$соль$хэш."""
    if iterations < 1:
        raise ValueError("Число итераций должно быть положительным")
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return f"{ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_pin(pin: str, pin_hash: str) -> bool:
    """Проверяет код по хэшу; пустой или мусорный хэш — всегда False.

    Сравнение через hmac.compare_digest, чтобы не выдавать длину хэша по времени.
    """
    if not pin_hash:
        return False
    parts = pin_hash.split("$")
    if len(parts) != 4:
        return False
    algorithm, iterations_text, salt_hex, expected_hex = parts
    if algorithm != ALGORITHM or not salt_hex or not expected_hex:
        return False
    try:
        iterations = int(iterations_text)
    except ValueError:
        return False
    if not 1 <= iterations <= MAX_ITERATIONS:
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(expected_hex)
    except ValueError:
        return False
    if not salt:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(digest, expected)
