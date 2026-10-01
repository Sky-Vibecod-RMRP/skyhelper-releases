# -*- coding: utf-8 -*-
"""Отпечаток компьютера (HWID) — привязка лицензии к конкретному ПК.

Схема выдачи ключей такая: админ запускает exe, копирует показанный код
ПК и присылает его администратору проекта; ключ генерируется под этот
код и работает только на этой машине (баг-репорт по защите: ключ должен
привязываться к ПК и уметь отключаться).

Источники — два устойчивых, оба читаются штатными средствами Windows:

* ``MachineGuid`` — идентификатор установки Windows в реестре
  (``HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid``): переживает
  перезагрузки и обновления, меняется при переустановке системы;
* серийник системного тома (``GetVolumeInformationW``): переживает почти
  всё, меняется при переформатировании.

Сознательно НЕ берём MAC-адрес и имя компьютера: первые плавают после
обновлений и при смене сети, второе меняется по щелчку — и то и другое
давало бы ложные отказы «ключ не для этого ПК».

Код выглядит как ``RM-7F3A-9K2D-4M1P-8ZR7``: base32 от sha256 от обоих
значений. Регистр и прочерки не важны — сравниваются «голые» символы,
поэтому ключ переживает копирование из чата с пробелами и переносами.
"""
from __future__ import annotations

import base64
import hashlib
import sys

#: Префикс кода ПК — чтобы на глаз отличать его от прочих кодов активации.
PREFIX = "RM"

#: Число символов хэша в коде (4 группы по 4).
CODE_LENGTH = 16


class HwidError(RuntimeError):
    """Не удалось собрать отпечаток: нет источников (не Windows/нет доступа)."""


def _read_machine_guid() -> str | None:
    """MachineGuid из реестра; недоступно → None (источник просто выпадает)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg  # noqa: PLC0415 (только Windows, импорт по требованию)

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "MachineGuid")
    except OSError:
        return None
    return str(value).strip() or None


def _read_volume_serial(root: str = "C:\\") -> str | None:
    """Серийник тома; недоступно → None (источник просто выпадает)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes  # noqa: PLC0415 (только Windows, импорт по требованию)

        buffer = ctypes.create_unicode_buffer(261)
        serial = ctypes.c_uint32()
        ok = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
            ctypes.c_wchar_p(root), buffer, len(buffer),
            ctypes.byref(serial), None, None, None, 0,
        )
    except (OSError, AttributeError):
        return None
    return f"{serial.value:08X}" if ok else None


def encode(*parts: str) -> str:
    """Собрать код ПК из сырых значений источников.

    Чистая функция (без чтения реестра) — на ней и построены тесты.
    Пустые части пропускаются, чтобы выпавший источник не ломал код.
    """
    joined = "|".join(part.strip() for part in parts if part and part.strip())
    if not joined:
        raise HwidError("нет ни одного источника для отпечатка ПК")
    digest = hashlib.sha256(joined.encode("utf-8")).digest()
    code = base64.b32encode(digest).decode("ascii").rstrip("=")[:CODE_LENGTH]
    return f"{PREFIX}-" + "-".join(
        code[i:i + 4] for i in range(0, CODE_LENGTH, 4)
    )


def current() -> str:
    """Код ПК этой машины (оба источника; чего-то нет — берём что есть)."""
    sources = [value for value in (_read_machine_guid(), _read_volume_serial())
               if value]
    if not sources:
        raise HwidError(
            "не удалось прочитать MachineGuid и серийник тома — "
            "отпечаток ПК недоступен (не Windows или нет прав)"
        )
    return encode(*sources)


def normalize(value: str) -> str:
    """Привести скопированный код к виду для сравнения.

    Убираем всё, кроме букв и цифр, и поднимаем регистр: чаты и почта
    спокойно ломают код пробелами, неразрывными пробелами и переносами.
    """
    return "".join(ch for ch in value.upper() if ch.isalnum())


def matches(expected: str, actual: str) -> bool:
    """Совпадают ли два кода ПК (без учёта регистра, пробелов и прочерков)."""
    return bool(expected) and normalize(expected) == normalize(actual)


def canonical(value: str) -> str:
    """Привести код к стандартному виду ``RM-XXXX-XXXX-XXXX-XXXX``.

    Нужно администратору при выдаче ключа: чаты приносят код с лишними
    пробелами, без прочерков, в нижнем регистре — payload ключа лучше
    записать в аккуратном виде, а сравнивать всё равно «голые» символы.
    """
    bare = normalize(value)
    body = bare[2:] if bare.startswith(PREFIX) else bare
    if not body:
        return ""
    return f"{PREFIX}-" + "-".join(
        body[i:i + 4] for i in range(0, len(body), 4)
    )
