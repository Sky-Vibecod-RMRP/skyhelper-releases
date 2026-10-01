# -*- coding: utf-8 -*-
"""Выдача и отзыв ключей активации — инструмент администратора проекта.

Всё делается **вручную** (решение 01.10.2026): пользователь присылает
код своего ПК, администратор генерирует ключ и присылает его обрату.
Исходники при этом остаются у администратора — наружу уходит только exe.

Команды (запускать из папки проекта):

    python tools/gen_key.py init
        Создать пару ключей. Приватный — в ~/.rmrp_signing_key.pem
        (в архив НЕ попадает, нужен бэкап на флешке!), публичный —
        в app/license_public.py. Повторный init обнуляет все старые ключи.

    python tools/gen_key.py key --hwid "RM-7F3A-9K2D-4M1P-8ZR7" --days 30 \
            --who "Nick"
        Выдать ключ на 30 дней под конкретный ПК. Ключ печатается в
        консоль (его копируют в чат) и по желанию пишется в файл --out.

    python tools/gen_key.py key --this-pc --days 365
        Выдать ключ под ЭТОТ компьютер (удобно для собственной машины).

    python tools/gen_key.py revoke --add ABCD-EFGH
        Отозвать ключ: дописать key_id в рабочий список, переподписать
        файл и напечатать содержимое для gist-записи.

    python tools/gen_key.py revoke --show
        Показать текущий подписанный список (что лежит в gist).

    python tools/gen_key.py show --key "..."
        Проверить ключ, не запуская программу: раскодировать, показать
        ПК, срок и метку, сверить подпись.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import serialization            # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (     # noqa: E402
    Ed25519PrivateKey,
)

from app import hwid as hwid_mod                                    # noqa: E402
from app import license as lic                                      # noqa: E402

PUBLIC_MODULE = Path(__file__).resolve().parent.parent / "app" / "license_public.py"
#: Рабочий список отозванных key_id (простой JSON, у администратора дома).
REVOKED_WORK = Path.home() / ".rmrp_revoked_kids.json"
#: Готовый подписанный файл — его содержимое публикуется в gist.
REVOKED_SIGNED = Path.home() / ".rmrp_revoked_gist.json"


def _die(message: str) -> None:
    print(f"ОШИБКА: {message}")
    raise SystemExit(1)


def _private_key() -> Ed25519PrivateKey:
    try:
        return lic.load_private_key()
    except lic.LicenseError as exc:
        _die(f"{exc.message}\nСначала выполните: python tools/gen_key.py init")


def cmd_init(args: argparse.Namespace) -> None:
    """Создать пару ключей: приватный дома, публичный — в проект."""
    if lic.default_private_key_path().exists() and not args.force:
        _die(
            "Приватный ключ уже существует: "
            f"{lic.default_private_key_path()}\n"
            "Повторный init обнулит ВСЕ ранее выданные ключи. Если это "
            "действительно нужно — запустите с ключом --force."
        )
    key = Ed25519PrivateKey.generate()
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    target = lic.default_private_key_path()
    target.write_bytes(private_pem)
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass

    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    PUBLIC_MODULE.write_text(
        "# -*- coding: utf-8 -*-\n"
        '"""Публичный ключ подписи лицензий (Ed25519) — сгенерирован '
        'tools/gen_key.py init.\n\n'
        "Сюда попадает только публичная часть пары; приватный ключ живёт в "
        "~/.rmrp_signing_key.pem и в репозиторий/архив не входит.\n"
        '"""\n\n'
        f"PUBLIC_KEY_PEM = \"\"\"{public_pem.strip()}\"\"\"\n",
        encoding="utf-8",
    )
    print("Создано:")
    print(f"  приватный ключ : {target}  (сделайте бэкап, без него "
          "старые ключи не перевыпустить)")
    print(f"  публичный ключ : {PUBLIC_MODULE}")
    print("Теперь пересоберите exe — иначе он никого не пустит "
          "(no_public_key).")


def cmd_key(args: argparse.Namespace) -> None:
    """Выдать ключ под указанный (или этот) ПК."""
    if args.this_pc:
        try:
            code = hwid_mod.current()
        except hwid_mod.HwidError as exc:
            _die(str(exc))
    else:
        if not args.hwid:
            _die("Укажите --hwid \"RM-XXXX-...\" или --this-pc")
        code = hwid_mod.canonical(args.hwid)
        if not code:
            _die("Код ПК пустой — проверьте, что скопирован целиком")

    issued = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)
    expires = (_dt.date.today() + _dt.timedelta(days=args.days))
    payload = lic.build_payload(
        code, issued.strftime("%Y-%m-%dT%H:%M:%SZ"), expires, args.who or "",
    )
    key_text = lic.sign_payload(payload, _private_key())
    kid = lic.key_id(payload)

    if args.out:
        Path(args.out).write_text(key_text + "\n", encoding="utf-8")
        print(f"Ключ записан: {args.out}")
    print()
    print(f"  ПК      : {code}")
    print(f"  ID ключа: {kid}")
    print(f"  Действует до: {expires.strftime('%d.%m.%Y')} "
          f"({args.days} дн.)")
    if args.who:
        print(f"  Выдан   : {args.who}")
    print()
    print("Ключ для пользователя (копировать одной строкой):")
    print()
    print(key_text)


def _load_revoked() -> list[str]:
    if not REVOKED_WORK.exists():
        return []
    try:
        data = json.loads(REVOKED_WORK.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _die(f"Рабочий список повреждён: {REVOKED_WORK}")
    return [str(kid).strip().upper() for kid in data if str(kid).strip()]


def _kid(raw: str) -> str:
    """Привести скопированный key_id к виду ``ABCD-EFGH``."""
    bare = hwid_mod.normalize(raw)
    return f"{bare[:4]}-{bare[4:]}" if len(bare) == 8 else bare


def _has(kids: list[str], kid: str) -> bool:
    target = hwid_mod.normalize(kid)
    return any(hwid_mod.normalize(item) == target for item in kids)


def cmd_revoke(args: argparse.Namespace) -> None:
    """Добавить/убрать key_id в списке отзывов и переподписать файл."""
    kids = _load_revoked()
    if args.add:
        for raw in args.add.split(","):
            kid = _kid(raw)
            if not kid:
                continue
            if _has(kids, kid):
                print(f"уже в списке: {kid}")
            else:
                kids.append(kid)
                print(f"добавлен: {kid}")
    if args.remove:
        for raw in args.remove.split(","):
            target = hwid_mod.normalize(raw)
            before = len(kids)
            kids = [k for k in kids if hwid_mod.normalize(k) != target]
            print(("убран" if len(kids) < before else "не найден") + f": {target}")
    REVOKED_WORK.write_text(
        json.dumps(sorted(kids), ensure_ascii=False, indent=1), encoding="utf-8",
    )
    signed = lic.sign_revocations(kids, private_key=_private_key())
    REVOKED_SIGNED.write_text(signed + "\n", encoding="utf-8")
    print()
    print(f"В списке {len(kids)} ключ(ей). Готовый файл для gist:")
    print(f"  {REVOKED_SIGNED}")
    if args.print or not (args.add or args.remove):
        print()
        print(signed)


def cmd_show(args: argparse.Namespace) -> None:
    """Раскодировать ключ: подпись, ПК, срок, метка."""
    payload, kid = lic.parse_and_verify(args.key)
    parts = payload.split("|")
    license_obj = lic.verify(args.key)
    print(f"  ID ключа : {kid}")
    print(f"  ПК       : {license_obj.hwid}")
    print(f"  Выдан    : {license_obj.issued}")
    print(f"  Действует до: {license_obj.expires.strftime('%d.%m.%Y')}"
          + ("  (ИСТЁК)" if license_obj.expires < _dt.date.today() else ""))
    if license_obj.who:
        print(f"  Выдан    : {license_obj.who}")
    print(f"  Поле v   : {parts[0]}")
    print("  Подпись  : проходит")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Выдача и отзыв ключей активации SKY HELPER",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="создать пару ключей")
    p_init.add_argument("--force", action="store_true",
                        help="перезаписать существующий приватный ключ")
    p_init.set_defaults(func=cmd_init)

    p_key = sub.add_parser("key", help="выдать ключ")
    p_key.add_argument("--hwid", help="код ПК пользователя")
    p_key.add_argument("--this-pc", action="store_true",
                       help="выдать ключ под этот компьютер")
    p_key.add_argument("--days", type=int, default=30,
                       help="срок действия в днях (по умолчанию 30)")
    p_key.add_argument("--who", default="", help="метка: кому выдан (ник)")
    p_key.add_argument("--out", help="дополнительно записать ключ в файл")
    p_key.set_defaults(func=cmd_key)

    p_rev = sub.add_parser("revoke", help="список отзывов для gist")
    p_rev.add_argument("--add", help="id через запятую")
    p_rev.add_argument("--remove", help="id через запятую")
    p_rev.add_argument("--print", action="store_true",
                       help="напечатать подписанный файл")
    p_rev.set_defaults(func=cmd_revoke)

    p_show = sub.add_parser("show", help="проверить ключ")
    p_show.add_argument("--key", required=True, help="строка ключа")
    p_show.set_defaults(func=cmd_show)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
