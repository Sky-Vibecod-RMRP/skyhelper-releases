"""Имена файлов и папок скриншотов: санация и защита от перезаписи.

Две разные санации, потому что задачи разные:

* :func:`sanitize` — имя **папки категории**. Здесь важно выбросить только то,
  что Windows не принимает (``/``, ``:`` и прочее), а пробелы и скобки
  оставить: «Захват/налёт (День)» превращается в «Захват-налёт (День)».
* :func:`file_tag` — кусок **имени файла**. Тут всё лишнее → «-», поэтому
  «Наказания (День)» даёт «Наказания-День» в файле
  ``2026-09-30_16-42-15_Наказания-День.jpg``.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

#: Символы, запрещённые Windows в именах файлов и папок.
WINDOWS_BAD = set('<>:"/\\|?*')

#: Имена, зарезервированные Windows: папку «CON» или «COM1» не создать.
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{kind}{number}" for kind in ("COM", "LPT") for number in range(1, 10)
}

_MAX_LEN = 100
_ONLY_SAFE = re.compile(r"[^0-9A-Za-zА-Яа-яЁё._-]+")
_SPACES = re.compile(r"\s{2,}")


def sanitize(text: str) -> str:
    """Имя папки: запрещённые символы → «-», пробелы и скобки сохраняем.

    Отдельно подстраховываемся от зарезервированных имён Windows (CON,
    COM1, LPT9 и т. п.): с ними ``mkdir`` падает, категория молча уезжала
    бы в запасную папку с невнятным «нет прав», хотя прав тут как раз есть.
    """
    out = []
    for char in text.strip():
        if char in WINDOWS_BAD or ord(char) < 32:
            out.append("-")
        else:
            out.append(char)
    name = _SPACES.sub(" ", "".join(out)).strip(" .")[:_MAX_LEN]
    if name.split(".")[0].upper() in RESERVED_NAMES:
        name = f"_{name}"
    return name


def file_tag(text: str) -> str:
    """Кусок имени файла: только буквы/цифры/точка/дефис, прочее → «-»."""
    raw = _ONLY_SAFE.sub("-", text)
    tag = re.sub(r"-{2,}", "-", raw).strip("-._")
    return tag[:_MAX_LEN] or "категория"


def file_name(stamp: datetime, category: str) -> str:
    """«2026-09-30_16-42-15_Наказания-День.jpg» — сортируется по времени."""
    return "{}_{}.jpg".format(
        stamp.strftime("%Y-%m-%d_%H-%M-%S"), file_tag(category)
    )


def unique_path(folder: Path, name: str) -> Path:
    """Путь, которого ещё нет: коллизия → ``_1``, ``_2`` … (перезаписи нет)."""
    path = folder / name
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    for n in range(1, 1000):
        candidate = folder / "{}_{}{}".format(stem, n, suffix)
        if not candidate.exists():
            return candidate
    # За тысячу коллизий в одну секунду прячемся за меткой времени.
    stamp = int(datetime.now().timestamp())
    return folder / "{}_{}{}".format(stem, stamp, suffix)
