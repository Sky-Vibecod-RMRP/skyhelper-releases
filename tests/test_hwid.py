# -*- coding: utf-8 -*-
"""Отпечаток ПК: формат кода, нормализация, сравнение."""
import pytest

from app import hwid


def test_encode_format():
    code = hwid.encode("GUID-ONE", "SERIAL2")
    assert code.startswith("RM-")
    parts = code.split("-")
    assert len(parts) == 5 and parts[0] == "RM"
    assert all(len(chunk) == 4 for chunk in parts[1:])
    assert all(ch.isalnum() for ch in "".join(parts[1:]))


def test_encode_stable_and_order_sensitive():
    a = hwid.encode("x", "y")
    assert a == hwid.encode("x", "y")
    assert a != hwid.encode("y", "x")


def test_encode_skips_empty_parts():
    assert hwid.encode("x", "", "  ") == hwid.encode("x")


def test_encode_without_sources_raises():
    with pytest.raises(hwid.HwidError):
        hwid.encode("", "   ")


def test_normalize_strips_junk_from_chats():
    # чаты ломают код: регистр, пробелы, неразрывные пробелы, переносы
    raw = " rm -7f3a 9k2d\n4m1p-8zr7 "
    assert hwid.normalize(raw) == "RM7F3A9K2D4M1P8ZR7"


def test_matches_ignores_formatting():
    assert hwid.matches("RM-7F3A-9K2D-4M1P-8ZR7", "rm7f3a 9k2d4m1p8zr7")
    assert not hwid.matches("RM-7F3A-9K2D-4M1P-8ZR7", "RM-7F3A-9K2D-4M1P-8ZR8")
    assert not hwid.matches("", "")


def test_canonical_roundtrip():
    code = hwid.encode("g", "s")
    assert hwid.canonical(code) == code
    # то же самое, но мусорное написание из чата
    assert hwid.canonical(code.lower().replace("-", " ")) == code
    # без префикса RM
    assert hwid.canonical(code.replace("RM-", "")) == code
    assert hwid.canonical("") == ""


def test_current_gives_a_code_on_this_machine():
    # на реальной машине источники есть (Windows); иначе — аккуратный отказ
    try:
        code = hwid.current()
    except hwid.HwidError:
        pytest.skip("нет источников отпечатка (не Windows)")
    assert code.startswith("RM-")
    assert hwid.matches(code, code.swapcase().replace("-", " "))
