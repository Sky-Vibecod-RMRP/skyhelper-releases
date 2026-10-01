"""Пути к файлам приложения. Всё хранится в папке пользователя."""
import json
import os
import sys
from pathlib import Path

APP_NAME = "SKYHELPER"

#: Старое имя папки данных (ребрендинг): при старте данные переносятся
#: в ``%APPDATA%\SKYHELPER`` — лицензия, база, настройки и логи сохраняются.
OLD_APP_NAME = "RMRPAdminTracker"

#: Старое имя папки отчётов в «Документах» (ребрендинг).
OLD_DOCUMENTS_DIR = "RMRP Admin Tracker"


def resource_dir(*parts: str) -> Path:
    """Папка с файлами самой программы (картинки сайта, ассеты).

    В обычном запуске это каталог ``app/`` проекта, в собранном ``exe`` —
    распакованная папка PyInstaller (``sys._MEIPASS``), куда те же файлы
    кладутся как ``app/...``.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS") or "") / "app"
    else:
        base = Path(__file__).resolve().parent
    return base.joinpath(*parts)


def window_icon_path() -> Path:
    """Иконка окна (панель задач, диалоги).

    В собранном exe файл лежит в распаковке PyInstaller (см. spec, ``datas``),
    в разработке — в ``assets/`` проекта.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS") or "") / "assets" / "SKYHELPER.ico"
    return Path(__file__).resolve().parent.parent / "assets" / "SKYHELPER.ico"


def _config_root() -> Path:
    base = os.environ.get("APPDATA")
    return Path(base) if base else Path.home() / ".config"


def _move_folder(old: Path, new: Path) -> None:
    """Переименовать ``old`` → ``new``: старая папка важнее красивого имени.

    Если целевая папка уже есть, но пуста (её может создать тест или первый
    запуск до миграции) — снимаем её и переименовываем старую целиком.
    Непустую целевую не трогаем: старые данные выбрасывать нельзя.
    """
    if not old.exists():
        return
    if new.exists():
        if not new.is_dir() or any(new.iterdir()):
            return
        try:
            new.rmdir()
        except OSError:
            return
    try:
        old.rename(new)
    except OSError:
        pass            # занята/нет прав — оставляем старую, ничего не губим


def migrate_legacy_dirs() -> None:
    r"""Переименование папок после ребрендинга (вызывается один раз при старте).

    * ``%APPDATA%\RMRPAdminTracker`` → ``%APPDATA%\SKYHELPER`` — лицензия,
      база, настройки, журналы и ключ активации переезжают целиком.
    * ``Документы\RMRP Admin Tracker`` → ``Документы\SKY HELPER`` — отчёты
      и папка «История» переезжают целиком (имена файлов внутри — новые,
      ``SKYHELPER_stats.xlsx`` и ``SKYHELPER_report.png``).
    * Если в config.json путь отчётов записан как старый дефолт — он
      сбрасывается в пустое значение («по умолчанию»), чтобы указывать на
      уже переехавшую папку. Свой, заданный вручную путь не трогается.
    """
    root = _config_root()
    _move_folder(root / OLD_APP_NAME, root / APP_NAME)

    docs = Path.home() / "Documents"
    old_docs = docs / OLD_DOCUMENTS_DIR
    new_docs = docs / "SKY HELPER"

    cfg_path = root / APP_NAME / "config.json"
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict) and data.get("output_dir") == str(old_docs):
        data["output_dir"] = ""
        try:
            cfg_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    _move_folder(old_docs, new_docs)


def app_dir() -> Path:
    path = _config_root() / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return app_dir() / "data.db"


def config_path() -> Path:
    return app_dir() / "config.json"


def logs_dir() -> Path:
    path = app_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def program_dir() -> Path:
    """Папка, где лежит сама программа (рядом с exe или с проектом)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def program_logs_dir() -> Path:
    """Логи рядом с программой — чтобы их было легко найти (предложение №1)."""
    path = program_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_output_dir() -> Path:
    """Отдельная папка для отчётов: «Документы/SKY HELPER»."""
    return Path.home() / "Documents" / "SKY HELPER"


def default_excel_path() -> Path:
    return default_output_dir() / "SKYHELPER_stats.xlsx"


def default_report_image_path() -> Path:
    """Путь по умолчанию для PNG-отчёта."""
    return default_output_dir() / "SKYHELPER_report.png"


def default_google_key_path() -> Path:
    """Сюда кладём JSON-ключ сервисного аккаунта Google."""
    return app_dir() / "google_key.json"
