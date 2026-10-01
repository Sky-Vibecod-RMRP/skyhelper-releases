"""Общие данные хелпера: разделы инструкций и список правил RMRP.

Один источник контента для двух мест:

* окно «Хелпер» в программе (PySide6, QTextBrowser);
* вкладки «Хелпер» и «Правила RMRP» на сайте sky-grafana.rmrp.

HTML здесь переносимый: инлайновые стили и теги, которые понимают и браузер,
и QTextDocument (``<p>``, ``<ul>``, ``<ol>``, ``<table>``, ``<a>``, ``<b>``,
``<code>``, ``<span>``). Палитра передаётся снаружи, поэтому хелпер выглядит
правильно и на сайте, и в любой теме программы.

Текст разделов — из ``Sky-Helper.md``. Правила — только реальные ссылки на
форум RMRP (прислал пользователь), ничего не сочиняется. Список правил можно
поправить без пересборки: файл ``%APPDATA%\\SKYHELPER\\rules.json``
в том же виде, что :data:`RULES`, заменяет встроенный список целиком.

Поиск идёт не только по названию, но и по **тексту правила** (снимок первых
сообщений тем лежит в :mod:`app.help.rules_text`): запрос «60 минут» находит
«Правила допросов», «не должен длиться» — тоже. Результаты ранжируются —
сначала совпадения в названии, потом в синонимах, потом в тексте, — и у каждого
показывается фрагмент текста с подсветкой.
"""
from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Iterable, Sequence

from app.paths import APP_NAME

from app.help.rules_text import RULE_TEXTS

#: Палитра по умолчанию — ровно те цвета, что на сайте (стиль MIDNIGHT).
PALETTE: dict[str, str] = {
    "bg": "#0b0c0e",
    "card": "#141519",
    "border": "#24262b",
    "text": "#edeef1",
    "muted": "#8a8c94",
    "accent": "#4ec3f0",
    "ok": "#3ddc97",
    "warn": "#ffb547",
    "danger": "#ff6b81",
}

#: Токен в тексте: подставляется папка с отчётами (или запасная подпись).
OUTPUT_DIR_TOKEN = "{{output_dir}}"
OUTPUT_DIR_FALLBACK = "папка из настроек (Настройки → Экспорт)"


# --- маленькие помощники ---------------------------------------------------


def esc(value: object) -> str:
    """Экранировать как содержимое тега."""
    return html.escape(str(value), quote=True)


def normalize(text: object) -> str:
    """Нормальность для поиска: нижний регистр, ё → е."""
    return str(text).lower().replace("ё", "е")


def stem(word: str) -> str:
    """Основа слова для поиска по русским словоформам.

    «война» и «войны» — разные строки, но общая основа ``вой``: поэтому
    от слова длиннее трёх букв берём первые три. Иначе запрос «семьи»
    не найдёт «Правила семей».
    """
    return word if len(word) <= 3 else word[:3]


#: Слова, из-за которых поиск впустую. «как наказать за спавн» должен
#: находить «спавн», а не требовать ещё и «как», и «за». Если запрос состоит
#: только из них — не выкидываем, а ищем как есть.
STOP_WORDS = {
    "не", "и", "в", "во", "на", "с", "со", "по", "за", "от", "до", "из",
    "как", "что", "для", "это", "то", "же", "а", "но", "у", "о", "об",
    "их", "его", "мне", "можно", "нужно", "быть", "если", "или", "там",
    "при", "над", "под", "про", "все", "всё", "уже", "ещё", "еще", "бы",
    "же", "ли", "бы", "ну", "да", "нет", "раз", "два", "три", "нет",
}


def query_stems(query: object) -> list[str]:
    """Основы всех слов запроса (пустой запрос → пустой список).

    Служебные слова выбрасываем: из-за них запрос вроде «сколько минут
    длится допрос» не находил ничего — требовалось найти ещё и «сколько».
    """
    words = [w for w in normalize(query).split() if w]
    kept = [w for w in words if w not in STOP_WORDS]
    return [stem(w) for w in (kept or words)]


def inline(text: object, palette: dict[str, str] | None = None) -> str:
    """Мини-разметка текста → переносимый HTML.

    Поддерживается два приёма: ``**жирный**`` и ```код``` (в т.ч. пути).
    Всё остальное экранируется, поэтому из данных нельзя сломать разметку.
    """
    p = palette or PALETTE
    out = html.escape(str(text), quote=False)
    out = _wrap_pairs(out, "**", "<b>", "</b>")
    out = _wrap_pairs(
        out,
        "`",
        '<code style="color:%s;font-family:Consolas,monospace;">' % p["warn"],
        "</code>",
    )
    return out


def _wrap_pairs(text: str, marker: str, open_tag: str, close_tag: str) -> str:
    """Заменить пары маркеров на теги; незакрытая пара остаётся как есть."""
    out = text
    guard = 0
    while marker in out and guard < 200:
        guard += 1
        start = out.find(marker)
        end = out.find(marker, start + len(marker))
        if end < 0:
            break
        out = (
            out[:start]
            + open_tag
            + out[start + len(marker):end]
            + close_tag
            + out[end + len(marker):]
        )
    return out


def _fill(text: object, output_dir: str) -> str:
    """Подставить папку отчётов вместо {{output_dir}}."""
    value = ("`%s`" % output_dir) if output_dir else OUTPUT_DIR_FALLBACK
    return str(text).replace(OUTPUT_DIR_TOKEN, value)


# --- содержимое хелпера ----------------------------------------------------
#
# Блоки: p (абзац), steps (нумерованный список), list (маркированный,
# элемент может быть {"text": ..., "sub": [...]}), note (плашка),
# h (подзаголовок внутри раздела), table (таблица «симптом → что делать»).

SECTIONS: list[dict] = [
    {
        "id": "excel",
        "title": "Открыть таблицу Excel",
        "color": "#4ec3f0",
        "blocks": [
            {"t": "steps", "items": [
                "Найди иконку приложения в системном трее (правый нижний угол "
                "экрана, рядом с часами). Если её не видно — нажми стрелку `^`, "
                "чтобы раскрыть скрытые значки.",
                "Щёлкни по иконке **правой кнопкой мыши**.",
                "Выбери **«Открыть таблицу Excel»** — откроется файл со статистикой.",
            ]},
            {"t": "note", "title": "Пишет «Файл таблицы ещё не создан»",
             "text": "Таблица обновляется через 30 секунд после запуска и дальше "
                     "раз в 2 часа. Быстрее: трей → правая кнопка → "
                     "**«Обновить таблицу сейчас»**."},
            {"t": "note", "title": "Excel уже открыт",
             "text": "Закрой его перед обновлением, иначе запись не пройдёт "
                     "(в окне будет «Файл Excel открыт в другой программе, "
                     "закрой его»). PNG-отчёт и Google Таблица при этом "
                     "обновятся в любом случае."},
            {"t": "p", "text": "**Что внутри:** `SKYHELPER_stats.xlsx` — три листа: "
                               "«Неделя», «По дням», «Динамика». Папка с отчётами — "
                               "в разделе **«Где что лежит»**."},
        ],
    },
    {
        "id": "png",
        "title": "Открыть PNG-отчёт и папку",
        "color": "#3ddc97",
        "blocks": [
            {"t": "p", "text": "То же меню трея:"},
            {"t": "list", "items": [
                "**«Открыть PNG-отчёт»** — дашборд в стиле Grafana: карточки KPI, "
                "график по дням, сравнение с прошлой неделей, итог за месяц.",
                "**«Открыть папку с отчётом»** — вся папка отчётов: `SKYHELPER_stats.xlsx`, "
                "`SKYHELPER_report.png` и папка `История` с копиями по неделям.",
                "**«Открыть Google Таблицу»** — если настроена.",
                "**«Обновить таблицу сейчас»** — вне расписания.",
            ]},
            {"t": "p", "text": "В окне программы есть кнопка **«Отчёт сейчас»** — "
                               "она же обновляет файлы."},
        ],
    },
    {
        "id": "site",
        "title": "Сайт sky-grafana.rmrp",
        "color": "#4f8cff",
        "blocks": [
            {"t": "h", "text": "Один раз настроить"},
            {"t": "steps", "items": [
                "Включи сайт: **Настройки → вкладка «Сайт» → «Включить локальный "
                "сайт» → «Сохранить»**.",
                "Адрес `sky-grafana.rmrp` прописывается сам: после установки "
                "программа (от имени администратора) один раз добавляет домен "
                "в систему, а на рабочем столе уже лежит готовый ярлык сайта. "
                "Если адрес не открывается — запусти файл "
                "**`install-sky-grafana.bat` от имени администратора** (правый клик → "
                "«Запуск от имени администратора»).",
            ]},
            {"t": "h", "text": "Адреса"},
            {"t": "list", "items": [
                "`http://127.0.0.1/` — только этот ПК, работает сразу.",
                "`http://sky-grafana.rmrp/` — то же самое, но с понятным именем "
                "(домен прописывается автоматически при запуске программы).",
                "С телефона: во вкладке «Сайт» включи «Разрешить доступ с телефона» "
                "и открой `http://<IP-ПК>/` (`ipconfig` посмотри IP). Компьютер и "
                "телефон — одна Wi-Fi сеть.",
            ]},
            {"t": "note", "title": "Безопасность",
             "text": "Вне своего ПК всегда ставь **код доступа** (там же, во вкладке "
                     "«Сайт»). Без кода страницу откроет любой в той же сети. "
                     "Код хранится хэшем, в логи не попадает; 5 неудач подряд = "
                     "минута ожидания."},
            {"t": "p", "text": "На странице три вкладки: **Дашборд** (сегодня, неделя, "
                               "стрик, статус и столбики за 7 дней — обновляется сам "
                               "каждые 3 секунды), **SKY HELPER** (эта инструкция) и "
                               "**Правила RMRP** с поиском."},
            {"t": "p", "text": "Сайт крутится на стандартном **80-м порту**, поэтому "
                               "в адресе нет «:8080». Если 80-й порт занят другим "
                               "сервисом, программа напишет об этом в окно и в журнал "
                               "(не упадёт): смени порт во вкладке «Сайт» — и ссылка "
                               "станет `http://sky-grafana.rmrp:<порт>/`."},
        ],
    },
    {
        "id": "duty",
        "title": "Дежурство и счётчики",
        "color": "#ffb547",
        "blocks": [
            {"t": "list", "items": [
                "**F10** — начать/закончить дежурство. Онлайн и обращения считаются "
                "только на дежурстве и при запущенной игре.",
                "**F9** = +1 обращение, **Ctrl+F9** = −1. Не засчитается, если игра "
                "закрыта или дежурство выключено — программа скажет почему.",
                "Когда игра закрывается, дежурство выключается само.",
                "**После перезапуска программы дежурство сброшено** — нажми F10 "
                "заново, иначе онлайн не пойдёт.",
                "**Не запускай две копии трекера одновременно** — счётчики удвоятся. "
                "Проверить: в трее одна иконка, в диспетчере задач — один "
                "SKYHELPER.",
                "Если игра запущена **от имени администратора**, трекер запускай "
                "тоже от администратора, иначе F9/F10 не сработают поверх игры.",
            ]},
        ],
    },
    {
        "id": "trouble",
        "title": "Если что-то не так",
        "color": "#ff6b81",
        "blocks": [
            {"t": "table", "head": ["Симптом", "Что делать"], "rows": [
                ["Онлайн не считается",
                 "Проверь имя процесса игры: `python tools/list_processes.py gta` "
                 "и впиши найденное в настройках (сейчас `GTA5.exe` — предположение)."],
                ["Не приходят плашки «+1 обращение»",
                 "Обнови до этой сборки — в предыдущих exe плашки не работали "
                 "(баг исправлен)."],
                ["Окно настроек не открывается / настройки слетели",
                 "Файл `config.json` должен быть UTF-8. Исправляется само: программа "
                 "читает и UTF-8, и ANSI, и пересохраняет."],
                ["Сайт не открывается",
                 "Смотри строку «Сайт не запустился» в окне и в журнале; чаще всего "
                 "занят порт — смени его во вкладке «Сайт»."],
                ["`sky-grafana.rmrp` пишет «Страница недоступна»",
                 "Домен прописывает сама программа при запуске, а "
                 "`install-sky-grafana.bat` (от администратора) — ручной запасной "
                 "путь. Проверь `http://127.0.0.1/` — он должен открываться."],
                ["Отчёты не сохраняются, ошибка `WinError 3`",
                 "Путь из настроек недоступен: **Настройки → Экспорт** → укажи "
                 "существующую папку."],
                ["Таблица устарела",
                 "Трей → «Обновить таблицу сейчас» (или подожди ближайшего "
                 "обновления)."],
                ["Что-то вообще непонятно",
                 "Журнал: `%APPDATA%\\SKYHELPER\\logs\\app.log`"],
            ]},
        ],
    },
    {
        "id": "paths",
        "title": "Где что лежит",
        "color": "#b388ff",
        "blocks": [
            {"t": "list", "items": [
                "**Отчёты (Excel, PNG, «История»):** " + OUTPUT_DIR_TOKEN,
                "**База, настройки, журнал:** `%APPDATA%\\SKYHELPER` "
                "(`data.db`, `config.json`, `logs\\app.log`)",
                "**Правка настроек руками:** только через окно «Настройки» — оно "
                "сразу сохранит `config.json` и перезапустит нужные части. "
                "Правка файла подхватится после перезапуска.",
                "**Список правил RMRP:** `%APPDATA%\\SKYHELPER\\rules.json` — "
                "если файл есть, он заменяет встроенный список (правится без "
                "пересборки программы).",
                "**Google Таблица (по желанию):** про сервисный аккаунт — в "
                "`README.md`, раздел «Google Таблица». Проще всего без API: укажи "
                "`output_dir` внутри папки Google Диска — файл будет "
                "синхронизироваться сам.",
            ]},
        ],
    },
]


# --- правила RMRP ----------------------------------------------------------
#
# Три категории и 28 ссылок — ровно те, что прислал пользователь.
# keywords — дополнительные слова для поиска (синонимы, сокращения).

RULES: list[dict] = [
    {
        "category": "Общие правила проекта",
        "color": "#4ec3f0",
        "items": [
            {"title": "Правила проекта",
             "url": "https://forum.rmrp.ru/threads/pravila-proekta.42266/",
             "keywords": "основные общие"},
            {"title": "Правила предвыборной агитации и выборов",
             "url": "https://forum.rmrp.ru/threads/pravila-predvybornoj-agitacii-i-vyborov.73228/",
             "keywords": "выборы агитация"},
            {"title": "Правила использования маркетплейса «Blueberries»",
             "url": "https://forum.rmrp.ru/threads/pravila-ispolzovanija-marketplejsa-blueberries.123660/",
             "keywords": "маркетплейс магазин покупка рынок"},
            {"title": "Правила союзов",
             "url": "https://forum.rmrp.ru/threads/pravila-sojuzov.42347/",
             "keywords": "союз альянс"},
            {"title": "Правила мероприятий",
             "url": "https://forum.rmrp.ru/threads/pravila-meroprijatij.42346/",
             "keywords": "мероприятие ивент"},
            {"title": "Правила и обязанности администраторов",
             "url": "https://forum.rmrp.ru/threads/pravila-i-objazannosti-administratorov.42275/",
             "keywords": "админ персонал персонала"},
            {"title": "Правила ограблений игроков",
             "url": "https://forum.rmrp.ru/threads/pravila-ograblenij-igrokov.42273/",
             "keywords": "ограбление кража"},
            {"title": "Правила нападения и обороны федеральной тюрьмы",
             "url": "https://forum.rmrp.ru/threads/pravila-napadenija-i-oborony-federalnoj-tjurmy.42270/",
             "keywords": "фцо тюрьма федеральная оборона"},
            {"title": "Правила ограблений и поставок",
             "url": "https://forum.rmrp.ru/threads/pravila-ograblenij-i-postavok.42269/",
             "keywords": "поставка поставки"},
            {"title": "Правила криминальных событий",
             "url": "https://forum.rmrp.ru/threads/pravila-kriminalnyx-sobytij.42267/",
             "keywords": "событие события"},
            {"title": "Правила налетов",
             "url": "https://forum.rmrp.ru/threads/pravila-naletov.42265/",
             "keywords": "налёт нападение"},
            {"title": "Правила войны за КрАЗ",
             "url": "https://forum.rmrp.ru/threads/pravila-vojny-za-kraz.42263/",
             "keywords": "краз"},
            {"title": "Правила похищений игроков",
             "url": "https://forum.rmrp.ru/threads/pravila-poxischenij-igrokov.42261/",
             "keywords": "похищение киднап угон"},
            {"title": "Правила семей",
             "url": "https://forum.rmrp.ru/threads/pravila-semej.42254/",
             "keywords": "семья род клан"},
            {"title": "Правила проверок на читы",
             "url": "https://forum.rmrp.ru/threads/pravila-proverok-na-chity.42253/",
             "keywords": "читы чит проверка"},
            {"title": "Правила и обязанности лидеров",
             "url": "https://forum.rmrp.ru/threads/pravila-i-objazannosti-liderov.42252/",
             "keywords": "лидер глава"},
        ],
    },
    {
        "category": "Правила криминальных организаций",
        "color": "#ff6b81",
        "items": [
            {"title": "Основные правила криминальных организаций",
             "url": "https://forum.rmrp.ru/threads/osnovnye-pravila-kriminalnyx-organizacij.42258/",
             "keywords": "ко организации основные"},
            {"title": "Титульные территории криминальных организаций",
             "url": "https://forum.rmrp.ru/threads/titulnye-territorii-kriminalnyx-organizacij.42276/",
             "keywords": "титул территория титульные"},
            {"title": "Правила войны за бизнес",
             "url": "https://forum.rmrp.ru/threads/pravila-vojny-za-biznes.42268/",
             "keywords": "бизнес"},
            {"title": "Правила войны за AirDrop",
             "url": "https://forum.rmrp.ru/threads/pravila-vojny-za-airdrop.42264/",
             "keywords": "аирдроп air дроп"},
            {"title": "Правила войны",
             "url": "https://forum.rmrp.ru/threads/pravila-vojny.42260/",
             "keywords": "война"},
            {"title": "Правила войны за территории",
             "url": "https://forum.rmrp.ru/threads/pravila-vojny-za-territorii.42259/",
             "keywords": "территория зоны"},
        ],
    },
    {
        "category": "Правила государственных организаций",
        "color": "#4f8cff",
        "items": [
            {"title": "Основные правила государственных организаций",
             "url": "https://forum.rmrp.ru/threads/osnovnye-pravila-gosudarstvennyx-organizacij.42255/",
             "keywords": "го государственные основные"},
            {"title": "Правила Следственного комитета и Прокуратуры",
             "url": "https://forum.rmrp.ru/threads/pravila-sledstvennogo-komiteta-i-prokuratury.101487/",
             "keywords": "ск следствие прокуратура"},
            {"title": "Правила судебной власти",
             "url": "https://forum.rmrp.ru/threads/pravila-sudebnoj-vlasti.42278/",
             "keywords": "суд судебная"},
            {"title": "Титульные районы государственных организаций",
             "url": "https://forum.rmrp.ru/threads/titulnye-rajony-gosudarstvennyx-organizacij.42277/",
             "keywords": "район титул титульные"},
            {"title": "Правила рейдов",
             "url": "https://forum.rmrp.ru/threads/pravila-rejdov.42257/",
             "keywords": "рейд"},
            {"title": "Правила допросов",
             "url": "https://forum.rmrp.ru/threads/pravila-doprosov.42256/",
             "keywords": "допрос"},
        ],
    },
]


def rules_path() -> Path:
    """Файл с локальным списком правил (в %APPDATA% программы)."""
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / APP_NAME / "rules.json"


def _validate_rules(data: object) -> list[dict] | None:
    """Похоже ли на RULES (список категорий с items)? Иначе None."""
    if not isinstance(data, list) or not data:
        return None
    clean: list[dict] = []
    for cat in data:
        if not isinstance(cat, dict):
            return None
        name = cat.get("category")
        items = cat.get("items")
        if not isinstance(name, str) or not name or not isinstance(items, list):
            return None
        checked: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                return None
            title, url = item.get("title"), item.get("url")
            if not isinstance(title, str) or not title:
                return None
            if not isinstance(url, str) or not url:
                return None
            checked.append({
                "title": title,
                "url": url,
                "keywords": str(item.get("keywords") or ""),
            })
        clean.append({
            "category": name,
            "color": str(cat.get("color") or PALETTE["accent"]),
            "items": checked,
        })
    return clean


def load_rules(path: str | os.PathLike | None = None) -> list[dict]:
    """Встроенные правила, но локальный rules.json (если валиден) их заменяет."""
    target = Path(path) if path is not None else rules_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return RULES
    return _validate_rules(data) or RULES


def total_rules(rules: Sequence[dict] | None = None) -> int:
    """Сколько правил во всех категориях."""
    source = RULES if rules is None else rules
    return sum(len(cat.get("items", ())) for cat in source)


def search_key(item: dict, category: str) -> str:
    """Строка поиска по «шапке» правила: название + категория + синонимы."""
    return normalize(
        "%s %s %s" % (item.get("title", ""), category, item.get("keywords", ""))
    )


def rule_text(item: dict) -> str:
    """Текст правила: свой у правил из ``rules.json``, иначе снимок с форума."""
    own = item.get("text")
    if isinstance(own, str) and own.strip():
        return own
    return RULE_TEXTS.get(str(item.get("url", "")), "")


#: Кэш нормализованных текстов: на каждый символ запроса не гоняем 236К символов.
_NORM_TEXTS: dict[str, str] = {}


def norm_text(item: dict) -> str:
    """Нормализованный текст правила (нижний регистр, ё → е), с кэшем."""
    raw = rule_text(item)
    if not raw:
        return ""
    cached = _NORM_TEXTS.get(raw)
    if cached is None:
        cached = normalize(raw)
        if len(_NORM_TEXTS) < 64:  # не растим память на чужих правилах
            _NORM_TEXTS[raw] = cached
    return cached


def _in_text(stem: str) -> bool:
    """Можно ли искать эту основу в полном тексте правила.

    Три буквы («сем» для «семьи») и цифры («60») — достаточно однозначно.
    Двухбуквенное «ко» по 236К символов нашло бы всё подряд, поэтому короткие
    буквы ищем только в названии, категории и синонимах.
    """
    return len(stem) >= 3 or stem.isdigit()


#: Сколько раз слово из двух букв может встретиться в тексте правила, чтобы мы
#: его показали. Нужно для запросов вроде «DM» или «МП»: раньше слово короче
#: трёх букв искалось только в заголовке, и такой запрос не находил ничего
#: (баг-репорт). Порог отсекает «ко» и прочие частые обрезки.
RARE_LIMIT = 30

#: Слово из двух букв, начало которого встречается чаще, чем в стольких
#: правилах, считается «шумом» и по тексту не ищется. Порог подобран по
#: замеру: полезные «DM» (10 правил), «ФСБ» (7), «дп» (1) проходят, а
#: «по» (28), «не» (26), «ин» (22) — отсекаются.
COMMON_LIMIT = 14


#: Одно упоминание слова в стольких символах — случайность, а не тема правила.
#: «неактивность» встречалась 1 раз в 42 337 символов «Правил проекта» и всё
#: равно показывалась; плотнее этого порога совпадение считаем настоящим.
TEXT_NOISE = 15000


def _text_hits(text: str, stems: list[str]) -> int:
    """Сколько раз основы запроса встретились в тексте правила."""
    if not text:
        return 0
    return sum(text.count(word) for word in stems if _in_text(word))


def _text_only(item: dict, category: str, stems: list[str]) -> bool:
    """Ни одно слово запроса не в заголовке и не в категории/синонимах.

    Такие правила не отсекаем никогда: там слово стоит в названии, оно
    точно не случайное.
    """
    if not stems:
        return False
    title = normalize(item.get("title", ""))
    meta = search_key(item, category)
    return not any(
        _starts_a_word(word, title) or _starts_a_word(word, meta)
        for word in stems
    )


def relevance(item: dict, category: str, stems: list[str]) -> float:
    """Насколько правило близко к тому, что искали: больше — ближе.

    Раньше внутри одного совпадения («только текст») правила шли в порядке,
    в каком лежат в файле, поэтому сверху оказывались гигантские документы,
    где искомое слово упомянуто пару раз. Считаем:

    * заголовок и категория/синонимы — самое точное, за каждое слово большой
      плюс (их же отдельно считает :func:`match_rank`);
    * плотность в тексте: чем чаще слово встречается и чем короче правило,
      тем вероятнее, что правило именно о нём;
    * близость к началу: о теме, как правило, пишут во введении;
    * короткое правило с тем же числом упоминаний точнее длинного.
    """
    if not stems:
        return 0.0
    score = 0.0
    title = normalize(item.get("title", ""))
    score += 1000 * sum(1 for word in stems if _starts_a_word(word, title))
    score += 400 * sum(
        1 for word in stems if _starts_a_word(word, search_key(item, category))
    )
    text = norm_text(item)
    if text:
        length = len(text)
        hits = _text_hits(text, stems)
        if hits:
            # Плотность с мягким штрафом за размер: правило в 42 337 символов
            # с 21 упоминанием важнее, чем в 5 178 с пятью, но короткое с тем
            # же числом упоминаний всё равно впереди. Делим на корень длины —
            # квадратный штраф (как было) отправлял общие правила в конец.
            score += 100.0 * hits / (1 + length ** 0.5 / 40)
            # Слова близко к началу — правило, скорее всего, об этом.
            first = min(
                text.find(word) for word in stems
                if _in_text(word) and word in text
            )
            score += 60.0 * (1.0 - first / max(length, 1))
    return score


def match_rank(item: dict, category: str, query: str,
              allow_short: set[str] | None = None) -> int | None:
    """Насколько правило подходит под запрос, или None если не подходит.

    0 — пустой запрос, 1 — совпало название, 2 — категория/синонимы,
    3 — совпал только текст правила. Все слова запроса должны найтись,
    но каждое само по себе: «допросы 60 минут» — «допрос» в заголовке,
    «60» и «минут» в тексте.
    """
    stems = query_stems(query)
    if not stems:
        return 0
    title = normalize(item.get("title", ""))
    if all(_starts_a_word(word, title) for word in stems):
        return 1
    meta = search_key(item, category)
    if all(_starts_a_word(word, meta) for word in stems):
        return 2
    text = norm_text(item)
    if not text:
        return None
    # «не должен длиться»: короткое служебное «не» ищем в тексте только когда
    # рядом есть слово посерьёзнее; одиночное «ко» остаётся «шапочным», иначе
    # по 236К символов оно нашло бы половину правил.
    deep = any(_in_text(word) for word in stems)

    def in_text(word: str) -> bool:
        if _in_text(word):
            return True
        if deep and len(stems) > 1:
            return True
        # Короткое слово ищем по тексту, только если оно редкое:
        # «DM» найдёт свои правила, а «ко» (сотни вхождений) — нет.
        if len(word) == 2:
            if allow_short is not None:
                return word in allow_short and _starts_a_word(word, text)
            count, _ = _word_hits(word, text)
            return 0 < count <= RARE_LIMIT
        return False

    if all(in_text(word) and _starts_a_word(word, text) for word in stems):
        return 3
    # Смешанный случай: часть слов в «шапке», часть в тексте.
    if all(
        _starts_a_word(word, meta)
        or (in_text(word) and _starts_a_word(word, text))
        for word in stems
    ):
        return 3
    return None


def rule_matches(item: dict, category: str, query: str) -> bool:
    """True, если правило подходит под запрос (см. :func:`match_rank`)."""
    return match_rank(item, category, query) is not None


def rule_snippet(item: dict, query: str = "", width: int = 190) -> str:
    """Фрагмент текста правила: место совпадения (или начало без запроса).

    Окно ±60 символов вокруг первого совпадения, разрез по границам слова —
    возвращается обычный текст, подсветку делает :func:`highlight`.
    """
    raw = rule_text(item)
    if not raw:
        return ""
    low = norm_text(item)
    stems = [w for w in query_stems(query) if _in_text(w)]

    start, end = 0, min(len(raw), width)
    if len(low) == len(raw):  # иначе позиции не сопоставимы — только начало
        # Окно вокруг самой редкой основы: запрос «60 минут» покажет «60 минут»,
        # а не первое «минут» где-то выше по тексту.
        hits = [hit for w in stems if (hit := _word_hits(w, low))[0]]
        if hits:
            _, at = min(hits)  # меньше вхождений, при равенстве — раньше позиция
            start = max(0, at - 60)
            end = min(len(raw), max(at + width - 60, at + 40))
            while start > 0 and raw[start].isalnum():
                start -= 1
    # Не рвём слово на правом крае окна (иначе «допро» вместо «допрос»).
    while end < len(raw) and raw[end].isalnum():
        end += 1

    piece = raw[start:end].strip()
    if start > 0:
        piece = "…" + piece
    if end < len(raw):
        piece = piece + "…"
    return piece


def _word_hits(stem: str, haystack: str) -> tuple[int, int]:
    """(сколько слов начинается с stem, позиция первого из них); при 0 — (0, −1)."""
    count, first = 0, -1
    at = haystack.find(stem)
    while at >= 0:
        if at == 0 or not haystack[at - 1].isalnum():
            if count == 0:
                first = at
            count += 1
        at = haystack.find(stem, at + 1)
    return count, first


def _starts_a_word(needle: str, haystack: str) -> bool:
    """Есть ли в haystack слово, начинающееся с needle."""
    start = haystack.find(needle)
    while start >= 0:
        if start == 0 or not haystack[start - 1].isalnum():
            return True
        start = haystack.find(needle, start + 1)
    return False


#: Буквы, которыми может быть опечатка.
_ALPHABET = "абвгдежзийклмнопрстуфхцчшщыэюяabcdefghijklmnopqrstuvwxyz0123456789"

#: Допуск работает только по коротким словам. Длинное слово и так ищется по
#: трём первым буквам (:func:`stem`), поэтому опечатка после третьей буквы
#: находится и без всяких ухищрений — а вот опечатка в первых трёх у
#: длинного слова даёт ту же основу и находится точно так же.
FUZZY_MAX = 8

#: Короче этого опечатки не ищем: «слев» на расстоянии одной буквы от «слев» —
#: это уже другое слово, а не опечатка.
FUZZY_MIN = 4

#: Меньше этого числа точных совпадений — ищем ещё и с опечатками.
FUZZY_MIN_EXACT = 3

#: Кэш: начало слова из двух букв → слова правила такой длины.
_WORDS2: dict[str, dict[str, frozenset[str]]] = {}
_BALLS: dict[str, frozenset[str]] = {}


def _typo_ball(word: str) -> frozenset[str]:
    """Все варианты слова с одной опечаткой: замена, забытая или лишняя буква,
    перестановка соседних.

    Пусто для слов короче :data:`FUZZY_MIN` и длиннее :data:`FUZZY_MAX`.
    """
    if not FUZZY_MIN <= len(word) <= FUZZY_MAX:
        return frozenset()
    got = _BALLS.get(word)
    if got is None:
        out = {word}
        for i in range(len(word)):
            head, tail = word[:i], word[i + 1:]
            for ch in _ALPHABET:              # замена буквы
                out.add(head + ch + tail)
            out.add(head + tail)              # забыли букву
        for i in range(len(word) + 1):        # лишняя буква
            for ch in _ALPHABET:
                out.add(word[:i] + ch + word[i:])
        for i in range(len(word) - 1):        # переставили местами
            out.add(word[:i] + word[i + 1] + word[i] + word[i + 2:])
        out.discard(word)
        got = frozenset(out)
        if len(_BALLS) < 64:
            _BALLS[word] = got
    return got


def _words2(item: dict) -> dict[str, frozenset[str]]:
    """Слова текста правила, разложенные по первым двум буквам, с кэшем.

    Раскладка нужна, чтобы проверить тысячу вариантов с опечаткой не перебором
    всего текста, а парой обращений к маленьким множествам.
    """
    raw = rule_text(item)
    if not raw:
        return {}
    got = _WORDS2.get(raw)
    if got is None:
        buckets: dict[str, set[str]] = {}
        for word in normalize(raw).split():
            if FUZZY_MIN <= len(word) <= FUZZY_MAX:
                buckets.setdefault(word[:2], set()).add(word)
        got = {key: frozenset(words) for key, words in buckets.items()}
        if len(_WORDS2) < 64:
            _WORDS2[raw] = got
    return got


def fuzzy_words(query: object) -> list[frozenset[str]]:
    """Шары опечаток для слов запроса (пустой список, если запрос не из чего)."""
    balls = []
    for word in normalize(query).split():
        got = _typo_ball(word)
        if got:
            balls.append(got)
    return balls


def fuzzy_rank(item: dict, query: str, balls: list[frozenset[str]] | None = None,
               mode: str = "all") -> bool:
    """Подходит ли правило, если запрос написан с опечатками.

    ``mode`` — ``all`` (каждое слово с опечаткой нашлось) либо ``one``
    (хватит одного: «допрос 60» найдёт допросы, где «60» не встречается).
    """
    if balls is None:
        balls = fuzzy_words(query)
    if not balls:
        return False
    title = normalize(item.get("title", ""))
    words = _words2(item)

    def hit(ball: frozenset[str]) -> bool:
        for variant in ball:
            bucket = words.get(variant[:2])
            if bucket and variant in bucket:
                return True
            if variant in title:
                return True
        return False

    hits = sum(1 for ball in balls if hit(ball))
    return hits >= (len(balls) if mode == "all" else 1)


def _short_stems(query: object, rules: Sequence[dict]) -> set[str]:
    """Какие слова из двух букв искать по тексту правил.

    «DM» встречается в handful правил и полезен, а «ко» или «не» — в
    каждом втором, и по ним находится всё подряд. Считаем по всему корпусу
    правил: слово пропускаем, если начало слова встречается чаще
    :data:`COMMON_LIMIT` раз.
    """
    wanted = {s for s in query_stems(query) if len(s) == 2}
    if not wanted:
        return set()
    items = [item for cat in rules for item in cat.get("items", ())]
    out: set[str] = set()
    for word in wanted:
        hits = 0
        for item in items:
            if _starts_a_word(word, norm_text(item)):
                hits += 1
                if hits > COMMON_LIMIT:
                    break
        if hits and hits <= COMMON_LIMIT:
            out.add(word)
    return out


def filter_rules(query: str, rules: Sequence[dict] | None = None) -> list[dict]:
    """Категории с подходящими правилами, отсортированными по совпадению.

    Совпадения в названии идут раньше, чем найденные только в тексте, а
    категории — по лучшему своему правилу: запрос «допросы» показывает сначала
    «Правила допросов», а не то правило из первой категории, где слово
    встретилось где-то в середине текста.
    """
    source = load_rules() if rules is None else rules
    allow = _short_stems(query, source)
    balls = fuzzy_words(query)
    stems = query_stems(query)

    # Сначала точный поиск по всем правилам.
    # Запись: (ранг, релевантность, позиция в категории, правило, случайно).
    draft: list[tuple[int, dict, list[dict], list[tuple], set[int]]] = []
    exact_total = 0
    for index, cat in enumerate(source):
        name = str(cat.get("category", ""))
        items = list(cat.get("items", ()))
        kept: list[tuple] = []
        taken: set[int] = set()
        for pos, item in enumerate(items):
            rank = match_rank(item, name, query, allow)
            if rank is None:
                continue
            text = norm_text(item)
            hits = _text_hits(text, stems)
            # «Случайно» = совпало только текстом и реже, чем раз в
            # TEXT_NOISE символов: одно упоминание в гиганте — не тема.
            noise = (
                rank == 3
                and _text_only(item, name, stems)
                and 0 < hits * TEXT_NOISE < len(text)
            )
            kept.append((rank, relevance(item, name, stems), pos, item, noise))
            taken.add(pos)
        exact_total += len(kept)
        draft.append((index, cat, items, kept, taken))

    # Опечатки — запасной вариант: показываем их, только если точных
    # совпадений почти нет, иначе «зарплата» нашла бы весь раздел.
    use_fuzzy = bool(balls) and exact_total < FUZZY_MIN_EXACT

    # Случайные совпадения убираем, но никогда — если уйдёт всё подряд:
    # на узком запросе иначе получился бы пустой экран.
    total = sum(len(kept) for _, _, _, kept, _ in draft)
    noisy = sum(1 for _, _, _, kept, _ in draft for row in kept if row[4])
    drop_noise = 0 < noisy < total

    out: list[tuple[int, float, int, dict]] = []
    for index, cat, items, kept, taken in draft:
        if use_fuzzy:
            # Дописываем те правила, что не нашлись точно: опечатка в запросе
            # не должна прятаться за тем, что в той же категории нашлось
            # другое правило.
            name = str(cat.get("category", ""))
            for pos, item in enumerate(items):
                if pos not in taken and fuzzy_rank(item, query, balls):
                    kept.append((4, relevance(item, name, stems), pos, item, False))
        if drop_noise:
            kept = [row for row in kept if not row[4]]
        if not kept:
            continue
        # Ранг важнее всего, дальше — релевантность, и только потом порядок
        # в файле (иначе «Правила проекта» всегда первые).
        kept.sort(key=lambda t: (t[0], -t[1], t[2]))
        out.append(
            (kept[0][0], -kept[0][1], index,
             {**cat, "items": [t[3] for t in kept]})
        )
    out.sort(key=lambda t: (t[0], t[1], t[2]))
    return [cat for _, _, _, cat in out]


def _expand_word(text: str, start: int, end: int) -> tuple[int, int]:
    """Растянуть найденный кусок до границ слова: подсвечиваем слово целиком."""
    while start > 0 and text[start - 1].isalnum():
        start -= 1
    while end < len(text) and text[end].isalnum():
        end += 1
    return start, end


def highlight(text: str, query: str) -> str:
    """Экранированный текст с подсветкой найденных слов (портабельный span).

    Ищем по основе («войн» найдёт и «войны»), а подсвечиваем всё слово.
    """
    stems = query_stems(query)
    plain = esc(text)
    if not stems:
        return plain

    low = normalize(text)
    spans: list[tuple[int, int]] = []
    for word in stems:
        start = 0
        while True:
            index = low.find(word, start)
            if index < 0:
                break
            spans.append(_expand_word(low, index, index + len(word)))
            start = index + len(word)
    if not spans:
        return plain

    spans.sort()
    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    parts: list[str] = []
    pos = 0
    for start, end in merged:
        parts.append(esc(text[pos:start]))
        parts.append(
            '<span style="background-color:#ffe08a;color:#10151f;'
            'font-weight:600;border-radius:3px;">%s</span>' % esc(text[start:end])
        )
        pos = end
    parts.append(esc(text[pos:]))
    return "".join(parts)


# --- рендер разделов -------------------------------------------------------


def _block_html(
    block: dict, palette: dict[str, str], color: str, output_dir: str
) -> str:
    kind = str(block.get("t") or "p")
    p = palette
    line = "line-height:1.45;margin:6px 0;"

    if kind == "p":
        return '<p style="%s">%s</p>' % (line, inline(_fill(block.get("text", ""), output_dir), p))

    if kind == "h":
        return (
            '<p style="color:%s;font-weight:700;font-size:14px;'
            'margin:14px 0 4px 0;">%s</p>' % (color, inline(block.get("text", ""), p))
        )

    if kind == "steps":
        items = "".join(
            '<li style="%s;margin:3px 0;">%s</li>'
            % (line, inline(_fill(item, output_dir), p))
            for item in block.get("items", ())
        )
        return '<ol style="margin:6px 0 6px 22px;padding:0;">%s</ol>' % items

    if kind == "list":
        return '<ul style="margin:6px 0 6px 20px;padding:0;">%s</ul>' % _list_items(
            block.get("items", ()), p, output_dir, line
        )

    if kind == "note":
        title = inline(block.get("title", ""), p)
        text = inline(_fill(block.get("text", ""), output_dir), p)
        return (
            '<div class="note" style="background-color:%s;border-left:4px solid %s;'
            'border-radius:8px;padding:8px 11px;margin:9px 0;">'
            '<b style="color:%s;">%s</b><br>%s</div>'
            % (p["card"], color, color, title, text)
        )

    if kind == "table":
        head = "".join(
            '<td style="color:%s;font-weight:700;padding:6px 9px;'
            'border-bottom:1px solid %s;">%s</td>' % (color, p["border"], esc(cell))
            for cell in block.get("head", ())
        )
        rows = []
        for row in block.get("rows", ()):
            cells = "".join(
                '<td style="padding:6px 9px;border-bottom:1px solid %s;'
                'vertical-align:top;">%s</td>' % (p["border"], inline(_fill(cell, output_dir), p))
                for cell in row
            )
            rows.append("<tr>%s</tr>" % cells)
        return (
            '<table class="h-table" style="width:100%%;border-collapse:collapse;'
            'margin:6px 0;"><tr>%s</tr>%s</table>' % (head, "".join(rows))
        )

    return ""


def _list_items(
    items: Iterable, palette: dict[str, str], output_dir: str, line: str
) -> str:
    """Маркированный список; элемент может быть вложенным {"text", "sub"}."""
    parts: list[str] = []
    for item in items:
        if isinstance(item, dict):
            text = _fill(item.get("text", ""), output_dir)
            sub = item.get("sub") or ()
        else:
            text = _fill(item, output_dir)
            sub = ()
        parts.append(
            '<li style="%s;margin:3px 0;">%s%s</li>'
            % (
                line,
                inline(text, palette),
                _list_items(sub, palette, output_dir, line) if sub else "",
            )
        )
    return "".join(parts)


def section_html(
    section: dict,
    palette: dict[str, str] | None = None,
    output_dir: str = "",
) -> str:
    """Только блоки раздела — заголовок рисует вызывающая сторона."""
    p = palette or PALETTE
    color = str(section.get("color") or p["accent"])
    return "".join(
        _block_html(block, p, color, output_dir) for block in section.get("blocks", ())
    )


def section_page_html(
    section: dict,
    palette: dict[str, str] | None = None,
    output_dir: str = "",
) -> str:
    """Заголовок раздела + блоки: готовый фрагмент для QTextBrowser."""
    p = palette or PALETTE
    color = str(section.get("color") or p["accent"])
    head = (
        '<p style="color:%s;font-size:17px;font-weight:700;margin:0 0 2px 0;">%s</p>'
        '<p style="color:%s;border-bottom:1px solid %s;margin:0 0 10px 0;">&nbsp;</p>'
        % (color, esc(section.get("title", "")), p["border"], p["border"])
    )
    return head + section_html(section, p, output_dir)


def rules_html(
    palette: dict[str, str] | None = None,
    query: str = "",
    web: bool = False,
    rules: Sequence[dict] | None = None,
) -> str:
    """Категории правил карточками: название + фрагмент текста правила.

    ``web=False`` — фильтрация и подсветка по ``query`` уже готовы (окно в
    программе перерисовывается на каждое нажатие клавиши).
    ``web=True`` — выводятся все правила с ``data-k``/``data-t``/``data-x`` для
    клиентского поиска в JavaScript на сайте: ``data-x`` — сырой текст правила,
    по нему ищут запросы вроде «60 минут» и берётся сниппет.
    """
    p = palette or PALETTE
    source = load_rules() if rules is None else rules
    shown = filter_rules(query, source) if not web else list(source)

    parts: list[str] = []
    for cat_index, cat in enumerate(shown):
        name = str(cat.get("category", ""))
        color = str(cat.get("color") or p["accent"])
        items = cat.get("items", ())
        if web:
            # На сайте вид целиком задаёт CSS (стиль MIDNIGHT), здесь — разметка.
            head = (
                '<div class="cat">'
                '<div class="cat-head"><span class="cat-title">%s</span>'
                '<span class="cat-n">%d</span></div>'
                '<div class="cat-rules">'
                % (esc(name), len(items))
            )
        else:
            head = (
                '<div class="cat" style="margin:0 0 16px 0;">'
                '<p style="color:%s;font-size:13px;font-weight:700;letter-spacing:1px;'
                'margin:0 0 8px 0;">%s <span class="cat-n" style="color:%s;'
                'font-weight:600;">%d</span></p>'
                '<div class="cat-rules">'
                % (color, esc(name), p["muted"], len(items))
            )
        for item in items:
            title = str(item.get("title", ""))
            href = str(item.get("url", ""))
            attrs = ""
            label = highlight(title, query)
            snip = rule_snippet(item, query)
            snip_html = highlight(snip, query) if snip else ""
            if web:
                key = esc(search_key(item, name))
                attrs = ' data-k="%s" data-t="%s" data-x="%s"' % (
                    key, esc(title), esc(rule_text(item)),
                )
                label, snip_html = esc(title), esc(snip)
                snip_block = (
                    '<span class="rule-snip">%s</span>' % snip_html
                ) if snip else ""
                head += (
                    '<div class="rule-card">'
                    '<a class="rule" href="%s" target="_blank" rel="noopener"%s'
                    '>%s</a>%s</div>'
                    % (esc(href), attrs, label, snip_block)
                )
                continue
            # Именно div, а не span: в QTextBrowser span остаётся строчным, и
            # заголовок правила примыкал к тексту вплотную («Правила допросов
            # Глава 1…»). На сайте разметку задаёт CSS, там остаётся span.
            snip_block = (
                '<div class="rule-snip" style="color:%s;'
                'font-size:12.5px;line-height:1.45;margin-top:5px;">%s</div>'
                % (p["muted"], snip_html)
            ) if snip else ""
            head += (
                # Отступ снизу вместо flex-gap: Qt в QTextBrowser не понимает
                # display:flex/gap, и карточки правил слипались в одну стену
                # текста — заголовок правила примыкал к его же тексту
                # (баг-репорт №1).
                '<div class="rule-card" style="background-color:%s;border:1px solid %s;'
                'border-radius:9px;padding:9px 13px;margin:0 0 8px 0;">'
                '<a class="rule" href="%s" target="_blank" rel="noopener"%s '
                'style="color:%s;text-decoration:none;font-size:14px;'
                'font-weight:600;">%s</a>%s</div>'
                % (
                    p["card"], p["border"], esc(href), attrs, p["accent"],
                    label, snip_block,
                )
            )
        head += "</div></div>"
        parts.append(head)
    return "".join(parts)
