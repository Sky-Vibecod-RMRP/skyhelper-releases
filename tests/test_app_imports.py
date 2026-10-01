# -*- coding: utf-8 -*-
"""Все модули программы импортируются — сборка exe не упадёт на старте.

Проверка нужна именно здесь: в замороженной сборке PySide6 отдаёт
QtWidgets/QtGui строго по модулям, и опечатка в импорте всплывает только
при запуске exe (баг: окно «Unhandled exception», сайт не поднимается).
"""
from __future__ import annotations

import importlib
import os
import pkgutil
import sys

import pytest


def _app_modules() -> list[str]:
    import app
    names = []
    for module in pkgutil.walk_packages(app.__path__, app.__name__ + "."):
        if module.ispkg:
            continue
        names.append(module.name)
    return sorted(set(names))


@pytest.mark.parametrize("name", _app_modules())
def test_every_app_module_imports(name: str):
    """Каждый модуль приложения импортируется без NameError/ImportError."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    importlib.import_module(name)


def test_gui_entry_imports_qt_classes_from_right_modules():
    """Ключевые Qt-классы доступны именно там, где их ищут в коде.

    QGraphicsDropShadowEffect живёт в QtWidgets — импорт из QtGui
    работает только в dev-среде и роняет exe (баг 30.09.2026).
    """
    from PySide6.QtGui import QColor                      # noqa: F401
    from PySide6.QtWidgets import QGraphicsDropShadowEffect  # noqa: F401

    import app.ui.helper_window as helper_window            # noqa: F401
    import app.gui_main as gui_main                         # noqa: F401
    assert callable(gui_main.main)
    assert helper_window.QGraphicsDropShadowEffect is QGraphicsDropShadowEffect
    assert sys.modules["app.ui.helper_window"] is helper_window
