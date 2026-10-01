# -*- coding: utf-8 -*-
"""tools/make_release.py: манифест, который клиент действительно примет.

Главная проверка здесь — «форматная»: подпись релизного инструмента
должна сходиться с проверкой клиента (:func:`app.update_check.verify_info`).
Приватный ключ в тесте генерируется — ~/.rmrp_signing_key.pem не нужен.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import update_check as uc
from tools import make_release as mr


@pytest.fixture
def test_key(monkeypatch):
    """Свой ключ на время теста вместо ~/.rmrp_signing_key.pem."""
    private = Ed25519PrivateKey.generate()
    pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    monkeypatch.setattr(mr.lic, "load_private_key", lambda path=None: private)
    return pem


def test_manifest_is_accepted_by_client(test_key):
    """Подпись релизного инструмента проходит проверку клиента."""
    sha = hashlib.sha256(b"installer").hexdigest()
    url = mr.installer_url("owner/repo", "1.2.3")
    manifest = mr.build_manifest("1.2.3", url, sha, 1_800_000_000, "Что нового")
    info = uc.parse_manifest(manifest)
    assert info.version == "1.2.3"
    assert info.url == url
    assert info.payload == f"1.2.3|{url}|{sha}|1800000000"
    assert uc.verify_info(info, pem=test_key) is True


def test_manifest_tamper_breaks_signature(test_key):
    sha = hashlib.sha256(b"installer").hexdigest()
    manifest = mr.build_manifest(
        "1.2.3", mr.installer_url("owner/repo", "1.2.3"), sha,
        1_800_000_000, "",
    )
    manifest["url"] = "https://evil.invalid/SKYHELPER_Setup.exe"
    info = uc.parse_manifest(manifest)
    assert uc.verify_info(info, pem=test_key) is False


def test_installer_url_shape():
    url = mr.installer_url("skyhelper-releases", "1.4.0")
    assert url == (
        "https://github.com/skyhelper-releases/releases/download/"
        "v1.4.0/SKYHELPER_Setup.exe"
    )


def test_version_regex():
    assert mr.VERSION_RE.fullmatch("1.2.3")
    assert mr.VERSION_RE.fullmatch("10.0")
    assert not mr.VERSION_RE.fullmatch("1.2.3-rc1")
    assert not mr.VERSION_RE.fullmatch("вторая")


def test_set_version_edits_only_version(tmp_path, monkeypatch):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    init = app_dir / "__init__.py"
    init.write_text('# -*- coding: utf-8 -*-\n"""док."""\n\nVERSION = "1.0.0"\n',
                    encoding="utf-8")
    monkeypatch.setattr(mr, "ROOT", tmp_path)
    mr.set_version("2.5.1")
    text = init.read_text(encoding="utf-8")
    assert 'VERSION = "2.5.1"' in text
    assert '"""док."""' in text, "остальной файл не тронут"


def test_set_repo_edits_only_repo(tmp_path, monkeypatch):
    module = tmp_path / "app" / "update_check.py"
    module.parent.mkdir()
    module.write_text("константы до\n\nUPDATE_REPO = \"\"\n\nпосле\n",
                      encoding="utf-8")
    monkeypatch.setattr(mr, "ROOT", tmp_path)
    mr.set_repo("owner/repo")
    text = module.read_text(encoding="utf-8")
    assert 'UPDATE_REPO = "owner/repo"' in text
    assert "константы до" in text and "после" in text


def test_set_installer_version_edits_only_version(tmp_path, monkeypatch):
    """Версия в установщике синхронизируется с релизом (раньше она была
    статичной «1.0.0» — и в мастере, и в свойствах файла, и в «Приложениях»)."""
    iss_dir = tmp_path / "installer"
    iss_dir.mkdir()
    iss = iss_dir / "SKYHELPER.iss"
    iss.write_text(
        '; шапка\n#define MyAppName "X"\n#define MyAppVersion "1.0.0"\n'
        "[Setup]\nPrivilegesRequired=lowest\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mr, "ROOT", tmp_path)
    mr.set_installer_version("3.4.5")
    text = iss.read_text(encoding="utf-8")
    assert '#define MyAppVersion "3.4.5"' in text
    assert "#define MyAppName" in text, "остальной файл не тронут"
    assert "[Setup]" in text


def test_manifest_json_is_utf8_readable(tmp_path):
    """Готовый файл манифеста должен быть обычным JSON (витрина лежит в git)."""
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {"version": "1.0", "notes": "по-русски"}, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert data["notes"] == "по-русски"
