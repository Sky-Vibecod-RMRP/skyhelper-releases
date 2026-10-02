"""Edge-детектор нажатий: гасит автоповтор зажатой клавиши.

``keyboard.add_hotkey`` вызывает колбэк на КАЖДОЕ событие KEY_DOWN, включая
автоповтор зажатой клавиши, — удержание F10 давало бы переключение дежурства
раз в дебаунс (0,3 с), а зажатая клавиша категории — серию снимков раз в
0,3 с. Тайм-дебаунс оставался единственной защитой и потому «дребезжал».

Хуки ``hook_key`` попадают в ``nonblocking_keys`` и выполняются в
``pre_process_event`` РАНЬШЕ колбэков ``add_hotkey`` (строки 212 и 217
``keyboard/__init__.py``), поэтому к моменту срабатывания хоткея гард уже
знает актуальное состояние клавиш. Всё происходит в одном processing-потоке
— гонок между press-хуком и ``allow()`` нет.

Если хуки повесить не удалось (фейковый ``keyboard`` в тестах, старая
библиотека, неразложимый хоткей) — гард для этого хоткея выключен и
``allow()`` всегда True: работает только тайм-дебаунс, как раньше.

Внимание: ``suppress=True``-хоткеи (Insert) сюда не годятся — их колбэк
выполняется в хук-потоке ДО того, как press-хук обновит состояние, гонка
решений неизбежна. Для них остаётся только дебаунс.
"""
from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)


def keys_of(hotkey: str) -> tuple[str, ...] | None:
    """«Ctrl + F9» → ``("ctrl", "f9")``; None — разложить не удалось."""
    text = str(hotkey or "").strip().lower()
    if not text:
        return None
    parts = [part.strip() for part in text.split("+")]
    if not all(parts):
        return None
    return tuple(parts)


class EdgeGuard:
    """Разрешает срабатывание только по первому нажатию, а не по автоповтору."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._down: set[str] = set()      # клавиши, зажатые сейчас
        self._fresh: set[str] = set()     # «настоящие» нажатия, ещё не потреблённые
        #: хоткей → его клавиши (только те, что под наблюдением)
        self._guarded: dict[str, tuple[str, ...]] = {}
        #: клавиша → (callback, remove) — снимаем при unwatch
        self._key_handles: dict[str, tuple[object, object]] = {}
        self._active = False

    # --- регистрация -----------------------------------------------------

    def watch(self, hotkey: str) -> bool:
        """Повесить press/release-хук на клавиши хоткея. False — фолбэк."""
        norm = str(hotkey or "").strip().lower()
        keys = keys_of(norm)
        if not norm or not keys:
            return False
        try:
            import keyboard  # импорт здесь, чтобы тесты не требовали keyboard
        except Exception:
            return False
        hooked: list[str] = []
        with self._lock:
            if norm in self._guarded:
                return True
            try:
                for key in keys:
                    if key in self._key_handles:
                        continue  # клавиша уже подвешена другим хоткеем
                    handle = self._hook(keyboard, key)
                    self._key_handles[key] = handle
                    hooked.append(key)
                self._guarded[norm] = keys
                self._active = True
            except Exception as exc:
                # Откатываем: частичная работа (часть клавиш с edge, часть
                # без) хуже честного дебаунса.
                log.warning(
                    "Edge-хуки на «%s» не повесились: %s — работает дебаунс",
                    norm, exc,
                )
                for key in hooked:
                    _callback, remove = self._key_handles.pop(key, (None, None))
                    self._unhook(remove)
                return False
        return True

    def unwatch(self) -> None:
        """Снять все хуки (stop/reload). Поздние вызовы гаснут флагом."""
        with self._lock:
            self._active = False
            self._guarded.clear()
            self._down.clear()
            self._fresh.clear()
            handles = list(self._key_handles.values())
            self._key_handles.clear()
        for _callback, remove in handles:
            self._unhook(remove)

    def _hook(self, keyboard, key: str) -> tuple[object, object]:
        """Один хук на клавишу: и press, и release.

        Два ``hook_key`` на одну клавишу снимаются с громким Keyerror
        (``keyboard`` стирает общий словарь ``_hooks[key]`` дважды), поэтому
        события различаем сами по ``event.event_type``.
        """
        key_down = keyboard.KEY_DOWN

        def _on_event(event, _key=key):
            if not self._active:
                return True  # поздний вызов после unwatch — игнорируем
            if event.event_type == key_down:
                self._press(_key)
            else:
                self._release(_key)
            return True

        remove = keyboard.hook_key(key, _on_event, suppress=False)
        return _on_event, remove

    @staticmethod
    def _unhook(remove) -> None:
        if remove is None:
            return
        try:
            remove()
        except Exception:  # pragma: no cover - уже снято/коллизия _hooks
            pass

    # --- состояние -------------------------------------------------------

    def _press(self, key: str) -> None:
        with self._lock:
            if key in self._down:
                return  # автоповтор: свежесть не ставим
            self._down.add(key)
            self._fresh.add(key)

    def _release(self, key: str) -> None:
        with self._lock:
            self._down.discard(key)
            # Заброшенное нажатие (хоткей так и не сработал — набор был
            # неполный) не должно выстрелить позже «из-под земли».
            self._fresh.discard(key)

    # --- решение ---------------------------------------------------------

    def allow(self, hotkey: str) -> bool:
        """True — первое нажатие, его можно обработать; False — автоповтор."""
        norm = str(hotkey or "").strip().lower()
        with self._lock:
            keys = self._guarded.get(norm)
            if not self._active or keys is None:
                return True  # фолбэк: решает тайм-дебаунс
            fired = self._fresh.intersection(keys)
            if not fired:
                return False
            # Потребляем свежесть ВСЕХ клавиш комбинации, чтобы автоповтор
            # модификатора не выстрелил повторно по уже сработавшему хоткею.
            self._fresh.difference_update(fired)
            return True
