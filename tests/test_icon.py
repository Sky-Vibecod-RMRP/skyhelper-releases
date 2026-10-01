# -*- coding: utf-8 -*-
"""Иконка SKY HELPER: файл на месте и подключён к exe и установщику."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICO = ROOT / "assets" / "SKYHELPER.ico"


def test_icon_file_exists_with_both_extremes():
    assert ICO.exists(), "assets/SKYHELPER.ico отсутствует — её генерирует скрипт"
    from PIL import Image

    with Image.open(ICO) as img:
        sizes = set(img.info.get("sizes", set()))
    sizes = {(w, h) for w, h in sizes}
    assert (256, 256) in sizes, f"нет 256px для проводника: {sizes}"
    assert (16, 16) in sizes, f"нет 16px для трея/панели задач: {sizes}"


def test_exe_build_uses_icon():
    spec = (ROOT / "SKYHELPER.spec").read_text(encoding="utf-8")
    assert "icon='assets/SKYHELPER.ico'" in spec, (
        "spec не ссылается на иконку — exe снова получит логотип Python"
    )


def test_installer_uses_icon():
    iss = (ROOT / "installer" / "SKYHELPER.iss").read_text(encoding="utf-8")
    assert "SetupIconFile=..\\assets\\SKYHELPER.ico" in iss, (
        "у установщика нет своей иконки"
    )
