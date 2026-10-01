"""Короткие сигналы уведомлений без файлов ресурсов.

Три темы: «off» — тишина, «system» — системные звуки Windows,
«soft» — мягкие тоны через winsound.Beep. Всё играется в фоновом
потоке, интерфейс не подвисает; на не-Windows просто ничего не играет.
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

try:
    import winsound
except ImportError:  # не Windows — сигналы выключены
    winsound = None  # type: ignore[assignment]

THEMES = {
    "off": "Без звуков",
    "system": "Системные",
    "soft": "Мягкие тоны",
}
DEFAULT_THEME = "system"

# Системные алиасы Windows (файлы не нужны).
_SYSTEM = {
    "duty_on": "SystemAsterisk",
    "duty_off": "SystemExclamation",
    "report_add": "SystemAsterisk",
    "report_undo": "SystemHand",
    "success": "SystemAsterisk",
    "error": "SystemHand",
}

# Мелодии (частота Гц, длительность мс) для темы «soft».
_SOFT = {
    "duty_on": [(740, 90), (988, 120)],
    "duty_off": [(587, 90), (440, 150)],
    "report_add": [(880, 70)],
    "report_undo": [(520, 70), (400, 90)],
    "success": [(660, 80), (880, 80), (1175, 140)],
    "error": [(300, 160), (220, 200)],
}

_lock = threading.Lock()


def play(theme: str, event: str) -> None:
    """Проиграть событие в указанной теме. Никогда не бросает исключений."""
    if theme == "off" or winsound is None or event not in _SYSTEM:
        return
    try:
        if theme == "system":
            winsound.PlaySound(_SYSTEM[event],
                               winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return
        notes = _SOFT.get(event)
        if not notes:
            return
        threading.Thread(target=_beep_sequence, args=(notes,), daemon=True).start()
    except Exception:  # звук не должен ломать работу программы
        log.debug("Не удалось проиграть сигнал %s (тема %s)", event, theme, exc_info=True)


# --- Звук скриншота (отдельной галочкой, темой sound_theme не управляется) ---

_SHOT_MELODIES = {
    # Удачный снимок: короткий каскад вверх — звучит как «есть!».
    "saved": [(880, 70), (1175, 80), (1568, 150)],
    # Блокировка/ошибка: два спадающих тона, чуть тише и мягче.
    "blocked": [(587, 110), (440, 170)],
    "black": [(587, 110), (440, 170)],
    "write_fail": [(494, 120), (370, 190)],
}
_SHOT_FALLBACK = "saved"
_melody_cache: dict[str, bytes] = {}
_melody_lock = threading.Lock()


def _melody(name: str) -> bytes:
    """Собирает WAV нужной мелодии в памяти (файлы ресурсов не нужны)."""
    with _melody_lock:
        cached = _melody_cache.get(name)
        if cached is not None:
            return cached
        data = _build_wav(_SHOT_MELODIES.get(name) or _SHOT_MELODIES[_SHOT_FALLBACK])
        _melody_cache[name] = data
        return data


def _build_wav(notes: list[tuple[int, int]]) -> bytes:
    """16-битный моно WAV: синус с мягкой атакой и затуханием (без щелчков)."""
    import io
    import math
    import struct
    import wave

    rate = 44100
    gap = int(rate * 0.035)   # микро-пауза между нотами
    frames = bytearray()
    for frequency, duration_ms in notes:
        count = int(rate * max(1, duration_ms) / 1000)
        attack = max(1, int(count * 0.12))
        for i in range(count):
            t = i / rate
            envelope = min(1.0, i / attack) * math.exp(-3.5 * i / count)
            value = math.sin(2.0 * math.pi * frequency * t) * envelope * 0.34
            frames += struct.pack("<h", int(max(-1.0, min(1.0, value)) * 32767))
        frames += b"\x00\x00" * gap
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(bytes(frames))
    return buffer.getvalue()


def play_shot(kind: str = "saved") -> None:
    """Мелодия скриншота. Вызывается по ``config.shots_sound`` напрямую —
    тема ``sound_theme`` здесь ни при чём (так в ТЗ). Никогда не бросает
    исключений и не подвисает: играется в фоновом потоке.
    """
    if winsound is None:
        return
    try:
        data = _melody(kind)
    except Exception:  # pragma: no cover - генерация не должна ронять снимок
        log.debug("Не собралась мелодия скриншота", exc_info=True)
        return
    # Поток держит буфер локальной ссылкой ровно всё воспроизведение —
    # иначе SND_MEMORY мог бы отдать память, которую ещё читает звуковая
    # система. Синхронное PlaySound здесь и решает это.
    threading.Thread(target=_play_blocking, args=(data,), daemon=True).start()


def _play_blocking(data: bytes) -> None:
    with _lock:
        try:
            winsound.PlaySound(
                data, winsound.SND_MEMORY | winsound.SND_NODEFAULT
            )
        except Exception:  # pragma: no cover
            log.debug("Мелодия скриншота не проигралась", exc_info=True)


def _beep_sequence(notes: list[tuple[int, int]]) -> None:
    with _lock:  # тоны не должны накладываться друг на друга
        for frequency, duration in notes:
            try:
                winsound.Beep(frequency, duration)
            except Exception:
                return
