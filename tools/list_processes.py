"""Показывает имена запущенных процессов, чтобы найти процесс игры.

  python tools/list_processes.py            - все процессы
  python tools/list_processes.py gta rage   - только с 'gta' или 'rage' в имени
"""
import sys

import psutil


def main() -> None:
    filters = [a.lower() for a in sys.argv[1:]]
    names = set()
    for proc in psutil.process_iter(["name"]):
        name = proc.info.get("name")
        if name:
            names.add(name)
    for name in sorted(names, key=str.lower):
        if not filters or any(f in name.lower() for f in filters):
            print(name)


if __name__ == "__main__":
    main()
