"""Сервис скриншотов: правдоподобный конвейер «клавиша → файл в неделе».

Порядок проверок — как в ТЗ:

1. на дежурстве (кроме режима «разрешить без дежурства»);
2. игра запущена;
3. окно игры найдено и не свёрнуто;
4. захват всего монитора игры (свои окна прячем только на мгновение
   снимка, затем возвращаем);
5. чёрный кадр → повтор через секунду, всё ещё чёрный → плашка;
6. запись в папку недели, при отказе диска/прав — запасная папка в
   «Документах».

Сервис не знает про Qt: результат отдаётся колбэком ``on_result`` из
потока слушателя, а GUI сам поднимает его в главный поток (см.
``Bridge.shot_result`` в ``gui_main``).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import quote

from app.shots import capture, weeks
from app.shots.listener import CategoryListener, normalize
from app.shots.names import file_name, sanitize, unique_path

log = logging.getLogger(__name__)

WEEK_CHECK_SEC = 600        # фоновая проверка новой недели: каждые 10 мин
BLACK_RETRY_SEC = 1.0       # повтор снимка чёрного кадра


# --- результат ------------------------------------------------------------

@dataclass
class ShotResult:
    """Что сказать пользователю после нажатия клавиши категории."""

    ok: bool
    kind: str                # saved | blocked | black | write_fail | week | ignored
    message: str
    category: str = ""
    path: str = ""
    fallback: bool = False    # файл уехал в запасную папку
    warning: str = ""        # «клавиша занята в игре», «нет места» и т. п.


class ShotsService:
    """Весь цикл скриншота. Внешних зависимостей, кроме Qt, нет."""

    def __init__(
        self,
        config,
        session,
        *,
        on_result: Callable[[ShotResult], None] | None = None,
        hide_windows: Callable[[], None] | None = None,
        show_windows: Callable[[], None] | None = None,
        window_finder: Callable = capture.find_window,
        grabber: Callable = capture.grab,
        clock: Callable[[], datetime] = datetime.now,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._session = session
        self.on_result = on_result
        # GUI подставляет сюда прятание/возврат своих окон: они должны
        # исчезнуть только на мгновение снимка и вернуться в любом случае.
        self.hide_windows = hide_windows
        self.show_windows = show_windows
        self._find_window = window_finder
        self._grab = grabber
        self._clock = clock
        self._sleep = sleeper
        self._listener = CategoryListener(self.shoot)
        self._week_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._busy = threading.Lock()
        self._week_folder: Path | None = None

    # --- жизненный цикл --------------------------------------------------

    def start(self) -> list[str]:
        """Вешает клавиши и поднимает проверку недели. Возвращает конфликты."""
        self._stop.clear()
        # На старте плашка нужна, только если неделя реально сменилась, пока
        # программу не было (иначе свежая установка поприветствует бы пустой
        # папкой) — это решает сам _ensure_week.
        self._ensure_week()
        conflicts = self._listener.reload(self._config.shots_categories)
        if self._week_thread is None or not self._week_thread.is_alive():
            self._week_thread = threading.Thread(
                target=self._week_loop, name="ShotsWeek", daemon=True
            )
            self._week_thread.start()
        return conflicts

    def stop(self) -> None:
        """Снимает клавиши и останавливает проверку недели."""
        self._stop.set()
        self._listener.stop()

    def reload(self) -> list[str]:
        """Перечитывает список категорий после сохранения настроек."""
        conflicts = self._listener.reload(self._config.shots_categories)
        self._ensure_week(silent=True)
        return conflicts

    # --- папка недели ----------------------------------------------------

    @property
    def week_folder(self) -> Path:
        """Текущая папка недели (создаётся при первом обращении)."""
        if self._week_folder is None:
            self._week_folder = weeks.week_folder(self._config, now=self._clock())
        return self._week_folder

    def open_week(self) -> Path | None:
        """Папку недели для пункта меню трея. None — создать не удалось."""
        try:
            return self._ensure_week(silent=True)
        except OSError:
            log.exception("Не удалось создать папку недели")
            return None

    # --- данные для сайта ------------------------------------------------

    def report_tree(self, week: str | None = None) -> dict:
        """Дерево «неделя → категории → файлы» для вкладки «Недельный отчёт»."""
        root = weeks.resolve_root(self._config)
        available = weeks.list_weeks(self._config)
        current = self.week_folder.name
        # Выбранная неделя должна существовать на диске, иначе пусто.
        if week not in available:
            week = current if current in available else (available[0] if available else current)

        by_folder = self._files_of(root, week)
        categories: list[dict] = []
        seen: set[str] = set()
        ordered = list(self._config.shots_categories or [])
        for cat in ordered:
            folder = sanitize(str(cat.get("name", "")))
            if folder and folder not in seen:
                seen.add(folder)
                categories.append(self._category_view(cat.get("name", folder), folder, by_folder))
        # Папки, оставшиеся от удалённых/переименованных категорий, тоже показываем.
        week_dir = root / week
        if week_dir.is_dir():
            for child in sorted(week_dir.iterdir(), key=lambda p: p.name):
                if child.is_dir() and child.name != weeks.TRASH_TITLE and child.name not in seen:
                    seen.add(child.name)
                    categories.append(self._category_view(child.name, child.name, by_folder))

        total = sum(len(c["files"]) for c in categories)
        return {
            "weeks": available,
            "selected": week,
            "current": current,
            "categories": categories,
            "total": total,
        }

    def _files_of(self, root: Path, week: str) -> dict[str, list[dict]]:
        """{папка категории: [файлы]}, файлы в хронологическом порядке."""
        result: dict[str, list[dict]] = {}
        week_dir = root / week
        if not week_dir.is_dir():
            return result
        for child in week_dir.iterdir():
            if not child.is_dir() or child.name == weeks.TRASH_TITLE:
                continue
            files = []
            for path in sorted(child.glob("*.jpg")):
                try:
                    stat = path.stat()
                except OSError:      # диск отвалился прямо под нами
                    continue
                files.append({
                    "name": path.name,
                    "size": int(stat.st_size),
                    "mtime": int(stat.st_mtime),
                    "url": "/shots/{}/{}/{}".format(
                        quote(week), quote(child.name), quote(path.name)
                    ),
                })
            result[child.name] = files
        return result

    @staticmethod
    def _category_view(name: str, folder: str, by_folder: dict) -> dict:
        return {
            "name": name.replace("/", "-"),     # как увидит человек
            "folder": folder,                   # как лежит на диске
            "files": by_folder.get(folder, []),
        }

    def resolve_file(self, week: str, category: str, name: str) -> Path | None:
        """Путь к картинке недели или None, если путь подозрительный.

        Сайт локальный, но картинки всё равно проверяем: никаких «..»,
        разделителей и лишних расширений — отдаём только .jpg изнутри корня.
        """
        for part in (week, category, name):
            if not part or part in (".", ".."):
                return None
            if "/" in part or "\\" in part:
                return None
            if any(ch in part for ch in '<>:"|?*') or any(ord(ch) < 32 for ch in part):
                return None
        if not name.lower().endswith((".jpg", ".jpeg")):
            return None
        if week not in weeks.list_weeks(self._config):
            return None
        try:
            root = weeks.resolve_root(self._config).resolve()
            path = (root / week / category / name).resolve()
        except (OSError, RuntimeError):
            return None
        if not path.is_relative_to(root):
            return None
        return path if path.is_file() else None

    def _ensure_week(self, silent: bool = False) -> Path:
        """Создаёт папку недели; плашку показываем только при переходе.

        Переход — это два случая: неделя сменилась во время работы (фоновая
        проверка) либо при запуске нашлись папки других недель, значит
        понедельник наступил, пока программу закрывали. Самый первый запуск
        на чистой папке молчит — это не переход.
        """
        now = self._clock()
        folder = weeks.week_folder(self._config, now=now)
        existed = folder.is_dir()
        made = weeks.ensure_week(self._config, self._config.shots_categories, now=now)
        previous = self._week_folder
        self._week_folder = made
        if silent or existed:
            return made
        others = [w for w in weeks.list_weeks(self._config) if w != made.name]
        if previous is None and not others:
            return made          # первая неделя — писать не о чём
        self._emit(
            ShotResult(
                ok=True,
                kind="week",
                message=f"Создана папка новой недели: {made.name}",
            )
        )
        return made

    def _week_loop(self) -> None:
        """Каждые 10 минут сверяем дату: наступил понедельник — новая папка."""
        while not self._stop.wait(WEEK_CHECK_SEC):
            try:
                self._ensure_week()
            except OSError:
                log.exception("Не удалось создать папку недели")

    # --- снимок ----------------------------------------------------------

    def shoot(self, category: str) -> ShotResult:
        """Точка входа по клавише категории. Всегда возвращает результат."""
        if not self._busy.acquire(blocking=False):
            # Дебаунс уже держит серию, тут просто страховка от гонки.
            # Молчать нельзя: человек нажал клавишу и должен понять почему.
            return self._emit(
                ShotResult(
                    ok=False,
                    kind="ignored",
                    message="Предыдущий скриншот ещё снимается",
                    category=category,
                )
            )
        try:
            return self._shoot(category)
        finally:
            self._busy.release()

    def _shoot(self, category: str) -> ShotResult:
        cfg = self._config

        # 1. дежурство (переключатель «разрешить без дежурства» снимает)
        if not getattr(cfg, "shots_allow_no_duty", False):
            if not getattr(self._session, "is_on_duty", False):
                return self._blocked(category, "Скриншот не сделан: не на дежурстве")

        # 2. игра запущена
        if not getattr(self._session, "is_game_running", False):
            return self._blocked(category, "Скриншот не сделан: игра не запущена")

        # 3. окно развёрнуто (не свёрнуто и вообще найдено)
        window = self._find_window(cfg.game_processes)
        if window is None:
            return self._blocked(category, "Скриншот не сделан: окно игры не найдено")
        if window.minimized:
            return self._blocked(category, "Скриншот не сделан: игра свёрнута")

        # 4–5. захват монитора, свои окна прячем только на мгновение
        image = self._capture(window.monitor)
        if image is None:
            return self._blocked(category, "Скриншот не сделан: сбой захвата экрана")
        if capture.is_black(image):
            self._sleep(BLACK_RETRY_SEC)
            image = self._capture(window.monitor)
            if image is None or capture.is_black(image):
                return self._emit(
                    ShotResult(
                        ok=False,
                        kind="black",
                        message="Скриншот чёрный — переключи игру в оконный режим",
                        category=category,
                    )
                )

        # 6. запись в папку недели
        return self._save(image, category)

    def _capture(self, monitor):
        """Свои окна → снимок → свои окна обратно. Окна возвращаются всегда."""
        if self.hide_windows:
            try:
                self.hide_windows()
            except Exception:
                log.exception("Не удалось спрятать свои окна")
        try:
            return self._grab(monitor)
        except Exception:
            log.exception("Ошибка захвата экрана")
            return None
        finally:
            if self.show_windows:
                try:
                    self.show_windows()
                except Exception:
                    log.exception("Не удалось вернуть свои окна")

    def _save(self, image, category: str) -> ShotResult:
        stamp = self._clock()
        name = file_name(stamp, category)
        fallback = False
        try:
            folder = weeks.category_folder(self._config, category, stamp)
            path = unique_path(folder, name)
            self._write(image, path)
        except OSError as exc:
            log.warning("Основная папка недоступна (%s), пробуем запасную", exc)
            try:
                folder = weeks.fallback_folder(self._config, category, stamp)
                path = unique_path(folder, name)
                self._write(image, path)
                fallback = True
            except OSError as exc2:
                log.error("Запасная папка тоже недоступна: %s", exc2)
                return self._emit(
                    ShotResult(
                        ok=False,
                        kind="write_fail",
                        message=f"Скриншот не сохранён: {exc2.strerror or exc2}",
                        category=category,
                    )
                )
        result = ShotResult(
            ok=True,
            kind="saved",
            message=f"Скриншот сохранён · {category}",
            category=category,
            path=str(path),
            fallback=fallback,
        )
        # Предупреждений может быть два сразу (уехали в «Документы» И ключ
        # занят в игре) — раньше второе затирало первое, и человек видел
        # только половину причины.
        warnings: list[str] = []
        if fallback:
            warnings.append("Нет прав на основную папку — файл в «Документы»")
        if self._in_game_key(category):
            warnings.append("Клавиша занята в игре — смени её в настройках")
        result.warning = "; ".join(warnings)
        return self._emit(result)

    def _write(self, image, path: Path) -> None:
        """JPG: качество из настроек (по ТЗ 90 %, ползунка нет), без перезаписи."""
        quality = int(getattr(self._config, "shots_quality", 90))
        image.convert("RGB").save(path, "JPEG", quality=max(1, min(100, quality)))

    def _in_game_key(self, category: str) -> bool:
        """Пометка «занята в игре» на конкретной категории."""
        for cat in self._config.shots_categories or []:
            if normalize(str(cat.get("name", ""))) == normalize(category):
                return bool(cat.get("in_game"))
        return False

    # --- уведомления -----------------------------------------------------

    def _blocked(self, category: str, message: str) -> ShotResult:
        return self._emit(
            ShotResult(ok=False, kind="blocked", message=message, category=category)
        )

    def _emit(self, result: ShotResult) -> ShotResult:
        if result.message and self.on_result:
            try:
                self.on_result(result)
            except Exception:
                log.exception("Обработчик результата скриншота упал")
        return result

__all__ = ["ShotsService", "ShotResult", "WEEK_CHECK_SEC"]
