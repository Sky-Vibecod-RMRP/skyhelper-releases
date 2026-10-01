"""Глобальные клавиши категорий скриншотов.

По образцу ``app.hotkeys.listener``: одна категория — один хоткей,
``suppress=False`` (клавиша не съедается, игра её тоже видит), дебаунс
0,3 с, чтобы зажатая клавиша не выдала серию снимков. Список категорий
меняется в настройках — значит, слушатель должен уметь перепривязываться
на лету через :meth:`CategoryListener.reload`.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Iterable

from app.shots.names import sanitize

log = logging.getLogger(__name__)

DEBOUNCE_SEC = 0.3


def normalize(hotkey: str) -> str:
    """«  Shift+F6  » → «shift+f6»; пустое → «»."""
    return (hotkey or "").strip().lower()


def category_problems(
    config, categories: list | None = None, reserved: list | None = None
) -> list[str]:
    """Почему список категорий негоден: пустые имена, конфликты, дубли.

    Возвращает список человекочитаемых ошибок — их показывает вкладка
    «Скриншоты» прямо при сохранении, до того как слушатель перепривяжется.
    ``reserved`` подставляют сами настройки (они правят F9/F10 и т. п.
    прямо в этом же окне), иначе берутся значения из ``config``.
    """
    cats = config.shots_categories if categories is None else categories
    if reserved is None:
        reserved = [
            config.hotkey_add,
            config.hotkey_remove,
            config.hotkey_duty,
            config.hotkey_toggle,
        ]
    reserved_keys = {normalize(r) for r in reserved if r}
    # Подсказка «на что уже стоит клавиша» — по позиции в списке резерва:
    # 0 = +1, 1 = −1, 2 = дежурство, 3 = показ окна.
    labels = (
        "это +1 обращение",
        "это −1 обращение",
        "это дежурство",
        "это показ/скрытие окна",
    )
    hints = {
        normalize(reserved[i]): labels[i]
        for i in range(min(len(reserved), len(labels)))
        if reserved[i]
    }
    problems: list[str] = []
    seen: dict[str, str] = {}
    seen_folders: dict[str, str] = {}
    for index, cat in enumerate(cats, start=1):
        name = str((cat or {}).get("name", "")).strip()
        key = normalize(str((cat or {}).get("hotkey", "")))
        if not name:
            problems.append(f"Категория №{index}: не задано название")
            continue
        # Две категории после санации могут дать одну папку («Захват/налёт
        # (День)» и «Захват-налёт (День)») — тогда снимки смешаются, а в
        # дереве отчёта видна будет только одна. Проверяем до ключей.
        folder = sanitize(name)
        if not folder:
            problems.append(f"«{name}»: из этого названия не получится папка")
            continue
        if folder in seen_folders:
            problems.append(
                f"«{name}»: на диске это папка «{folder}», "
                f"как у «{seen_folders[folder]}»"
            )
            continue
        seen_folders[folder] = name
        if not key:
            problems.append(f"«{name}»: не назначена клавиша")
            continue
        if key in reserved_keys:
            what = hints.get(key, "это горячая клавиша программы")
            problems.append(f"«{name}»: клавиша {key} занята программой — {what}")
            continue
        if key in seen:
            problems.append(
                f"«{name}»: клавиша {key} уже используется в «{seen[key]}»"
            )
            continue
        seen[key] = name
    return problems


def is_reserved(hotkey: str, reserved: Iterable[str]) -> bool:
    """Клавиша занята программой (F9 / Ctrl+F9 / F10 / Insert)."""
    key = normalize(hotkey)
    return bool(key) and key in {normalize(r) for r in reserved if r}


class CategoryListener:
    """Держит привязку «категория → клавиша» и зовёт ``on_shot(name)``."""

    def __init__(
        self,
        on_shot: Callable[[str], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._on_shot = on_shot
        self._clock = clock
        self._handles: list = []
        self._keys: dict[str, float] = {}   # клавиша → время последного нажатия
        self._lock = threading.Lock()

    # --- публичное -------------------------------------------------------

    def reload(self, categories: list) -> list[str]:
        """Перепривязывает все клавиши. Возвращает список конфликтов.

        Битые/занятые клавиши не вешаются (иначе ``keyboard`` уронит
        слушатель целиком), а попадают в возвращаемый список — его GUI
        показывает плашкой. Проверка на конфликт с программой делается
        заранее, в :func:`category_problems`, при сохранении настроек.
        """
        self.stop()
        conflicts: list[str] = []
        for cat in categories or []:
            name = str((cat or {}).get("name", "")).strip()
            key = normalize(str((cat or {}).get("hotkey", "")))
            if not name or not key:
                continue
            try:
                handle = self._add(key, name)
            except Exception as exc:
                log.warning("Не удалось повесить %s на «%s»: %s", key, name, exc)
                conflicts.append(f"«{name}»: клавиша {key} не распознана ({exc})")
                continue
            if handle is not None:
                self._handles.append(handle)
        log.info("Привязано клавиш скриншотов: %d", len(self._handles))
        return conflicts

    def stop(self) -> None:
        """Снимает все привязки (нужно до перезапуска слушателя)."""
        if not self._handles:
            return
        try:
            import keyboard

            for handle in self._handles:
                try:
                    keyboard.remove_hotkey(handle)
                except Exception:  # pragma: no cover - уже снято
                    pass
        except Exception:
            log.exception("Не снялись клавиши скриншотов")
        self._handles.clear()
        with self._lock:
            self._keys.clear()

    # --- внутреннее ------------------------------------------------------

    def _add(self, key: str, name: str):
        import keyboard

        def _fire() -> None:
            # Таймстемп под замком: две нажатые подряд клавиши приходят из
            # разных потоков listener'а и не должны прочитать одно и то же.
            with self._lock:
                now = self._clock()
                last = self._keys.get(key)   # None = первое нажатие, его не режем
                if last is not None and now - last < DEBOUNCE_SEC:
                    return
                self._keys[key] = now
            try:
                self._on_shot(name)
            except Exception:
                log.exception("Скриншот по %s не удался", key)

        # suppress=False: игра тоже видит нажатие, мы его лишь подмечаем.
        return keyboard.add_hotkey(key, _fire, suppress=False)
