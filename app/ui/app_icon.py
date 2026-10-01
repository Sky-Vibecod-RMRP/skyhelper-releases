# -*- coding: utf-8 -*-
"""Иконка окна приложения: панель задач должна показывать SH, а не кэш."""
from __future__ import annotations

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.paths import window_icon_path


def apply_window_icon(app: QApplication) -> None:
    """Ставит окну иконку SH из assets/SKYHELPER.ico.

    Без ``setWindowIcon`` окно не отдаёт свою иконку системе (WM_GETICON
    пуст), и панель задач берёт иконку файла exe из кэша Windows — после
    автообновления там надолго остаётся иконка прошлой версии («питон»
    или старый знак).
    """
    path = window_icon_path()
    if path.exists():
        app.setWindowIcon(QIcon(str(path)))
