"""Папка недели: «Отчёты ¦ Администратор ¦ 28.09.2026–04.10.2026».

Неделя календарная, пн–вс (первый день берётся из ``week_start_weekday``).
Корень создаётся автоматически рядом с программой; если туда писать нельзя
(Program Files, нет прав), молча переключаемся в «Документы\\SKY HELPER» —
снимок важнее места.

Важно: символ «|» Windows **запрещает** в именах папок (в отличие от Google
Диска, где он запросто стоит). Поэтому в локальном имени — «¦» (U+00A6),
визуально почти неотличимый от «|». См. раздел «Ограничения Windows» в
инструкции.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from app.paths import default_output_dir, program_dir
from app.shots.names import sanitize

log = logging.getLogger(__name__)

#: Корень отчётов. «|» в Windows запрещён → стоит «¦» (U+00A6).
ROOT_TITLE = "Отчёты ¦ Администратор"
DASH = "\u2013"          # длинный дефис — как в Google Диске
TRASH_TITLE = "Корзина"   # сюда уезжают удалённые категории

#: Время в этом году пишем как 4 цифры, как на Google Диске.
_DATE_FMT = "%d.%m.%Y"


def week_bounds(today: date, start_weekday: int = 0) -> tuple[date, date]:
    """(понедельник, воскресенье) недели, в которую попадает ``today``."""
    shift = (today.weekday() - start_weekday) % 7
    start = today - timedelta(days=shift)
    return start, start + timedelta(days=6)


def week_title(start: date, end: date) -> str:
    """Полное имя папки недели."""
    return "{} ¦ {}{}{}".format(
        ROOT_TITLE, start.strftime(_DATE_FMT), DASH, end.strftime(_DATE_FMT)
    )


def _writable(path: Path) -> bool:
    """Можно ли туда писать (пробуем реально, а не по os.access).

    Имя пробного файла уникально на каждый вызов: корень проверяют сразу
    несколько потоков (сайт, служба недели, сохранение настроек), и общий
    файл приводил к гонке — один поток удалял пробник другого, проверка
    падала и корень ложно считался недоступным.
    """
    probe = path / f".rmrp_shots_write_test_{os.getpid()}_{threading.get_ident()}"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        # Остаток пробника не должен мешать следующему вызову — но и сам
        # сбой в чистке не должен вылететь наружу: это просто проверка.
        try:
            probe.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def resolve_root(config) -> Path:
    """Корень отчётов: настройка → папка с программой → Документы."""
    configured = (getattr(config, "shots_root", "") or "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if _writable(candidate):
            return candidate
        log.warning("Папка скриншотов «%s» недоступна, берём запасную", candidate)
    for candidate in (program_dir(), default_output_dir()):
        if _writable(candidate):
            return candidate
    log.error("Ни одна папка недоступна, используем Документы")
    return default_output_dir()


def week_folder(config, now: datetime | None = None) -> Path:
    """Путь папки текущей недели (папка может ещё не существовать)."""
    now = now or datetime.now()
    start, end = week_bounds(now.date(), config.week_start_weekday)
    return resolve_root(config) / week_title(start, end)


def ensure_week(config, categories, now: datetime | None = None) -> Path:
    """Создать папку недели, все 8 подпапок категорий и «Корзину».

    Возвращает путь папки. Ошибка прав/диска кидает OSError — её ловит
    сервис и переключается на запасную папку.
    """
    folder = week_folder(config, now)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / TRASH_TITLE).mkdir(exist_ok=True)
    for cat in categories or []:
        name = sanitize((cat or {}).get("name", ""))
        if name:
            (folder / name).mkdir(exist_ok=True)
    return folder


def category_folder(config, category_name: str, now: datetime | None = None) -> Path:
    """Папка категории внутри текущей недели."""
    folder = week_folder(config, now) / sanitize(category_name)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def fallback_folder(config, category_name: str, now: datetime | None = None) -> Path:
    """Запасная папка: ``Документы\\SKY HELPER\\<неделя>\\<категория>``.

    Срабатывает, когда основной корень недоступен (нет прав, забит диск).
    """
    now = now or datetime.now()
    start, end = week_bounds(now.date(), config.week_start_weekday)
    folder = (
        default_output_dir() / week_title(start, end) / sanitize(category_name)
    )
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def list_weeks(config) -> list[str]:
    """Имена папок недель, новые первыми. Без недель на диске — пусто."""
    root = resolve_root(config)
    if not root.is_dir():
        return []
    names = [
        p.name
        for p in root.iterdir()
        if p.is_dir() and p.name.startswith(ROOT_TITLE)
    ]
    return sorted(names, reverse=True)
