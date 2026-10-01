"""HTML/CSS/JS страниц локального дашборда.

Всё лежит прямо в строках модуля: ни файлов на диске, ни CDN, ни прочих
внешних ресурсов — страница обязана полностью работать офлайн. Стиль —
тёмный дашборд в духе Grafana, подписи русские.

Схема ``status`` для :func:`dashboard_page` (все ключи опциональны,
отсутствующие отрисовываются нулями/заглушками)::

    {
        "date": "29.09.2026",              # дата для подзаголовка
        "weekday": "Пн",                   # день недели строкой
        "week": "29.09 — 05.10",           # диапазон текущей недели
        "today": {
            "seconds": 12345,              # онлайн за сегодня, сек
            "reports": 43,                 # обращения за сегодня
            "plan_seconds": 10285,         # дневной план, сек (0 = плана нет)
        },
        "week_stats": {
            "seconds": 250000,             # онлайн за неделю, сек
            "reports": 321,
            "hours_percent": 62.0,         # проценты к недельной норме
            "reports_percent": 55.0,
        },
        "streak": {"days": 6, "today_done": True},
        "flags": {"duty": True, "game": False, "counting": True},
        "days": [                          # последние дни, новые сверху
            {"label": "29.09 Пн", "seconds": 7200, "reports": 50},
        ],
    }

Страница один раз рендерится на сервере (первая отрисовка), дальше JavaScript
каждые 3 секунды дергает ``fetch('/api/status')`` и аккуратно обновляет DOM.
"""
from __future__ import annotations

import html
import json
from datetime import datetime

from app import OWNER_NOTICE
from app.catalog import data as CAT_DATA
from app.commands import data as CMD_DATA
from app.events import data as EV_DATA
from app.staff import data as STAFF_DATA
from app.help.data import (
    PALETTE as HELP_PALETTE,
    RULES as RULE_CATEGORIES,
    SECTIONS as HELP_SECTIONS,
    rules_html,
    section_html,
    total_rules,
)

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# --- маленькие помощники ---------------------------------------------------


def _int(value: object, default: int = 0) -> int:
    """Целое из значения JSON; мусор → default."""
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _float(value: object, default: float = 0.0) -> float:
    """Вещественное из значения JSON; мусор → default."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _pct(value: object) -> int:
    """Проценты из JSON → целое (так подписи короче и аккуратнее)."""
    return round(_float(value))


def _section(status: dict, key: str) -> dict:
    """Вложенная секция status; если её нет или она не словарь — пусто."""
    value = status.get(key)
    return value if isinstance(value, dict) else {}


def _hm(seconds: object) -> str:
    """Секунды → чч:мм (часы могут быть больше суток)."""
    total = max(0, _int(seconds))
    hours, minutes = divmod(total // 60, 60)
    return f"{hours}:{minutes:02d}"


def _duration(seconds: object) -> str:
    """Секунды → «X ч Y мин»."""
    total = max(0, _int(seconds))
    hours, minutes = divmod(total // 60, 60)
    return f"{hours} ч {minutes:02d} мин"


def _today_time(seconds: object) -> str:
    """Крупное значение в карточке «СЕГОДНЯ»: чч:мм, а до часа — «X ч Y мин»."""
    return _hm(seconds) if _int(seconds) >= 3600 else _duration(seconds)


def _flag_chip(element_id: str, on: bool, on_text: str, off_text: str) -> str:
    """Плашка статуса в карточке «СТАТУС»."""
    text = on_text if on else off_text
    cls = "chip ok" if on else "chip off"
    return f'<span class="{cls}" id="{element_id}">{html.escape(text)}</span>'


def _bars_html(days: object) -> str:
    """Столбики последних дней (первая отрисовка страницы)."""
    items = [d for d in (days if isinstance(days, list) else []) if isinstance(d, dict)]
    items = items[:14]
    if not items:
        return '<div class="empty">нет данных за последние дни</div>'

    max_seconds = max((_int(d.get("seconds")) for d in items), default=0) or 1
    parts: list[str] = []
    for day in items:
        seconds = max(0, _int(day.get("seconds")))
        reports = max(0, _int(day.get("reports")))
        label = html.escape(str(day.get("label") or day.get("date") or ""))
        height = max(2, round(seconds / max_seconds * 100))
        fill_cls = "col-fill on" if seconds > 0 else "col-fill"
        parts.append(
            '<div class="col">'
            f'<div class="col-val">{_hm(seconds)}</div>'
            f'<div class="col-track"><div class="{fill_cls}" style="height:{height}%"></div></div>'
            f'<div class="col-lab">{label}</div>'
            f'<div class="col-rep">{reports} обр.</div>'
            "</div>"
        )
    return "".join(parts)


# --- общая рамка документа -------------------------------------------------


def _document(title: str, css: str, body: str, script: str = "") -> str:
    """Собирает HTML-документ из готовых кусков (скобки CSS/JS не мешают)."""
    tail = f"<script>\n{script}\n</script>\n" if script else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ru">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n"
        f"<style>\n{css}\n</style>\n"
        "</head>\n"
        f"{body}\n"
        f"{tail}"
        "</body>\n"
        "</html>\n"
    )


_BASE_CSS = """:root {
  --bg: #0b0c0e;
  --panel: #0f1013;
  --card: #141519;
  --field: #101115;
  --border: #24262b;
  --text: #edeef1;
  --muted: #8a8c94;
  --accent: #4ec3f0;
  --accent-soft: #10222c;
  --ok: #3ddc97;
  --ok-soft: #11241d;
  --warn: #ffb547;
  --warn-soft: #2a2113;
  --danger: #ff6b81;
  --bar: #1e2025;
  --badge: #1c1e23;
  --badge-active: #10313f;
  --tab-active: #191b20;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: "Segoe UI", "Segoe UI Variable", system-ui, -apple-system, Arial, sans-serif;
  font-size: 15px;
}
/* Курсор на странице ровно один — нарисованный скриптом ниже (баг-репорт
   №6). Раньше тут стоял ещё и битмап cursor.png, и рядом с ним точка с
   кольцом — в сумме «два курсора». Системный курсор прячем только когда
   скрипт точно загрузился (класс sky-cursor-on), иначе он остаётся. */
html.sky-cursor-on, html.sky-cursor-on * { cursor: none !important; }
a { color: var(--accent); }

/* эффект: мягкое свечение при наведении на карточки */
.card { transition: border-color 0.15s ease, box-shadow 0.15s ease; }
.card:hover {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent), 0 6px 24px rgba(78, 195, 240, 0.12);
}"""

# --- страница входа --------------------------------------------------------

_LOGIN_CSS = """
.login-body {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-card {
  width: 340px;
  max-width: calc(100vw - 32px);
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 28px 26px;
}
.login-title {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 1px;
  text-align: center;
}
.login-sub {
  margin-top: 8px;
  color: var(--muted);
  font-size: 13px;
  text-align: center;
}
.login-label {
  display: block;
  margin-top: 22px;
  font-size: 13px;
  color: var(--muted);
}
.login-input {
  width: 100%;
  margin-top: 8px;
  padding: 10px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-size: 16px;
  letter-spacing: 3px;
  outline: none;
}
.login-input:focus { border-color: var(--accent); }
.login-error {
  min-height: 18px;
  margin-top: 10px;
  font-size: 13px;
  color: var(--danger);
}
.login-btn {
  width: 100%;
  margin-top: 14px;
  padding: 11px;
  background: var(--accent);
  color: #06161c;
  border: none;
  border-radius: 8px;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
}
.login-btn:hover { filter: brightness(1.12); }
.login-owner {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  line-height: 1.5;
  color: var(--muted);
  text-align: center;
}"""

#: Текст о правообладателе (общий с окном программы, см. app.OWNER_NOTICE),
#: в HTML — с переводами строк.
NOTICE_HTML = OWNER_NOTICE.replace("\n", "<br>\n")

_LOGIN_BODY = """<body class="login-body">
  <form class="login-card" method="post" action="/login" autocomplete="off">
    <div class="login-title">SKY-GRAFANA.RMRP</div>
    <div class="login-sub">Введите код доступа, чтобы открыть дашборд</div>
    <label class="login-label" for="pin">Код доступа</label>
    <input class="login-input" id="pin" name="pin" type="password"
           autocomplete="off" autofocus spellcheck="false">
    <div class="login-error">{{error}}</div>
    <button class="login-btn" type="submit">Войти</button>
    <div class="login-owner">""" + NOTICE_HTML + """</div>
  </form>"""

#: Страница входа; ``{{error}}`` заменяется сервером на текст ошибки (или пусто).
LOGIN_PAGE: str = _document("sky-grafana.rmrp — вход", _BASE_CSS + _LOGIN_CSS, _LOGIN_BODY)

# --- дашборд ---------------------------------------------------------------

_DASH_CSS = """
.top {
  display: flex;
  align-items: baseline;
  gap: 16px;
  flex-wrap: wrap;
  padding: 20px 26px 16px;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
}
.brand { font-size: 20px; font-weight: 700; letter-spacing: 1px; }
.sub { color: var(--muted); font-size: 13px; }
.conn { margin-left: auto; font-size: 12px; color: var(--muted); }
.conn.ok { color: var(--ok); }
.conn.bad { color: var(--danger); }
main { padding: 18px 26px 8px; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 14px;
}
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 18px;
}
.card-title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 1.2px;
  color: var(--muted);
}
.card-title.accent { color: var(--accent); }
.big { margin-top: 12px; font-size: 30px; font-weight: 700; }
.muted { margin-top: 6px; font-size: 13px; color: var(--muted); }
.pcts { margin-top: 8px; font-size: 13px; }
.track {
  height: 8px;
  margin-top: 14px;
  background: var(--bar);
  border-radius: 5px;
  overflow: hidden;
}
.fill { height: 100%; background: var(--accent); border-radius: 5px; }
.fill.ok { background: var(--ok); }
.chip {
  display: inline-block;
  margin-top: 12px;
  padding: 4px 10px;
  border-radius: 7px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 12px;
  font-weight: 600;
}
.chip.ok { background: var(--ok-soft); color: var(--ok); }
.chip.warn { background: var(--warn-soft); color: var(--warn); }
.chip.off { background: var(--bar); color: var(--muted); }
.flags {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  margin-top: 14px;
}
.flags .chip { margin-top: 0; }
.chart { margin-top: 14px; }
.cols {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  margin-top: 14px;
  overflow-x: auto;
}
.col {
  flex: 1 1 0;
  min-width: 56px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
}
.col-val { font-size: 12px; }
.col-track {
  width: 30px;
  height: 130px;
  background: var(--bar);
  border-radius: 6px;
  display: flex;
  align-items: flex-end;
  overflow: hidden;
}
.col-fill { width: 100%; background: var(--bar); border-radius: 6px 6px 0 0; }
.col-fill.on { background: var(--accent); }
.col-lab { font-size: 12px; font-weight: 600; color: var(--muted); }
.col-rep { font-size: 11px; color: var(--muted); }
.empty { padding: 24px 0; font-size: 13px; color: var(--muted); }
footer { padding: 12px 26px 24px; font-size: 12px; color: var(--muted); }"""

# JavaScript — без шаблонизатора и внешних библиотек: только DOM и fetch.
_DASH_JS = """'use strict';

var POLL_MS = 3000;

function el(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  var node = el(id);
  if (node) {
    node.textContent = value;
  }
}

function setFill(id, percent, done) {
  var node = el(id);
  if (!node) {
    return;
  }
  var width = Math.max(0, Math.min(100, Number(percent) || 0));
  node.style.width = width + '%';
  node.className = done ? 'fill ok' : 'fill';
}

function setChip(id, value, state) {
  var node = el(id);
  if (!node) {
    return;
  }
  node.textContent = value;
  node.className = state;
}

function num(value) {
  var number = Number(value);
  return isFinite(number) ? Math.round(number) : 0;
}

function hm(seconds) {
  var total = Math.max(0, num(seconds));
  var hours = Math.floor(total / 3600);
  var minutes = Math.floor((total % 3600) / 60);
  return hours + ':' + (minutes < 10 ? '0' + minutes : String(minutes));
}

function duration(seconds) {
  var total = Math.max(0, num(seconds));
  var hours = Math.floor(total / 3600);
  var minutes = Math.floor((total % 3600) / 60);
  return hours + ' ч ' + (minutes < 10 ? '0' + minutes : String(minutes)) + ' мин';
}

function todayTime(seconds) {
  return num(seconds) >= 3600 ? hm(seconds) : duration(seconds);
}

function renderDays(days) {
  var box = el('days');
  if (!box) {
    return;
  }
  var list = Array.isArray(days) ? days.slice(0, 14) : [];
  var maxSeconds = 1;
  list.forEach(function (day) {
    var seconds = num(day && day.seconds);
    if (seconds > maxSeconds) {
      maxSeconds = seconds;
    }
  });
  while (box.firstChild) {
    box.removeChild(box.firstChild);
  }
  if (!list.length) {
    var empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = 'нет данных за последние дни';
    box.appendChild(empty);
    return;
  }
  list.forEach(function (day) {
    var seconds = Math.max(0, num(day && day.seconds));
    var reports = Math.max(0, num(day && day.reports));
    var label = String((day && (day.label || day.date)) || '');

    var col = document.createElement('div');
    col.className = 'col';

    var value = document.createElement('div');
    value.className = 'col-val';
    value.textContent = hm(seconds);

    var track = document.createElement('div');
    track.className = 'col-track';
    var fill = document.createElement('div');
    fill.className = seconds > 0 ? 'col-fill on' : 'col-fill';
    fill.style.height = Math.max(2, Math.round(seconds / maxSeconds * 100)) + '%';
    track.appendChild(fill);

    var lab = document.createElement('div');
    lab.className = 'col-lab';
    lab.textContent = label;

    var rep = document.createElement('div');
    rep.className = 'col-rep';
    rep.textContent = reports + ' обр.';

    col.appendChild(value);
    col.appendChild(track);
    col.appendChild(lab);
    col.appendChild(rep);
    box.appendChild(col);
  });
}

function render(status) {
  var s = (status && typeof status === 'object') ? status : {};
  var today = (s.today && typeof s.today === 'object') ? s.today : {};
  var week = (s.week_stats && typeof s.week_stats === 'object') ? s.week_stats : {};
  var streak = (s.streak && typeof s.streak === 'object') ? s.streak : {};
  var flags = (s.flags && typeof s.flags === 'object') ? s.flags : {};

  var head = [];
  if (s.date) {
    head.push(String(s.date));
  }
  if (s.weekday) {
    head.push(String(s.weekday));
  }
  if (s.week) {
    head.push('неделя ' + String(s.week));
  }
  setText('sub', head.length ? head.join(' • ') : 'sky-grafana.rmrp');

  // СЕГОДНЯ
  var seconds = num(today.seconds);
  setText('today-time', todayTime(seconds));
  setText('today-reports', 'обращения ' + num(today.reports));
  var plan = num(today.plan_seconds);
  var planPercent = plan > 0 ? seconds / plan * 100 : 0;
  setFill('today-bar', planPercent, plan > 0 && planPercent >= 100);
  if (plan > 0) {
    setChip('today-chip', Math.round(planPercent) + '% плана',
            planPercent >= 100 ? 'chip ok' : 'chip');
  } else {
    setChip('today-chip', 'без плана', 'chip off');
  }

  // НЕДЕЛЯ
  setText('week-hours', hm(week.seconds));
  setText('week-reports', 'обращения ' + num(week.reports));
  var hoursPercent = num(week.hours_percent);
  var reportsPercent = num(week.reports_percent);
  setText('week-pcts', hoursPercent + '% часов • ' + reportsPercent + '% обращений');
  setFill('week-bar', hoursPercent, false);

  // СТРИК
  setText('streak-days', num(streak.days) + ' дн.');
  var done = !!streak.today_done;
  setChip('streak-state', done ? 'выполнено' : 'в процессе',
          done ? 'chip ok' : 'chip warn');

  // СТАТУС
  setChip('flag-duty', flags.duty ? 'дежурство вкл' : 'дежурство выкл',
          flags.duty ? 'chip ok' : 'chip off');
  setChip('flag-game', flags.game ? 'игра запущена' : 'игра не запущена',
          flags.game ? 'chip ok' : 'chip off');
  setChip('flag-count', flags.counting ? 'онлайн считается' : 'онлайн не считается',
          flags.counting ? 'chip ok' : 'chip off');

  renderDays(s.days);
}

function connOk() {
  var node = el('conn');
  if (!node) {
    return;
  }
  var now = new Date();
  var hours = now.getHours();
  var minutes = now.getMinutes();
  node.textContent = 'обновлено ' +
    (hours < 10 ? '0' + hours : hours) + ':' +
    (minutes < 10 ? '0' + minutes : minutes);
  node.className = 'conn ok';
}

function connFail() {
  var node = el('conn');
  if (!node) {
    return;
  }
  node.textContent = 'нет связи с трекером';
  node.className = 'conn bad';
}

function tick() {
  fetch('/api/status', { cache: 'no-store' })
    .then(function (response) {
      if (response.status === 401) {
        window.location.href = '/';
        return null;
      }
      if (!response.ok) {
        throw new Error('bad status');
      }
      return response.json();
    })
    .then(function (data) {
      if (data === null) {
        return;
      }
      render(data);
      connOk();
    })
    .catch(function () {
      connFail();
    });
}

tick();
window.setInterval(tick, POLL_MS);
"""

# --- вкладки «Дашборд · Хелпер · Правила RMRP» -----------------------------

_VIEW_CSS = """
/* шапка с вкладками */
.tabs { display: flex; gap: 2px; flex-wrap: wrap; }
.tab {
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--muted);
  border-radius: 0;
  padding: 9px 13px;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.8px;
  text-transform: uppercase;
  cursor: pointer;
}
.tab:hover { color: var(--text); }
.tab.active { background: transparent; border-bottom-color: var(--accent); color: var(--accent); }
.tab-n {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 8px;
  background: var(--badge);
  color: var(--muted);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0;
}
.tab.active .tab-n { background: var(--badge-active); color: var(--accent); }
.view[hidden] { display: none; }

/* хелпер: цветные карточки разделов */
.help-intro { color: var(--muted); font-size: 13px; margin: 0 0 14px; }
.help-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 14px;
}
.help-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-top: 3px solid var(--c, var(--accent));
  border-radius: 12px;
  padding: 16px 18px 14px;
}
.help-card:hover { border-color: var(--c, var(--accent)); }
.help-title { font-size: 15px; font-weight: 700; color: var(--c, var(--accent)); }
.help-body { margin-top: 6px; font-size: 14px; }
.help-body .note { transition: filter 0.15s ease; }
.help-body .note:hover { filter: brightness(1.1); }
.help-body td { font-size: 13.5px; }

/* эффект: мягкое свечение точек под курсором.
   top/left обязательны: без них position:fixed ставит элемент там, где он
   встал в потоке, — то есть в самом конце длинного <body>, за пределами
   экрана. Курсор был не виден вовсе, а системный уже был скрыт. */
.sky-cursor-dot {
  position: fixed;
  top: 0; left: 0;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--accent);
  pointer-events: none;
  z-index: 99999;
  opacity: 0.9;
}
.sky-cursor-ring {
  position: fixed;
  top: 0; left: 0;
  width: 32px; height: 32px;
  border-radius: 50%;
  border: 2px solid var(--accent);
  pointer-events: none;
  z-index: 99998;
  opacity: 0.7;
}

/* Белый кружок (вид по умолчанию) — с тёмной обводкой, чтобы был виден
   и на светлых превью, и на тёмном фоне. */
.sky-cursor-dot.white {
  width: 14px; height: 14px;
  background: #ffffff;
  box-shadow: 0 0 0 1.5px rgba(0, 0, 0, 0.55), 0 0 10px rgba(255, 255, 255, 0.35);
  opacity: 1;
}

/* дождь: тонкие наклонные штрихи на фоне, под всем содержимым */
#sky-rain {
  position: fixed;
  inset: 0;
  z-index: -1;
  pointer-events: none;
}

/* правила RMRP: поиск и карточки в стиле MIDNIGHT */
.rules-head {
  display: flex;
  gap: 14px;
  align-items: center;
  flex-wrap: wrap;
  margin: 4px 0 20px;
}
.rules-q {
  flex: 1 1 300px;
  min-width: 240px;
  background: var(--field);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 11px 14px;
  color: var(--text);
  font-family: inherit;
  font-size: 14px;
  outline: none;
}
.rules-q:focus { border-color: var(--accent); }
.rules-q::placeholder { color: var(--muted); }
.rules-count { color: var(--muted); font-size: 13px; }
.rules-empty { color: var(--muted); padding: 14px 2px; font-size: 14px; }

/* группа правил — как «Combat», «Visuals» в MIDNIGHT */
.cat { margin: 0 0 22px; }
.cat-head {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0 0 10px;
  padding: 0 2px;
}
.cat-title {
  color: var(--muted);
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 1.3px;
  text-transform: uppercase;
}
.cat-n {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--badge);
  color: var(--muted);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
}
.cat-rules { display: flex; flex-direction: column; gap: 8px; }

/* карточка одного правила */
.rule-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  transition: border-color 0.12s ease, background 0.12s ease;
}
.rule-card:hover { background: var(--tab-active); border-color: var(--accent); }
a.rule {
  display: block;
  color: var(--text);
  font-size: 14px;
  font-weight: 600;
  text-decoration: none;
}
a.rule:hover { color: var(--accent); }
a.rule:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
  border-radius: 4px;
}
.rule-snip {
  display: block;
  margin-top: 6px;
  color: var(--muted);
  font-size: 12.5px;
  line-height: 1.5;
}
.hit {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 700;
  border-radius: 3px;
  padding: 0 2px;
}
"""

_VIEW_JS = """
function vNorm(value) {
  return String(value === null || value === undefined ? '' : value)
    .toLowerCase().replace(/ё/g, 'е');
}

function vEsc(value) {
  return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function vStem(word) {
  // «война» и «войны» — общая основа «вой» (как в app.help.data).
  return word.length > 3 ? word.slice(0, 3) : word;
}

// Слова, из-за которых поиск впустую. Зеркало STOP_WORDS в app.help.data:
// «как наказать за спавн» должен находить «спавн», а не требовать ещё и «как».
var V_STOP_WORDS = {
  'не': 1, 'и': 1, 'в': 1, 'во': 1, 'на': 1, 'с': 1, 'со': 1, 'по': 1,
  'за': 1, 'от': 1, 'до': 1, 'из': 1, 'как': 1, 'что': 1, 'для': 1,
  'это': 1, 'то': 1, 'же': 1, 'а': 1, 'но': 1, 'у': 1, 'о': 1, 'об': 1,
  'их': 1, 'его': 1, 'мне': 1, 'можно': 1, 'нужно': 1, 'быть': 1,
  'если': 1, 'или': 1, 'там': 1, 'при': 1, 'над': 1, 'под': 1, 'про': 1,
  'все': 1, 'всё': 1, 'уже': 1, 'ещё': 1, 'еще': 1, 'бы': 1, 'ли': 1,
  'ну': 1, 'да': 1, 'нет': 1, 'раз': 1, 'два': 1, 'три': 1
};

function vWords(query) {
  var words = vNorm(query).split(/\\s+/).filter(function (w) { return w.length > 0; });
  var kept = words.filter(function (w) { return !V_STOP_WORDS[w]; });
  return kept.length ? kept : words;   // запрос только из служебных — ищем как есть
}

function vIsWord(ch) {
  // Как str().isalnum() в app.help.data — с учётом заглавных (сниппет режет сырой текст).
  return ch !== '' && ch !== undefined && /[0-9a-zа-яё]/i.test(ch);
}

function vPrefixIn(needle, haystack) {
  // Основа должна начинать какое-нибудь слово: «ко» находит «ко организации»,
  // но не «игроков» (то же правило в app.help.data.rule_matches).
  var at = haystack.indexOf(needle);
  while (at >= 0) {
    if (at === 0 || !vIsWord(haystack.charAt(at - 1))) {
      return true;
    }
    at = haystack.indexOf(needle, at + 1);
  }
  return false;
}

function vHl(text, stems) {
  if (!stems.length) {
    return vEsc(text);
  }
  var low = vNorm(text);
  var ranges = [];
  for (var i = 0; i < stems.length; i++) {
    var word = stems[i];
    var from = 0;
    var at = low.indexOf(word, from);
    while (at >= 0) {
      var start = at;
      var end = at + word.length;
      while (start > 0 && vIsWord(low.charAt(start - 1))) {
        start--;
      }
      while (end < low.length && vIsWord(low.charAt(end))) {
        end++;
      }
      ranges.push([start, end]);
      from = at + word.length;
      at = low.indexOf(word, from);
    }
  }
  if (!ranges.length) {
    return vEsc(text);
  }
  ranges.sort(function (a, b) { return a[0] - b[0]; });
  var merged = [];
  for (var j = 0; j < ranges.length; j++) {
    var range = ranges[j];
    var last = merged[merged.length - 1];
    if (last && range[0] <= last[1]) {
      if (range[1] > last[1]) { last[1] = range[1]; }
    } else {
      merged.push([range[0], range[1]]);
    }
  }
  var out = '';
  var pos = 0;
  for (var k = 0; k < merged.length; k++) {
    out += vEsc(text.slice(pos, merged[k][0]));
    out += '<span class="hit">' + vEsc(text.slice(merged[k][0], merged[k][1])) + '</span>';
    pos = merged[k][1];
  }
  return out + vEsc(text.slice(pos));
}

function vWordHits(stem, hay) {
  // [сколько слов начинается с stem, позиция первого] — как _word_hits в app.help.data.
  var count = 0, first = -1;
  var at = hay.indexOf(stem);
  while (at >= 0) {
    if (at === 0 || !vIsWord(hay.charAt(at - 1))) {
      if (count === 0) { first = at; }
      count++;
    }
    at = hay.indexOf(stem, at + 1);
  }
  return [count, first];
}

function vInText(stem) {
  // Три буквы и цифры ищем в полном тексте, двухбуквенные — только в «шапке».
  return stem.length >= 3 || /^[0-9]+$/.test(stem);
}

// Слова из двух букв ищем по тексту, только если они редкие: «DM» полезно,
// а «по» находит всё подряд. Порог тот же, что в app.help.data.
var V_COMMON_LIMIT = 14;

function vShortStems(stems) {
  var allow = {};
  var cards = document.querySelectorAll('.rule-card');
  for (var i = 0; i < stems.length; i++) {
    var s = stems[i];
    if (s.length !== 2) { continue; }
    var hits = 0;
    for (var c = 0; c < cards.length; c++) {
      var link = cards[c].querySelector('.rule');
      var low = vNorm((link && link.getAttribute('data-x')) || '');
      if (low && vWordHits(s, low)[0]) { hits++; }
      if (hits > V_COMMON_LIMIT) { break; }
    }
    if (hits > 0 && hits <= V_COMMON_LIMIT) { allow[s] = true; }
  }
  return allow;
}

function vRank(stems, title, key, low, allowShort) {
  // Зеркало match_rank: 0 пусто, 1 заголовок, 2 категория/синонимы, 3 текст, −1 мимо.
  if (!stems.length) { return 0; }
  var j;
  for (j = 0; j < stems.length; j++) {
    if (!vPrefixIn(stems[j], title)) { break; }
  }
  if (j === stems.length) { return 1; }
  for (j = 0; j < stems.length; j++) {
    if (!vPrefixIn(stems[j], key)) { break; }
  }
  if (j === stems.length) { return 2; }
  if (!low) { return -1; }
  var deep = false;
  for (j = 0; j < stems.length; j++) {
    if (vInText(stems[j])) { deep = true; }
  }
  var inText = function (s) {
    if (vInText(s)) { return true; }
    if (deep && stems.length > 1) { return true; }
    if (s.length === 2) { return !!(allowShort && allowShort[s]); }
    return false;
  };
  for (j = 0; j < stems.length; j++) {
    if (!(inText(stems[j]) && vPrefixIn(stems[j], low))) { break; }
  }
  if (j === stems.length) { return 3; }
  for (j = 0; j < stems.length; j++) {
    if (!(vPrefixIn(stems[j], key) ||
          (inText(stems[j]) && vPrefixIn(stems[j], low)))) {
      break;
    }
  }
  return j === stems.length ? 3 : -1;
}

// Одно упоминание слова в стольких символах — случайность, а не тема правила.
// Порог тот же, что TEXT_NOISE в app.help.data.
var V_TEXT_NOISE = 15000;

function vCount(hay, needle) {
  // Сколько раз needle встречается в hay — как str.count в Python.
  if (!needle) { return 0; }
  var n = 0;
  var at = hay.indexOf(needle);
  while (at >= 0) {
    n++;
    at = hay.indexOf(needle, at + needle.length);
  }
  return n;
}

function vTextHits(low, stems) {
  // Сколько раз основы запроса встретились в тексте правила.
  if (!low) { return 0; }
  var hits = 0;
  for (var i = 0; i < stems.length; i++) {
    if (vInText(stems[i])) { hits += vCount(low, stems[i]); }
  }
  return hits;
}

function vTextOnly(stems, title, key) {
  // Ни одно слово запроса не в заголовке и не в категории/синонимах:
  // такие правила не отсекаем никогда, там слово точно не случайное.
  if (!stems.length) { return false; }
  for (var i = 0; i < stems.length; i++) {
    if (vPrefixIn(stems[i], title) || vPrefixIn(stems[i], key)) { return false; }
  }
  return true;
}

function vRel(stems, title, key, low) {
  // Зеркало relevance: чем ближе правило к тому, что искали, тем больше число.
  // Без этого правила шли в порядке, в каком лежат в странице, и сверху
  // оказывались гигантские документы с парой случайных упоминаний.
  if (!stems.length) { return 0; }
  var score = 0;
  var i;
  for (i = 0; i < stems.length; i++) {
    if (vPrefixIn(stems[i], title)) { score += 1000; }
    if (vPrefixIn(stems[i], key)) { score += 400; }
  }
  if (!low) { return score; }
  var length = low.length;
  var hits = vTextHits(low, stems);
  if (hits) {
    // Плотность с мягким штрафом за размер: короткое правило с тем же числом
    // упоминаний впереди, но общее не уходит в конец из-за длины.
    score += 100 * hits / (1 + Math.sqrt(length) / 40);
    var first = -1;
    for (i = 0; i < stems.length; i++) {
      if (!vInText(stems[i])) { continue; }
      var at = low.indexOf(stems[i]);
      if (at >= 0 && (first < 0 || at < first)) { first = at; }
    }
    if (first >= 0) { score += 60 * (1 - first / Math.max(length, 1)); }
  }
  return score;
}

function vNoise(low, stems) {
  // «Случайно» = совпало только текстом и реже, чем раз в V_TEXT_NOISE
  // символов: одно упоминание в гиганте — не тема правила.
  if (!low) { return false; }
  var hits = vTextHits(low, stems);
  return hits > 0 && hits * V_TEXT_NOISE < low.length;
}

function vSnippet(raw, low, stems, width, allowShort) {
  // Зеркало rule_snippet: окно вокруг самой редкой основы, края — по словам.
  if (!raw) { return ''; }
  var start = 0, end = Math.min(raw.length, width);
  if (low && low.length === raw.length) {
    var best = null;
    for (var s = 0; s < stems.length; s++) {
      if (!vInText(stems[s]) && !(allowShort && allowShort[stems[s]])) {
        continue;   // зеркало rule_snippet: в окно берём только «годные» основы
      }
      var hit = vWordHits(stems[s], low);
      if (hit[0] > 0 && (best === null || hit[0] < best[0] ||
                         (hit[0] === best[0] && hit[1] < best[1]))) {
        best = hit;
      }
    }
    if (best) {
      var at = best[1];
      start = Math.max(0, at - 60);
      end = Math.min(raw.length, Math.max(at + width - 60, at + 40));
      while (start > 0 && vIsWord(raw.charAt(start))) { start--; }
    }
  }
  while (end < raw.length && vIsWord(raw.charAt(end))) { end++; }
  var piece = raw.slice(start, end).replace(/^\\s+|\\s+$/g, '');
  if (start > 0) { piece = '…' + piece; }
  if (end < raw.length) { piece = piece + '…'; }
  return piece;
}

// Буквы, которыми может быть опечатка.
var V_ALPHABET = 'абвгдежзийклмнопрстуфхцчшщыэюяabcdefghijklmnopqrstuvwxyz0123456789';
// Допуск работает только по коротким словам. Длинное слово и так ищется по
// трём первым буквам (vStem), поэтому опечатка после третьей буквы находится
// и без ухищрений — а вот опечатка в первых трёх у длинного слова даёт ту же
// основу и находится точно так же.
var V_FUZZY_MAX = 8;
// Короче этого опечатки не ищем: «слев» на расстоянии одной буквы от «слев» —
// это уже другое слово, а не опечатка.
var V_FUZZY_MIN = 4;
// Меньше этого числа точных совпадений — ищем ещё и с опечатками.
var V_FUZZY_MIN_EXACT = 3;
var V_BALL_CACHE = {};

function vTypoBall(word) {
  // Все варианты слова с одной опечаткой: замена, забытая или лишняя буква,
  // перестановка соседних.
  if (word.length < V_FUZZY_MIN || word.length > V_FUZZY_MAX) { return null; }
  if (V_BALL_CACHE[word]) { return V_BALL_CACHE[word]; }
  var out = {}, i, a, ch, head, tail;
  for (i = 0; i < word.length; i++) {
    head = word.slice(0, i);
    tail = word.slice(i + 1);
    for (a = 0; a < V_ALPHABET.length; a++) {
      ch = V_ALPHABET.charAt(a);
      out[head + ch + tail] = 1;        // замена буквы
      // Лишняя буква вставляется перед word[i], поэтому хвост не теряется:
      // без word.charAt(i) получались бы обрезки в одну букву, а такие есть
      // в любом заголовке — и поиск находил вообще всё.
      out[head + ch + word.charAt(i) + tail] = 1;
    }
    out[head + tail] = 1;           // забыли букву
  }
  for (i = 0; i + 1 < word.length; i++) {
    out[word.slice(0, i) + word.charAt(i + 1) + word.charAt(i) +
        word.slice(i + 2)] = 1;     // переставили местай
  }
  delete out[word];
  V_BALL_CACHE[word] = out;
  return out;
}

function vBalls(words) {
  var out = [];
  for (var i = 0; i < words.length; i++) {
    var got = vTypoBall(words[i]);
    if (got) { out.push(got); }
  }
  return out;
}

function vWords2(card, low) {
  // Слова текста правила, разложенные по первым двум буквам; кэш на карточке.
  // Раскладка нужна, чтобы проверить тысячу вариантов с опечаткой не перебором
  // всего текста, а обращением к маленьким множествам.
  if (card._words2) { return card._words2; }
  var buckets = {};
  var parts = low.split(/\\s+/);
  for (var i = 0; i < parts.length; i++) {
    var w = parts[i];
    if (w.length >= V_FUZZY_MIN && w.length <= V_FUZZY_MAX) {
      var key = w.slice(0, 2);
      if (!buckets[key]) { buckets[key] = {}; }
      buckets[key][w] = 1;
    }
  }
  card._words2 = buckets;
  return buckets;
}

function vFuzzyHit(ball, card, low, title) {
  for (var variant in ball) {
    var bucket = card._words2 ? card._words2[variant.slice(0, 2)] : null;
    if (bucket && bucket[variant]) { return true; }
    if (title.indexOf(variant) >= 0) { return true; }
  }
  return false;
}

function applyRules() {
  var input = el('rules-q');
  if (!input) {
    return;
  }
  var words = vWords(input.value);
  var stems = [];
  for (var w = 0; w < words.length; w++) {
    stems.push(vStem(words[w]));
  }
  var nodes = document.querySelectorAll('.rule-card');
  // Редкие двухбуквенные слова («DM», «дп») ищем по тексту, частые — нет.
  var allowShort = vShortStems(stems);
  var shown = 0;
  // Первый проход: ранг, релевантность и «шум» каждого правила — как в
  // app.help.data.filter_rules. Случайные совпадения убираем только если
  // остаётся хоть что-то, иначе на узком запросе был бы пустой экран.
  var okTotal = 0, noiseTotal = 0, i, card, link;
  for (i = 0; i < nodes.length; i++) {
    card = nodes[i];
    link = card.querySelector('.rule');
    if (!link) { continue; }
    var t0 = vNorm(link.getAttribute('data-t') || '');
    var k0 = link.getAttribute('data-k') || '';
    var r0 = link.getAttribute('data-x') || '';
    var l0 = r0 ? vNorm(r0) : '';
    card._rank = vRank(stems, t0, k0, l0, allowShort);
    if (card._rank < 0) { card._rank = 99; }
    card._rel = vRel(stems, t0, k0, l0);
    card._noise = card._rank === 3 && vTextOnly(stems, t0, k0) && vNoise(l0, stems);
    card._idx = i;
    if (card._rank < 99) {
      okTotal++;
      if (card._noise) { noiseTotal++; }
    }
  }
  var dropNoise = noiseTotal > 0 && noiseTotal < okTotal;

  for (i = 0; i < nodes.length; i++) {
    card = nodes[i];
    link = card.querySelector('.rule');
    if (!link) { continue; }
    var title = link.getAttribute('data-t') || '';
    var raw = link.getAttribute('data-x') || '';
    var low = raw ? vNorm(raw) : '';
    var ok = card._rank < 99 && !(dropNoise && card._noise);
    card.style.display = ok ? '' : 'none';
    if (ok) {
      shown++;
      link.innerHTML = vHl(title, stems);
      var text = vSnippet(raw, low, stems, 190, allowShort);
      var snip = card.querySelector('.rule-snip');
      if (text) {
        if (!snip) {
          snip = document.createElement('span');
          snip.className = 'rule-snip';   // вид даёт CSS (стиль MIDNIGHT)
          card.appendChild(snip);
        }
        snip.style.display = 'block';
        snip.innerHTML = vHl(text, stems);
      } else if (snip) {
        snip.style.display = 'none';
      }
    }
  }

  // Опечатки. Точных совпадений почти нет — значит, человек написал не так,
  // как в правилах: «савн» вместо «спавн». Сравниваем начала слов, а не
  // трёхбуквенные основы: по основам «зар» находилось вообще всё.
  if (shown < V_FUZZY_MIN_EXACT) {
    var balls = vBalls(words);
    if (balls.length) {
      for (var f = 0; f < nodes.length; f++) {
        var card2 = nodes[f];
        if (card2.style.display !== 'none') { continue; }
        var link2 = card2.querySelector('.rule');
        if (!link2) { continue; }
        var low2 = vNorm(link2.getAttribute('data-x') || '');
        if (!low2) { continue; }
        var title2 = vNorm(link2.getAttribute('data-t') || '');
        vWords2(card2, low2);
        var found2 = balls.length > 0;
        for (var b = 0; b < balls.length && found2; b++) {
          // Нужно, чтобы нашлось каждое слово запроса: «допрос 60» найдёт
          // допросы, где «60» тоже встречается (как в app.help.data).
          found2 = vFuzzyHit(balls[b], card2, low2, title2);
        }
        if (!found2) { continue; }
        card2._rank = 4;                 // после точных совпадений
        card2._rel = vRel(stems, title2, link2.getAttribute('data-k') || '', low2);
        card2._noise = false;
        card2.style.display = '';
        shown++;
        var raw2 = link2.getAttribute('data-x') || '';
        var text2 = vSnippet(raw2, low2, stems, 190, allowShort);
        var snip2 = card2.querySelector('.rule-snip');
        if (text2) {
          if (!snip2) {
            snip2 = document.createElement('span');
            snip2.className = 'rule-snip';
            card2.appendChild(snip2);
          }
          snip2.style.display = 'block';
          snip2.innerHTML = vEsc(text2);
        } else if (snip2) {
          snip2.style.display = 'none';
        }
      }
    }
  }

  var cats = document.querySelectorAll('.cat');
  var visibleCats = 0;
  var catList = [];
  for (var c = 0; c < cats.length; c++) {
    var cat = cats[c];
    var visible = 0;
    var best = 99;
    var bestRel = 0;
    var cards = cat.querySelectorAll('.rule-card');
    var order = [];
    for (var r = 0; r < cards.length; r++) {
      order.push(cards[r]);
      if (cards[r].style.display !== 'none') {
        visible++;
        if (cards[r]._rank < best) {
          best = cards[r]._rank;
          bestRel = cards[r]._rel;
        } else if (cards[r]._rank === best && cards[r]._rel > bestRel) {
          bestRel = cards[r]._rel;   // в категории важнее правило поближе к запросу
        }
      }
    }
    if (visible) {
      visibleCats++;
    }
    cat.style.display = visible ? '' : 'none';
    var count = cat.querySelector('.cat-n');
    if (count) {
      count.textContent = String(visible);
    }
    // Ранг важнее всего (заголовок раньше текста), дальше — релевантность,
    // и только потом порядок в файле — как в app.help.data.filter_rules.
    order.sort(function (a, b) {
      return (a._rank - b._rank) || (b._rel - a._rel) || (a._idx - b._idx);
    });
    var box = cat.querySelector('.cat-rules');
    for (var o = 0; o < order.length; o++) {
      box.appendChild(order[o]);
    }
    cat._best = visible ? best : 99;
    cat._bestRel = visible ? bestRel : 0;
    cat._idx = c;
    catList.push(cat);
  }

  var host = cats.length ? cats[0].parentNode : null;
  var empty = el('rules-empty');
  catList.sort(function (a, b) {
    return (a._best - b._best) || (b._bestRel - a._bestRel) ||
           (a._idx - b._idx);
  });
  if (host) {
    for (var n = 0; n < catList.length; n++) {
      host.appendChild(catList[n]);
    }
    if (empty) { host.appendChild(empty); }   // плашка «ничего не нашлось» — последней
  }

  var total = el('rules-count');
  if (total) {
    total.textContent = words.length
      ? ('Найдено: ' + shown)
      : (shown + ' правил в ' + visibleCats + ' разделах');
  }
  if (empty) {
    empty.hidden = shown > 0;
  }
}

function showView(name) {
  var views = document.querySelectorAll('.view');
  for (var i = 0; i < views.length; i++) {
    views[i].hidden = views[i].id !== 'view-' + name;
  }
  var tabs = document.querySelectorAll('.tab');
  for (var t = 0; t < tabs.length; t++) {
    tabs[t].classList.toggle('active', tabs[t].getAttribute('data-view') === name);
  }
  try {
    window.localStorage.setItem('sky-view', name);
  } catch (e) {
    // приватный режим — просто не запоминаем
  }
  if (name === 'rules') {
    applyRules();
  }
  if (name === 'commands' && typeof applyCommands === 'function') {
    applyCommands();
  }
  if (name === 'events' && typeof applyEvents === 'function') {
    applyEvents();
  }
  if (name === 'transport' && typeof applyCatalog === 'function') {
    applyCatalog('transport');
  }
  if (name === 'weapon' && typeof applyCatalog === 'function') {
    applyCatalog('weapon');
  }
  if (name === 'gt' && typeof applyCatalog === 'function') {
    applyCatalog('gt');
  }
  if (name === 'staff' && typeof staffRefresh === 'function') {
    staffRefresh();
  }
  if (name === 'shots' && typeof shotsLoad === 'function') {
    shotsLoad();
  }
}

(function initViews() {
  var tabs = document.querySelectorAll('.tab');
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].addEventListener('click', function () {
      showView(this.getAttribute('data-view'));
    });
  }
  var input = el('rules-q');
  if (input) {
    // Ищем не на каждую букву: пересборка подсветки по 236К символов
    // подтормаживала на длинных запросах.
    var rulesTimer = null;
    var queueRules = function () {
      if (rulesTimer) { window.clearTimeout(rulesTimer); }
      rulesTimer = window.setTimeout(function () {
        rulesTimer = null;
        applyRules();
      }, 160);
    };
    input.addEventListener('input', queueRules);
    input.addEventListener('search', queueRules);
  }
  var saved = 'dash';
  try {
    saved = window.localStorage.getItem('sky-view') || 'dash';
  } catch (e) {
    saved = 'dash';
  }
  if (!document.getElementById('view-' + saved)) {
    saved = 'dash';
  }
  showView(saved);
  applyRules();
})();
"""

_CMDS_CSS = """
/* команды: список, страница команды, форма и права */
.cmd-list { display: flex; flex-direction: column; gap: 7px; }
.cmd-item {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  width: 100%; text-align: left; cursor: pointer;
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 9px; padding: 9px 12px;
  font-family: inherit; color: var(--text);
}
.cmd-item:hover { border-color: var(--accent); filter: brightness(1.1); }
.cmd-name {
  font-family: Consolas, 'Courier New', monospace;
  font-weight: 700; font-size: 14px; color: var(--accent);
}
.cmd-d { color: var(--muted); font-size: 13px; }
.cmd-dots { margin-left: auto; font-size: 11px; letter-spacing: 3px; }
.cmd-back {
  background: var(--bg); border: 1px solid var(--border); color: var(--muted);
  border-radius: 8px; padding: 7px 13px; font-family: inherit; font-size: 13px;
  cursor: pointer; margin-bottom: 10px;
}
.cmd-back:hover { color: var(--text); border-color: var(--accent); }
.cmd-title {
  font-family: Consolas, 'Courier New', monospace;
  font-size: 22px; font-weight: 700; color: var(--accent); margin: 2px 0 4px;
}
.cmd-about { font-size: 14px; margin: 0 0 8px; }
.cmd-alias { color: var(--muted); font-size: 13px; margin-bottom: 6px; }
.cmd-note {
  background: var(--bg); border-left: 4px solid var(--accent);
  border-radius: 8px; padding: 8px 11px; margin: 8px 0;
  color: var(--muted); font-size: 13px;
}
.cmd-sec {
  font-size: 12px; font-weight: 700; letter-spacing: 1px;
  color: var(--muted); margin: 16px 0 7px;
}
.cmd-box {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 12px 14px;
}
.cmd-field {
  display: grid; grid-template-columns: minmax(180px, 260px) 1fr;
  gap: 5px 12px; margin-bottom: 11px;
}
.cmd-lab { font-size: 13px; font-weight: 600; }
.cmd-tok {
  align-self: center; font-family: Consolas, monospace; font-size: 12.5px;
  color: var(--muted); background: var(--bg);
  border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px;
}
.cmd-input {
  background: var(--bg); border: 1px solid var(--border); border-radius: 7px;
  padding: 7px 9px; color: var(--text); font-family: Consolas, monospace;
  font-size: 13px; outline: none; width: 100%;
}
.cmd-input:focus { border-color: var(--accent); }
.cmd-hint { grid-column: 1 / -1; color: var(--muted); font-size: 12.5px; }
.cmd-preview {
  font-family: Consolas, monospace; font-size: 16px; font-weight: 700;
  color: var(--text); background: var(--bg);
  border: 1px dashed var(--accent); border-radius: 8px; padding: 10px 12px;
  word-break: break-all;
}
.cmd-copy {
  background: var(--bg); border: 1px solid var(--border); color: var(--muted);
  border-radius: 8px; padding: 7px 13px; font-family: inherit; font-size: 13px;
  cursor: pointer; margin-top: 8px;
}
.cmd-copy:hover { color: var(--text); border-color: var(--accent); }
.cmd-ranks { width: 100%; border-collapse: collapse; font-size: 13px; }
.cmd-ranks td { padding: 6px 8px; border-bottom: 1px solid var(--border); }
.cmd-ranks .lvl { color: var(--muted); width: 74px; }
.cmd-ranks .rid { font-family: Consolas, monospace; width: 210px; }
.cmd-ranks .grp { color: var(--muted); }
.state-always { color: #2ea043; }
.state-duty { color: #d29922; }
.state-never { color: #f85149; }
"""


_EVENTS_CSS = """
/* серверные события: категории, список событий, координаты и телепорт */
.evt-cat {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
  width: 100%; text-align: left; cursor: pointer;
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 10px; padding: 11px 13px;
  font-family: inherit; color: var(--text);
}
.evt-cat:hover { border-color: var(--accent); filter: brightness(1.1); }
.evt-cat-name { font-weight: 700; font-size: 15px; color: var(--accent); }
.evt-cat-n { color: var(--muted); font-size: 12px; }
.evt-back {
  background: var(--bg); border: 1px solid var(--border); color: var(--muted);
  border-radius: 8px; padding: 7px 13px; font-family: inherit; font-size: 13px;
  cursor: pointer; margin-bottom: 10px;
}
.evt-back:hover { color: var(--text); border-color: var(--accent); }
.evt-sec {
  font-size: 12px; font-weight: 700; letter-spacing: 1px;
  color: var(--muted); margin: 14px 0 7px;
}
.evt-item {
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 10px; padding: 11px 13px;
}
.evt-item-top { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.evt-title {
  background: none; border: none; padding: 0; cursor: pointer;
  font-family: inherit; font-size: 15px; font-weight: 700; color: var(--text);
}
.evt-title:hover { color: var(--accent); }
.evt-chip {
  font-size: 11.5px; color: var(--muted); background: var(--card);
  border: 1px solid var(--border); border-radius: 9px; padding: 2px 8px;
}
.evt-chip.alt { color: var(--accent); }
.evt-shot {
  display: block; width: auto; max-width: 100%; height: auto;
  border: 1px solid var(--border); border-radius: 8px; margin-top: 9px;
}
.evt-coords {
  font-family: Consolas, 'Courier New', monospace; font-size: 13.5px;
  color: var(--text); background: var(--card); border: 1px solid var(--border);
  border-radius: 8px; padding: 7px 10px; margin-top: 8px;
  word-break: break-all;
}
.evt-tp {
  display: inline-block; margin-top: 9px; padding: 7px 13px;
  font-family: inherit; font-size: 12.5px; font-weight: 700;
  color: var(--bg); background: var(--accent); border: none; border-radius: 8px;
  cursor: pointer;
}
.evt-tp:hover { filter: brightness(1.12); }
"""

_CATALOG_CSS = """
/* «Транспорт» и «Оружие»: таблицы из документации RMRP Study */
.cat-sec, .cat-back {
  font-family: inherit; font-size: 14px; cursor: pointer; text-align: left;
}
.cat-sec {
  display: block; width: 100%; background: var(--card); color: var(--text);
  border: 1px solid var(--border); border-radius: 9px;
  padding: 10px 12px; margin: 7px 0;
}
.cat-sec:hover, .cat-sec:focus-visible { border-color: var(--accent); outline: none; }
.cat-sec-n { color: var(--muted); font-size: 12px; font-weight: 400; }
.cat-back {
  background: transparent; color: var(--accent); border: 1px solid var(--border);
  border-radius: 8px; padding: 7px 12px; margin-bottom: 8px;
}
.cat-back:hover, .cat-back:focus-visible { border-color: var(--accent); outline: none; }
.cat-sec-head {
  color: var(--accent); font-size: 15px; font-weight: 700; margin: 2px 0 8px;
}
.cat-sec-name { color: var(--muted); font-size: 12px; margin-bottom: 4px; }
.cat-item {
  background: var(--card); border: 1px solid var(--border); border-radius: 9px;
  padding: 9px 12px; margin: 7px 0;
}
.cat-item-top { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.cat-name { color: var(--text); font-size: 15px; font-weight: 700; }
.cat-id {
  font-family: Consolas, 'Courier New', monospace; font-size: 12.5px;
  color: var(--accent); background: rgba(127, 127, 127, 0.12);
  border: 1px solid var(--border); border-radius: 9px; padding: 1px 7px;
}
.cat-cmd {
  display: block; width: 100%; text-align: left; margin-top: 7px;
  font-family: Consolas, 'Courier New', monospace; font-size: 13.5px;
  background: transparent; color: var(--muted); border: 1px dashed var(--border);
  border-radius: 7px; padding: 6px 9px; cursor: pointer;
}
.cat-cmd:hover, .cat-cmd:focus-visible {
  color: var(--accent); border-color: var(--accent); outline: none;
}
/* «Транспорт (Google)»: фото из Google-Таблицы и статус спавна */
.cat-photo {
  display: block; width: 100%; max-width: 360px; border-radius: 8px;
  border: 1px solid var(--border); margin: 0 0 8px 0;
}
.cat-spawn {
  font-size: 12.5px; margin-bottom: 6px;
}
.cat-spawn.ok { color: var(--good, #3fb950); }
.cat-spawn.no { color: var(--bad, #f85149); }
.cat-nocmd {
  font-size: 12.5px; color: var(--muted); margin-top: 7px;
}
"""


#: Зеркало app.commands.data.SYNONYMS — как человек ищет команду («кик»,
#: «тп», «блокировка») и как она называется на самом деле. Держат одинаковыми
#: tests/test_commands.py::test_synonyms_stay_in_sync_with_the_site.
V_CMD_SYNONYMS: dict[str, list[str]] = {
    "кик": ["kick"], "кикнуть": ["kick"], "выгнать": ["kick"],
    "мут": ["mute"], "мутить": ["mute"], "замутить": ["mute"],
    "бан": ["ban"], "забанить": ["ban"], "банить": ["ban"],
    "разбанить": ["unban"],
    "блокировка": ["ban", "mute"], "заблокировать": ["ban", "mute"],
    "предупреждение": ["warn"], "варн": ["warn"],
    "пред": ["pred"],
    "заморозить": ["freeze"], "заморозка": ["freeze"], "фриз": ["freeze"],
    "разморозить": ["unfreeze"],
    "телепорт": ["goto", "tp", "teleport"], "тп": ["goto", "tp", "teleport"],
    "телепортировать": ["goto", "teleport"],
    "убить": ["kill"], "килл": ["kill"],
    "здоровье": ["health", "hp"], "хп": ["health", "hp"], "лечение": ["health"],
    "броня": ["armor"], "броник": ["armor"],
    "оружие": ["gun"], "ствол": ["gun"],
    "машина": ["vehicle", "car"], "машину": ["vehicle", "car"],
    "транспорт": ["vehicle", "car"],
    "спавн": ["spawn"], "возродить": ["respawn"], "респавн": ["respawn"],
    "фракция": ["faction"], "лидер": ["leader"], "ранг": ["rank"],
    "деменшин": ["dimension"], "демка": ["dimension"],
    "гм": ["godmode"], "бессмертие": ["godmode"],
    "ноуклип": ["noclip"], "полет": ["noclip"],
    "невидимка": ["esp"], "видеть": ["esp"],
    "чат": ["mutechat", "chat"], "голос": ["mutevoice", "voice"],
    "ник": ["changename", "name"], "никнейм": ["changename", "name"],
    "деньги": ["money", "credits"], "кредиты": ["credits"],
    "предмет": ["item"], "хранилище": ["storage"], "кейс": ["case"],
    "ремонт": ["fixcar"],
    "убить всех": ["killall"], "все": ["all"],
}


_CMDS_JS = """
var V_CMD_SYNONYMS = {"кик": ["kick"], "кикнуть": ["kick"], "выгнать": ["kick"], "мут": ["mute"], "мутить": ["mute"], "замутить": ["mute"], "бан": ["ban"], "забанить": ["ban"], "банить": ["ban"], "разбанить": ["unban"], "блокировка": ["ban", "mute"], "заблокировать": ["ban", "mute"], "предупреждение": ["warn"], "варн": ["warn"], "пред": ["pred"], "заморозить": ["freeze"], "заморозка": ["freeze"], "фриз": ["freeze"], "разморозить": ["unfreeze"], "телепорт": ["goto", "tp", "teleport"], "тп": ["goto", "tp", "teleport"], "телепортировать": ["goto", "teleport"], "убить": ["kill"], "килл": ["kill"], "здоровье": ["health", "hp"], "хп": ["health", "hp"], "лечение": ["health"], "броня": ["armor"], "броник": ["armor"], "оружие": ["gun"], "ствол": ["gun"], "машина": ["vehicle", "car"], "машину": ["vehicle", "car"], "транспорт": ["vehicle", "car"], "спавн": ["spawn"], "возродить": ["respawn"], "респавн": ["respawn"], "фракция": ["faction"], "лидер": ["leader"], "ранг": ["rank"], "деменшин": ["dimension"], "демка": ["dimension"], "гм": ["godmode"], "бессмертие": ["godmode"], "ноуклип": ["noclip"], "полет": ["noclip"], "невидимка": ["esp"], "видеть": ["esp"], "чат": ["mutechat", "chat"], "голос": ["mutevoice", "voice"], "ник": ["changename", "name"], "никнейм": ["changename", "name"], "деньги": ["money", "credits"], "кредиты": ["credits"], "предмет": ["item"], "хранилище": ["storage"], "кейс": ["case"], "ремонт": ["fixcar"], "убить всех": ["killall"], "все": ["all"]};
function cmdPack() {
  return window.SKY_COMMANDS || { ranks: [], commands: [] };
}

function cmdState(letter) {
  return letter === 'G' ? 'always' : (letter === 'Y' ? 'duty' : 'never');
}

function cmdMark(letter) {
  return letter === 'G' ? '🟩' : (letter === 'Y' ? '🟨' : '🟥');
}

function cmdStateLabel(state) {
  if (state === 'always') { return '🟩 Всегда'; }
  if (state === 'duty') { return '🟨 Только на смене'; }
  return '🟥 Недоступна';
}

var CMD_WORD_RE = /[0-9A-Za-z_\\u0400-\\u04FF]/;
var CMD_SPLIT_RE = /[^0-9A-Za-z_\\u0400-\\u04FF]+/;

function cmdVariants(word) {
  // «кик» → ['кик', 'kick']: слово запроса остаётся первым, синоним
  // добавляется, а не заменяет (иначе «предупреждение» пропускает /pred).
  var extra = V_CMD_SYNONYMS[word];
  if (!extra) { return [word]; }
  return [word].concat(extra);
}

function cmdSameWord(a, b) {
  // «блокировка» ≈ «блокировку» (общая основа 8 букв), но
  // «предупреждение» ≉ «предмет» — общих 4 буквы мало.
  var shortest = a.length < b.length ? a.length : b.length;
  var shared = 0;
  while (shared < shortest && a.charAt(shared) === b.charAt(shared)) { shared++; }
  return shared >= 5 || (shared === shortest && shortest >= 4);
}

function cmdWholeWord(hay, needle) {
  var at = hay.indexOf(needle);
  while (at >= 0) {
    var before = at > 0 ? hay.charAt(at - 1) : '';
    var after = hay.charAt(at + needle.length);
    if (!CMD_WORD_RE.test(before) && !CMD_WORD_RE.test(after)) { return true; }
    at = hay.indexOf(needle, at + 1);
  }
  return false;
}

function cmdInName(word, name) {
  // Двухбуквенные ищем только по частям названия: «id» не должно
  // находить forbid_buy_chips, а «ban» — внутри infoban должно.
  var variants = cmdVariants(word);
  var parts = name.split('_');
  for (var i = 0; i < variants.length; i++) {
    var v = variants[i];
    for (var j = 0; j < parts.length; j++) {
      if (parts[j].indexOf(v) === 0) { return true; }
    }
    if (v.length >= 3 && name.indexOf(v) >= 0) { return true; }
  }
  return false;
}

function cmdInDesc(word, desc) {
  // Целым словом или по основе; короткие вроде «тп» в описание не лезут —
  // иначе «тп» находилось внутри слова «Отправить».
  var variants = cmdVariants(word);
  var pieces = desc.split(CMD_SPLIT_RE);
  for (var i = 0; i < variants.length; i++) {
    var v = variants[i];
    if (v.length < 3) { continue; }
    if (cmdWholeWord(desc, v)) { return true; }
    for (var j = 0; j < pieces.length; j++) {
      if (pieces[j] && cmdSameWord(v, pieces[j])) { return true; }
    }
  }
  return false;
}

function cmdAllInName(words, name) {
  for (var i = 0; i < words.length; i++) {
    if (!cmdInName(words[i], name)) { return false; }
  }
  return true;
}

function cmdAllInDesc(words, desc) {
  for (var i = 0; i < words.length; i++) {
    if (!cmdInDesc(words[i], desc)) { return false; }
  }
  return true;
}

function cmdStartsWithAny(name, variants) {
  if (name.indexOf(variants[0]) === 0) { return true; }
  for (var i = 0; i < variants.length; i++) {
    if (name.indexOf(variants[i]) === 0) { return true; }
  }
  return false;
}

function cmdSearch(query) {
  // Зеркало app.commands.data.search: регистр и слэш не важны, русское
  // слово находит латинскую команду, короткие слова не ловят мусор
  // из середины слов.
  var pack = cmdPack();
  var text = vNorm(query).replace(/^\\s+|\\s+$/g, '');
  if (!text) { return pack.commands.slice(); }
  if (text.charAt(0) === '/') { text = text.slice(1); }
  var words = text.split(/\\s+/).filter(function (w) { return w.length > 0; });
  var whole = cmdVariants(text);
  var exact = [], prefix = [], inside = [], byDesc = [];
  for (var i = 0; i < pack.commands.length; i++) {
    var command = pack.commands[i];
    var name = vNorm(command.n).slice(1);
    var desc = vNorm(command.d);
    var isExact = name === text;
    for (var e = 0; e < whole.length && !isExact; e++) {
      isExact = name === whole[e];
    }
    if (isExact) { exact.push(command); }
    else if (cmdStartsWithAny(name, whole.concat([text]))) { prefix.push(command); }
    else if (words.length && cmdAllInName(words, name)) { inside.push(command); }
    else if (words.length && cmdAllInDesc(words, desc)) { byDesc.push(command); }
  }
  var byLength = function (a, b) { return a.n.length - b.n.length; };
  inside.sort(byLength);
  byDesc.sort(byLength);
  return exact.concat(prefix, inside, byDesc);
}

function cmdStems(query) {
  var words = vNorm(query).split(/\\s+/).filter(function (w) { return w.length > 0; });
  var stems = [];
  for (var i = 0; i < words.length; i++) { stems.push(vStem(words[i])); }
  return stems;
}

function cmdRenderList() {
  var input = el('cmd-q');
  var list = el('cmd-list');
  if (!input || !list) { return; }
  var query = input.value;
  var stems = cmdStems(query.replace(/^\\//, ''));
  var found = cmdSearch(query);
  var html = '';
  for (var i = 0; i < found.length; i++) {
    var c = found[i];
    var dots = '';
    for (var d = 0; d < c.r.length; d++) { dots += cmdMark(c.r.charAt(d)); }
    html += '<button type="button" class="cmd-item" data-n="' + vEsc(c.n) + '">' +
      '<span class="cmd-name">' + vHl(c.n, stems) + '</span>' +
      '<span class="cmd-d">' + vHl(c.d, stems) + '</span>' +
      '<span class="cmd-dots">' + dots + '</span></button>';
  }
  list.innerHTML = html;
  var count = el('cmd-count');
  if (count) {
    count.textContent = query.trim()
      ? ('Найдено: ' + found.length + ' из ' + cmdPack().commands.length)
      : (found.length + ' команд');
  }
  var empty = el('cmd-empty');
  if (empty) { empty.hidden = found.length > 0; }
}

function cmdBack() {
  var page = el('cmd-page');
  var tools = el('cmd-tools');
  if (page) { page.hidden = true; page.innerHTML = ''; }
  if (tools) { tools.hidden = false; }
  cmdRenderList();
}

function cmdOpen(name) {
  var pack = cmdPack();
  var command = null;
  for (var i = 0; i < pack.commands.length; i++) {
    if (pack.commands[i].n === name) { command = pack.commands[i]; }
  }
  var page = el('cmd-page');
  if (!command || !page) { return; }

  var html = '<button type="button" class="cmd-back" id="cmd-back">← Ко всем командам</button>' +
    '<div class="cmd-title">' + vEsc(command.n) + '</div>' +
    '<div class="cmd-about">' + vEsc(command.d) + '</div>';
  if (command.a) {
    html += '<div class="cmd-alias">В примере используется запись <b>' +
      vEsc(command.a) + '</b></div>';
  }
  if (command.nt) {
    html += '<div class="cmd-note">' + vEsc(command.nt) + '</div>';
  }

  html += '<div class="cmd-sec">ФОРМА ПАРАМЕТРОВ</div><div class="cmd-box">';
  if (!command.p.length) {
    html += '<div class="cmd-hint">Параметры не нужны — команда вызывается без ' +
      'аргументов.</div>';
  }
  for (var p = 0; p < command.p.length; p++) {
    var param = command.p[p];
    html += '<div class="cmd-field">' +
      '<div class="cmd-lab">' + vEsc(param[1]) + '</div>' +
      '<div class="cmd-tok">' + vEsc(param[0]) + '</div>' +
      '<input class="cmd-input" data-i="' + p + '" value="' + vEsc(param[0]) +
      '" spellcheck="false" autocomplete="off">' +
      '<div class="cmd-hint">' + vEsc(param[2]) + '</div></div>';
  }
  html += '</div>';

  html += '<div class="cmd-sec">ПРЕДПРОСМОТР СОБРАННОЙ КОМАНДЫ</div>' +
    '<div class="cmd-box"><div class="cmd-preview" id="cmd-preview"></div>' +
    '<button type="button" class="cmd-copy" id="cmd-copy">Скопировать</button>' +
    '<div class="cmd-hint" style="margin-top:8px;">Значения подставляются в том ' +
    'порядке, в каком параметры идут в синтаксисе — сам синтаксис не меняется.' +
    '</div></div>';

  var states = [];
  for (var s = 0; s < command.r.length; s++) { states.push(cmdState(command.r.charAt(s))); }
  var first = -1;
  for (var f = 0; f < states.length; f++) {
    if (states[f] !== 'never') { first = f; break; }
  }
  var summary = first < 0
    ? 'Ни один ранг не может использовать эту команду.'
    : ('С <b>' + vEsc(pack.ranks[first].id) + '</b> (уровень ' +
       pack.ranks[first].level + ') — ' +
       (states[first] === 'always' ? 'доступна всегда.' : 'только на смене.'));

  html += '<div class="cmd-sec">ПРАВА ДОСТУПА ПО РАНГАМ</div>' +
    '<div class="cmd-hint" style="margin-bottom:7px;">🟩 всегда (если есть ранг) • ' +
    '🟨 только на смене • 🟥 недоступна. ' + summary + '</div>' +
    '<div class="cmd-box"><table class="cmd-ranks"><tr>' +
    '<td class="lvl"><b>Уровень</b></td><td class="rid"><b>Ранг</b></td>' +
    '<td class="grp"><b>Группа</b></td><td><b>Доступ</b></td></tr>';
  for (var r = 0; r < pack.ranks.length; r++) {
    var rank = pack.ranks[r];
    var state = states[r] || 'never';
    html += '<tr><td class="lvl">' + rank.level + '</td>' +
      '<td class="rid">' + vEsc(rank.id) + '</td>' +
      '<td class="grp">' + vEsc(rank.group) + '</td>' +
      '<td class="state-' + state + '">' + cmdStateLabel(state) + '</td></tr>';
  }
  html += '</table></div>';

  page.innerHTML = html;
  var tools = el('cmd-tools');
  if (tools) { tools.hidden = true; }
  page.hidden = false;

  var back = el('cmd-back');
  if (back) { back.addEventListener('click', cmdBack); }
  var copy = el('cmd-copy');
  if (copy) {
    copy.addEventListener('click', function () {
      var text = el('cmd-preview') ? el('cmd-preview').textContent : '';
      try {
        if (navigator.clipboard) {
          navigator.clipboard.writeText(text);
        }
      } catch (e) {
        // браузер без буфера обмена — текст всё равно можно выделить мышью
      }
      copy.textContent = 'Скопировано';
      setTimeout(function () { copy.textContent = 'Скопировать'; }, 1400);
    });
  }
  var inputs = document.querySelectorAll('.cmd-input');
  var update = function () {
    var parts = [command.h];
    for (var k = 0; k < inputs.length; k++) {
      var value = inputs[k].value.replace(/^\\s+|\\s+$/g, '');
      if (value) { parts.push(value); }
    }
    var box = el('cmd-preview');
    if (box) { box.textContent = parts.join(' '); }
  };
  for (var n = 0; n < inputs.length; n++) {
    inputs[n].addEventListener('input', update);
  }
  update();
}

function applyCommands() {
  var page = el('cmd-page');
  if (page && !page.hidden) { return; }   // внутри страницы команды список не мешаем
  cmdRenderList();
}

(function initCommands() {
  var input = el('cmd-q');
  if (!input) { return; }
  input.addEventListener('input', function () {
    var page = el('cmd-page');
    if (page && !page.hidden) { cmdBack(); }
    cmdRenderList();
  });
  input.addEventListener('search', cmdRenderList);
  var list = el('cmd-list');
  if (list) {
    list.addEventListener('click', function (event) {
      var item = event.target.closest ? event.target.closest('.cmd-item') : null;
      if (item) { cmdOpen(item.getAttribute('data-n')); }
    });
  }
  cmdRenderList();
})();
"""

_SHOTS_JS = """
// Недельный отчёт: дерево категорий с превью, переключатель недель,
// автообновление, пока вкладка открыта.
var SHOTS_WEEK = '';
var SHOTS_SIG = '';

function shotsRender(data) {
  var host = el('shots-tree');
  if (!host) { return; }
  var count = el('shots-count');
  var empty = el('shots-empty');
  var select = el('shots-week');
  var weeks = data.weeks || [];

  if (select) {
    var signature = weeks.join('|');
    if (SHOTS_SIG !== signature) {   // перерисовываем список только при изменении
      SHOTS_SIG = signature;
      select.innerHTML = '';
      for (var i = 0; i < weeks.length; i++) {
        var option = document.createElement('option');
        option.value = weeks[i];
        option.textContent = weeks[i];
        select.appendChild(option);
      }
    }
    if (data.selected) { select.value = data.selected; }
    select.hidden = weeks.length < 2;
  }

  host.innerHTML = '';
  var total = 0;
  var categories = data.categories || [];
  for (var c = 0; c < categories.length; c++) {
    var cat = categories[c];
    var files = cat.files || [];
    total += files.length;
    if (!files.length) { continue; }   // пустые категории не заваливают вкладку

    var block = document.createElement('div');
    block.className = 'shots-cat';
    var title = document.createElement('div');
    title.className = 'shots-cat-title';
    title.textContent = cat.name + ' · ' + files.length;
    block.appendChild(title);

    var grid = document.createElement('div');
    grid.className = 'shots-grid';
    for (var f = 0; f < files.length; f++) {
      var file = files[f];
      var link = document.createElement('a');
      link.className = 'shots-item';
      link.href = file.url;
      link.target = '_blank';
      link.rel = 'noopener';
      var img = document.createElement('img');
      img.loading = 'lazy';
      img.alt = file.name;
      img.src = file.url;
      var caption = document.createElement('div');
      caption.className = 'shots-caption';
      caption.textContent = file.name;
      link.appendChild(img);
      link.appendChild(caption);
      grid.appendChild(link);
    }
    block.appendChild(grid);
    host.appendChild(block);
  }

  if (count) {
    count.textContent = total ? ('Скриншотов: ' + total) : 'Пока ни одного';
  }
  if (empty) { empty.hidden = total > 0; }
}

function shotsLoad() {
  var host = el('shots-tree');
  if (!host) { return; }
  var url = '/api/shots';
  if (SHOTS_WEEK) { url += '?week=' + encodeURIComponent(SHOTS_WEEK); }
  fetch(url, { credentials: 'same-origin' })
    .then(function (response) { return response.ok ? response.json() : null; })
    .then(function (data) { if (data) { shotsRender(data); } })
    .catch(function () { /* локальный сайт: тихо ждём следующей попытки */ });
}

(function initShots() {
  var select = el('shots-week');
  if (select) {
    select.addEventListener('change', function () {
      SHOTS_WEEK = this.value || '';
      shotsLoad();
    });
  }
  // Автообновление — только пока открыта именно эта вкладка.
  setInterval(function () {
    var view = document.querySelector('.view:not([hidden])');
    if (view && view.id === 'view-shots') { shotsLoad(); }
  }, 10000);
})();
"""

_SHOTS_CSS = """
/* недельный отчёт: переключатель недель, категории, плитка превью */
.shots-head { display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
              margin-bottom: 14px; }
.shots-week { background: var(--field); color: var(--text);
              border: 1px solid var(--border); border-radius: 8px;
              padding: 8px 10px; font: inherit; font-size: 14px;
              max-width: 100%; }
.shots-week[hidden] { display: none; }
.shots-tree { display: flex; flex-direction: column; gap: 18px; }
.shots-cat-title { font-size: 12px; letter-spacing: .07em; text-transform: uppercase;
                   color: var(--muted); margin-bottom: 8px; }
.shots-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
              gap: 10px; }
.shots-item { display: block; text-decoration: none; color: inherit;
              background: var(--bg); border: 1px solid var(--border);
              border-radius: 8px; overflow: hidden; }
.shots-item:hover { border-color: var(--accent); }
.shots-item img { display: block; width: 100%; aspect-ratio: 16 / 9;
                  object-fit: cover; background: #000; }
.shots-caption { font-size: 11px; color: var(--muted); padding: 6px 8px;
                 word-break: break-all; }
"""

_RAIN_JS = """
// Эффект дождя: тонкие наклонные штрихи на фоне страницы.
// Включается настройкой «Дождь на фоне сайта» (window.SKY_OPTS.rain) и
// всегда выключается, если в системе включено «уменьшить анимацию».
(function () {
  var opts = window.SKY_OPTS || {};
  if (!opts.rain) { return; }
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { return; }
  var canvas = document.createElement('canvas');
  canvas.id = 'sky-rain';
  document.body.appendChild(canvas);
  var ctx = canvas.getContext('2d');
  if (!ctx) { return; }

  var drops = [];
  var width = 0, height = 0;
  // Плотность зависит от площади окна, но не превышает разумного — иначе
  // на большом мониторе фон превращается в белёсую кашу.
  function resize() {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;
    var want = Math.round(width * height / 26000);
    if (want < 40) { want = 40; }
    if (want > 160) { want = 160; }
    drops.length = 0;
    for (var i = 0; i < want; i++) {
      drops.push(newDrop(true));
    }
  }
  function newDrop(anywhere) {
    return {
      x: Math.random() * (width + 120) - 60,
      y: anywhere ? Math.random() * height : -20 - Math.random() * 90,
      len: 9 + Math.random() * 16,
      speed: 5.5 + Math.random() * 6.5,
      alpha: 0.10 + Math.random() * 0.16,
    };
  }
  var tilt = 0.16;   // наклон капли

  function frame() {
    ctx.clearRect(0, 0, width, height);
    for (var i = 0; i < drops.length; i++) {
      var d = drops[i];
      d.y += d.speed;
      d.x += d.speed * tilt;
      if (d.y > height + 20 || d.x > width + 40) {
        drops[i] = newDrop(false);
        continue;
      }
      ctx.strokeStyle = 'rgba(210, 232, 244, ' + d.alpha + ')';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(d.x, d.y);
      ctx.lineTo(d.x - d.len * tilt, d.y - d.len);
      ctx.stroke();
    }
    requestAnimationFrame(frame);
  }

  window.addEventListener('resize', resize);
  resize();
  frame();
})();
"""


_CURSOR_JS = """
// Кастомный курсор сайта. Вид выбирается в настройках программы
// (window.SKY_OPTS.cursor): white — белый кружок, ring — кружок с кольцом,
// off — обычный системный курсор.
(function () {
  var opts = window.SKY_OPTS || {};
  var style = opts.cursor || 'white';
  if (style === 'off') { return; }                              // системный курсор
  if (window.matchMedia('(pointer: coarse)').matches) { return; }  // тач-устройства

  var dot = document.createElement('div');
  dot.className = 'sky-cursor-dot' + (style === 'white' ? ' white' : '');
  document.body.appendChild(dot);
  // Гасим системный курсор: иначе рядом с нарисованным виден ещё и
  // штатный — на сайте это читалось как «два курсора» (баг-репорт №6).
  document.documentElement.classList.add('sky-cursor-on');

  var size = style === 'white' ? 14 : 6;
  var mx = -100, my = -100, rx = -100, ry = -100;
  var ring = null;
  if (style === 'ring') {
    ring = document.createElement('div');
    ring.className = 'sky-cursor-ring';
    document.body.appendChild(ring);
  }

  document.addEventListener('mousemove', function (e) {
    mx = e.clientX; my = e.clientY;
    dot.style.transform = 'translate(' + (mx - size / 2) + 'px,' + (my - size / 2) + 'px)';
  });
  document.addEventListener('mouseleave', function () {
    dot.style.opacity = '0';
    if (ring) { ring.style.opacity = '0'; }
  });
  document.addEventListener('mouseenter', function () {
    dot.style.opacity = '1';
    if (ring) { ring.style.opacity = '1'; }
  });
  if (!ring) { return; }
  function loop() {
    // Кольцо догоняет точку плотнее, чем раньше: иначе при быстром движении
    // они расходились настолько, что это читалось как второй курсор.
    rx += (mx - rx) * 0.32;
    ry += (my - ry) * 0.32;
    ring.style.transform = 'translate(' + (rx - 16) + 'px,' + (ry - 16) + 'px)';
    requestAnimationFrame(loop);
  }
  loop();
})();
"""


_EVENTS_JS = """
var evState = { cat: null };

function evPack() {
  return window.SKY_EVENTS || { categories: [], events: [] };
}

function evNorm(query) {
  // Как app.events.data._norm: регистр, ё/е, слэш и лишние пробелы не важны.
  return vNorm(query).replace(/\\s+/g, ' ').replace(/^\\s+|\\s+$/g, '')
    .replace(/^\\/+/, '');
}

function evCat(slug) {
  var cats = evPack().categories;
  for (var i = 0; i < cats.length; i++) {
    if (cats[i].slug === slug) { return cats[i]; }
  }
  return null;
}

function evEventsOf(slug) {
  var out = [], all = evPack().events;
  for (var i = 0; i < all.length; i++) {
    if (all[i].c === slug) { out.push(all[i]); }
  }
  return out;
}

function evGet(id) {
  var all = evPack().events;
  for (var i = 0; i < all.length; i++) {
    if (all[i].i === id) { return all[i]; }
  }
  return null;
}

function evHay(ev) {
  var cat = evCat(ev.c);
  return evNorm((ev.n || '') + ' ' + (ev.g || '') + ' ' + (cat ? cat.name : ''));
}

function evSearch(query) {
  // Зеркало app.events.data.search: по названию события и по названию категории.
  var text = evNorm(query);
  var all = evPack().events;
  if (!text) { return all; }
  var found = [];
  for (var i = 0; i < all.length; i++) {
    if (evHay(all[i]).indexOf(text) >= 0) { found.push(all[i]); }
  }
  return found;
}

function evStems(query) {
  var words = evNorm(query).split(/\\s+/);
  var stems = [];
  for (var i = 0; i < words.length; i++) {
    if (words[i]) { stems.push(vStem(words[i])); }
  }
  return stems;
}

function evCard(ev, stems) {
  var cat = evCat(ev.c);
  var chips = '';
  if (cat) {
    chips += '<span class="evt-chip">' + vHl(cat.name, stems) + '</span>';
  }
  if (ev.g) {
    chips += '<span class="evt-chip alt">' + vHl(ev.g, stems) + '</span>';
  }
  // скриншот события скачан из документации RMRP Study и лежит на сайте
  var shot = ev.s
    ? '<img class="evt-shot" src="' + vEsc(ev.s) + '" alt="' + vEsc(ev.n) +
      '" loading="lazy" width="' + (ev.w || 0) + '" height="' + (ev.h || 0) + '">'
    : '';
  return '<div class="evt-item" data-id="' + vEsc(ev.i) + '">' +
    '<div class="evt-item-top"><span class="evt-title">' + vHl(ev.n, stems) +
    '</span>' + chips + '</div>' + shot +
    '<div class="evt-coords">' + vEsc(ev.m) + '</div>' +
    '<button type="button" class="evt-tp" data-cmd="' + vEsc(ev.m) + '">' +
    'Телепортироваться на событие</button></div>';
}

function evRender() {
  // showView() может зваться при самом старте страницы — раньше, чем ниже
  // присваивается evState. Тогда просто отрисует initEvents() после загрузки.
  if (!evState) { return; }
  var input = el('evt-q');
  var list = el('evt-list');
  if (!input || !list) { return; }
  var raw = input.value.replace(/^\\s+|\\s+$/g, '');
  var stems = evStems(input.value);
  var html = '';
  var shown = 0;
  var pack = evPack();

  if (raw) {
    var found = evSearch(input.value);
    shown = found.length;
    for (var c = 0; c < pack.categories.length; c++) {
      var cat = pack.categories[c];
      var inCat = [];
      for (var f = 0; f < found.length; f++) {
        if (found[f].c === cat.slug) { inCat.push(found[f]); }
      }
      if (!inCat.length) { continue; }
      html += '<div class="evt-sec">' + vEsc(cat.name) + ' — ' + inCat.length +
        '</div>';
      for (var e = 0; e < inCat.length; e++) { html += evCard(inCat[e], stems); }
    }
  } else if (evState.cat) {
    var open = evCat(evState.cat);
    var events = evEventsOf(evState.cat);
    shown = events.length;
    html = '<button type="button" class="evt-back">← Все категории</button>';
    if (open) { html += '<div class="evt-sec">' + vEsc(open.name) + '</div>'; }
    for (var k = 0; k < events.length; k++) { html += evCard(events[k], []); }
  } else {
    for (var s = 0; s < pack.categories.length; s++) {
      var item = pack.categories[s];
      html += '<button type="button" class="evt-cat" data-cat="' +
        vEsc(item.slug) + '"><span class="evt-cat-name">' + vEsc(item.name) +
        '</span><span class="evt-cat-n">' + evEventsOf(item.slug).length +
        ' событий</span></button>';
    }
    shown = pack.events.length;
  }

  list.innerHTML = html;

  var count = el('evt-count');
  if (count) {
    if (raw) {
      count.textContent = 'Найдено: ' + shown + ' из ' + pack.events.length;
    } else if (evState.cat) {
      count.textContent = shown + ' событий';
    } else {
      count.textContent = pack.events.length + ' событий в ' +
        pack.categories.length + ' категориях';
    }
  }
  var empty = el('evt-empty');
  if (empty) { empty.hidden = !(raw && shown === 0); }
}

function applyEvents() {
  evRender();
}

(function initEvents() {
  var input = el('evt-q');
  if (!input) { return; }
  input.addEventListener('input', evRender);
  input.addEventListener('search', evRender);
  var list = el('evt-list');
  if (list) {
    list.addEventListener('click', function (event) {
      var target = event.target;
      var cat = target.closest ? target.closest('.evt-cat') : null;
      if (cat) {
        evState.cat = cat.getAttribute('data-cat');
        evRender();
        return;
      }
      var back = target.closest ? target.closest('.evt-back') : null;
      if (back) {
        evState.cat = null;
        evRender();
        return;
      }
      var tp = target.closest ? target.closest('.evt-tp') : null;
      if (tp) {
        var cmd = tp.getAttribute('data-cmd') || '';
        if (cmd && navigator.clipboard) {
          navigator.clipboard.writeText(cmd).catch(function () {});
        }
        var old = tp.textContent;
        tp.textContent = 'Скопировано ✓';
        setTimeout(function () { tp.textContent = old; }, 1600);
      }
    });
  }
  evRender();
})();
"""

_CATALOG_JS = """
// «Транспорт» и «Оружие» — те же таблицы RMRP Study, что и в окне программы.
var catOpen = { transport: null, weapon: null, gt: null };   // открытый раздел или null

function catPack() {
  return window.SKY_CATALOG || { titles: {}, sections: {}, items: {} };
}

function catNorm(value) {
  return vNorm(value).replace(/\\s+/g, ' ').replace(/^\\s+|\\s+$/g, '')
    .replace(/^\\/+/, '');            // слэш не обязателен — как в окне
}

function catSection(kind, index) {
  var list = catPack().sections[kind] || [];
  return list[index] || null;
}

function catRow(item, secName, stems) {
  var photo = item.im
    ? '<img class="cat-photo" src="' + vEsc(item.im) + '" alt="' +
      vEsc(item.n) + '">' +
      '<div class="cat-spawn' + (item.c ? ' ok' : ' no') + '">' +
      vEsc(item.sp || '') + '</div>'
    : '';
  var cmd = item.c
    ? '<button type="button" class="cat-cmd" data-s="' + item.s +
      '" data-r="' + item.r + '">' + vHl(item.c, stems) + '</button>'
    : (item.im ? '<div class="cat-nocmd">Команда не применяется — спавн в ' +
      'таблице запрещён</div>' : '');
  return '<div class="cat-item">' +
    (secName ? '<div class="cat-sec-name">' + vHl(secName, stems) + '</div>' : '') +
    photo +
    '<div class="cat-item-top"><span class="cat-name">' + vHl(item.n, stems) +
    '</span><span class="cat-id">' + vHl(item.i, stems) + '</span></div>' +
    cmd + '</div>';
}

function catRender(kind) {
  // showView() может зваться при старте страницы — раньше, чем ниже
  // присваивается catOpen. Тогда отрисует initCatalog() после загрузки.
  if (!catOpen) { return; }
  var input = el(kind + '-q');
  var list = el(kind + '-list');
  if (!input || !list) { return; }
  var pack = catPack();
  var sections = pack.sections[kind] || [];
  var items = pack.items[kind] || [];
  var raw = input.value;
  var query = catNorm(raw);
  var stems = query ? vNorm(raw).split(/\\s+/).filter(function (w) {
    return w;
  }).map(vStem) : [];
  var html = '';
  var shown = 0;
  var i;

  if (query) {
    for (i = 0; i < items.length; i++) {
      var item = items[i];
      var section = catSection(kind, item.s);
      var hay = catNorm(item.n + ' ' + item.i + ' ' + item.c + ' ' +
        item.sp + ' ' + (section ? section.t : ''));
      if (hay.indexOf(query) < 0) { continue; }
      shown++;
      html += catRow(item, section ? section.t : '', stems);
    }
  } else if (catOpen[kind] !== null && catSection(kind, catOpen[kind])) {
    var open = catSection(kind, catOpen[kind]);
    html += '<button type="button" class="cat-back">← Все разделы</button>';
    html += '<div class="cat-sec-head">' + vEsc(open.t) +
      ' <span class="cat-sec-n">' + open.n + ' строк</span></div>';
    for (i = 0; i < items.length; i++) {
      if (items[i].s === catOpen[kind]) {
        shown++;
        html += catRow(items[i], '', stems);
      }
    }
  } else {
    for (i = 0; i < sections.length; i++) {
      shown++;
      html += '<button type="button" class="cat-sec" data-s="' + i + '">' +
        vEsc(sections[i].t) + ' <span class="cat-sec-n">' + sections[i].n +
        ' строк</span></button>';
    }
  }

  list.innerHTML = html;
  var count = el(kind + '-count');
  if (count) {
    if (query) {
      count.textContent = 'Найдено: ' + shown + ' из ' + items.length;
    } else if (catOpen[kind] !== null) {
      count.textContent = shown + ' строк';
    } else {
      count.textContent = items.length + ' строк в ' + sections.length +
        ' разделах';
    }
  }
  var empty = el(kind + '-empty');
  if (empty) { empty.hidden = !(query && shown === 0); }
}

function catCopy(kind, button) {
  var items = catPack().items[kind] || [];
  var s = Number(button.getAttribute('data-s'));
  var r = Number(button.getAttribute('data-r'));
  var item = null;
  for (var i = 0; i < items.length; i++) {
    if (items[i].s === s && items[i].r === r) { item = items[i]; break; }
  }
  if (!item) { return; }
  try {
    if (navigator.clipboard) { navigator.clipboard.writeText(item.c); }
  } catch (e) {
    // браузер без буфера обмена — команда на виду, её можно выделить мышью
  }
  var old = button.textContent;
  button.textContent = 'Скопировано ✓';
  setTimeout(function () { button.textContent = old; }, 1600);
}

function applyCatalog(kind) {
  catRender(kind);
}

function catInit(kind) {
  var input = el(kind + '-q');
  if (!input) { return; }
  var list = el(kind + '-list');
  if (list) {
    list.addEventListener('click', function (event) {
      var target = event.target;
      var sec = target.closest ? target.closest('.cat-sec') : null;
      if (sec) {
        catOpen[kind] = Number(sec.getAttribute('data-s'));
        catRender(kind);
        return;
      }
      var back = target.closest ? target.closest('.cat-back') : null;
      if (back) {
        catOpen[kind] = null;
        catRender(kind);
        return;
      }
      var cmd = target.closest ? target.closest('.cat-cmd') : null;
      if (cmd) { catCopy(kind, cmd); }
    });
  }
  input.addEventListener('input', function () { catRender(kind); });
  input.addEventListener('search', function () { catRender(kind); });
  catRender(kind);
}

(function initCatalog() {
  catInit('transport');
  catInit('weapon');
  catInit('gt');
})();
"""

_STAFF_JS = """
// Online-STAFF: страница отдаёт свои данные без сети, а живой онлайн
// серверов приходит с локального сервера (/api/online → rmrp.ru, кэш 60 с).
// Имена серверов — как в лаунчере RAGE:MP (prod1 → «Рублёвка» и т.д.).
var SKY_SERVER_NAMES = {
  prod1: 'Рублёвка', prod2: 'Арбат', prod3: 'Патрики',
  prod4: 'Тверской', prod5: 'Кутузовский'
};
function staffApply(data) {
  if (!data || !data.found) { return; }
  var total = document.getElementById('staff-total');
  if (total) {
    total.textContent = String(data.total);
    total.style.color = 'var(--accent)';
    total.style.fontSize = '34px';
    total.style.fontWeight = '800';
  }
  var rows = document.getElementById('staff-servers');
  if (rows && data.servers) {
    var names = Object.keys(data.servers);
    var html = '';
    for (var i = 0; i < names.length; i++) {
      html += '<div style="display:flex;gap:10px;justify-content:space-between;' +
        'padding:5px 0;border-bottom:1px solid var(--border);">' +
        '<span style="font-family:Consolas,monospace;">' + vEsc(SKY_SERVER_NAMES[names[i]] || names[i]) +
        '</span><span style="font-weight:700;">' +
        vEsc(data.servers[names[i]]) + '</span></div>';
    }
    rows.innerHTML = html;
  }
  var note = document.getElementById('staff-note');
  if (note) { note.textContent = 'всего игроков на всех серверах'; }
  var updated = document.getElementById('staff-updated');
  if (updated && data.updated) { updated.textContent = 'Обновлено: ' + data.updated; }
}

function staffRefresh() {
  if (typeof fetch !== 'function') { return; }
  fetch('/api/online?refresh=1').then(function (res) {
    if (!res.ok) { throw new Error('HTTP ' + res.status); }
    return res.json();
  }).then(staffApply).catch(function () {
    // сеть недоступна — остаются цифры, что уже на странице
  });
}
"""


def dashboard_page(status: dict, options: dict | None = None) -> str:
    """Собирает HTML дашборда из dict со статусом (схема — в докстринге модуля).

    ``options`` — настройки оформления из Config (дождь, вид курсора).
    Они уезжают в страницу как window.SKY_OPTS. По умолчанию дождь включён,
    курсор — белый кружок.
    """
    if not isinstance(status, dict):
        status = {}
    opts = {"rain": True, "cursor": "white", **(options or {})}
    now = datetime.now()

    today = _section(status, "today")
    week = _section(status, "week_stats")
    streak = _section(status, "streak")
    flags = _section(status, "flags")

    # Подзаголовок: дата • день недели • диапазон недели.
    date_text = str(status.get("date") or now.strftime("%d.%m.%Y"))
    weekday_text = str(status.get("weekday") or WEEKDAYS[now.weekday()])
    week_text = str(status.get("week") or "")
    subtitle_bits = [date_text, weekday_text]
    if week_text:
        subtitle_bits.append("неделя " + week_text)
    subtitle = html.escape(" \u2022 ".join(subtitle_bits))

    # СЕГОДНЯ: время, обращения, полоса к дневному плану, чип с процентом.
    today_seconds = _int(today.get("seconds"))
    today_reports = _int(today.get("reports"))
    plan_seconds = _int(today.get("plan_seconds"))
    plan_ratio = today_seconds / plan_seconds if plan_seconds > 0 else 0.0
    plan_width = max(0.0, min(100.0, plan_ratio * 100))
    if plan_seconds > 0:
        today_chip = f"{round(plan_ratio * 100)}% плана"
        today_chip_class = "chip ok" if plan_ratio >= 1 else "chip"
    else:
        today_chip = "без плана"
        today_chip_class = "chip off"
    today_fill_class = " fill ok" if plan_ratio >= 1 and plan_seconds > 0 else ""

    # НЕДЕЛЯ: часы, обращения, проценты к норме.
    week_seconds = _int(week.get("seconds"))
    week_reports = _int(week.get("reports"))
    week_hours_pct = _pct(week.get("hours_percent"))
    week_reports_pct = _pct(week.get("reports_percent"))
    week_width = float(max(0, min(100, week_hours_pct)))

    # СТРИК: число дней и статус сегодняшнего дня.
    streak_days = _int(streak.get("days"))
    today_done = bool(streak.get("today_done"))
    streak_text = "выполнено" if today_done else "в процессе"
    streak_class = "chip ok" if today_done else "chip warn"

    # СТАТУС: три переключателя.
    duty_chip = _flag_chip(
        "flag-duty", bool(flags.get("duty")), "дежурство вкл", "дежурство выкл"
    )
    game_chip = _flag_chip(
        "flag-game", bool(flags.get("game")), "игра запущена", "игра не запущена"
    )
    count_chip = _flag_chip(
        "flag-count",
        bool(flags.get("counting")),
        "онлайн считается",
        "онлайн не считается",
    )

    bars = _bars_html(status.get("days"))

    # Хелпер и правила — общий контент из app.help.data; папка отчётов
    # приезжает в статусе (см. app.services.live_status.build_status).
    output_dir = str(status.get("output_dir") or "")
    helper_cards = "".join(
        '<section class="help-card" style="--c:%s;">'
        '<div class="help-title">%s</div>'
        '<div class="help-body">%s</div>'
        "</section>"
        % (
            html.escape(str(section.get("color") or HELP_PALETTE["accent"])),
            html.escape(str(section.get("title") or "")),
            section_html(section, HELP_PALETTE, output_dir),
        )
        for section in HELP_SECTIONS
    )
    rules_total = total_rules()
    rules_sections = len(RULE_CATEGORIES)
    commands_total = len(CMD_DATA.COMMANDS)
    events_total = len(EV_DATA.EVENTS)
    events_cats = len(EV_DATA.CATEGORIES)
    transport_total = CAT_DATA.count("transport")
    weapon_total = CAT_DATA.count("weapon")
    gt_total = CAT_DATA.count("gt")
    transport_sections = len(CAT_DATA.sections("transport"))
    weapon_sections = len(CAT_DATA.sections("weapon"))
    gt_sections = len(CAT_DATA.sections("gt"))
    # панель Online-STAFF без сети: цифры докачает JS при открытии вкладки
    staff_panel = STAFF_DATA.combined_html(HELP_PALETTE, ids=True, network=False)

    body = f"""<body>
<header class="top">
  <div class="brand">SKY-GRAFANA.RMRP</div>
  <nav class="tabs" id="tabs">
    <button type="button" class="tab active" data-view="dash">Дашборд</button>
    <button type="button" class="tab" data-view="helper">SKY HELPER</button>
    <button type="button" class="tab" data-view="commands">Команды<span class="tab-n">{commands_total}</span></button>
    <button type="button" class="tab" data-view="events">Серверные события<span class="tab-n">{events_total}</span></button>
    <button type="button" class="tab" data-view="transport">Транспорт<span class="tab-n">{transport_total}</span></button>
    <button type="button" class="tab" data-view="weapon">Оружие<span class="tab-n">{weapon_total}</span></button>
    <button type="button" class="tab" data-view="gt">Транспорт (Google)<span class="tab-n">{gt_total}</span></button>
    <button type="button" class="tab" data-view="staff">Online-STAFF</button>
    <button type="button" class="tab" data-view="shots">Недельный отчёт</button>
    <button type="button" class="tab" data-view="rules">Правила RMRP<span class="tab-n">{rules_total}</span></button>
  </nav>
  <div class="sub" id="sub">{subtitle}</div>
  <div class="conn" id="conn">ожидание данных…</div>
</header>
<main>
  <div class="view" id="view-dash">
  <div class="grid">
    <section class="card">
      <div class="card-title accent">СЕГОДНЯ</div>
      <div class="big" id="today-time">{_today_time(today_seconds)}</div>
      <div class="muted" id="today-reports">обращения {today_reports}</div>
      <div class="track"><div class="fill{today_fill_class}" id="today-bar" style="width:{plan_width:.0f}%"></div></div>
      <span class="{today_chip_class}" id="today-chip">{today_chip}</span>
    </section>
    <section class="card">
      <div class="card-title">НЕДЕЛЯ</div>
      <div class="big" id="week-hours">{_hm(week_seconds)}</div>
      <div class="muted" id="week-reports">обращения {week_reports}</div>
      <div class="pcts" id="week-pcts">{week_hours_pct}% часов • {week_reports_pct}% обращений</div>
      <div class="track"><div class="fill" id="week-bar" style="width:{week_width:.0f}%"></div></div>
    </section>
    <section class="card">
      <div class="card-title">СТРИК</div>
      <div class="big" id="streak-days">{streak_days} дн.</div>
      <div class="muted">дней подряд с выполненным планом</div>
      <span class="{streak_class}" id="streak-state">{streak_text}</span>
    </section>
    <section class="card">
      <div class="card-title">СТАТУС</div>
      <div class="flags">
        {duty_chip}
        {game_chip}
        {count_chip}
      </div>
    </section>
  </div>
  <section class="card chart">
    <div class="card-title">ПОСЛЕДНИЕ ДНИ</div>
    <div class="muted">столбики — часы онлайн, подписи — дата, часы и обращения</div>
    <div class="cols" id="days">{bars}</div>
  </section>
  </div>

  <div class="view" id="view-helper" hidden>
    <p class="help-intro">То же самое, что в окне программы: трей → «SKY HELPER».
    Правила проекта — во вкладке «Правила RMRP», там же поиск.</p>
    <div class="help-grid">{helper_cards}</div>
  </div>

  <div class="view" id="view-commands" hidden>
    <section class="card">
      <div class="card-title">КОМАНДЫ АДМИНИСТРАЦИИ</div>
      <p class="help-intro">Та же база, что в окне программы (раздел «Команды»).
      Выбери команду — откроется её страница: описание, форма параметров с
      пояснениями, предпросмотр собранной команды и права доступа по рангам.</p>
      <div id="cmd-tools">
        <div class="rules-head">
          <input id="cmd-q" class="rules-q" type="search"
                 placeholder="Поиск по командам — /ban, kick, предупреждение"
                 autocomplete="off" spellcheck="false">
          <div class="rules-count" id="cmd-count">{commands_total} команд</div>
        </div>
        <div id="cmd-list" class="cmd-list"></div>
        <div class="rules-empty" id="cmd-empty" hidden>Команда не нашлась —
        попробуй без слэша или другое написание.</div>
      </div>
      <div id="cmd-page" hidden></div>
    </section>
  </div>

  <div class="view" id="view-events" hidden>
    <section class="card">
      <div class="card-title">СЕРВЕРНЫЕ СОБЫТИЯ</div>
      <p class="help-intro">Та же база, что в окне программы (раздел
      «Серверные события»). Пять категорий из документации RMRP Study:
      открой категорию — увидишь её события и скриншот, у каждого свои
      координаты.</p>
      <div class="rules-head">
        <input id="evt-q" class="rules-q" type="search"
               placeholder="Поиск по событиям — налёт, склад, захват, КрАЗ"
               autocomplete="off" spellcheck="false">
        <div class="rules-count" id="evt-count">{events_total} событий в {events_cats} категориях</div>
      </div>
      <div id="evt-list"></div>
      <div class="rules-empty" id="evt-empty" hidden>Событий не нашлось —
      попробуй другое название или категорию.</div>
    </section>
  </div>

  <div class="view" id="view-transport" hidden>
    <section class="card">
      <div class="card-title">ТРАНСПОРТ</div>
      <p class="help-intro">Та же база, что в окне программы (раздел
      «Транспорт»). Таблица документации RMRP Study «Автомобили RMRP»:
      наименование, ID и пример команды. Нажми на команду — она скопируется.
      Картинок в документе нет — только таблицы.</p>
      <div class="rules-head">
        <input id="transport-q" class="rules-q" type="search"
               placeholder="Поиск по транспорту — Adder, полиция, /spawnvehicle"
               autocomplete="off" spellcheck="false">
        <div class="rules-count" id="transport-count">{transport_total} строк в {transport_sections} разделах</div>
      </div>
      <div id="transport-list"></div>
      <div class="rules-empty" id="transport-empty" hidden>Ничего не нашлось —
      попробуй другое слово или ID транспорта.</div>
    </section>
  </div>

  <div class="view" id="view-weapon" hidden>
    <section class="card">
      <div class="card-title">ОРУЖИЕ</div>
      <p class="help-intro">Та же база, что в окне программы (раздел
      «Оружие»). Таблица документации RMRP Study «Оружие RMRP»: наименование,
      ID и пример команды. Нажми на команду — она скопируется. Картинок в
      документе нет — только таблицы.</p>
      <div class="rules-head">
        <input id="weapon-q" class="rules-q" type="search"
               placeholder="Поиск по оружию — винтовка, weapon_pistol, /givegun"
               autocomplete="off" spellcheck="false">
        <div class="rules-count" id="weapon-count">{weapon_total} строк в {weapon_sections} разделах</div>
      </div>
      <div id="weapon-list"></div>
      <div class="rules-empty" id="weapon-empty" hidden>Ничего не нашлось —
      попробуй другое слово или ID оружия.</div>
    </section>
  </div>

  <div class="view" id="view-gt" hidden>
    <section class="card">
      <div class="card-title">ТРАНСПОРТ (GOOGLE)</div>
      <p class="help-intro">Все данные о каждом транспорте из Google-Таблицы
      RMRP: фотография, игровое название, ID и возможность спавна —
      {gt_total} единиц в {gt_sections} категориях. Фото скачаны в программу,
      поэтому раздел работает без сети. Нажми на команду — она скопируется.</p>
      <div class="rules-head">
        <input id="gt-q" class="rules-q" type="search"
               placeholder="Поиск по таблице — название, ID, категория, спавн"
               autocomplete="off" spellcheck="false">
        <div class="rules-count" id="gt-count">{gt_total} строк в {gt_sections} разделах</div>
      </div>
      <div id="gt-list"></div>
      <div class="rules-empty" id="gt-empty" hidden>Ничего не нашлось —
      попробуй другое слово или ID транспорта.</div>
    </section>
  </div>

  <div class="view" id="view-staff" hidden>
    <section class="card">
      <div class="card-title">ONLINE-STAFF</div>
      <p class="help-intro">Живой онлайн серверов RMRP (общий счётчик rmrp.ru)
      и все данные игрока, который пользуется программой: статик, имя, админ-ранг,
      фракция, семья, телефон и прочее. Чужих игроков здесь нет — только свои
      данные из логов RAGE:MP.</p>
      {staff_panel}
    </section>
  </div>

  <div class="view" id="view-shots" hidden>
    <section class="card">
      <div class="card-title">НЕДЕЛЬНЫЙ ОТЧЁТ</div>
      <p class="help-intro">Скриншоты недели по категориям — ровно то, что лежит
      в папке «Отчёты ¦ Администратор …» рядом с программой. Клик по превью
      открывает полноразмерный снимок в новой вкладке. Вкладка обновляется сама,
      пока открыта.</p>
      <div class="shots-head">
        <select id="shots-week" class="shots-week" hidden></select>
        <div class="rules-count" id="shots-count">Загружаю…</div>
      </div>
      <div class="shots-tree" id="shots-tree"></div>
      <div class="rules-empty" id="shots-empty" hidden>Скриншотов пока нет —
      включи дежурство и нажми клавишу категории.</div>
    </section>
  </div>

  <div class="view" id="view-rules" hidden>
    <section class="card">
      <div class="card-title">ПРАВИЛА RMRP</div>
      <div class="rules-head">
        <input id="rules-q" class="rules-q" type="search"
               placeholder="Поиск по правилам — например: допросы, война, семьи"
               autocomplete="off" spellcheck="false">
        <div class="rules-count" id="rules-count">{rules_total} правил в {rules_sections} разделах</div>
      </div>
      {rules_html(HELP_PALETTE, web=True)}
      <div class="rules-empty" id="rules-empty" hidden>Ничего не нашлось — попробуй другое слово.</div>
    </section>
  </div>
</main>
<footer>sky-grafana.rmrp • данные из локального трекера<br>
{NOTICE_HTML}</footer>"""

    return _document(
        "sky-grafana.rmrp",
        _BASE_CSS + _DASH_CSS + _VIEW_CSS + _CMDS_CSS + _EVENTS_CSS
        + _CATALOG_CSS + _SHOTS_CSS,
        body,
        # данные разделов — первыми: остальной JS читает их при своей инициализации
        "window.SKY_COMMANDS = " + CMD_DATA.payload() + ";\n"
        + "window.SKY_EVENTS = " + EV_DATA.payload() + ";\n"
        + "window.SKY_CATALOG = " + CAT_DATA.payload() + ";\n"
        + "window.SKY_OPTS = " + json.dumps(opts, ensure_ascii=False) + ";\n"
        + _DASH_JS + "\n" + _VIEW_JS + "\n" + _CMDS_JS + "\n" + _EVENTS_JS
        + "\n" + _CATALOG_JS + "\n" + _STAFF_JS + "\n" + _SHOTS_JS
        + "\n" + _RAIN_JS + "\n" + _CURSOR_JS,
    )
