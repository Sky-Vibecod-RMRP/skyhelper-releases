"""Корзина для удалённых категорий.

По требованию удаление идёт в **два** места сразу:

1. копия уезжает в ``<корень недели>/Корзина/<категория> <время>`` — это
   переживает очистку системной корзины;
2. оригинал удаляется **в корзину Windows** (``SHFileOperationW`` с
   ``FOF_ALLOWUNDO``), чтобы пользователь мог восстановить его там.

Если системная корзина по какой-то причине недоступна — просто удаляем:
страховочная копия уже сделана, данные не теряются.
"""
from __future__ import annotations

import ctypes
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

_FO_DELETE = 3
_FOF_ALLOWUNDO = 0x0040
_FOF_NOCONFIRMATION = 0x0010
_FOF_SILENT = 0x0004


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", ctypes.c_int),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    ]


def to_recycle_bin(path: Path) -> bool:
    """Отправляет папку/файл в корзину Windows. False — не вышло."""
    if os.name != "nt":  # pragma: no cover - проект под Windows
        return False
    try:
        op = _SHFILEOPSTRUCTW()
        op.wFunc = _FO_DELETE
        # pFrom обязан заканчиваться двумя \0: ctypes добавит одну сам.
        op.pFrom = str(path) + "\0"
        op.fFlags = _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return result == 0
    except Exception:
        log.exception("Не удалось отправить в корзину Windows: %s", path)
        return False


def unique_backup(trash_dir: Path, name: str) -> Path:
    """Путь для копии без перезаписи: «имя 16-42-15», затем «имя 1» …."""
    stamp = datetime.now().strftime("%H-%M-%S")
    candidate = trash_dir / f"{name} {stamp}"
    if not candidate.exists():
        return candidate
    for n in range(1, 1000):
        candidate = trash_dir / f"{name} {n}"
        if not candidate.exists():
            return candidate
    return trash_dir / f"{name} {int(datetime.now().timestamp())}"


def remove_category(folder: Path, trash_dir: Path) -> Path | None:
    """Копия в «Корзину» + удаление в корзину Windows. Возвращает копию."""
    if not folder.is_dir():
        return None
    trash_dir.mkdir(parents=True, exist_ok=True)
    backup = unique_backup(trash_dir, folder.name)
    shutil.copytree(folder, backup)
    log.info("Категория скопирована в Корзину: %s", backup.name)

    if not to_recycle_bin(folder):
        # Копия уже есть — данные не потеряются, удаляем напрямую.
        shutil.rmtree(folder, ignore_errors=True)
    elif folder.exists():  # pragma: no cover - редкий сбой корзины
        shutil.rmtree(folder, ignore_errors=True)
    return backup
