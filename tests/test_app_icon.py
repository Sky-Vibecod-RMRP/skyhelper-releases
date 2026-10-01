# -*- coding: utf-8 -*-
"""Окно и панель задач: иконка задаётся программно (фикс кэша Windows).

Баг: окно без setWindowIcon не отдаёт иконку системе (WM_GETICON = 0), и
панель задач брала иконку файла exe из кэша Windows — после автообновления
там надолго оставалась иконка прошлой версии («питон» или старый знак).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_window_icon_path_dev_points_to_asset():
    from app.paths import window_icon_path

    path = window_icon_path()
    assert path == ROOT / "assets" / "SKYHELPER.ico"
    assert path.exists(), "в разработке иконка окна лежит в assets/"


def test_exe_build_bundles_icon_for_runtime():
    """Иконка должна попасть в распаковку exe, иначе setWindowIcon пуст."""
    spec = (ROOT / "SKYHELPER.spec").read_text(encoding="utf-8")
    assert "('assets/SKYHELPER.ico', 'assets')" in spec, (
        "spec не кладёт иконку в datas — в exe её не будет"
    )


def test_apply_window_icon_sets_qapp_icon():
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from app.ui.app_icon import apply_window_icon

    app = QApplication.instance() or QApplication([])
    app.setWindowIcon(QIcon())                 # сбрасываем — что поставил до нас?
    assert app.windowIcon().isNull()
    apply_window_icon(app)
    assert not app.windowIcon().isNull(), "apply_window_icon не поставил иконку"


def test_apply_window_icon_tolerates_missing_file(tmp_path, monkeypatch):
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from app.ui import app_icon

    app = QApplication.instance() or QApplication([])
    app.setWindowIcon(QIcon())
    monkeypatch.setattr(app_icon, "window_icon_path", lambda: tmp_path / "нет.ico")
    app_icon.apply_window_icon(app)            # не должно упасть
    assert app.windowIcon().isNull(), "без файла иконку трогать не надо"


def test_gui_main_wires_icon_and_migration():
    """Вызовы стоят в точке входа: миграция папок и иконка окна."""
    src = (ROOT / "app" / "gui_main.py").read_text(encoding="utf-8")
    assert "from app.ui.app_icon import apply_window_icon" in src
    assert "apply_window_icon(app)" in src, "главное окно без setWindowIcon"
    assert "migrate_legacy_dirs()" in src, "миграция папок не вызывается"
