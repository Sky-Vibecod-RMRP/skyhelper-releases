# -*- coding: utf-8 -*-
"""Ребрендинг: продукт называется SKY HELPER, старые папки переезжают.

«RMRP» как игровой проект (правила, события, sky-grafana.rmrp) остаётся —
убрано только старое имя программы «RMRP Admin Tracker».
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Строки, которых больше не должно быть в пользовательских текстах.
OLD = ("RMRP Admin Tracker", "RMRPAdminTracker", "RMRP_stats", "RMRP_report")


def _make_home(tmp_path: Path, monkeypatch) -> Path:
    home = tmp_path / "home"
    (home / "Documents").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda *args: home)
    return home


# --- имена ------------------------------------------------------------------

def test_default_names_are_sky_helper():
    from app import paths

    assert paths.APP_NAME == "SKYHELPER"
    assert paths.OLD_APP_NAME == "RMRPAdminTracker"      # источник миграции
    assert paths.default_excel_path().name == "SKYHELPER_stats.xlsx"
    assert paths.default_report_image_path().name == "SKYHELPER_report.png"
    assert paths.default_output_dir().name == "SKY HELPER"
    assert "RMRP Admin Tracker" not in str(paths.default_output_dir())


def test_rules_path_follows_app_name(monkeypatch, tmp_path):
    from app.help import data as help_data

    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert help_data.rules_path() == tmp_path / "SKYHELPER" / "rules.json"


# --- миграция папок при старте ---------------------------------------------

def test_migrate_moves_appdata_and_documents(tmp_path, monkeypatch):
    from app import paths

    roaming = tmp_path / "Roaming"
    old_app = roaming / "RMRPAdminTracker"
    old_app.mkdir(parents=True)
    (old_app / "license.key").write_text("k", encoding="utf-8")
    (old_app / "data.db").write_bytes(b"db")

    home = _make_home(tmp_path, monkeypatch)
    old_docs = home / "Documents" / "RMRP Admin Tracker"
    old_docs.mkdir(parents=True)
    (old_docs / "RMRP_stats.xlsx").write_bytes(b"xlsx")

    monkeypatch.setenv("APPDATA", str(roaming))
    paths.migrate_legacy_dirs()

    new_app = roaming / "SKYHELPER"
    assert not old_app.exists(), "старая папка данных не переименовалась"
    assert (new_app / "license.key").read_text(encoding="utf-8") == "k"
    assert (new_app / "data.db").exists(), "база должна переехать целиком"

    new_docs = home / "Documents" / "SKY HELPER"
    assert not old_docs.exists(), "старая папка отчётов не переименовалась"
    assert (new_docs / "RMRP_stats.xlsx").exists(), (
        "старые отчёты должны переехать целиком (имя файла при переезде "
        "сохраняется, новые будут писаться как SKYHELPER_stats.xlsx)"
    )

    paths.migrate_legacy_dirs()                     # повторный запуск безопасен
    assert new_app.exists() and new_docs.exists()


def test_migrate_resets_output_dir_that_pointed_to_old_documents(
        tmp_path, monkeypatch):
    from app import paths

    home = _make_home(tmp_path, monkeypatch)
    old_docs = home / "Documents" / "RMRP Admin Tracker"

    roaming = tmp_path / "Roaming"
    old_app = roaming / "RMRPAdminTracker"
    old_app.mkdir(parents=True)
    (old_app / "config.json").write_text(
        json.dumps({"output_dir": str(old_docs), "excel_path": ""}),
        encoding="utf-8")

    monkeypatch.setenv("APPDATA", str(roaming))
    paths.migrate_legacy_dirs()

    data = json.loads(
        (roaming / "SKYHELPER" / "config.json").read_text(encoding="utf-8"))
    assert data["output_dir"] == "", (
        "путь отчётов указывал на старую папку — надо сбросить на дефолт"
    )


def test_migrate_keeps_custom_output_dir(tmp_path, monkeypatch):
    """Свой, заданный вручную путь отчётов трогать нельзя."""
    from app import paths

    home = _make_home(tmp_path, monkeypatch)
    roaming = tmp_path / "Roaming"
    old_app = roaming / "RMRPAdminTracker"
    old_app.mkdir(parents=True)
    (old_app / "config.json").write_text(
        json.dumps({"output_dir": "D:\\Отчёты\\Своя"}),
        encoding="utf-8")

    monkeypatch.setenv("APPDATA", str(roaming))
    paths.migrate_legacy_dirs()

    data = json.loads(
        (roaming / "SKYHELPER" / "config.json").read_text(encoding="utf-8"))
    assert data["output_dir"] == "D:\\Отчёты\\Своя"
    assert home.exists()


def test_migrate_keeps_both_when_new_exists(tmp_path, monkeypatch):
    """Обе папки есть — новую не трогаем, старую не выбрасываем."""
    from app import paths

    roaming = tmp_path / "Roaming"
    old_app = roaming / "RMRPAdminTracker"
    old_app.mkdir(parents=True)
    (old_app / "old.txt").write_text("old", encoding="utf-8")
    new_app = roaming / "SKYHELPER"
    new_app.mkdir(parents=True)
    (new_app / "new.txt").write_text("new", encoding="utf-8")

    _make_home(tmp_path, monkeypatch)
    monkeypatch.setenv("APPDATA", str(roaming))
    paths.migrate_legacy_dirs()

    assert (old_app / "old.txt").exists(), "старые данные нельзя выбрасывать"
    assert (new_app / "new.txt").read_text(encoding="utf-8") == "new"


def test_migrate_replaces_empty_new_appdata(tmp_path, monkeypatch):
    """Пустую целевую (создал тест/первый запуск) миграция снимает.

    Иначе лицензия и база останутся в старой папке, а новая версия
    посмотрит в пустую — пользователь «потеряет» активацию.
    """
    from app import paths

    roaming = tmp_path / "Roaming"
    old_app = roaming / "RMRPAdminTracker"
    old_app.mkdir(parents=True)
    (old_app / "license.key").write_text("k", encoding="utf-8")
    (roaming / "SKYHELPER").mkdir(parents=True)     # пустая помеха

    _make_home(tmp_path, monkeypatch)
    monkeypatch.setenv("APPDATA", str(roaming))
    paths.migrate_legacy_dirs()

    new_app = roaming / "SKYHELPER"
    assert not old_app.exists()
    assert (new_app / "license.key").read_text(encoding="utf-8") == "k"


# --- тексты и подписи --------------------------------------------------------

def test_no_old_product_name_in_user_texts():
    files = (
        "app/export/excel_export.py",
        "app/export/gsheets.py",
        "app/export/report_image.py",
        "app/export/service.py",
        "app/ui/tray.py",
        "app/help/data.py",
        "app/ui/settings_dialog.py",
        "app/__init__.py",
        "app/config.py",
    )
    for rel in files:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for bad in OLD:
            assert bad not in text, f"{rel}: осталось старое имя «{bad}»"


def test_headlines_say_sky_helper():
    excel = (ROOT / "app/export/excel_export.py").read_text(encoding="utf-8")
    assert '"SKY HELPER"' in excel, "шапка Excel не заменена"
    gsheets = (ROOT / "app/export/gsheets.py").read_text(encoding="utf-8")
    assert '["SKY HELPER"]' in gsheets, "шапка Google Таблицы не заменена"
    png = (ROOT / "app/export/report_image.py").read_text(encoding="utf-8")
    assert '"SKY HELPER"' in png, "заголовок PNG-отчёта не заменён"
    tray = (ROOT / "app/ui/tray.py").read_text(encoding="utf-8")
    assert 'setToolTip("SKY HELPER")' in tray, "подсказка трея не заменена"


# --- exe и установщик --------------------------------------------------------

def test_spec_names_exe_and_bundles_icon():
    spec = (ROOT / "SKYHELPER.spec").read_text(encoding="utf-8")
    assert "name='SKYHELPER'" in spec
    assert not (ROOT / "RMRPAdminTracker.spec").exists(), (
        "старый spec остался — сборка пойдёт на него"
    )


def test_installer_targets_new_exe_and_migrates_old_name():
    iss = (ROOT / "installer/SKYHELPER.iss").read_text(encoding="utf-8")
    assert '#define MyAppExeName "SKYHELPER.exe"' in iss
    assert "..\\dist\\SKYHELPER.exe" in iss
    # переход со старых версий: убиваем оба имени и переводим реестр/ярлыки
    assert "/IM {#MyAppOldExeName} /F /T" in iss, (
        "тихое обновление со старой версии не убьёт старый процесс"
    )
    assert "MigrateOldName" in iss, (
        "автозапуск/RUNASADMIN/ярлыки останутся на старом пути"
    )
    assert "DeleteFile" in iss, "старый exe не удаляется после обновления"


def test_installed_exe_path_is_new_name():
    from app.update_check import installed_exe_path

    assert installed_exe_path().name == "SKYHELPER.exe"
