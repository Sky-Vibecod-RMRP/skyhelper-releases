# -*- coding: utf-8 -*-
"""Установщик: принудительное закрытие приложения и настоящая версия.

Два живых бага, пойманных при ручной установке 1.0.5 (см. отчёт
об автообновлении, эпизод про страницу «Программе установки не удалось
автоматически закрыть все приложения»):
  1. SKY HELPER по дизайну уходит в трей, Restart Manager его не закрывает —
     нужен taskkill в InitializeSetup (самый первый хук, до проверки файлов);
  2. #define MyAppVersion был статичным «1.0.0» — его правит make_release.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISS = ROOT / "installer" / "SKYHELPER.iss"


def test_setup_kills_running_app_before_files_check():
    text = ISS.read_text(encoding="utf-8")
    assert "function InitializeSetup(): Boolean;" in text, (
        "без InitializeSetup ручная установка поверх работающей программы "
        "упирается в «не удалось закрыть все приложения»"
    )
    assert "taskkill.exe" in text
    assert "/IM {#MyAppExeName} /F /T" in text, (
        "гасим все экземпляры образа, включая второй процесс onefile"
    )
    # CloseApplications остаётся для остальных программ (Explorer и т.п.)
    assert "CloseApplications=yes" in text


def test_app_version_define_is_machine_editable():
    """Строка, которую правит tools.make_release.set_installer_version."""
    text = ISS.read_text(encoding="utf-8")
    assert re.search(r'^#define MyAppVersion "[^"]*"$', text, re.MULTILINE), (
        "строка версии не найдена/многострочная — regex релиза упадёт"
    )
