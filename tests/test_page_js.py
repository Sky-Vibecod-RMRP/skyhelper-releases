# -*- coding: utf-8 -*-
"""JS страницы должен разбираться браузером — иначе вкладки мертвы.

Один русский комментарий с решёткой внутри _CURSOR_JS ронял весь скрипт
страницы: вкладки не переключались, каталог не рисовался, а обычные
проверки HTML это не ловили. Здесь скрипт страницы прогоняется через
node --check (если node есть в PATH).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from app.web import page as web_page


def _page_script() -> str:
    html = web_page.dashboard_page({})
    match = re.search(r"<script>(.*)</script>", html, re.S)
    assert match, "на странице нет <script>"
    return match.group(1)


def test_page_script_is_syntactically_valid():
    if not shutil.which("node"):
        pytest.skip("node не установлен — проверка синтаксиса JS недоступна")
    script = _page_script()
    tmp = Path(__file__).resolve().parent / "_page_script.js"
    tmp.write_text(script, encoding="utf-8")
    try:
        proc = subprocess.run(["node", "--check", str(tmp)],
                              capture_output=True, text=True, encoding="utf-8")
    finally:
        tmp.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr


def test_js_blocks_have_no_python_style_comments():
    """В JS-строках Python-комментарии (`# ...`) недопустимы — только `//`."""
    for name in ("_DASH_JS", "_VIEW_JS", "_CMDS_JS", "_EVENTS_JS",
                 "_CATALOG_JS", "_STAFF_JS", "_CURSOR_JS"):
        source = getattr(web_page, name, None)
        assert source is not None, name
        bad = [ln for ln in source.split("\n") if ln.lstrip().startswith("#")]
        assert not bad, "%s: Python-комментарий внутри JS: %s" % (name, bad[:2])
