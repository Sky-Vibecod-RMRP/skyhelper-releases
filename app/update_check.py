# -*- coding: utf-8 -*-
"""Автообновления: проверка манифеста, сроки, подпись и загрузка.

Схема (решение 01.10.2026): свежий установщик лежит в GitHub Releases
публичного репозитория-витрины (без исходников). В корне репозитория —
``manifest.json``: версия, прямая ссылка на установщик, SHA-256, срок
выпуска и подпись Ed25519 **той же парой ключей, что и лицензии**
(:func:`app.license.sign_payload` / :func:`app.license.load_public_key`).

Поведение (решение пользователя 01.10.2026):

  * при запуске, но не чаще раза в :data:`CHECK_INTERVAL_HOURS`, манифест
    сверяется с локальной версией :data:`app.VERSION`;
  * вышла новая версия — окно «Доступна версия X: обновитесь в течение
    дня» (:mod:`app.ui.update_dialog`);
  * прошёл срок :data:`GRACE_HOURS` с выпуска — старая версия
    **отключается**: в собранном ``exe`` пуск только через обновление.
    В исходниках принудительное отключение не действует — как и гейт
    лицензии, оно нужно только для выданного штату ``exe``.

Часы: сроки считаются по ``max(системное время, отметка в state)`` —
откат системных часов не «возвращает в строй» просроченную версию
(тот же приём, что у :func:`app.license.save_state`).

Сеть: сбои сети и отсутствие адреса манифеста — это не ошибка, а
«проверить не получилось»: запуск продолжается как обычно. Уже
полученный и просроченный манифест отключает версию и без сети.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from app import VERSION
from app import license as lic
from app.paths import app_dir

log = logging.getLogger(__name__)

#: Сколько дней на обновление («в течение дня») до отключения версии.
GRACE_HOURS = 24.0

#: Как часто ходить за манифестом в сеть (часы).
CHECK_INTERVAL_HOURS = 6.0

#: Репозиторий-витрина «OWNER/REPO». Пусто = автообновления выключены.
#: Заполняется один раз после создания репозитория (см. README,
#: раздел «Автообновления»); то же значение печатает make_release.py.
UPDATE_REPO = "Sky-Vibecod-RMRP/skyhelper-releases"

#: Файл манифеста в корне витрины (читается напрямую, без API GitHub).
MANIFEST_FILE = "manifest.json"

_USER_AGENT = "SKYHELPER-update/1"


class UpdateError(Exception):
    """Проблема манифеста или загрузки (текст — для журнала и окна)."""


def manifest_url() -> str:
    """Прямой адрес манифеста; пустая строка = обновления выключены."""
    if not UPDATE_REPO:
        return ""
    return (
        f"https://raw.githubusercontent.com/{UPDATE_REPO}/main/{MANIFEST_FILE}"
    )


@dataclass
class UpdateInfo:
    """Одна известная версия из манифеста."""

    version: str
    url: str
    sha256: str
    released_at: float
    notes: str = ""
    sig: str = ""

    @property
    def payload(self) -> str:
        """Строка, которую подписывает автор релиза."""
        return "|".join((
            self.version,
            self.url,
            self.sha256,
            str(int(self.released_at)),
        ))


# --- версии ------------------------------------------------------------------

def _parts(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in str(version).split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(remote: str, local: str) -> bool:
    """True, если ``remote`` новее ``local`` (1.10 > 1.9, «1.2» == «1.2.0»)."""
    if not remote:
        return False
    left, right = _parts(remote), _parts(local)
    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))
    return left > right


# --- манифест ----------------------------------------------------------------

def _b64d(text: str) -> bytes:
    """Тот же код, что у ``license._b64e``: urlsafe без паддинга."""
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def parse_manifest(data: dict) -> UpdateInfo:
    try:
        info = UpdateInfo(
            version=str(data["version"]).strip(),
            url=str(data["url"]).strip(),
            sha256=str(data["sha256"]).strip().lower(),
            released_at=float(data["released_at"]),
            notes=str(data.get("notes", "")),
            sig=str(data.get("sig", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateError(f"манифест повреждён: {exc}") from exc
    if not info.version:
        raise UpdateError("манифест повреждён: нет версии")
    if not info.url.startswith(("http://", "https://")):
        raise UpdateError("манифест повреждён: ссылка не http(s)")
    if len(info.sha256) != 64 or not all(c in "0123456789abcdef" for c in info.sha256):
        raise UpdateError("манифест повреждён: SHA-256 не похож на хеш")
    return info


def verify_info(info: UpdateInfo, *, pem: str | None = None) -> bool:
    """Сошлась ли подпись манифеста с публичным ключом из сборки.

    ``pem`` — только для тестов: подменить ключ, встроенный в сборку
    (:mod:`app.license_public`).
    """
    if not info.sig:
        return False
    try:
        public_key = lic.load_public_key(pem)
        public_key.verify(_b64d(info.sig), info.payload.encode("utf-8"))
        return True
    except Exception:  # noqa: BLE001 — любая ошибка = подпись не сошлась
        log.warning("Обновления: подпись манифеста не сошлась")
        return False


def fetch_manifest(
    url: str | None = None,
    *,
    timeout: float = 4.0,
    pem: str | None = None,
) -> UpdateInfo:
    """Скачать и проверить манифест. Ошибки сети/формата → UpdateError."""
    target = manifest_url() if url is None else url
    if not target:
        raise UpdateError("адрес манифеста не задан")
    request = urllib.request.Request(target, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (намеренный URL)
            raw = response.read(1_000_000)
    except Exception as exc:  # noqa: BLE001 — любая сетевая ошибка
        raise UpdateError(f"нет связи с манифестом: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError(f"манифест не JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise UpdateError("манифест не JSON-объект")
    info = parse_manifest(data)
    if not verify_info(info, pem=pem):
        raise UpdateError("подпись манифеста не сошлась")
    return info


# --- состояние ---------------------------------------------------------------

def state_path() -> Path:
    return app_dir() / "update_state.json"


def load_state() -> dict:
    try:
        data = json.loads(state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state: dict) -> None:
    path = state_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(path)


def effective_now(state: dict, now: float | None = None) -> float:
    """Текущее время, но не раньше уже наблюдавшегося (анти-откат часов)."""
    ts = time.time() if now is None else float(now)
    return max(ts, float(state.get("max_seen", 0.0)))


def snooze(now: float | None = None) -> None:
    """«Напомнить позже»: не показывать уведомление следующие интервал."""
    state = load_state()
    ts = effective_now(state, now)
    state["max_seen"] = ts
    state["snooze_until"] = ts + CHECK_INTERVAL_HOURS * 3600.0
    save_state(state)


# --- сроки -------------------------------------------------------------------

def grace_deadline(info: UpdateInfo) -> float:
    """Момент, после которого прошлая версия отключается."""
    return info.released_at + GRACE_HOURS * 3600.0


def is_expired(info: UpdateInfo, now: float) -> bool:
    return now >= grace_deadline(info)


def effective_status(
    info: UpdateInfo | None,
    local_version: str,
    now: float,
    *,
    frozen: bool | None = None,
) -> str:
    """none | notify | forced.

    ``forced`` — только в собранном ``exe``: в исходниках просроченная
    версия лишь напоминает об обновлении (не мешает разработке).
    """
    if info is None or not is_newer(info.version, local_version):
        return "none"
    if is_expired(info, now):
        is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
        return "forced" if is_frozen else "notify"
    return "notify"


def _stored_info(state: dict) -> UpdateInfo | None:
    raw = state.get("manifest")
    if not isinstance(raw, dict):
        return None
    try:
        info = parse_manifest(raw)
    except UpdateError:
        return None
    if not verify_info(info):
        # локальный файл правили руками — не верим: ни чужую ссылку,
        # ни искусственную «просрочку» из него не берём
        log.warning("Обновления: сохранённый манифест не прошёл проверку")
        return None
    return info


def check_for_update(
    *,
    now: float | None = None,
    fetch=None,
    local_version: str | None = None,
) -> tuple[str, UpdateInfo | None]:
    """(статус, манифест). Статус: none | notify | forced.

    * адрес не задан / всё свежее → ("none", None);
    * известный манифест уже просрочен → ("forced", ...) **без сети**;
    * сеть ходит не чаще :data:`CHECK_INTERVAL_HOURS`; сбой сети —
      не ошибка: остаёмся на уже полученном манифесте.
    """
    url = manifest_url()
    if not url:
        return "none", None
    local = VERSION if local_version is None else local_version
    state = load_state()
    ts = effective_now(state, now)

    stored = _stored_info(state)
    status = effective_status(stored, local, ts)
    if status == "forced":
        state["max_seen"] = ts
        save_state(state)
        return "forced", stored          # отключение действует и без сети

    last = float(state.get("last_check", 0.0))
    due = (ts - last) >= CHECK_INTERVAL_HOURS * 3600.0
    current = stored
    if due:
        state["last_check"] = ts
        state["max_seen"] = ts
        do_fetch = fetch or fetch_manifest
        try:
            fresh = do_fetch(url)
        except UpdateError as exc:
            log.warning("Обновления: %s", exc)
            fresh = None
        if fresh is not None:
            state["manifest"] = asdict(fresh)
            state.pop("snooze_until", None)   # новая свежка = новое напоминание
            current = fresh
        save_state(state)

    status = effective_status(current, local, ts)
    if status == "none":
        return "none", None
    if ts < float(state.get("snooze_until", 0.0)):
        log.info("Обновления: версия %s отложена пользователем", current.version)
        return "none", None
    return status, current


# --- загрузка и установка ----------------------------------------------------

def download_update(
    info: UpdateInfo,
    dest: Path | None = None,
    *,
    progress=None,
    timeout: float = 60.0,
) -> Path:
    """Скачать установщик, сверить SHA-256, вернуть готовый файл.

    ``progress(done, total)`` — вызывается по мере скачивания.
    """
    if dest is None:
        name = f"SKYHELPER_Setup_{info.version}.exe"
        dest = Path(tempfile.gettempdir()) / name
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(info.url, headers={"User-Agent": _USER_AGENT})
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (намеренный URL)
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            with open(tmp, "wb") as handle:
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress is not None and total:
                        progress(done, total)
    except Exception as exc:  # noqa: BLE001 — человеку показываем текст ошибки
        tmp.unlink(missing_ok=True)
        raise UpdateError(f"не удалось скачать: {exc}") from exc
    if digest.hexdigest() != info.sha256:
        tmp.unlink(missing_ok=True)
        raise UpdateError("файл повреждён: SHA-256 не совпал")
    dest.unlink(missing_ok=True)
    tmp.replace(dest)
    return dest


def installed_exe_path() -> Path:
    """Куда ставит программу установщик (см. installer/SKYHELPER.iss)."""
    local = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(local) / "Programs" / "SKY HELPER" / "SKYHELPER.exe"


def install_update(installer: Path, *, target: Path | None = None) -> None:
    """Молча установить обновление и перезапустить уже новую копию.

    Порядок важен: этот процесс сразу завершается, а отдельный ``cmd``
    ждёт окончания установщика и запускает новую копию. Если же ждать
    установщик внутри программы, тот упрётся в залоченный собственный
    exe (см. отчёт об установщике: файл держится до закрытия процесса).
    """
    installer = Path(installer)
    if not installer.exists():
        raise UpdateError(f"установщик не найден: {installer}")
    new_exe = Path(target) if target else installed_exe_path()
    if not new_exe.exists():
        new_exe = Path(sys.executable)   # «без установки»: перезапускаем себя
    chain = (
        f'""{installer}" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-'
        f' & ping -n 4 127.0.0.1 >nul & start "" "{new_exe}""'
    )
    flags = (
        # cmd нужна НЕВИДИМАЯ консоль (CREATE_NO_WINDOW): ею же делятся
        # консольные дети цепочки — ping не порождает отдельного окна.
        # А вот DETACHED_PROCESS («вообще без консоли») вреден: тогда у cmd
        # консоли нет и ping при запуске создает новую, УЖЕ видимую — на
        # Windows 11 это мелькает окном Терминала секунд 4 (живая матрица:
        # DETACHED+ping = 2 окна, без него = 0; без ping = 0 — виноват именно
        # консольный ping при detached-cmd).
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    )
    # _PYI_* переменные наследуются от этой программы и говорят новому
    # onefile-экземпляру: «ты продолжение нашего дерева процессов, бери наш
    # каталог распаковки». Но нас и старого bootloader-а к тому моменту уже
    # нет — PyInstaller и падает с «Security validation failure: PID not
    # found» (протестировано: см. Отчёты/Автообновление_*.txt). Без этих
    # переменных новая копия стартует как самостоятельный процесс, минуя
    # ветку наследования и её проверку.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("_PYI")
    }
    subprocess.Popen(                          # noqa: S603 — своя строка, не данные
        # строкой, НЕ списком: list2cmdline экранировал бы вложенные кавычки
        # как \", а cmd.exe их так не читает — цепочка сломалась бы
        f"cmd.exe /c {chain}",
        cwd=tempfile.gettempdir(),
        env=env,
        creationflags=flags,
        close_fds=True,
    )
    log.info("Обновления: установка %s запущена, программа завершается",
             installer.name)
