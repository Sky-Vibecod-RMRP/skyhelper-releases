# -*- coding: utf-8 -*-
"""Сборка релиза: версия, установщик, подписанный манифест обновлений.

Использование::

    python tools/make_release.py 1.1.0 --notes "Что нового: ..."
        [--repo OWNER/REPO] [--skip-tests] [--skip-exe] [--skip-installer]

Что делает:
  1. вписывает версию в ``app/__init__.py`` (VERSION) и в
     ``installer/SKYHELPER.iss`` (MyAppVersion) — их сверяют клиенты
     и показывает установщик;
  2. при ``--repo`` ещё и обновляет ``UPDATE_REPO`` в ``app/update_check.py``
     (адрес манифеста; нужно один раз, потом значение живёт в коде);
  3. гоняет pytest (отключается ``--skip-tests``);
  4. собирает ``dist\\SKYHELPER.exe`` (PyInstaller, ``--skip-exe``);
  5. собирает ``dist\\SKYHELPER_Setup.exe`` (Inno Setup, ``--skip-installer``);
  6. считает SHA-256 установщика, подписывает строку
     ``version|url|sha256|released_at`` приватным ключом
     (``~\\.rmrp_signing_key.pem``, тот же, что у лицензий);
  7. пишет ``release\\manifest.json`` и печатает чек-лист выкладки.

Витрина — отдельная папка с публичным репозиторием БЕЗ исходников:
туда кладётся manifest.json, а установщик идёт asset'ом GitHub Release.
Клиенты читают манифест напрямую с raw.githubusercontent.com (без API
и его лимитов), установщик качают с releases/download — оба адреса
подписаны внутри манифеста.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import license as lic  # noqa: E402
from app import update_check as uc  # noqa: E402

VERSION_RE = re.compile(r"^\d+(\.\d+)*$")
ISCC_CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
]


def die(message: str) -> None:
    print(f"ОШИБКА: {message}", file=sys.stderr)
    raise SystemExit(1)


def set_version(version: str) -> None:
    """Вписать версию в app/__init__.py, не трогая больше ничего."""
    path = ROOT / "app" / "__init__.py"
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'^VERSION = "[^"]*"$',
        f'VERSION = "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        die("в app/__init__.py не найдена строка VERSION = \"...\"")
    path.write_text(updated, encoding="utf-8")
    print(f"VERSION = {version}  (app/__init__.py)")


def set_installer_version(version: str) -> None:
    """Вписать версию в installer/SKYHELPER.iss (#define MyAppVersion).

    Без этого установщик всем показывал статичные «1.0.0»: и в заголовке
    мастера, и в свойствах файла, и в списке «Приложения» Windows.
    """
    path = ROOT / "installer" / "SKYHELPER.iss"
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'^#define MyAppVersion "[^"]*"$',
        f'#define MyAppVersion "{version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        die('в installer/SKYHELPER.iss не найдена строка #define MyAppVersion "..."')
    path.write_text(updated, encoding="utf-8")
    print(f"MyAppVersion = {version}  (installer/SKYHELPER.iss)")


def set_repo(repo: str) -> None:
    """Вписать адрес репозитория-витрины в app/update_check.py."""
    path = ROOT / "app" / "update_check.py"
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'^UPDATE_REPO = "[^"]*"$',
        f'UPDATE_REPO = "{repo}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        die("в app/update_check.py не найдена строка UPDATE_REPO = \"...\"")
    path.write_text(updated, encoding="utf-8")
    uc.UPDATE_REPO = repo
    print(f"UPDATE_REPO = {repo}  (app/update_check.py)")


def run(cmd: list[str], *, label: str) -> None:
    print(f"--- {label}")
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        die(f"{label}: код {result.returncode}")


def run_tests() -> None:
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"],
        cwd=ROOT, env=env,
    )
    if result.returncode != 0:
        die("тесты не прошли — релиз остановлен")


def find_iscc() -> Path:
    for candidate in ISCC_CANDIDATES:
        if candidate.is_file():
            return candidate
    die("Inno Setup 6 не найден: winget install -e --id JRSoftware.InnoSetup")
    raise AssertionError  # die не возвращается


def installer_url(repo: str, version: str) -> str:
    return f"https://github.com/{repo}/releases/download/v{version}/SKYHELPER_Setup.exe"


def build_manifest(version: str, url: str, sha256: str, released_at: int,
                   notes: str) -> dict:
    """Манифест с подписью — ровно та строка, что сверяет клиент.

    Подпись «сырая» (как её проверяет
    :func:`app.update_check.verify_info`), НЕ в формате ключа активации:
    там payload встроен в саму строку ключа, а здесь поля манифеста
    лежат открыто и подпись — отдельно.
    """
    payload = "|".join((version, url, sha256, str(released_at)))
    private_key = lic.load_private_key()
    signature = private_key.sign(payload.encode("utf-8"))
    return {
        "version": version,
        "url": url,
        "sha256": sha256,
        "released_at": released_at,
        "notes": notes,
        "sig": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Сборка релиза SKY HELPER")
    parser.add_argument("version", help="новая версия, например 1.1.0")
    parser.add_argument("--notes", default="", help="что нового (видно в окне)")
    parser.add_argument("--repo", default=None,
                        help="OWNER/REPO репозитория-витрины "
                             "(по умолчанию — из app/update_check.py)")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-exe", action="store_true",
                        help="exe уже собран")
    parser.add_argument("--skip-installer", action="store_true",
                        help="установщик уже собран")
    args = parser.parse_args()

    if not VERSION_RE.fullmatch(args.version):
        die(f"версия «{args.version}» не похожа на номер (нужно 1.2.3)")
    repo = args.repo or uc.UPDATE_REPO
    if args.repo:
        set_repo(args.repo)
    elif not repo:
        die("репозиторий не задан: --repo OWNER/REPO "
            "(нужен один раз — он впишется в app/update_check.py)")

    set_version(args.version)
    set_installer_version(args.version)

    if not args.skip_tests:
        run_tests()
    if not args.skip_exe:
        run([sys.executable, "-m", "PyInstaller",
             "--noconfirm", "--clean", "SKYHELPER.spec"],
            label="сборка exe")
    if not args.skip_installer:
        run([str(find_iscc()), str(ROOT / "installer" / "SKYHELPER.iss")],
            label="сборка установщика")

    installer = ROOT / "dist" / "SKYHELPER_Setup.exe"
    if not installer.is_file():
        die(f"нет установщика: {installer}")
    sha = hashlib.sha256(installer.read_bytes()).hexdigest()
    url = installer_url(repo, args.version)
    released_at = int(time.time())
    manifest = build_manifest(args.version, url, sha, released_at, args.notes)

    out_dir = ROOT / "release"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "manifest.json"
    out_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print()
    print(f"ГОТОВО: релиз {args.version} собран и подписан.")
    print(f"  установщик: {installer}  ({installer.stat().st_size} байт)")
    print(f"  sha256:     {sha}")
    print(f"  манифест:   {out_path}")
    print()
    print("Чек-лист выкладки (витрина = отдельная папка с публичным репозиторием):")
    print(f"  1. скопируй manifest.json в папку витрины и сделай push:")
    print(f"       git -C <витрина> add manifest.json")
    print(f"       git -C <витрина> commit -m \"manifest {args.version}\"")
    print(f"       git -C <витрина> push")
    print(f"  2. GitHub → Releases → New release:")
    print(f"       tag: v{args.version}, title: {args.version}")
    print(f"       asset: dist\\SKYHELPER_Setup.exe")
    print(f"  3. клиенты читают манифест по")
    print(f"       {uc.manifest_url()}")
    print(f"     и качают установщик по")
    print(f"       {url}")


if __name__ == "__main__":
    main()
