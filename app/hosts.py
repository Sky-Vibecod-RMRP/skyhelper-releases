"""Пропись локального домена сайта статистики в файл hosts (Windows).

Сайт открывается по адресу http://sky-grafana.rmrp/ — красиво и без ":80".
Такое имя существует только через файл hosts (строка ``127.0.0.1
sky-grafana.rmrp``). Программа запускается от имени администратора
(RUNASADMIN), поэтому запись ставится молча при каждом старте — один раз
добавилась и живёт в системе дальше.

Если прав всё-таки нет (например, тестовый запуск) — просто возвращаем
False и сайт остаётся доступен по http://127.0.0.1/; батник
install-sky-grafana.bat остаётся ручным фолбэком. Существующие записи
не дублируются, файл читается байтами (кодировка hosts не важна).
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Типовой путь Windows: C:\Windows\System32\drivers\etc\hosts (без расширения).
HOSTS_PATH = (
    Path(__import__("os").environ.get("SystemRoot", r"C:\Windows"))
    / "System32" / "drivers" / "etc" / "hosts"
)

DOMAIN = "sky-grafana.rmrp"
SITE_URL = f"http://{DOMAIN}/"


def ensure_local_domain(
    hosts_path: Path | None = None,
    domain: str = DOMAIN,
    ip: str = "127.0.0.1",
) -> bool:
    """Добавить строку ``{ip} {domain}`` в hosts, если её ещё нет.

    Возвращает True, когда запись уже была или добавлена; False, когда
    файл недоступен либо прав на запись мало. Никогда не бросает
    исключений — сайт не должен мешать запуску программы.
    """
    path = HOSTS_PATH if hosts_path is None else Path(hosts_path)
    wanted = domain.encode("ascii", "ignore")
    try:
        data = path.read_bytes()
    except OSError as exc:
        log.debug("hosts не читается (%s) — пропись домена пропущена", exc)
        return False

    # Строка-кандидат: убираем комментарий и смотрим токены (таб или пробел).
    for raw in data.split(b"\n"):
        head = raw.split(b"#", 1)[0]
        if wanted in head.split():
            return True

    line = ip.encode("ascii", "ignore") + b" " + wanted + b"\n"
    try:
        with path.open("ab") as fh:
            if data and not data.endswith(b"\n"):
                fh.write(b"\n")     # не приклеиться к незаконченной строке
            fh.write(line)
    except OSError as exc:
        log.warning(
            "Не удалось дописать %s в hosts (%s) — сайт открыт по http://127.0.0.1/",
            domain, exc,
        )
        return False
    log.info("hosts: добавлена запись %s %s", ip, domain)
    return True
