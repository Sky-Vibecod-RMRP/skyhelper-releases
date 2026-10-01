"""Настройки приложения (хранятся в config.json).

Файл всегда сохраняется в UTF-8, но читаем и «сломанные» варианты:
программа Windows иногда пишет JSON в cp1251 или с BOM, раньше из-за такого
файла все настройки молча слетали в дефолт.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)


#: Виды кастомного курсора сайта: ключ → как называется в настройках.
CURSOR_STYLES = {
    "white": "Белый кружок",
    "ring": "Кружок с кольцом",
    "off": "Системный (без рисования)",
}


def default_shot_categories() -> list[dict]:
    """Восемь категорий недельного отчёта.

    Имена дословно с Google Диска (включая «/» — на диск он ляжет как «-»),
    клавиши подобраны так, чтобы не пересечься с F9 / Ctrl+F9 / F10 /
    Insert, которые уже заняты программой.
    """
    return [
        {"name": "Захват/налёт (День)", "hotkey": "f6", "in_game": False},
        {"name": "Захват/налёт (Ночь)", "hotkey": "f7", "in_game": False},
        {"name": "Наказания (День)", "hotkey": "f8", "in_game": False},
        {"name": "Наказания (Ночь)", "hotkey": "f11", "in_game": False},
        {"name": "Нападение на ИК-7", "hotkey": "f12", "in_game": False},
        {"name": "Ограбы/поставки/КРАЗ/AirDrop (День)", "hotkey": "shift+f6", "in_game": False},
        {"name": "Ограбы/поставки/КРАЗ/AirDrop (Ночь)", "hotkey": "shift+f7", "in_game": False},
        {"name": "Помощь в проведении МП", "hotkey": "shift+f8", "in_game": False},
    ]


def _read_text(path: Path) -> tuple[str, str]:
    """Читает текст в любом из поддерживаемых кодировок. Возвращает (текст, кодировка)."""
    raw = path.read_bytes()
    for name in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return raw.decode(name), name
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


@dataclass
class Config:
    # Имена процессов игры. Точное имя на RMRP нужно проверить через
    # tools/list_processes.py; GTA5.exe стоит как предположение.
    game_processes: list[str] = field(default_factory=lambda: ["GTA5.exe"])

    hotkey_add: str = "f9"
    hotkey_remove: str = "ctrl+f9"
    hotkey_duty: str = "f10"  # начать/закончить дежурство
    # Показать/спрятать окно поверх игры. Пусто = клавиша выключена.
    hotkey_toggle: str = "insert"
    # Держать главное окно поверх других окон (над игрой).
    window_on_top: bool = True

    # Считать онлайн и обращения только пока включено дежурство.
    # False = считать всё время, пока запущена игра.
    require_duty: bool = True
    # Когда игра закрывается, дежурство выключается само.
    duty_auto_off_on_game_close: bool = True

    weekly_hours_norm: float = 70.0
    weekly_reports_norm: int = 600
    week_start_weekday: int = 0  # 0 = понедельник

    poll_interval_sec: float = 3.0        # как часто проверяем процесс игры
    heartbeat_interval_sec: float = 30.0  # как часто «пульс» открытой сессии
    max_gap_sec: float = 30.0             # разрыв между проверками = сон/зависание ПК

    # Засчитывать нажатие клавиши только когда игра запущена
    count_only_in_game: bool = True

    # Экспорт. Пустой output_dir = папка «Документы\SKY HELPER».
    output_dir: str = ""
    excel_path: str = ""          # пусто = <output_dir>\SKYHELPER_stats.xlsx
    report_image_path: str = ""   # пусто = <output_dir>\SKYHELPER_report.png
    archive_weekly: bool = True   # копия PNG каждой недели в <output_dir>\История
    export_interval_min: float = 120.0

    # Google Таблица (необязательно). Пустой gsheet_id = выключено.
    gsheet_id: str = ""
    # Путь к JSON-ключу сервисного аккаунта. Пусто = google_key.json в папке настроек.
    gsheet_credentials: str = ""

    # Локальный сайт с живыми цифрами. Стандартный 80-й порт, чтобы ссылка была
    # без ":8080" — http://sky-grafana.rmrp/ (просто http://127.0.0.1/).
    web_enabled: bool = False
    # "127.0.0.1" = только этот ПК; "0.0.0.0" = открыть и для телефона в той же Wi-Fi сети.
    web_host: str = "127.0.0.1"
    web_port: int = 80
    # Код доступа в виде хэша (pbkdf2_sha256$...). Пусто = без кода.
    web_pin_hash: str = ""

    # Локальный вход в программу (вариант B): логин + хэш пароля (sha256).
    # Пустой пароль = вход выключен. Хэш считается от пароля в UTF-8.
    login: str = "Tester-STAFF-SKYHELPER"
    password_hash: str = "4cadeeb131631cd9f6e21ec72afa041bb9e3e7446927d9cf25f97f99fbf6c23d"
    # «Запомнить меня»: не спрашивать пароль при следующем запуске.
    remember_me: bool = False

    # --- Лицензия -----------------------------------------------------------
    # Адрес подписанного списка отозванных ключей (публичная gist-запись).
    # Пусто = обновлять нечего, работаем по кэшу. Задаётся в настройках —
    # чтобы сменить адрес, пересобирать exe не нужно.
    revocation_url: str = ""

    # Оформление окна и звуки уведомлений.
    ui_theme: str = "dark"       # dark | midnight | light
    sound_theme: str = "system"  # off | system | soft

    # --- Оформление сайта ---------------------------------------------------
    # Эффект дождя на фоне сайта. По умолчанию включён, но при
    # prefers-reduced-motion в браузере всё равно не рисуется.
    rain_enabled: bool = True
    # Кастомный курсор сайта: white — белый кружок, ring — кружок с кольцом,
    # off — обычный системный курсор.
    cursor_style: str = "white"

    # --- Скриншоты для еженедельного отчёта ------------------------------
    # Корень отчётов. Пусто = папка с программой (если туда нельзя писать —
    # автоматически «Документы\SKY HELPER»). Папка недели
    # «Отчёты ¦ Администратор ¦ 28.09.2026–04.10.2026» создаётся внутри сама.
    shots_root: str = ""
    # Качество JPG. По ТЗ фиксировано на 90 %, ползунка в интерфейсе нет.
    shots_quality: int = 90
    # Звук скриншота отдельным переключателем: общей темой (sound_theme)
    # не управляет, по умолчанию включён.
    shots_sound: bool = True
    # Разрешить снимок, когда не на дежурстве. По умолчанию выключен —
    # пока дежурство не включено (F10), клавиши категорий не работают.
    shots_allow_no_duty: bool = False
    # 8 категорий: имя в точности как на Google Диске («/» станет «-» при
    # записи на диск), своя клавиша и пометка «занята в игре».
    shots_categories: list[dict] = field(default_factory=default_shot_categories)

    @classmethod
    def load(cls, path: Path) -> "Config":
        if not path.exists():
            config = cls()
            config.save(path)
            return config
        try:
            text, encoding = _read_text(path)
            raw = json.loads(text)
            known = {f.name for f in fields(cls)}
            config = cls(**{k: v for k, v in raw.items() if k in known})
        except (OSError, ValueError, TypeError):
            log.exception(
                "Не удалось прочитать config.json, сохраняю копию и беру настройки по умолчанию"
            )
            try:
                path.replace(path.with_suffix(".json.bak"))
            except OSError:
                pass
            config = cls()
            config.save(path)
            return config
        if encoding != "utf-8":
            # Файл был не в UTF-8 — пересохраняем сразу, чтобы чтение дальше не ломалось.
            log.warning("config.json был в %s, пересохраняю в UTF-8", encoding)
            config.save(path)
        return config

    def save(self, path: Path) -> None:
        text = json.dumps(asdict(self), ensure_ascii=False, indent=2)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)  # замена атомарная: файл не порвётся при сбое
