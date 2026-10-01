"""Захват экрана: монитор окна игры, прятание своих окон, чёрный кадр.

Ключевой момент — «весь экран того монитора, где запущена игра». Поэтому мы
не пишем скриншот окна, а находим окно игры через ``EnumWindows``, берём его
``rcMonitor`` и снимаем именно этот прямоугольник (в координатах виртуального
экрана, где мониторы могут иметь отрицательные координаты — Pillow их умеет).
"""
from __future__ import annotations

import ctypes
import logging
import os
from dataclasses import dataclass
from typing import Callable, Iterable

log = logging.getLogger(__name__)

#: Ярче этого (0..255) кадр чёрным не считаем.
BLACK_LEVEL = 12

_MONITOR_DEFAULTTONEAREST = 0x00000002


@dataclass
class GameWindow:
    """Окно игры: прямоугольник в координатах виртуального экрана."""

    rect: tuple[int, int, int, int]
    monitor: tuple[int, int, int, int]
    minimized: bool
    title: str = ""


def _game_pids(process_names: Iterable[str]) -> set[int]:
    try:
        import psutil  # импорт здесь, чтобы тесты не требовали psutil
    except Exception:  # pragma: no cover - psutil в requirements
        log.exception("psutil недоступен")
        return set()
    wanted = {name.lower() for name in process_names}
    pids: set[int] = set()
    for proc in psutil.process_iter(["pid", "name"]):
        name = proc.info.get("name")
        if name and name.lower() in wanted:
            pids.add(int(proc.info["pid"]))
    return pids


def _monitor_of(user32, hwnd) -> tuple[int, int, int, int] | None:
    """rcMonitor монитора, где лежит окно (ближайший к окну)."""

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint32),
            ("rcMonitor", ctypes.wintypes.RECT),
            ("rcWork", ctypes.wintypes.RECT),
            ("dwFlags", ctypes.c_uint32),
        ]

    hmon = user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
    if not hmon:
        return None
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        return None
    r = info.rcMonitor
    return (r.left, r.top, r.right, r.bottom)


def _windows_window(process_names: Iterable[str]) -> GameWindow | None:
    """Первое видимое окно процесса игры. ``None`` — игра свёрнута в трей."""
    user32 = ctypes.windll.user32
    pids = _game_pids(process_names)
    if not pids:
        return None
    my_pid = os.getpid()
    found: list[GameWindow] = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
    )
    buf = ctypes.create_unicode_buffer(512)

    def _visit(hwnd, _lparam):  # noqa: ANN001 - типы из ctypes
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value or pid.value == my_pid or pid.value not in pids:
            return True
        user32.GetWindowTextW(hwnd, buf, 512)
        title = buf.value.strip()
        if not title:
            return True
        rect = ctypes.wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        monitor = _monitor_of(user32, hwnd) or (0, 0, 1, 1)
        found.append(
            GameWindow(
                rect=(rect.left, rect.top, rect.right, rect.bottom),
                monitor=monitor,
                minimized=bool(user32.IsIconic(hwnd)),
                title=title,
            )
        )
        return False  # первое видимое окно игры достаточно

    try:
        user32.EnumWindows(WNDENUMPROC(_visit), 0)
    except Exception:  # pragma: no cover - зависит от платформы
        log.exception("EnumWindows не сработал")
        return None
    return found[0] if found else None


def find_window(
    process_names: Iterable[str],
    finder: Callable[[Iterable[str]], GameWindow | None] | None = None,
) -> GameWindow | None:
    """Окно игры. Нестандартный ``finder`` подставляют тесты."""
    if finder is not None:
        try:
            return finder(process_names)
        except Exception:
            log.exception("Ошибка поиск окна игры")
            return None
    if os.name != "nt":  # pragma: no cover - проект под Windows
        return None
    try:
        return _windows_window(list(process_names))
    except Exception:
        log.exception("Не удалось найти окно игры")
        return None


def grab(monitor: tuple[int, int, int, int] | None = None) -> "object":
    """Снять нужный монитор целиком. Возвращает PIL-изображение."""
    from PIL import ImageGrab

    if monitor is None:
        return ImageGrab.grab(all_screens=True)
    # bbox в координатах виртуального экрана, all_screens=True даёт смещение
    # (offset) — Pillow сам вычтет его, поэтому мониторы с минусом работают.
    return ImageGrab.grab(bbox=monitor, all_screens=True)


def is_black(image) -> bool:
    """True, если кадр почти полностью чёрный (например, exclusive fullscreen)."""
    if image is None:
        return True
    try:
        extrema = image.convert("L").getextrema()
    except Exception:
        log.exception("Не удалось проверить кадр на черноту")
        return True
    # У одного канала getextrema возвращает кортеж (min, max).
    highest = extrema[1] if isinstance(extrema, tuple) else extrema[0][1]
    return highest < BLACK_LEVEL
