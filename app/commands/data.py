"""Единая база команд администрации — единственный источник для раздела
«Команды»: в окне программы, поиска и вкладки «Команды» на сайте.

Названия, синтаксис и описания — дословно из списка пользователя: ничего
не переименовано, не переставлено и не сокращено. Права доступа — из таблицы
«Команды по рангам» (Google Таблица RMRP), прочитанной по цветам ячеек со
скриншотов: ``G`` — доступна всегда (если есть ранг), ``Y`` — только на
смене, ``R`` — недоступна. Строки без команды пользователя в базу не входят.
"""
from __future__ import annotations

import json
import re

#: Ранги ровно в том порядке, в каком они идут в таблице (уровни 0–8).
RANKS: list[dict] = [
 {
  "id": "moderator",
  "level": 0,
  "group": "Модерация"
 },
 {
  "id": "admin",
  "level": 1,
  "group": "Младшая Администрация"
 },
 {
  "id": "adminplus",
  "level": 2,
  "group": "Младшая Администрация"
 },
 {
  "id": "headadmin",
  "level": 3,
  "group": "Администрация"
 },
 {
  "id": "superadmin",
  "level": 4,
  "group": "Администрация"
 },
 {
  "id": "globaladmin",
  "level": 5,
  "group": "Пом.Гл.Куратора"
 },
 {
  "id": "globaladminplus",
  "level": 6,
  "group": "Гл. Куратор"
 },
 {
  "id": "deputy_staff_leader",
  "level": 7,
  "group": "Зам. Гл. Админа"
 },
 {
  "id": "staff_leader",
  "level": 8,
  "group": "Главный админ"
 }
]

#: Код состояния → (цвет, подпись) для таблицы прав.
STATE: dict[str, tuple[str, str]] = {
    "always": ("#2ea043", "🟩 Всегда"),
    "duty": ("#d29922", "🟨 Только на смене"),
    "never": ("#f85149", "🟥 Недоступна"),
}
STATE_TEXT: dict[str, str] = {
    "always": "Всегда",
    "duty": "Только на смене",
    "never": "Недоступна",
}

COMMANDS: list[dict] = [
 {
  "name": "/adminbase",
  "desc": "Телепортирует на базу администрации.",
  "syntax": "/adminbase",
  "head": "/adminbase",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "always",
   "admin": "always",
   "adminplus": "always",
   "headadmin": "always",
   "superadmin": "always",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "GGGGGGGGG",
  "row": 5
 },
 {
  "name": "/getwarns",
  "desc": "Посмотреть кол-во предупреждений и время до их истечения.",
  "syntax": "/getwarns 123456",
  "head": "/getwarns",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "always",
   "admin": "always",
   "adminplus": "always",
   "headadmin": "always",
   "superadmin": "always",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "GGGGGGGGG",
  "row": 6
 },
 {
  "name": "/infoban",
  "desc": "Посмотреть информацию о бане.",
  "syntax": "/infoban 123456",
  "head": "/infoban",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "always",
   "admin": "always",
   "adminplus": "always",
   "headadmin": "always",
   "superadmin": "always",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "GGGGGGGGG",
  "row": 7
 },
 {
  "name": "/godmode",
  "desc": "Включить режим бессмертия.",
  "syntax": "/gm",
  "head": "/gm",
  "alias": "/gm",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "YYYYYYYYY",
  "row": 8
 },
 {
  "name": "/uncuff",
  "desc": "Снять наручники.",
  "syntax": "/uncuff 123456 Баг",
  "head": "/uncuff",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "Баг",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «Баг»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "YYYYYYYYY",
  "row": 9
 },
 {
  "name": "/dimensionstat",
  "desc": "Информация о деменшине.",
  "syntax": "/dimensionstat",
  "head": "/dimensionstat",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "YYYYYYYYY",
  "row": 10
 },
 {
  "name": "/adminmode",
  "desc": "Включить режим полёта и невидимки (F3)",
  "syntax": "/am",
  "head": "/am",
  "alias": "/am",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 11
 },
 {
  "name": "/esp",
  "desc": "Включить возможность видеть всех игроков в определенном радиусе с дополнительной информацией.",
  "syntax": "/esp",
  "head": "/esp",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYYGG",
  "row": 12
 },
 {
  "name": "/goto",
  "desc": "Телепортироваться к игроку.",
  "syntax": "/goto 123456",
  "head": "/goto",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 13
 },
 {
  "name": "/tp",
  "desc": "Телепортировать игрока.",
  "syntax": "/tp 123456",
  "head": "/tp",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 14
 },
 {
  "name": "/return",
  "desc": "Вернуть себя/игрока.",
  "syntax": "/return",
  "head": "/return",
  "alias": "",
  "params": [],
  "note": "Также: /return 123456.",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 15
 },
 {
  "name": "/spectate",
  "desc": "Войти в режим наблюдений за игроком.",
  "syntax": "/spectate 123456",
  "head": "/spectate",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYYGG",
  "row": 16
 },
 {
  "name": "/callcar",
  "desc": "Вызвать машину игрока из быстрого вызова.",
  "syntax": "/callcar 123456",
  "head": "/callcar",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 17
 },
 {
  "name": "/teleportcar",
  "desc": "Телепортировать машину игрока к себе.",
  "syntax": "/tpcar 123456:123456",
  "head": "/tpcar",
  "alias": "/tpcar",
  "params": [
   {
    "t": "123456:123456",
    "ti": "ID через двоеточие",
    "h": "Два ID через двоеточие — как в примере (игрок:машина)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 18
 },
 {
  "name": "/flipcar",
  "desc": "Перевернуть машину.",
  "syntax": "/flipcar 123456:123456",
  "head": "/flipcar",
  "alias": "",
  "params": [
   {
    "t": "123456:123456",
    "ti": "ID через двоеточие",
    "h": "Два ID через двоеточие — как в примере (игрок:машина)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 19
 },
 {
  "name": "/freeze",
  "desc": "Заморозить игрока.",
  "syntax": "/freeze 123456",
  "head": "/freeze",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYYGG",
  "row": 20
 },
 {
  "name": "/unfreeze",
  "desc": "Разморозить игрока.",
  "syntax": "/unfreeze 123456",
  "head": "/unfreeze",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYYGG",
  "row": 21
 },
 {
  "name": "/noclip",
  "desc": "Включает нивидимку.",
  "syntax": "/noclip",
  "head": "/noclip",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 22
 },
 {
  "name": "/respawn",
  "desc": "Переспавнить игрока.",
  "syntax": "/respawn 123456",
  "head": "/respawn",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 23
 },
 {
  "name": "/pacifist",
  "desc": "Выдать режим пацифиста.",
  "syntax": "/pacifist 123456 420mi DM",
  "head": "/pacifist",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "420mi",
    "ti": "Срок",
    "h": "Длительность: 420 минут (как в примере)."
   },
   {
    "t": "DM",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «DM»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYGGGG",
  "row": 24
 },
 {
  "name": "/unpacifist",
  "desc": "Снять режим пацифиста с игрока.",
  "syntax": "/unpacifist 123456 Ошибка",
  "head": "/unpacifist",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "Ошибка",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «Ошибка»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 25
 },
 {
  "name": "/setpos",
  "desc": "Телепортироваться по координатам.",
  "syntax": "/setpos x y z",
  "head": "/setpos",
  "alias": "",
  "params": [
   {
    "t": "x",
    "ti": "Координата X",
    "h": "Координата X из примера /setpos x y z."
   },
   {
    "t": "y",
    "ti": "Координата Y",
    "h": "Координата Y из примера /setpos x y z."
   },
   {
    "t": "z",
    "ti": "Координата Z",
    "h": "Координата Z из примера /setpos x y z."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYYGG",
  "row": 26
 },
 {
  "name": "/kick",
  "desc": "Отключить игрока от сервера.",
  "syntax": "/kick 1234 Причина",
  "head": "/kick",
  "alias": "",
  "params": [
   {
    "t": "1234",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "Причина",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «Причина»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYGGGG",
  "row": 27
 },
 {
  "name": "/ban",
  "desc": "Забанить/Отправить в оффлайн бан игрока.",
  "syntax": "/ban 123456 30mi Причина",
  "head": "/ban",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "30mi",
    "ti": "Срок",
    "h": "Длительность: 30 минут (как в примере)."
   },
   {
    "t": "Причина",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «Причина»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYGGGG",
  "row": 28
 },
 {
  "name": "/mutechat",
  "desc": "Заблокировать текстовый чат.",
  "syntax": "/mutechat 123456 30mi MF",
  "head": "/mutechat",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "30mi",
    "ti": "Срок",
    "h": "Длительность: 30 минут (как в примере)."
   },
   {
    "t": "MF",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «MF»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYGGGG",
  "row": 29
 },
 {
  "name": "/mutevoice",
  "desc": "Заблокировать голосовой чат.",
  "syntax": "/mutevoice 123456 30mi VA",
  "head": "/mutevoice",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "30mi",
    "ti": "Срок",
    "h": "Длительность: 30 минут (как в примере)."
   },
   {
    "t": "VA",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «VA»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYYGG",
  "row": 30
 },
 {
  "name": "/mutereport",
  "desc": "Заблокировать репорт-чат.",
  "syntax": "/mutereport 123456 30mi MF",
  "head": "/mutereport",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "30mi",
    "ti": "Срок",
    "h": "Длительность: 30 минут (как в примере)."
   },
   {
    "t": "MF",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «MF»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYYGG",
  "row": 31
 },
 {
  "name": "/unmute",
  "desc": "Снять блокировку чата.",
  "syntax": "/unmute 123456 Ошибка",
  "head": "/unmute",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "Ошибка",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «Ошибка»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYGGGG",
  "row": 32
 },
 {
  "name": "/deafness",
  "desc": "Выдает иконку глухого.",
  "syntax": "/deafness",
  "head": "/deafness",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 33
 },
 {
  "name": "/numbness",
  "desc": "Выдает иконку немого.",
  "syntax": "/numbness",
  "head": "/numbness",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 34
 },
 {
  "name": "/unicon",
  "desc": "Снимает любую иконку кроме /mute",
  "syntax": "/unicon",
  "head": "/unicon",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYYGGG",
  "row": 35
 },
 {
  "name": "/unrk",
  "desc": "Снимает RK-зону у игрока находившегося в ней",
  "syntax": "/unrk",
  "head": "/unrk",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "duty",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "YYYYYGGGG",
  "row": 36
 },
 {
  "name": "/warn",
  "desc": "Выдать предупреждение.",
  "syntax": "/warn 123456 1.14 ПГО",
  "head": "/warn",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "1.14",
    "ti": "Номер",
    "h": "Код/номер в причине предупреждения (в примере 1.14)."
   },
   {
    "t": "ПГО",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «ПГО»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RYYYYGGGG",
  "row": 38
 },
 {
  "name": "/unarrest",
  "desc": "Выпустить с тюрьмы.",
  "syntax": "/unarrest 123456 Ошибка",
  "head": "/unarrest",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "Ошибка",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «Ошибка»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "duty",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RYYYYGGGG",
  "row": 39
 },
 {
  "name": "/unban",
  "desc": "Снять бан/деморган.",
  "syntax": "/unban 123456 Ошибка",
  "head": "/unban",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "Ошибка",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «Ошибка»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRYYYGGGG",
  "row": 40
 },
 {
  "name": "/pred",
  "desc": "Выдать устное предупреждение",
  "syntax": "/pred 123456 4.12 ПП",
  "head": "/pred",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "4.12",
    "ti": "Номер",
    "h": "Код/номер в причине предупреждения (в примере 4.12)."
   },
   {
    "t": "ПП",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «ПП»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRYYYGGGG",
  "row": 41
 },
 {
  "name": "/spawnvehicle",
  "desc": "Вызвать транспорт.",
  "syntax": "/spawnvehicle dawe_231 e4b41d",
  "head": "/spawnvehicle",
  "alias": "",
  "params": [
   {
    "t": "dawe_231",
    "ti": "Название транспорта",
    "h": "Название модели из примера: dawe_231."
   },
   {
    "t": "e4b41d",
    "ti": "Цвет транспорта",
    "h": "Цвет в hex из примера: e4b41d."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRYYYYYGG",
  "row": 42
 },
 {
  "name": "/fixcar",
  "desc": "Починить транспорт.",
  "syntax": "/fixcar 123456:12345",
  "head": "/fixcar",
  "alias": "",
  "params": [
   {
    "t": "123456:12345",
    "ti": "ID через двоеточие",
    "h": "Два ID через двоеточие — как в примере (игрок:машина)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRYYYYGGG",
  "row": 43
 },
 {
  "name": "/vehiclerows",
  "desc": "Вызвать несколько транспортных средств.",
  "syntax": "/rveh 5 3 gemera",
  "head": "/rveh",
  "alias": "/rveh",
  "params": [
   {
    "t": "5",
    "ti": "Количество машин в ряду",
    "h": "Сколько машин ставить в один ряд."
   },
   {
    "t": "3",
    "ti": "Количество линий",
    "h": "Сколько рядов (линий) поставить."
   },
   {
    "t": "gemera",
    "ti": "Модель транспорта",
    "h": "Название модели из примера: gemera."
   }
  ],
  "note": "(P.S. 5 - кол-во машин в ряду, 3 - кол-во линий)",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRYYYYYGG",
  "row": 44
 },
 {
  "name": "/clearvehicles",
  "desc": "Удалить весь транспорт в деменшине.",
  "syntax": "/clearveh",
  "head": "/clearveh",
  "alias": "/clearveh",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRYYYYYGG",
  "row": 45
 },
 {
  "name": "/sethealth",
  "desc": "Установить здоровье.",
  "syntax": "/sethealth 123456 100",
  "head": "/sethealth",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "100",
    "ti": "Здоровье",
    "h": "Новое значение здоровья (в примере 100)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 46
 },
 {
  "name": "/sethealthall",
  "desc": "Установить здоровье в радиусе.",
  "syntax": "/sethpall 100",
  "head": "/sethpall",
  "alias": "/sethpall",
  "params": [
   {
    "t": "100",
    "ti": "Здоровье",
    "h": "Новое значение здоровья в радиусе (в примере 100)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 47
 },
 {
  "name": "/setarmor",
  "desc": "Установить броню.",
  "syntax": "/setarmor 123456 100",
  "head": "/setarmor",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "100",
    "ti": "Броня",
    "h": "Новое значение брони (в примере 100)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 48
 },
 {
  "name": "/setarmorall",
  "desc": "Установить броню в радиусе.",
  "syntax": "/setarmorall 100",
  "head": "/setarmorall",
  "alias": "",
  "params": [
   {
    "t": "100",
    "ti": "Броня",
    "h": "Новое значение брони в радиусе (в примере 100)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 49
 },
 {
  "name": "/freezeall",
  "desc": "Заморозить всех в деменшине.",
  "syntax": "/freezeall",
  "head": "/freezeall",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 50
 },
 {
  "name": "/unfreezeall",
  "desc": "Разморозить всех в деменшине.",
  "syntax": "/unfreezeall",
  "head": "/unfreezeall",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 51
 },
 {
  "name": "/givegun",
  "desc": "Выдать оружие.",
  "syntax": "/givegun 123456 weapon_model 1000",
  "head": "/givegun",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "weapon_model",
    "ti": "Модель оружия",
    "h": "Название модели оружия из примера."
   },
   {
    "t": "1000",
    "ti": "Количество",
    "h": "Сколько патронов/единиц (в примере 1000)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 52
 },
 {
  "name": "/givegunall",
  "desc": "Выдать оружие в радиусе.",
  "syntax": "/givegunall weapon_model 1000",
  "head": "/givegunall",
  "alias": "",
  "params": [
   {
    "t": "weapon_model",
    "ti": "Модель оружия",
    "h": "Название модели оружия из примера."
   },
   {
    "t": "1000",
    "ti": "Количество",
    "h": "Сколько патронов/единиц (в примере 1000)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 53
 },
 {
  "name": "/model",
  "desc": "Установить скин.",
  "syntax": "/model 123456 skin_id",
  "head": "/model",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "skin_id",
    "ti": "ID скина",
    "h": "Номер скина персонажа."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 54
 },
 {
  "name": "/modelall",
  "desc": "Установить скин в радиусе.",
  "syntax": "/modelall skin_id",
  "head": "/modelall",
  "alias": "",
  "params": [
   {
    "t": "skin_id",
    "ti": "ID скина",
    "h": "Номер скина персонажа."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 55
 },
 {
  "name": "/muteall",
  "desc": "Заблокировать голосовой/текстовый чат всем в деменшине.",
  "syntax": "/muteall",
  "head": "/muteall",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 56
 },
 {
  "name": "/unmuteall",
  "desc": "Снять блокировку голосового/текстового чата всем в деменшине.",
  "syntax": "/unmuteall",
  "head": "/unmuteall",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 57
 },
 {
  "name": "/killall",
  "desc": "Убить всех в деменшине (Отправить в больницу).",
  "syntax": "/killall",
  "head": "/killall",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "duty",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRYYYYYYY",
  "row": 58
 },
 {
  "name": "/dimension",
  "desc": "Переместить себя/игрока в деменшин.",
  "syntax": "/dimension 123456 2",
  "head": "/dimension",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "2",
    "ti": "Номер деменшина",
    "h": "Номер деменшина из примера: 2."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRRYYYYYY",
  "row": 59
 },
 {
  "name": "/dimension_close",
  "desc": "Закрыть деменшин.",
  "syntax": "/dimension_close 2",
  "head": "/dimension_close",
  "alias": "",
  "params": [
   {
    "t": "2",
    "ti": "Номер деменшина",
    "h": "Номер закрываемого деменшина: 2."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRRYYYYYY",
  "row": 60
 },
 {
  "name": "/gomp",
  "desc": "Начать мероприятие.",
  "syntax": "/gomp 30 1mi Прятки",
  "head": "/gomp",
  "alias": "",
  "params": [
   {
    "t": "30",
    "ti": "Количество мест на мероприятии",
    "h": "Сколько мест на мероприятии."
   },
   {
    "t": "1mi",
    "ti": "Срок",
    "h": "Длительность: 1 минут (как в примере)."
   },
   {
    "t": "Прятки",
    "ti": "Название мероприятия",
    "h": "Тип мероприятия из примера: Прятки."
   }
  ],
  "note": "P.S. Цифра “30” обозначает количество мест на мероприятии",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRRYYYYYY",
  "row": 61
 },
 {
  "name": "/gomp_stop",
  "desc": "Закрыть вход на мероприятие.",
  "syntax": "/gomp_stop",
  "head": "/gomp_stop",
  "alias": "",
  "params": [],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "duty",
   "staff_leader": "duty"
  },
  "code": "RRRYYYYYY",
  "row": 62
 },
 {
  "name": "/unwarn",
  "desc": "Снять предупреждение.",
  "syntax": "/unwarn 123456 Ошибка",
  "head": "/unwarn",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "Ошибка",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «Ошибка»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRYYGGGG",
  "row": 63
 },
 {
  "name": "/cheatcheck",
  "desc": "Вызвать на проверку читера.",
  "syntax": "/cheatcheck 123456",
  "head": "/cheatcheck",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "duty",
   "superadmin": "duty",
   "globaladmin": "duty",
   "globaladminplus": "duty",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRYYYYGG",
  "row": 64
 },
 {
  "name": "/setleader",
  "desc": "Установить лидера фракции.",
  "syntax": "/setleader 123456 faction_id",
  "head": "/setleader",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "faction_id",
    "ti": "ID фракции",
    "h": "Номер фракции."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRGGGG",
  "row": 65
 },
 {
  "name": "/unsetleader",
  "desc": "Снять лидера фракции.",
  "syntax": "/unsetleader 123456",
  "head": "/unsetleader",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRGGGG",
  "row": 66
 },
 {
  "name": "/setfactionrank",
  "desc": "Установить ранг во фракции.",
  "syntax": "/setfactionrank 123456 faction_id rank_id",
  "head": "/setfactionrank",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "faction_id",
    "ti": "ID фракции",
    "h": "Номер фракции."
   },
   {
    "t": "rank_id",
    "ti": "ID ранга",
    "h": "Номер ранга."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRGGGG",
  "row": 67
 },
 {
  "name": "/setfaction",
  "desc": "Установить фракцию.",
  "syntax": "/setfaction 123456 faction_id",
  "head": "/setfaction",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "faction_id",
    "ti": "ID фракции",
    "h": "Номер фракции."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRGGGG",
  "row": 68
 },
 {
  "name": "/getfactioninfo",
  "desc": "Получить информацию о фракции.",
  "syntax": "/getfactioninfo faction_id",
  "head": "/getfactioninfo",
  "alias": "",
  "params": [
   {
    "t": "faction_id",
    "ti": "ID фракции",
    "h": "Номер фракции."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRGGGG",
  "row": 69
 },
 {
  "name": "/forbid_buy_chips",
  "desc": "Запретить покупать фишки в казино.",
  "syntax": "/forbid_buy_chips 123456",
  "head": "/forbid_buy_chips",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRGGGG",
  "row": 70
 },
 {
  "name": "/unforbid_buy_chips",
  "desc": "Разрешить покупать фишки в казино.",
  "syntax": "/unforbid_buy_chips 123456",
  "head": "/unforbid_buy_chips",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRGGGG",
  "row": 71
 },
 {
  "name": "/greenzoneoff",
  "desc": "Выключить зеленую зону.",
  "syntax": "/greenzoneoff gz_id",
  "head": "/greenzoneoff",
  "alias": "",
  "params": [
   {
    "t": "gz_id",
    "ti": "ID зелёной зоны",
    "h": "Номер зелёной зоны."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRGGGG",
  "row": 72
 },
 {
  "name": "/greenzoneon",
  "desc": "Включить зеленую зону.",
  "syntax": "/greenzoneon gz_id",
  "head": "/greenzoneon",
  "alias": "",
  "params": [
   {
    "t": "gz_id",
    "ti": "ID зелёной зоны",
    "h": "Номер зелёной зоны."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRGGGG",
  "row": 73
 },
 {
  "name": "/setstaff",
  "desc": "Установить ранг администратора.",
  "syntax": "/setstaff 123456 rank_id",
  "head": "/setstaff",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "rank_id",
    "ti": "ID ранга",
    "h": "Номер ранга."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRGGGG",
  "row": 74
 },
 {
  "name": "/prolongedban",
  "desc": "Забанить.",
  "syntax": "/prolongedban 123456 60mi NonRP",
  "head": "/prolongedban",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "60mi",
    "ti": "Срок",
    "h": "Длительность: 60 минут (как в примере)."
   },
   {
    "t": "NonRP",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «NonRP»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRGGGG",
  "row": 75
 },
 {
  "name": "/strictban",
  "desc": "Забанить скрытно.",
  "syntax": "/strictban 123456 60mi NonRP",
  "head": "/strictban",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "60mi",
    "ti": "Срок",
    "h": "Длительность: 60 минут (как в примере)."
   },
   {
    "t": "NonRP",
    "ti": "Причина",
    "h": "Причина или пояснение (в примере «NonRP»)."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "always",
   "globaladminplus": "always",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRGGGG",
  "row": 76
 },
 {
  "name": "/giveitem",
  "desc": "Выдать предмет в инвентарь.",
  "syntax": "/giveitem 123456 item_id count",
  "head": "/giveitem",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "item_id",
    "ti": "ID предмета",
    "h": "Номер предмета в инвентаре."
   },
   {
    "t": "count",
    "ti": "Количество",
    "h": "Сколько штук выдать."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "never",
   "globaladminplus": "never",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRRRGG",
  "row": 77
 },
 {
  "name": "/changename",
  "desc": "Сменить имя.",
  "syntax": "/changename 123456 Иван Петухов",
  "head": "/changename",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "Иван",
    "ti": "Новое имя",
    "h": "Имя и фамилия целиком (в примере «Иван Петухов»)."
   },
   {
    "t": "Петухов",
    "ti": "Значение",
    "h": "Значение из примера: Петухов."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "never",
   "globaladminplus": "never",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRRRGG",
  "row": 78
 },
 {
  "name": "/wipestorage",
  "desc": "Очистить инвентарь/хранилище.",
  "syntax": "/wipestorage 123456",
  "head": "/wipestorage",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "never",
   "globaladminplus": "never",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRRRGG",
  "row": 79
 },
 {
  "name": "/addcredits",
  "desc": "Добавить донат-валюты.",
  "syntax": "/addcredits 123456 500",
  "head": "/addcredits",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "500",
    "ti": "Сумма",
    "h": "Сколько донат-валюты выдать."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "never",
   "globaladminplus": "never",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRRRGG",
  "row": 80
 },
 {
  "name": "/addmoney",
  "desc": "Добавить игровой валюты.",
  "syntax": "/addmoney 123456 10000",
  "head": "/addmoney",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "10000",
    "ti": "Сумма",
    "h": "Сколько игровой валюты выдать."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "never",
   "globaladminplus": "never",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRRRGG",
  "row": 81
 },
 {
  "name": "/givecase",
  "desc": "Выдать кейс.",
  "syntax": "/givecase 123456 case_id",
  "head": "/givecase",
  "alias": "",
  "params": [
   {
    "t": "123456",
    "ti": "ID игрока",
    "h": "ID игрока, к которому применяется команда."
   },
   {
    "t": "case_id",
    "ti": "ID кейса",
    "h": "Номер кейса."
   }
  ],
  "note": "",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "never",
   "globaladminplus": "never",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRRRGG",
  "row": 82
 },
 {
  "name": "/perma",
  "desc": "Пермаментный бан.",
  "syntax": "/perma id",
  "head": "/perma",
  "alias": "",
  "params": [
   {
    "t": "id",
    "ti": "ID",
    "h": "ID из примера."
   }
  ],
  "note": "Синтаксис взят из списка пользователя: «/perma id».",
  "rights": {
   "moderator": "never",
   "admin": "never",
   "adminplus": "never",
   "headadmin": "never",
   "superadmin": "never",
   "globaladmin": "never",
   "globaladminplus": "never",
   "deputy_staff_leader": "always",
   "staff_leader": "always"
  },
  "code": "RRRRRRRGG",
  "row": 83
 }
]


_BY_NAME: dict[str, dict] = {c["name"]: c for c in COMMANDS}


def get(name: str) -> dict | None:
    """Команда по точному названию (регистр не важен, слэш не обязателен)."""
    key = str(name or "").strip()
    if not key:
        return None
    if key in _BY_NAME:
        return _BY_NAME[key]
    if "/" + key in _BY_NAME:
        return _BY_NAME["/" + key]
    lowered = {k.lower(): v for k, v in _BY_NAME.items()}
    return lowered.get(key.lower()) or lowered.get("/" + key.lower())


#: Как человек ищет команду и как она называется на самом деле: он пишет
#: «кик», а команда — /kick; пишет «блокировка», а в описании — «забанить».
#: Ключ — нормализованное слово запроса, значение — как искать в названии и
#: в описании. Зеркало — V_CMD_SYNONYMS в app.web.page (тест держит их одинаковыми).
SYNONYMS: dict[str, tuple[str, ...]] = {
    "кик": ("kick",), "кикнуть": ("kick",), "выгнать": ("kick",),
    "мут": ("mute",), "мутить": ("mute",), "замутить": ("mute",),
    "бан": ("ban",), "забанить": ("ban",), "банить": ("ban",),
    "разбанить": ("unban",),
    "блокировка": ("ban", "mute"), "заблокировать": ("ban", "mute"),
    "предупреждение": ("warn",), "варн": ("warn",),
    "пред": ("pred",),
    "заморозить": ("freeze",), "заморозка": ("freeze",), "фриз": ("freeze",),
    "разморозить": ("unfreeze",),
    "телепорт": ("goto", "tp", "teleport"), "тп": ("goto", "tp", "teleport"),
    "телепортировать": ("goto", "teleport"),
    "убить": ("kill",), "килл": ("kill",),
    "здоровье": ("health", "hp"), "хп": ("health", "hp"), "лечение": ("health",),
    "броня": ("armor",), "броник": ("armor",),
    "оружие": ("gun",), "ствол": ("gun",),
    "машина": ("vehicle", "car"), "машину": ("vehicle", "car"),
    "транспорт": ("vehicle", "car"),
    "спавн": ("spawn",), "возродить": ("respawn",), "респавн": ("respawn",),
    "фракция": ("faction",), "лидер": ("leader",), "ранг": ("rank",),
    "деменшин": ("dimension",), "демка": ("dimension",),
    "гм": ("godmode",), "бессмертие": ("godmode",),
    "ноуклип": ("noclip",), "полет": ("noclip",),
    "невидимка": ("esp",), "видеть": ("esp",),
    "чат": ("mutechat", "chat"), "голос": ("mutevoice", "voice"),
    "ник": ("changename", "name"), "никнейм": ("changename", "name"),
    "деньги": ("money", "credits"), "кредиты": ("credits",),
    "предмет": ("item",), "хранилище": ("storage",), "кейс": ("case",),
    "ремонт": ("fixcar",),
    "убить всех": ("killall",), "все": ("all",),
}


def _variants(word: str) -> tuple[str, ...]:
    """Варианты слова для поиска: «кик» → («кик», «kick»).

    Слово запроса всегда идёт первым: синоним добавляется, а не заменяет.
    Иначе «предупреждение» искало бы только ``warn`` и пропускало /pred
    («Выдать устное предупреждение» — слово есть в описании).
    """
    extra = SYNONYMS.get(word)
    if not extra:
        return (word,)
    return tuple(dict.fromkeys((word,) + extra))


def _same_word(a: str, b: str) -> bool:
    """Похожие ли это слова: «блокировка» ≈ «блокировку», но «предупреждение» ≉ «предмет».

    Стеммер обрезает до трёх букв (обе дают «пре»), поэтому сравниваем основу
    напрямую: совпало пять букв с начала, либо одно слово целиком — начало
    другого и не короче четырёх («warn» ≈ «warning»).
    """
    shared = 0
    for x, y in zip(a, b):
        if x != y:
            break
        shared += 1
    shortest = min(len(a), len(b))
    return shared >= 5 or (shared == shortest and shortest >= 4)


def _in_desc(word: str, desc: str) -> bool:
    """Есть ли слово в описании команды — целым словом или по основе.

    «блокировка» должно находить «Снять блокировку чата» (разные формы),
    а короткие вроде «тп» в описание не лезут вообще: иначе «тп» находилось
    внутри слова «Отправить».
    """
    for variant in _variants(word):
        if len(variant) < 3:
            continue
        if re.search(r"(?<!\w)%s(?!\w)" % re.escape(variant), desc):
            return True
        if any(
            _same_word(variant, piece)
            for piece in re.split(r"\W+", desc)
            if piece
        ):
            return True
    return False


def _in_name(word: str, name: str) -> bool:
    """Слово есть в названии команды: по частям («b» в ``give_gun``) или
    подстрокой — но только если слово не короче трёх букв, иначе «id»
    находило ``forbid_buy_chips``."""
    for variant in _variants(word):
        if any(part.startswith(variant) for part in name.split("_")):
            return True
        if len(variant) >= 3 and variant in name:
            return True
    return False


def _norm(value: object) -> str:
    return str(value or "").lower().replace("\u0451", "\u0435")


def search(query: object) -> list[dict]:
    """Поиск по команде: название важнее описания, порядок базы сохраняется.

    Слэш в запросе не обязателен (``kick`` найдёт ``/kick``). Что изменилось
    по баг-репорту №1 («поиск работает криво»):

    * русское слово находит латинскую команду — «кик» → /kick, «тп» → /tp,
      «блокировка» → /ban и /mutechat (см. :data:`SYNONYMS`);
    * короткие слова («id», «тп») ищутся только по частям названия с «_» —
      раньше «id» находило forbid_buy_chips, а «тп» — слово «Отправить»
      в описании /ban;
    * описание сравнивается по целым словам и по основе: «блокировка»
      находит «Снять блокировку чата».
    """
    text = _norm(query).strip()
    if not text:
        return list(COMMANDS)
    needle = text[1:] if text.startswith("/") else text
    words = [w for w in re.split(r"\s+", needle) if w]

    exact: list[dict] = []
    prefix: list[dict] = []
    inside: list[dict] = []
    by_desc: list[dict] = []
    for command in COMMANDS:
        name = _norm(command["name"]).lstrip("/")
        desc = _norm(command["desc"])
        whole = _norm(needle)
        if name == whole or any(name == v for v in _variants(whole)):
            exact.append(command)
        elif name.startswith(whole) or any(
            name.startswith(v) for v in _variants(whole)
        ):
            prefix.append(command)
        elif words and all(_in_name(w, name) for w in words):
            inside.append(command)
        elif words and all(_in_desc(w, desc) for w in words):
            by_desc.append(command)
    # Чем короче название, тем точнее попадание: «/ban» важнее «/infoban».
    inside.sort(key=lambda c: len(c["name"]))
    by_desc.sort(key=lambda c: len(c["name"]))
    return exact + prefix + inside + by_desc


def rights_rows(command: dict) -> list[dict]:
    """Таблица прав: ранг, уровень, состояние — по порядку уровней 0–8."""
    rows = []
    for rank in RANKS:
        state = command["rights"].get(rank["id"], "never")
        color, label = STATE[state]
        rows.append({
            "id": rank["id"],
            "level": rank["level"],
            "group": rank["group"],
            "state": state,
            "color": color,
            "label": label,
            "text": STATE_TEXT[state],
        })
    return rows


def first_available(command: dict) -> dict | None:
    """Самый младший ранг, с которым команду можно использовать (не «никогда»)."""
    for rank in RANKS:
        if command["rights"].get(rank["id"]) != "never":
            return rank
    return None


def payload() -> str:
    """JSON для вкладки «Команды» на сайте (тот же источник, что и в окне)."""
    data = {
        "ranks": RANKS,
        "commands": [
            {
                "n": c["name"],
                "d": c["desc"],
                "s": c["syntax"],
                "h": c["head"],
                "a": c["alias"],
                "p": [[p["t"], p["ti"], p["h"]] for p in c["params"]],
                "nt": c["note"],
                "r": c["code"],
            }
            for c in COMMANDS
        ],
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _badge(state: str) -> str:
    color, label = STATE[state]
    return (
        '<span style="background:%s1f;border:1px solid %s;color:%s;'
        'border-radius:9px;padding:1px 7px;font-size:12px;">%s</span>'
        % (color, color, color, label.replace(" ", "&nbsp;", 1))
    )


def list_html(query: str = "", palette: dict | None = None) -> str:
    """Список команд для QTextBrowser: название, описание, краткие права."""
    from app.help.data import PALETTE, esc, highlight

    p = palette or PALETTE
    rows = search(query)
    if not rows:
        return (
            '<p style="color:%s;margin:14px 2px;">Команда не нашлась — попробуй '
            "без слэша или другое написание.</p>" % p["muted"]
        )
    items = []
    for command in rows:
        summary = "".join(
            '<span style="color:%s;font-size:11px;">%s</span>&nbsp;'
            % (STATE[state][0], symbol)
            for state, symbol in (("always", "🟩"), ("duty", "🟨"),
                                  ("never", "🟥"))
            if state in set(command["rights"].values())
        )
        items.append(
            '<div style="padding:7px 9px;border-bottom:1px solid %s;">'
            '<a href="cmd:%s" style="color:%s;text-decoration:none;'
            'font-family:Consolas,monospace;font-weight:700;font-size:14px;">%s</a>'
            '<span style="float:right;">%s</span>'
            '<div style="color:%s;font-size:13px;margin-top:2px;">%s</div>'
            "</div>"
            % (
                p["border"],
                esc(command["name"]),
                p["accent"],
                highlight(command["name"], query),
                summary,
                p["muted"],
                highlight(command["desc"], query),
            )
        )
    head = (
        '<p style="color:%s;font-size:13px;margin:2px 0 8px 0;">'
        "%d команд • выбор открывает страницу команды</p>" % (p["muted"], len(rows))
    )
    return head + "".join(items)


def page_head_html(command: dict, palette: dict | None = None) -> str:
    """Шапка страницы команды: точное название и описание из списка."""
    from app.help.data import PALETTE, esc

    p = palette or PALETTE
    alias = ""
    if command["alias"]:
        alias = (
            '<div style="color:%s;font-size:13px;margin-top:4px;">В примере '
            "используется запись <b>%s</b></div>" % (p["muted"], esc(command["alias"]))
        )
    note = ""
    if command["note"]:
        note = (
            '<div style="background:%s;border-left:4px solid %s;border-radius:8px;'
            'padding:8px 11px;margin-top:9px;font-size:13px;">%s</div>'
            % (p["field"], p["accent"], esc(command["note"]))
        )
    return (
        '<p style="font-family:Consolas,monospace;font-size:20px;font-weight:700;'
        'color:%s;margin:0 0 4px 0;">%s</p>'
        '<p style="font-size:14px;margin:0 0 6px 0;">%s</p>%s%s'
        '<p style="color:%s;font-size:13px;margin:8px 0 0 0;">Синтаксис: '
        '<b style="font-family:Consolas,monospace;color:%s;">%s</b></p>'
        % (p["accent"], esc(command["name"]), esc(command["desc"]), alias, note,
           p["muted"], p["text"], esc(command["syntax"]))
    )
