"""Просмотр текста с картинками из папки самой программы.

``QTextBrowser`` по умолчанию умеет рисовать ``<img>``, но только из
``file:`` и ``qrc:``. Здесь дополнительно разрешаются ссылки вида
``/img/events/xxx.jpg`` — так скриншоты серверных событий показываются
и в окне программы, и на локальном сайте одним и тем же путём.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QTextBrowser
from PySide6.QtGui import QTextDocument

from app.paths import resource_dir

#: Папка картинок внутри приложения (та же, что раздаёт веб-сервер).
IMAGE_ROOT = resource_dir("web", "static", "img")


def resolve_image(url: QUrl | str) -> Path | None:
    """Путь к картинке по ссылке из HTML; если файла нет — None."""
    raw = url.toString() if isinstance(url, QUrl) else str(url)
    if raw.startswith("file:"):
        local = QUrl(raw).toLocalFile()
        path = Path(local)
        return path if path.is_file() else None
    if not raw.startswith("/img/"):
        return None
    rel = raw[len("/img/"):]
    if not rel or ".." in rel or "\\" in rel:
        return None
    try:
        root = IMAGE_ROOT.resolve()
        path = (IMAGE_ROOT / rel).resolve()
    except OSError:
        return None
    if path != root and root not in path.parents:
        return None
    return path if path.is_file() else None


class ImageBrowser(QTextBrowser):
    """``QTextBrowser``, который тянет картинки из ``app/web/static/img``."""

    def loadResource(self, rtype: int, url: QUrl):  # noqa: N802 — имя из Qt
        if rtype == QTextDocument.ImageResource:
            path = resolve_image(url)
            if path is not None:
                image = QImage(str(path))
                if not image.isNull():
                    return image
        return super().loadResource(rtype, url)
