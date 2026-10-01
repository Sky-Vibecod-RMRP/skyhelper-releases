# -*- coding: utf-8 -*-
"""Автообновления: версии, манифест, подписи, сроки, состояние, загрузка.

Всё локально: %APPDATA% подменяется на tmp_path (как в test_license),
ключи для подписи генерируются в тесте — приватный ключ администратора
здесь не участвует.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import VERSION, license as lic, update_check as uc

GRACE = uc.GRACE_HOURS * 3600.0
INTERVAL = uc.CHECK_INTERVAL_HOURS * 3600.0
RELEASED = 1_800_000_000.0


# --- фикстуры и помощники ----------------------------------------------------

@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """Вся «своя» пачка (update_state.json) живёт во временной папке."""
    monkeypatch.setattr(uc, "app_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def keypair(monkeypatch):
    """Свой ключ подписи: и для явных проверок (pem=...), и для путей
    продакшена, которые берут встроенный ключ из сборки
    (проверка сохранённого манифеста, загрузка манифеста без pem).
    """
    private = Ed25519PrivateKey.generate()
    public_key = private.public_key()
    pem = public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    real_load = lic.load_public_key

    def load(pem_arg: str | None = None):
        if pem_arg is None:
            return public_key
        return real_load(pem_arg)

    monkeypatch.setattr(lic, "load_public_key", load)
    return private, pem


@pytest.fixture
def frozen_on(monkeypatch):
    """Притвориться собранным exe: только тогда версия реально отключается."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)


def _sign(private, payload: str) -> str:
    raw = private.sign(payload.encode("utf-8"))
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def make_info(private, *, version="1.1.0", released_at=RELEASED, notes=""):
    info = uc.UpdateInfo(
        version=version,
        url="https://example.invalid/SKYHELPER_Setup.exe",
        sha256=hashlib.sha256(b"body").hexdigest(),
        released_at=released_at,
        notes=notes,
    )
    info.sig = _sign(private, info.payload)
    return info


def manifest_json(info) -> bytes:
    from dataclasses import asdict
    return json.dumps(asdict(info), ensure_ascii=False).encode("utf-8")


class _FakeResponse:
    """Минимальный ответ urlopen: read() + context manager."""

    def __init__(self, body: bytes, headers: dict | None = None) -> None:
        self._body = body
        self.headers = {"Content-Length": str(len(body))} if headers is None else headers

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            body, self._body = self._body, b""
            return body
        chunk, self._body = self._body[:size], self._body[size:]
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# --- версии ------------------------------------------------------------------

@pytest.mark.parametrize(("remote", "local", "expected"), [
    ("1.1.0", "1.0.0", True),
    ("1.0.0", "1.1.0", False),
    ("1.0.0", "1.0.0", False),
    ("1.10", "1.9", True),
    ("1.9", "1.10", False),
    ("1.0.0", "1.0", False),
    ("2", "1.9.9", True),
    ("", "1.0.0", False),
    ("1.0.1", "1.0.0", True),
])
def test_is_newer(remote, local, expected):
    assert uc.is_newer(remote, local) is expected


def test_version_constant_has_shape():
    """VERSION существует и похожа на номер — её сверяет обновление."""
    assert VERSION.strip()
    assert VERSION[0].isdigit()


# --- манифест и подпись ------------------------------------------------------

def test_manifest_roundtrip(keypair):
    private, pem = keypair
    info = make_info(private, notes="Что нового: правки")
    from dataclasses import asdict
    parsed = uc.parse_manifest(asdict(info))
    assert parsed.version == "1.1.0"
    assert parsed.notes == "Что нового: правки"
    assert uc.verify_info(parsed, pem=pem)


@pytest.mark.parametrize("damage", [
    {},                                     # ничего нет
    {"version": "", "url": "https://x", "sha256": "a" * 64, "released_at": 1},
    {"version": "1.1.0", "url": "ftp://x", "sha256": "a" * 64, "released_at": 1},
    {"version": "1.1.0", "url": "https://x", "sha256": "нет-хеш", "released_at": 1},
    {"version": "1.1.0", "url": "https://x", "sha256": "a" * 64,
     "released_at": "не-число"},
])
def test_parse_manifest_rejects(damage):
    with pytest.raises(uc.UpdateError):
        uc.parse_manifest(damage)


def test_verify_info_rejects_foreign_key(keypair):
    private, _ = keypair
    other = Ed25519PrivateKey.generate()
    other_pem = other.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    info = make_info(private)
    assert uc.verify_info(info, pem=other_pem) is False


def test_verify_info_rejects_tamper(keypair):
    private, pem = keypair
    info = make_info(private)
    info.url = "https://evil.invalid/SKYHELPER_Setup.exe"   # подписи уже нет на это
    assert uc.verify_info(info, pem=pem) is False


def test_verify_info_rejects_empty_signature():
    info = uc.UpdateInfo("1.1.0", "https://x", "a" * 64, RELEASED)
    assert uc.verify_info(info) is False


# --- загрузка манифеста ------------------------------------------------------

def test_fetch_manifest_ok(keypair, monkeypatch):
    private, pem = keypair
    body = manifest_json(make_info(private))
    monkeypatch.setattr(
        uc.urllib.request, "urlopen",
        lambda request, timeout=None: _FakeResponse(body),
    )
    info = uc.fetch_manifest("https://raw.githubusercontent.com/o/r/main/manifest.json",
                             pem=pem)
    assert info.version == "1.1.0"


def test_fetch_manifest_bad_signature(keypair, monkeypatch):
    _, pem = keypair
    stranger = Ed25519PrivateKey.generate()
    body = manifest_json(make_info(stranger))
    monkeypatch.setattr(
        uc.urllib.request, "urlopen",
        lambda request, timeout=None: _FakeResponse(body),
    )
    with pytest.raises(uc.UpdateError, match="подпись"):
        uc.fetch_manifest("https://example.invalid/manifest.json", pem=pem)


def test_fetch_manifest_not_json(monkeypatch):
    monkeypatch.setattr(
        uc.urllib.request, "urlopen",
        lambda request, timeout=None: _FakeResponse(b"<html>not json</html>"),
    )
    with pytest.raises(uc.UpdateError, match="JSON"):
        uc.fetch_manifest("https://example.invalid/manifest.json")


def test_fetch_manifest_network_error(monkeypatch):
    def boom(request, timeout=None):
        raise OSError("network is unreachable")
    monkeypatch.setattr(uc.urllib.request, "urlopen", boom)
    with pytest.raises(uc.UpdateError, match="нет связи"):
        uc.fetch_manifest("https://example.invalid/manifest.json")


def test_fetch_manifest_without_url():
    with pytest.raises(uc.UpdateError, match="адрес"):
        uc.fetch_manifest("")


# --- сроки -------------------------------------------------------------------

def test_status_within_grace_is_notify(keypair):
    private, _ = keypair
    info = make_info(private)
    now = info.released_at + GRACE - 1
    assert uc.effective_status(info, "1.0.0", now, frozen=True) == "notify"


def test_status_after_grace_is_forced_in_exe(keypair):
    private, _ = keypair
    info = make_info(private)
    now = info.released_at + GRACE + 1
    assert uc.effective_status(info, "1.0.0", now, frozen=True) == "forced"


def test_status_after_grace_stays_notify_in_sources(keypair):
    """В исходниках просрочка только напоминает — не блокирует разработку."""
    private, _ = keypair
    info = make_info(private)
    now = info.released_at + GRACE + 1
    assert uc.effective_status(info, "1.0.0", now, frozen=False) == "notify"


def test_status_none_when_local_is_current(keypair):
    private, _ = keypair
    info = make_info(private, version="1.0.0")
    assert uc.effective_status(info, "1.0.0", RELEASED + GRACE + 1,
                                frozen=True) == "none"
    assert uc.effective_status(None, "1.0.0", RELEASED, frozen=True) == "none"


# --- состояние и анти-откат часов --------------------------------------------

def test_state_roundtrip(state_dir):
    uc.save_state({"last_check": 42})
    assert uc.load_state() == {"last_check": 42}


def test_state_corrupt_file_is_empty(state_dir):
    uc.state_path().write_text("не json {", encoding="utf-8")
    assert uc.load_state() == {}


def test_effective_now_ignores_clock_rollback(state_dir):
    future = RELEASED + 999_999
    assert uc.effective_now({"max_seen": future}, now=1.0) == future
    assert uc.effective_now({}, now=100.0) == 100.0


def test_snooze_moves_into_future(state_dir):
    uc.snooze(now=RELEASED)
    state = uc.load_state()
    assert state["snooze_until"] == RELEASED + INTERVAL
    assert state["max_seen"] == RELEASED


# --- check_for_update --------------------------------------------------------

def _enabled_repo(monkeypatch, repo="owner/repo"):
    monkeypatch.setattr(uc, "UPDATE_REPO", repo)


def test_disabled_without_repo(state_dir, monkeypatch):
    monkeypatch.setattr(uc, "UPDATE_REPO", "")
    assert uc.check_for_update(now=RELEASED) == ("none", None)


def test_first_check_fetches_and_notifies(state_dir, keypair, monkeypatch):
    _enabled_repo(monkeypatch)
    private, _ = keypair
    info = make_info(private)
    calls = []

    def fetch(url):
        calls.append(url)
        return info

    status, got = uc.check_for_update(now=RELEASED, fetch=fetch,
                                      local_version="1.0.0")
    assert status == "notify"
    assert got.version == "1.1.0"
    assert calls and calls[0].startswith("https://raw.githubusercontent.com/")
    # состояние запомнило и манифест, и время проверки
    state = uc.load_state()
    assert state["manifest"]["version"] == "1.1.0"
    assert state["last_check"] == RELEASED


def test_up_to_date_is_silent(state_dir, keypair, monkeypatch):
    _enabled_repo(monkeypatch)
    private, _ = keypair
    info = make_info(private, version="1.0.0")
    status, got = uc.check_for_update(now=RELEASED, fetch=lambda url: info,
                                      local_version="1.0.0")
    assert status == "none" and got is None
    assert uc.load_state()["manifest"]["version"] == "1.0.0"   # «мы свежие» тоже помним


def test_second_check_within_interval_skips_network(state_dir, keypair, monkeypatch):
    _enabled_repo(monkeypatch)
    private, _ = keypair
    info = make_info(private)
    uc.check_for_update(now=RELEASED, fetch=lambda url: info,
                        local_version="1.0.0")
    calls = []

    def fetch(url):
        calls.append(url)
        return info

    status, _ = uc.check_for_update(now=RELEASED + INTERVAL - 1, fetch=fetch,
                                    local_version="1.0.0")
    assert not calls, "внутри интервала сеть не трогаем"
    assert status == "notify"           # но напоминаем по сохранённому манифесту


def test_forced_without_network(state_dir, keypair, monkeypatch, frozen_on):
    """Срок прошёл: отключение действует даже без связи."""
    _enabled_repo(monkeypatch)
    private, _ = keypair
    info = make_info(private)
    uc.check_for_update(now=RELEASED, fetch=lambda url: info,
                        local_version="1.0.0")

    def no_net(url):
        raise AssertionError("сеть не должна понадобиться")

    status, got = uc.check_for_update(now=RELEASED + GRACE + 10, fetch=no_net,
                                      local_version="1.0.0")
    assert status == "forced"
    assert got.version == "1.1.0"


def test_forced_survives_clock_rollback(state_dir, keypair, monkeypatch, frozen_on):
    """Откат часов не возвращает отключённую версию в строй."""
    _enabled_repo(monkeypatch)
    private, _ = keypair
    info = make_info(private)
    uc.check_for_update(now=RELEASED + GRACE + 10, fetch=lambda url: info,
                        local_version="1.0.0")   # уже forced, max_seen в будущем
    # часы откатили «назад» — до срока граничного
    status, _ = uc.check_for_update(now=RELEASED + 60, fetch=lambda url: info,
                                    local_version="1.0.0")
    assert status == "forced"


def test_network_failure_falls_back_to_stored(state_dir, keypair, monkeypatch):
    _enabled_repo(monkeypatch)
    private, _ = keypair
    info = make_info(private)
    uc.check_for_update(now=RELEASED, fetch=lambda url: info,
                        local_version="1.0.0")

    def down(url):
        raise uc.UpdateError("нет связи")

    status, got = uc.check_for_update(now=RELEASED + INTERVAL + 1, fetch=down,
                                      local_version="1.0.0")
    assert status == "notify"           # сеть легла — работаем по памяти
    assert got.version == "1.1.0"


def test_network_failure_first_time_is_silent(state_dir, monkeypatch):
    _enabled_repo(monkeypatch)

    def down(url):
        raise uc.UpdateError("нет связи")

    status, got = uc.check_for_update(now=RELEASED, fetch=down,
                                      local_version="1.0.0")
    assert status == "none" and got is None


def test_tampered_state_manifest_is_ignored(state_dir, keypair, monkeypatch,
                                             frozen_on):
    """Файл состояния правили руками: без верной подписи ему не верим."""
    _enabled_repo(monkeypatch)
    private, _ = keypair
    info = make_info(private, released_at=RELEASED - GRACE * 2)  # «просрочен»
    uc.check_for_update(now=RELEASED, fetch=lambda url: info,
                        local_version="1.0.0")

    def down(url):
        raise uc.UpdateError("нет связи")

    # подменяем сохранённый манифест: подписи нет (или чужая)
    state = uc.load_state()
    state["manifest"]["sig"] = "чужая-подпись"
    uc.save_state(state)
    status, got = uc.check_for_update(now=RELEASED + GRACE + 5, fetch=down,
                                      local_version="1.0.0")
    assert status == "none" and got is None, (
        "подделанный манифест не должен ни отключать версию, ни давать ссылку"
    )


def test_snoozed_update_is_silent(state_dir, keypair, monkeypatch):
    _enabled_repo(monkeypatch)
    private, _ = keypair
    info = make_info(private)
    uc.check_for_update(now=RELEASED, fetch=lambda url: info,
                        local_version="1.0.0")
    uc.snooze(now=RELEASED)
    status, _ = uc.check_for_update(now=RELEASED + 60, fetch=lambda url: info,
                                    local_version="1.0.0")
    assert status == "none", "после «напомнить позже» окно не показываем"
    # а после интервала — показываем снова
    status, _ = uc.check_for_update(now=RELEASED + INTERVAL + 60,
                                    fetch=lambda url: info,
                                    local_version="1.0.0")
    assert status == "notify"


def test_snooze_does_not_protect_expired(state_dir, keypair, monkeypatch, frozen_on):
    """Отложенное уведомление не отменяет отключение по сроку."""
    _enabled_repo(monkeypatch)
    private, _ = keypair
    info = make_info(private)
    uc.check_for_update(now=RELEASED, fetch=lambda url: info,
                        local_version="1.0.0")
    uc.snooze(now=RELEASED)
    status, _ = uc.check_for_update(now=RELEASED + GRACE + 5,
                                    fetch=lambda url: info,
                                    local_version="1.0.0")
    assert status == "forced"


# --- загрузка установщика ----------------------------------------------------

def test_download_ok(tmp_path, keypair, monkeypatch):
    private, _ = keypair
    body = b"MZ-" + b"x" * 100
    info = make_info(private)
    info.sha256 = hashlib.sha256(body).hexdigest()
    info.sig = _sign(private, info.payload)
    monkeypatch.setattr(
        uc.urllib.request, "urlopen",
        lambda request, timeout=None: _FakeResponse(body),
    )
    seen = []
    dest = tmp_path / "setup.exe"
    path = uc.download_update(info, dest,
                              progress=lambda done, total: seen.append((done, total)))
    assert path == dest and dest.read_bytes() == body
    assert seen and seen[-1][0] == len(body)


def test_download_hash_mismatch_leaves_nothing(tmp_path, keypair, monkeypatch):
    private, _ = keypair
    info = make_info(private)          # sha256 под «body», придёт другое
    monkeypatch.setattr(
        uc.urllib.request, "urlopen",
        lambda request, timeout=None: _FakeResponse(b"tampered file"),
    )
    dest = tmp_path / "setup.exe"
    with pytest.raises(uc.UpdateError, match="SHA-256"):
        uc.download_update(info, dest)
    assert not dest.exists()
    assert not dest.with_suffix(dest.suffix + ".part").exists()


def test_download_network_error(tmp_path, keypair, monkeypatch):
    private, _ = keypair
    info = make_info(private)

    def boom(request, timeout=None):
        raise OSError("connection reset")
    monkeypatch.setattr(uc.urllib.request, "urlopen", boom)
    with pytest.raises(uc.UpdateError, match="скачать"):
        uc.download_update(info, tmp_path / "setup.exe")


# --- запуск установщика ------------------------------------------------------

def test_install_update_requires_installer(tmp_path):
    with pytest.raises(uc.UpdateError, match="не найден"):
        uc.install_update(tmp_path / "нет.exe")


def test_install_update_spawns_waiting_cmd(tmp_path, monkeypatch):
    installer = tmp_path / "SKYHELPER_Setup.exe"
    installer.write_bytes(b"MZ")
    target = tmp_path / "new.exe"
    target.write_bytes(b"MZ")
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(uc.subprocess, "Popen", fake_popen)
    uc.install_update(installer, target=target)
    command = captured["args"]
    # строкой, не списком: cmd.exe не понимает \" — такие list2cmdline
    assert isinstance(command, str)
    assert command.startswith('cmd.exe /c ""') and command.endswith('""')
    assert str(installer) in command and "/VERYSILENT" in command
    assert str(target) in command and "ping -n" in command   # ждём выхода старой копии
    assert captured["kwargs"].get("creationflags"), "процесс должен быть отвязан"
    assert captured["kwargs"].get("cwd")


def test_install_update_strips_pyi_env_and_hides_cmd(tmp_path, monkeypatch):
    """Окружение цепочки без _PYI_* (иначе новая копия падает с PID not
    found), окно cmd спрятано CREATE_NO_WINDOW."""
    installer = tmp_path / "SKYHELPER_Setup.exe"
    installer.write_bytes(b"MZ")
    target = tmp_path / "new.exe"
    target.write_bytes(b"MZ")
    captured = {}

    def fake_popen(args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(uc.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("_PYI_PARENT_PROCESS_LEVEL", "2")
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", r"C:\Temp\_MEI0000dead")
    monkeypatch.setenv("_PYI_ARCHIVE_FILE", r"C:\app\self.exe")
    uc.install_update(installer, target=target)

    env = captured["env"]
    pyi_keys = [k for k in env if k.startswith("_PYI")]
    assert pyi_keys == [], f"_PYI_* не должны наследоваться: {pyi_keys}"
    assert env.get("PATH"), "остальное окружение сохраняется"
    CREATE_NO_WINDOW = getattr(uc.subprocess, "CREATE_NO_WINDOW", 0x08000000)
    NEW_GROUP = getattr(uc.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    DETACHED = getattr(uc.subprocess, "DETACHED_PROCESS", 0x00000008)
    assert captured["creationflags"] & CREATE_NO_WINDOW, "окно cmd должно быть спрятано"
    assert not captured["creationflags"] & DETACHED, (
        "DETACHED_PROCESS лишает cmd консоли — и консольный ping в цепочке "
        "создаёт новую видимую консоль (окно Терминала, «CMDшка» при обнове)"
    )
    assert captured["creationflags"] == (NEW_GROUP | CREATE_NO_WINDOW), (
        "флаги цепочки только эти два: невидимая консоль, которой делятся дети"
    )


@pytest.mark.skipif(sys.platform != "win32", reason="ловля окон консоли — только Windows")
def test_update_chain_opens_no_console_window(tmp_path, monkeypatch):
    """Живая проверка: цепочка обновления не показывает окон консоли.

    Форма цепочки — как у install_update (GUI-«установщик» & ping & start
    «новой копии»), флаги — ровно те, что install_update выставляет (их же
    проверяет тест выше). DETACHED_PROCESS раньше давал 2 видимых окна
    (Windows Terminal + PseudoConsole) — см. эпизод 03 отчёта об автообновлении.
    """
    import subprocess as sp
    import time as _time

    pyw = Path(sys.executable).with_name("pythonw.exe")
    if not pyw.exists():
        pytest.skip("нет pythonw.exe")
    (tmp_path / "a.pyw").write_text("import time\ntime.sleep(1)\n", encoding="utf-8")
    (tmp_path / "b.pyw").write_text("import time\ntime.sleep(0.2)\n", encoding="utf-8")
    chain = (
        f'""{pyw}" "{tmp_path / "a.pyw"}"'
        f' & ping -n 2 127.0.0.1 >nul'
        f' & start "" "{pyw}" "{tmp_path / "b.pyw"}""'
    )
    flags = (0x00000200 | 0x08000000)  # CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW

    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    enum = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    classes = {
        "ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "PseudoConsoleWindow",
    }

    def consoles():
        """HWND видимых окон консольного семейства."""
        found = []

        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, buf, 256)
                if buf.value in classes:
                    found.append(int(hwnd))
            return True

        user32.EnumWindows(enum(cb), 0)
        return found

    _time.sleep(0.2)
    base = set(consoles())                   # что открыто в покое — не наше
    fresh: set = set()
    proc = sp.Popen(
        f"cmd.exe /c {chain}",
        cwd=str(tmp_path),
        creationflags=flags,
        close_fds=True,
    )
    deadline = _time.time() + 8
    while _time.time() < deadline:
        fresh.update(h for h in consoles() if h not in base)
        if proc.poll() is not None and _time.time() > deadline - 3:
            break
        _time.sleep(0.02)
    _time.sleep(1.2)
    fresh.update(h for h in consoles() if h not in base)
    assert not fresh, (
        f"цепочка открыла {len(fresh)} новых окон консоли (hwnd={sorted(fresh)}) "
        "(проверь DETACHED_PROCESS/консольных детей в install_update)"
    )


def test_installed_exe_path_has_program_folder():
    path = uc.installed_exe_path()
    assert path.name == "SKYHELPER.exe"
    assert "SKY HELPER" in str(path)


# --- manifest_url ------------------------------------------------------------

def test_manifest_url(monkeypatch):
    monkeypatch.setattr(uc, "UPDATE_REPO", "")
    assert uc.manifest_url() == ""
    monkeypatch.setattr(uc, "UPDATE_REPO", "owner/repo")
    assert uc.manifest_url() == (
        "https://raw.githubusercontent.com/owner/repo/main/manifest.json"
    )
