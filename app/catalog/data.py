# -*- coding: utf-8 -*-
"""Транспорт и оружие RMRP — таблицы из документации RMRP Study.

Источник — документы «Автомобили RMRP» и «Оружие RMRP»: наименование, ID
и пример команды перенесены как есть. В этих документах картинок нет —
только таблицы, поэтому карточки текстовые.
"""
from __future__ import annotations

import json
import re

from app.catalog import sheet_data

#: Ключ справочника → заголовок вкладки (в окне и на сайте).
TITLES = {
    "transport": "Транспорт",
    "weapon": "Оружие",
    "gt": "Транспорт (Google)",
}

#: Шапка таблицы источника: наименование | ID | пример команды.
COLUMNS = ["Наименование", "ID", "Пример команды"]

#: Свои колонки у справочника из Google-Таблицы (фото и спавн).
COLUMNS_BY_KIND = {"gt": sheet_data.COLUMNS}


def columns(kind: str) -> list[str]:
    """Колонки источника для справочника (по умолчанию — Study)."""
    return COLUMNS_BY_KIND.get(kind, COLUMNS)

#: Разделы источника: ключ справочника → список {title, rows} (3 колонки).
SECTIONS: dict[str, list[dict]] = {
    "transport": [
        {"title": "🚤 Водный транспорт", "rows": [
            ["Субмарина Avisa", "avisa", "/spawnvehicle avisa"],
            ["Лодка", "dinghy", "/spawnvehicle dinghy"],
            ["Лодка 2", "dinghy2", "/spawnvehicle dinghy2"],
            ["Лодка 3", "dinghy3", "/spawnvehicle dinghy3"],
            ["Лодка 4", "dinghy4", "/spawnvehicle dinghy4"],
            ["Лодка 5", "dinghy5", "/spawnvehicle dinghy5"],
            ["Лодка Jetmax", "jetmax", "/spawnvehicle jetmax"],
            ["Подлодка Косатка", "kosatka", "/spawnvehicle kosatka"],
            ["Лодка Longfin", "longfin", "/spawnvehicle longfin"],
            ["Парусная лодка", "marquis", "/spawnvehicle marquis"],
            ["Патрульная лодка", "patrolboat", "/spawnvehicle patrolboat"],
            ["Гидроцикл", "seashark", "/spawnvehicle seashark"],
            ["Гидроцикл 2", "seashark2", "/spawnvehicle seashark2"],
            ["Гидроцикл 3", "seashark3", "/spawnvehicle seashark3"],
            ["Лодка Speeder", "speeder", "/spawnvehicle speeder"],
            ["Лодка Speeder 2", "speeder2", "/spawnvehicle speeder2"],
            ["Лодка Squalo", "squalo", "/spawnvehicle squalo"],
            ["Субмарина", "submersible", "/spawnvehicle submersible"],
            ["Батискаф", "submersible2", "/spawnvehicle submersible2"],
            ["Лодка Suntrap", "suntrap", "/spawnvehicle suntrap"],
            ["Лодка Toro", "toro", "/spawnvehicle toro"],
            ["Лодка Toro 2", "toro2", "/spawnvehicle toro2"],
            ["Лодка Tropic", "tropic", "/spawnvehicle tropic"],
            ["Лодка Tropic 2", "tropic2", "/spawnvehicle tropic2"],
            ["Буксир", "tug", "/spawnvehicle tug"],
        ],
        },
        {"title": "🚛 Грузовой транспорт", "rows": [
            ["Фургон Benson", "benson", "/spawnvehicle benson"],
            ["Фургон Benson 2", "benson2", "/spawnvehicle benson2"],
            ["Мусоровоз", "biff", "/spawnvehicle biff"],
            ["Фургон с огнеметом", "cerberus", "/spawnvehicle cerberus"],
            ["Фургон 2 с огнеметом", "cerberus2", "/spawnvehicle cerberus2"],
            ["Фургон 3 с огнеметом", "cerberus3", "/spawnvehicle cerberus3"],
            ["Фура", "hauler", "/spawnvehicle hauler"],
            ["Фура 2", "hauler2", "/spawnvehicle hauler2"],
            ["Фургон Mule", "mule", "/spawnvehicle mule"],
            ["Фургон Mule 2", "mule2", "/spawnvehicle mule2"],
            ["Фургон Mule 3", "mule3", "/spawnvehicle mule3"],
            ["Фургон Mule 4", "mule4", "/spawnvehicle mule4"],
            ["Фургон Mule 5", "mule5", "/spawnvehicle mule5"],
            ["Тягач", "packer", "/spawnvehicle packer"],
            ["Тягач", "phantom", "/spawnvehicle phantom"],
            ["Тягач Крушитель", "phantom2", "/spawnvehicle phantom2"],
            ["Тягач 3", "phantom3", "/spawnvehicle phantom3"],
            ["Тягач новогодний", "phantom4", "/spawnvehicle phantom4"],
            ["Удлинённый фургон", "pounder", "/spawnvehicle pounder"],
            ["Фургон 2", "pounder2", "/spawnvehicle pounder2"],
            ["Инкассатор", "stockade", "/spawnvehicle stockade"],
            ["Инкассатор (снег)", "stockade3", "/spawnvehicle stockade3"],
            ["Большой инкассатор", "terbyte", "/spawnvehicle terbyte"],
        ],
        },
        {"title": "🚓 Спецслужбы", "rows": [
            ["Скорая помощь", "ambulance", "/spawnvehicle ambulance"],
            ["FBI", "fbi", "/spawnvehicle fbi"],
            ["FBI 2", "fbi2", "/spawnvehicle fbi2"],
            ["Пожарная", "firetruk", "/spawnvehicle firetruk"],
            ["Береговая охрана", "lguard", "/spawnvehicle lguard"],
            ["Автобус полиции", "pbus", "/spawnvehicle pbus"],
        ],
        },
        {"title": "🚔 Полиция", "rows": [
            ["Полиция", "police", "/spawnvehicle police"],
            ["Полиция 2", "police2", "/spawnvehicle police2"],
            ["Полиция 3", "police3", "/spawnvehicle police3"],
            ["Полиция 4", "police4", "/spawnvehicle police4"],
            ["Полицейский байк", "policeb", "/spawnvehicle policeb"],
            ["Полицейский вертолёт", "polmav", "/spawnvehicle polmav"],
            ["Старая полиция", "policeold1", "/spawnvehicle policeold1"],
            ["Старая полиция 2", "policeold2", "/spawnvehicle policeold2"],
            ["Полицейский грузовик", "policet", "/spawnvehicle policet"],
            ["Ranger", "pranger", "/spawnvehicle pranger"],
            ["Полицейская лодка", "predator", "/spawnvehicle predator"],
            ["Riot", "riot", "/spawnvehicle riot"],
            ["Riot 2", "riot2", "/spawnvehicle riot2"],
            ["Шериф", "sheriff", "/spawnvehicle sheriff"],
            ["Шериф 2", "sheriff2", "/spawnvehicle sheriff2"],
        ],
        },
        {"title": "🚗 Мини машины", "rows": [
            ["Asbo", "asbo", "/spawnvehicle asbo"],
            ["Blista", "blista", "/spawnvehicle blista"],
            ["Brioso", "brioso", "/spawnvehicle brioso"],
            ["Brioso 2", "brioso2", "/spawnvehicle brioso2"],
            ["Brioso 3", "brioso3", "/spawnvehicle brioso3"],
            ["Club", "club", "/spawnvehicle club"],
            ["Dilettante", "dilettante", "/spawnvehicle dilettante"],
            ["Dilettante 2", "dilettante2", "/spawnvehicle dilettante2"],
            ["Kanjo", "kanjo", "/spawnvehicle kanjo"],
            ["Issi 2", "issi2", "/spawnvehicle issi2"],
            ["Issi 4", "issi4", "/spawnvehicle issi4"],
            ["Issi 5", "issi5", "/spawnvehicle issi5"],
            ["Issi 6", "issi6", "/spawnvehicle issi6"],
            ["Panto", "panto", "/spawnvehicle panto"],
            ["Prairie", "prairie", "/spawnvehicle prairie"],
            ["Rhapsody", "rhapsody", "/spawnvehicle rhapsody"],
            ["Weevil", "weevil", "/spawnvehicle weevil"],
        ],
        },
        {"title": "🚘 Легковые", "rows": [
            ["Cogcabrio", "cogcabrio", "/spawnvehicle cogcabrio"],
            ["Exemplar", "exemplar", "/spawnvehicle exemplar"],
            ["F620", "f620", "/spawnvehicle f620"],
            ["Felon", "felon", "/spawnvehicle felon"],
            ["Felon 2", "felon2", "/spawnvehicle felon2"],
            ["Jackal", "jackal", "/spawnvehicle jackal"],
            ["Kanjo SJ", "kanjosj", "/spawnvehicle kanjosj"],
            ["Oracle", "oracle", "/spawnvehicle oracle"],
            ["Oracle 2", "oracle2", "/spawnvehicle oracle2"],
            ["Postlude", "postlude", "/spawnvehicle postlude"],
            ["Previon", "previon", "/spawnvehicle previon"],
            ["Sentinel", "sentinel", "/spawnvehicle sentinel"],
            ["Sentinel 2", "sentinel2", "/spawnvehicle sentinel2"],
            ["Windsor", "windsor", "/spawnvehicle windsor"],
            ["Windsor 2", "windsor2", "/spawnvehicle windsor2"],
            ["Zion", "zion", "/spawnvehicle zion"],
            ["Zion 2", "zion2", "/spawnvehicle zion2"],
        ],
        },
        {"title": "🚴 Велосипеды", "rows": [
            ["BMX", "bmx", "/spawnvehicle bmx"],
            ["Cruiser", "cruiser", "/spawnvehicle cruiser"],
            ["Fixter", "fixter", "/spawnvehicle fixter"],
            ["Scorcher", "scorcher", "/spawnvehicle scorcher"],
            ["Tribike", "tribike", "/spawnvehicle tribike"],
            ["Tribike 2", "tribike2", "/spawnvehicle tribike2"],
            ["Tribike 3", "tribike3", "/spawnvehicle tribike3"],
        ],
        },
        {"title": "🚁 Вертолёты", "rows": [
            ["Akula", "akula", "/spawnvehicle akula"],
            ["Annihilator", "annihilator", "/spawnvehicle annihilator"],
            ["Annihilator 2", "annihilator2", "/spawnvehicle annihilator2"],
            ["Buzzard", "buzzard", "/spawnvehicle buzzard"],
            ["Buzzard 2", "buzzard2", "/spawnvehicle buzzard2"],
            ["Cargobob", "cargobob", "/spawnvehicle cargobob"],
            ["Cargobob 2", "cargobob2", "/spawnvehicle cargobob2"],
            ["Cargobob 3", "cargobob3", "/spawnvehicle cargobob3"],
            ["Cargobob 4", "cargobob4", "/spawnvehicle cargobob4"],
            ["Conada", "conada", "/spawnvehicle conada"],
            ["Frogger", "frogger", "/spawnvehicle frogger"],
            ["Frogger 2", "frogger2", "/spawnvehicle frogger2"],
            ["Havok", "havok", "/spawnvehicle havok"],
            ["Hunter", "hunter", "/spawnvehicle hunter"],
            ["Maverick", "maverick", "/spawnvehicle maverick"],
            ["Savage", "savage", "/spawnvehicle savage"],
            ["Skylift", "skylift", "/spawnvehicle skylift"],
            ["SuperVolito", "supervolito", "/spawnvehicle supervolito"],
            ["SuperVolito 2", "supervolito2", "/spawnvehicle supervolito2"],
            ["Swift", "swift", "/spawnvehicle swift"],
            ["Swift 2", "swift2", "/spawnvehicle swift2"],
            ["Valkyrie", "valkyrie", "/spawnvehicle valkyrie"],
            ["Valkyrie 2", "valkyrie2", "/spawnvehicle valkyrie2"],
            ["Volatus", "volatus", "/spawnvehicle volatus"],
        ],
        },
        {"title": "⚔️ Военная техника", "rows": [
            ["APC", "apc", "/spawnvehicle apc"],
            ["Barracks", "barracks", "/spawnvehicle barracks"],
            ["Barracks 2", "barracks2", "/spawnvehicle barracks2"],
            ["Barracks 3", "barracks3", "/spawnvehicle barracks3"],
            ["Barrage", "barrage", "/spawnvehicle barrage"],
            ["Chernobog", "chernobog", "/spawnvehicle chernobog"],
            ["Crusader", "crusader", "/spawnvehicle crusader"],
            ["Halftrack", "halftrack", "/spawnvehicle halftrack"],
            ["Khanjali", "khanjali", "/spawnvehicle khanjali"],
            ["Minitank", "minitank", "/spawnvehicle minitank"],
            ["Rhino", "rhino", "/spawnvehicle rhino"],
            ["Scarab", "scarab", "/spawnvehicle scarab"],
            ["Scarab 2", "scarab2", "/spawnvehicle scarab2"],
            ["Scarab 3", "scarab3", "/spawnvehicle scarab3"],
            ["Thruster", "thruster", "/spawnvehicle thruster"],
            ["Vetir", "vetir", "/spawnvehicle vetir"],
        ],
        },
        {"title": "🏍️ Мотоциклы", "rows": [
            ["Akuma", "akuma", "/spawnvehicle akuma"],
            ["Avarus", "avarus", "/spawnvehicle avarus"],
            ["Bagger", "bagger", "/spawnvehicle bagger"],
            ["Bati", "bati", "/spawnvehicle bati"],
            ["Bati 2", "bati2", "/spawnvehicle bati2"],
            ["BF400", "bf400", "/spawnvehicle bf400"],
            ["Carbon RS", "carbonrs", "/spawnvehicle carbonrs"],
            ["Chimera", "chimera", "/spawnvehicle chimera"],
            ["Cliffhanger", "cliffhanger", "/spawnvehicle cliffhanger"],
            ["Daemon", "daemon", "/spawnvehicle daemon"],
            ["Daemon 2", "daemon2", "/spawnvehicle daemon2"],
            ["Defiler", "defiler", "/spawnvehicle defiler"],
            ["Deathbike", "deathbike", "/spawnvehicle deathbike"],
            ["Deathbike 2", "deathbike2", "/spawnvehicle deathbike2"],
            ["Deathbike 3", "deathbike3", "/spawnvehicle deathbike3"],
            ["Diablous", "diablous", "/spawnvehicle diablous"],
            ["Diablous 2", "diablous2", "/spawnvehicle diablous2"],
            ["Double", "double", "/spawnvehicle double"],
            ["Enduro", "enduro", "/spawnvehicle enduro"],
            ["Esskey", "esskey", "/spawnvehicle esskey"],
            ["Faggio", "faggio", "/spawnvehicle faggio"],
            ["Faggio 2", "faggio2", "/spawnvehicle faggio2"],
            ["Faggio 3", "faggio3", "/spawnvehicle faggio3"],
            ["FCR", "fcr", "/spawnvehicle fcr"],
            ["FCR 2", "fcr2", "/spawnvehicle fcr2"],
            ["Gargoyle", "gargoyle", "/spawnvehicle gargoyle"],
            ["Hakuchou", "hakuchou", "/spawnvehicle hakuchou"],
            ["Hakuchou 2", "hakuchou2", "/spawnvehicle hakuchou2"],
            ["Hexer", "hexer", "/spawnvehicle hexer"],
            ["Innovation", "innovation", "/spawnvehicle innovation"],
            ["Lectro", "lectro", "/spawnvehicle lectro"],
            ["Manchez", "manchez", "/spawnvehicle manchez"],
            ["Manchez 2", "manchez2", "/spawnvehicle manchez2"],
            ["Manchez 3", "manchez3", "/spawnvehicle manchez3"],
            ["Nemesis", "nemesis", "/spawnvehicle nemesis"],
            ["Nightblade", "nightblade", "/spawnvehicle nightblade"],
            ["Oppressor", "oppressor", "/spawnvehicle oppressor"],
            ["Oppressor 2", "oppressor2", "/spawnvehicle oppressor2"],
            ["PCJ", "pcj", "/spawnvehicle pcj"],
            ["Powersurge", "powersurge", "/spawnvehicle powersurge"],
            ["Ratbike", "ratbike", "/spawnvehicle ratbike"],
            ["Reever", "reever", "/spawnvehicle reever"],
            ["Ruffian", "ruffian", "/spawnvehicle ruffian"],
            ["Rocket", "rocket", "/spawnvehicle rocket"],
            ["Sanchez", "sanchez", "/spawnvehicle sanchez"],
            ["Sanchez 2", "sanchez2", "/spawnvehicle sanchez2"],
            ["Sanctus", "sanctus", "/spawnvehicle sanctus"],
            ["Shinobi", "shinobi", "/spawnvehicle shinobi"],
            ["Shotaro", "shotaro", "/spawnvehicle shotaro"],
            ["Sovereign", "sovereign", "/spawnvehicle sovereign"],
            ["Stryder", "stryder", "/spawnvehicle stryder"],
            ["Thrust", "thrust", "/spawnvehicle thrust"],
            ["Vader", "vader", "/spawnvehicle vader"],
            ["Vindicator", "vindicator", "/spawnvehicle vindicator"],
            ["Vortex", "vortex", "/spawnvehicle vortex"],
            ["Wolfsbane", "wolfsbane", "/spawnvehicle wolfsbane"],
            ["Zombie A", "zombiea", "/spawnvehicle zombiea"],
            ["Zombie B", "zombieb", "/spawnvehicle zombieb"],
        ],
        },
        {"title": "🚜 Промышленная техника", "rows": [
            ["Бульдозер", "bulldozer", "/spawnvehicle bulldozer"],
            ["Cutter", "cutter", "/spawnvehicle cutter"],
            ["Dump", "dump", "/spawnvehicle dump"],
            ["Flatbed", "flatbed", "/spawnvehicle flatbed"],
            ["Guardian", "guardian", "/spawnvehicle guardian"],
            ["Handler", "handler", "/spawnvehicle handler"],
            ["Mixer", "mixer", "/spawnvehicle mixer"],
            ["Mixer 2", "mixer2", "/spawnvehicle mixer2"],
            ["Rubble", "rubble", "/spawnvehicle rubble"],
            ["Tiptruck", "tiptruck", "/spawnvehicle tiptruck"],
            ["Tiptruck 2", "tiptruck2", "/spawnvehicle tiptruck2"],
        ],
        },
        {"title": "✈️ Самолёты", "rows": [
            ["Alkonost", "alkonost", "/spawnvehicle alkonost"],
            ["Alphaz1", "alphaz1", "/spawnvehicle alphaz1"],
            ["Avenger", "avenger", "/spawnvehicle avenger"],
            ["Avenger 2", "avenger2", "/spawnvehicle avenger2"],
            ["Besra", "besra", "/spawnvehicle besra"],
            ["Blimp", "blimp", "/spawnvehicle blimp"],
            ["Blimp 2", "blimp2", "/spawnvehicle blimp2"],
            ["Blimp 3", "blimp3", "/spawnvehicle blimp3"],
            ["Bombushka", "bombushka", "/spawnvehicle bombushka"],
            ["Cuban 800", "cuban800", "/spawnvehicle cuban800"],
            ["Duster", "duster", "/spawnvehicle duster"],
            ["Hydra", "hydra", "/spawnvehicle hydra"],
            ["Jet", "jet", "/spawnvehicle jet"],
            ["Lazer", "lazer", "/spawnvehicle lazer"],
            ["Luxor", "luxor", "/spawnvehicle luxor"],
            ["Luxor 2", "luxor2", "/spawnvehicle luxor2"],
            ["Mammatus", "mammatus", "/spawnvehicle mammatus"],
            ["Miljet", "miljet", "/spawnvehicle miljet"],
            ["Molotok", "molotok", "/spawnvehicle molotok"],
            ["Nimbus", "nimbus", "/spawnvehicle nimbus"],
            ["Nokota", "nokota", "/spawnvehicle nokota"],
            ["Pyro", "pyro", "/spawnvehicle pyro"],
            ["Rogue", "rogue", "/spawnvehicle rogue"],
            ["Seabreeze", "seabreeze", "/spawnvehicle seabreeze"],
            ["Shamal", "shamal", "/spawnvehicle shamal"],
            ["Starling", "starling", "/spawnvehicle starling"],
            ["Strikeforce", "strikeforce", "/spawnvehicle strikeforce"],
            ["Titan", "titan", "/spawnvehicle titan"],
            ["Tula", "tula", "/spawnvehicle tula"],
            ["Velum", "velum", "/spawnvehicle velum"],
            ["Velum 2", "velum2", "/spawnvehicle velum2"],
            ["Vestra", "vestra", "/spawnvehicle vestra"],
            ["Volatol", "volatol", "/spawnvehicle volatol"],
        ],
        },
        {"title": "🚎 Автобусы", "rows": [
            ["Airbus", "airbus", "/spawnvehicle airbus"],
            ["Brickade", "brickade", "/spawnvehicle brickade"],
            ["Bus", "bus", "/spawnvehicle bus"],
            ["Coach", "coach", "/spawnvehicle coach"],
            ["Police Bus", "pbus2", "/spawnvehicle pbus2"],
            ["Rally Truck", "rallytruck", "/spawnvehicle rallytruck"],
            ["Rental Bus", "rentalbus", "/spawnvehicle rentalbus"],
            ["Taxi", "taxi", "/spawnvehicle taxi"],
            ["Tour Bus", "tourbus", "/spawnvehicle tourbus"],
            ["Мусоровоз", "trash", "/spawnvehicle trash"],
            ["Мусоровоз RMRP", "trash2", "/spawnvehicle trash2"],
            ["Wastelander", "wastelander", "/spawnvehicle wastelander"],
        ],
        },
        {"title": "🚗 Классические авто", "rows": [
            ["Blade", "blade", "/spawnvehicle blade"],
            ["Broadway", "broadway", "/spawnvehicle broadway"],
            ["Buccaneer", "buccaneer", "/spawnvehicle buccaneer"],
            ["Buccaneer 2", "buccaneer2", "/spawnvehicle buccaneer2"],
            ["Chino", "chino", "/spawnvehicle chino"],
            ["Chino 2", "chino2", "/spawnvehicle chino2"],
            ["Clique", "clique", "/spawnvehicle clique"],
            ["Coquette BlackFin", "coquette3", "/spawnvehicle coquette3"],
            ["Deviant", "deviant", "/spawnvehicle deviant"],
            ["Dominator", "dominator", "/spawnvehicle dominator"],
            ["Dominator 2", "dominator2", "/spawnvehicle dominator2"],
            ["Dominator 3", "dominator3", "/spawnvehicle dominator3"],
            ["Dominator 4", "dominator4", "/spawnvehicle dominator4"],
            ["Dominator 5", "dominator5", "/spawnvehicle dominator5"],
            ["Dominator 6", "dominator6", "/spawnvehicle dominator6"],
            ["Dominator 7", "dominator7", "/spawnvehicle dominator7"],
            ["Dukes", "dukes", "/spawnvehicle dukes"],
            ["Dukes 2", "dukes2", "/spawnvehicle dukes2"],
            ["Dukes 3", "dukes3", "/spawnvehicle dukes3"],
            ["Faction", "faction", "/spawnvehicle faction"],
            ["Faction 2", "faction2", "/spawnvehicle faction2"],
            ["Faction 3", "faction3", "/spawnvehicle faction3"],
            ["Ellie", "ellie", "/spawnvehicle ellie"],
            ["Eudora", "eudora", "/spawnvehicle eudora"],
            ["Gauntlet", "gauntlet", "/spawnvehicle gauntlet"],
            ["Gauntlet 2", "gauntlet2", "/spawnvehicle gauntlet2"],
            ["Gauntlet 3", "gauntlet3", "/spawnvehicle gauntlet3"],
            ["Gauntlet 4", "gauntlet4", "/spawnvehicle gauntlet4"],
            ["Gauntlet 5", "gauntlet5", "/spawnvehicle gauntlet5"],
            ["Greenwood", "greenwood", "/spawnvehicle greenwood"],
            ["Hermes", "hermes", "/spawnvehicle hermes"],
            ["Hotknife", "hotknife", "/spawnvehicle hotknife"],
            ["Hustler", "hustler", "/spawnvehicle hustler"],
            ["Impaler", "impaler", "/spawnvehicle impaler"],
            ["Impaler 2", "impaler2", "/spawnvehicle impaler2"],
            ["Impaler 3", "impaler3", "/spawnvehicle impaler3"],
            ["Impaler 4", "impaler4", "/spawnvehicle impaler4"],
            ["Imperator", "imperator", "/spawnvehicle imperator"],
            ["Imperator 2", "imperator2", "/spawnvehicle imperator2"],
            ["Imperator 3", "imperator3", "/spawnvehicle imperator3"],
            ["Lurcher", "lurcher", "/spawnvehicle lurcher"],
            ["Moonbeam", "moonbeam", "/spawnvehicle moonbeam"],
            ["Moonbeam 2", "moonbeam2", "/spawnvehicle moonbeam2"],
            ["Nightshade", "nightshade", "/spawnvehicle nightshade"],
            ["Peyote Custom", "peyote2", "/spawnvehicle peyote2"],
            ["Picador", "picador", "/spawnvehicle picador"],
            ["Ratloader", "ratloader", "/spawnvehicle ratloader"],
            ["Ratloader 2", "ratloader2", "/spawnvehicle ratloader2"],
            ["Ruiner", "ruiner", "/spawnvehicle ruiner"],
            ["Ruiner 2", "ruiner2", "/spawnvehicle ruiner2"],
            ["Ruiner 3", "ruiner3", "/spawnvehicle ruiner3"],
            ["Ruiner 4", "ruiner4", "/spawnvehicle ruiner4"],
            ["Sabre GT", "sabregt", "/spawnvehicle sabregt"],
            ["Sabre GT 2", "sabregt2", "/spawnvehicle sabregt2"],
            ["Slamvan", "slamvan", "/spawnvehicle slamvan"],
            ["Slamvan 2", "slamvan2", "/spawnvehicle slamvan2"],
            ["Slamvan 3", "slamvan3", "/spawnvehicle slamvan3"],
            ["Slamvan 4", "slamvan4", "/spawnvehicle slamvan4"],
            ["Slamvan 5", "slamvan5", "/spawnvehicle slamvan5"],
            ["Slamvan 6", "slamvan6", "/spawnvehicle slamvan6"],
            ["Station Wagon", "station", "/spawnvehicle station"],
            ["Station Wagon 2", "station2", "/spawnvehicle station2"],
            ["Tahoma", "tahoma", "/spawnvehicle tahoma"],
            ["Tampa", "tampa", "/spawnvehicle tampa"],
            ["Tampa 3", "tampa3", "/spawnvehicle tampa3"],
            ["Tulip", "tulip", "/spawnvehicle tulip"],
            ["Tulip 2", "tulip2", "/spawnvehicle tulip2"],
            ["Vamos", "vamos", "/spawnvehicle vamos"],
            ["Vigero", "vigero", "/spawnvehicle vigero"],
            ["Vigero 2", "vigero2", "/spawnvehicle vigero2"],
            ["Virgo", "virgo", "/spawnvehicle virgo"],
            ["Virgo 2", "virgo2", "/spawnvehicle virgo2"],
            ["Virgo 3", "virgo3", "/spawnvehicle virgo3"],
            ["Voodoo", "voodoo", "/spawnvehicle voodoo"],
            ["Voodoo 2", "voodoo2", "/spawnvehicle voodoo2"],
            ["Yosemite", "yosemite", "/spawnvehicle yosemite"],
            ["Yosemite 2", "yosemite2", "/spawnvehicle yosemite2"],
            ["Yosemite 3", "yosemite3", "/spawnvehicle yosemite3"],
        ],
        },
        {"title": "🚙 Внедорожники", "rows": [
            ["Bifta", "bifta", "/spawnvehicle bifta"],
            ["Blazer", "blazer", "/spawnvehicle blazer"],
            ["Blazer 2", "blazer2", "/spawnvehicle blazer2"],
            ["Blazer 3", "blazer3", "/spawnvehicle blazer3"],
            ["Blazer 4", "blazer4", "/spawnvehicle blazer4"],
            ["Blazer 5", "blazer5", "/spawnvehicle blazer5"],
            ["Bodhi", "bodhi2", "/spawnvehicle bodhi2"],
            ["Brawler", "brawler", "/spawnvehicle brawler"],
            ["Bruiser", "bruiser", "/spawnvehicle bruiser"],
            ["Bruiser 2", "bruiser2", "/spawnvehicle bruiser2"],
            ["Bruiser 3", "bruiser3", "/spawnvehicle bruiser3"],
            ["Brutus", "brutus", "/spawnvehicle brutus"],
            ["Brutus 2", "brutus2", "/spawnvehicle brutus2"],
            ["Brutus 3", "brutus3", "/spawnvehicle brutus3"],
            ["Caracara", "caracara", "/spawnvehicle caracara"],
            ["Caracara 2", "caracara2", "/spawnvehicle caracara2"],
            ["DLoader", "dloader", "/spawnvehicle dloader"],
            ["Draugur", "draugur", "/spawnvehicle draugur"],
            ["Dubsta 6x6", "dubsta3", "/spawnvehicle dubsta3"],
            ["Dune", "dune", "/spawnvehicle dune"],
            ["Dune 2", "dune2", "/spawnvehicle dune2"],
            ["Dune 3", "dune3", "/spawnvehicle dune3"],
            ["Dune 4", "dune4", "/spawnvehicle dune4"],
            ["Dune 5", "dune5", "/spawnvehicle dune5"],
            ["Everon", "everon", "/spawnvehicle everon"],
            ["Freecrawler", "freecrawler", "/spawnvehicle freecrawler"],
            ["Hellion", "hellion", "/spawnvehicle hellion"],
            ["Insurgent", "insurgent", "/spawnvehicle insurgent"],
            ["Insurgent 2", "insurgent2", "/spawnvehicle insurgent2"],
            ["Insurgent 3", "insurgent3", "/spawnvehicle insurgent3"],
            ["Kalahari", "kalahari", "/spawnvehicle kalahari"],
            ["Kamacho", "kamacho", "/spawnvehicle kamacho"],
            ["Marshall", "marshall", "/spawnvehicle marshall"],
            ["Mesa 3", "mesa3", "/spawnvehicle mesa3"],
            ["Monster Truck", "monster", "/spawnvehicle monster"],
            ["Monster 4", "monster4", "/spawnvehicle monster4"],
            ["Monster 5", "monster5", "/spawnvehicle monster5"],
            ["Menacer", "menacer", "/spawnvehicle menacer"],
            ["Outlaw", "outlaw", "/spawnvehicle outlaw"],
            ["Nightshark", "nightshark", "/spawnvehicle nightshark"],
            ["Patriot 3", "patriot3", "/spawnvehicle patriot3"],
            ["Rancher XL", "rancherxl", "/spawnvehicle rancherxl"],
            ["Rancher XL 2", "rancherxl2", "/spawnvehicle rancherxl2"],
            ["Rebel", "rebel", "/spawnvehicle rebel"],
            ["Rebel 2", "rebel2", "/spawnvehicle rebel2"],
            ["RC Bandito", "rcbandito", "/spawnvehicle rcbandito"],
            ["Riata", "riata", "/spawnvehicle riata"],
            ["Sandking", "sandking", "/spawnvehicle sandking"],
            ["Sandking 2", "sandking2", "/spawnvehicle sandking2"],
            ["Technical", "technical", "/spawnvehicle technical"],
            ["Technical 2", "technical2", "/spawnvehicle technical2"],
            ["Trophy Truck", "trophytruck", "/spawnvehicle trophytruck"],
            ["Trophy Truck 2", "trophytruck2", "/spawnvehicle trophytruck2"],
            ["Vagrant", "vagrant", "/spawnvehicle vagrant"],
            ["Verus", "verus", "/spawnvehicle verus"],
            ["Winky", "winky", "/spawnvehicle winky"],
            ["Zhaba", "zhaba", "/spawnvehicle zhaba"],
        ],
        },
        {"title": "🏎️ Спорткары", "rows": [
            ["Adder", "adder", "/spawnvehicle adder"],
            ["Autarch", "autarch", "/spawnvehicle autarch"],
            ["Bullet", "bullet", "/spawnvehicle bullet"],
            ["Champion", "champion", "/spawnvehicle champion"],
            ["Cheetah", "cheetah", "/spawnvehicle cheetah"],
            ["Cyclone", "cyclone", "/spawnvehicle cyclone"],
            ["Entity XF", "entityxf", "/spawnvehicle entityxf"],
            ["Entity XXR", "entity2", "/spawnvehicle entity2"],
            ["Entity MT", "entity3", "/spawnvehicle entity3"],
            ["Emerus", "emerus", "/spawnvehicle emerus"],
            ["FMJ", "fmj", "/spawnvehicle fmj"],
            ["Furia", "furia", "/spawnvehicle furia"],
            ["GP1", "gp1", "/spawnvehicle gp1"],
            ["Ignus", "ignus", "/spawnvehicle ignus"],
            ["Infernus", "infernus", "/spawnvehicle infernus"],
            ["Itali GTB", "italigtb", "/spawnvehicle italigtb"],
            ["Itali GTB 2", "italigtb2", "/spawnvehicle italigtb2"],
            ["Krieger", "krieger", "/spawnvehicle krieger"],
            ["Nero", "nero", "/spawnvehicle nero"],
            ["Nero 2", "nero2", "/spawnvehicle nero2"],
            ["Osiris", "osiris", "/spawnvehicle osiris"],
            ["Penetrator", "penetrator", "/spawnvehicle penetrator"],
            ["Pfister 811", "pfister811", "/spawnvehicle pfister811"],
            ["Prototipo", "prototipo", "/spawnvehicle prototipo"],
            ["Reaper", "reaper", "/spawnvehicle reaper"],
            ["S80RR", "s80", "/spawnvehicle s80"],
            ["SC1", "sc1", "/spawnvehicle sc1"],
            ["Scramjet", "scramjet", "/spawnvehicle scramjet"],
            ["Sheava", "sheava", "/spawnvehicle sheava"],
            ["Sultan RS", "sultanrs", "/spawnvehicle sultanrs"],
            ["T20", "t20", "/spawnvehicle t20"],
            ["Taipan", "taipan", "/spawnvehicle taipan"],
            ["Tempesta", "tempesta", "/spawnvehicle tempesta"],
            ["Tezeract", "tezeract", "/spawnvehicle tezeract"],
            ["Thrax", "thrax", "/spawnvehicle thrax"],
            ["Tigon", "tigon", "/spawnvehicle tigon"],
            ["Torero 2", "torero2", "/spawnvehicle torero2"],
            ["Turismo R", "turismor", "/spawnvehicle turismor"],
            ["Tyrant", "tyrant", "/spawnvehicle tyrant"],
            ["Tyrus", "tyrus", "/spawnvehicle tyrus"],
            ["Vacca", "vacca", "/spawnvehicle vacca"],
            ["Vagner", "vagner", "/spawnvehicle vagner"],
            ["Vigilante", "vigilante", "/spawnvehicle vigilante"],
            ["Virtue", "virtue", "/spawnvehicle virtue"],
            ["Visione", "visione", "/spawnvehicle visione"],
            ["Voltic", "voltic", "/spawnvehicle voltic"],
            ["Voltic 2", "voltic2", "/spawnvehicle voltic2"],
            ["XA-21", "xa21", "/spawnvehicle xa21"],
            ["Zentorno", "zentorno", "/spawnvehicle zentorno"],
            ["Zeno", "zeno", "/spawnvehicle zeno"],
            ["Zorrusso", "zorrusso", "/spawnvehicle zorrusso"],
        ],
        },
        {"title": "🚙 SUV / Джипы", "rows": [
            ["Aleutian", "aleutian", "/spawnvehicle aleutian"],
            ["Astron", "astron", "/spawnvehicle astron"],
            ["Baller", "baller", "/spawnvehicle baller"],
            ["Baller 2", "baller2", "/spawnvehicle baller2"],
            ["Baller 3", "baller3", "/spawnvehicle baller3"],
            ["Baller 4", "baller4", "/spawnvehicle baller4"],
            ["Baller 5", "baller5", "/spawnvehicle baller5"],
            ["Baller 6", "baller6", "/spawnvehicle baller6"],
            ["Baller 7", "baller7", "/spawnvehicle baller7"],
            ["BJXL", "bjxl", "/spawnvehicle bjxl"],
            ["Cavalcade", "cavalcade", "/spawnvehicle cavalcade"],
            ["Cavalcade 2", "cavalcade2", "/spawnvehicle cavalcade2"],
            ["Contender", "contender", "/spawnvehicle contender"],
            ["Dubsta", "dubsta", "/spawnvehicle dubsta"],
            ["Dubsta 2", "dubsta2", "/spawnvehicle dubsta2"],
            ["FQ2", "fq2", "/spawnvehicle fq2"],
            ["Granger", "granger", "/spawnvehicle granger"],
            ["Granger 2", "granger2", "/spawnvehicle granger2"],
            ["Gresley", "gresley", "/spawnvehicle gresley"],
            ["Habanero", "habanero", "/spawnvehicle habanero"],
            ["Huntley", "huntley", "/spawnvehicle huntley"],
            ["Iwagen", "iwagen", "/spawnvehicle iwagen"],
            ["Jubilee", "jubilee", "/spawnvehicle jubilee"],
            ["Landstalker", "landstalker", "/spawnvehicle landstalker"],
            ["Landstalker 2", "landstalker2", "/spawnvehicle landstalker2"],
            ["Mesa", "mesa", "/spawnvehicle mesa"],
            ["Mesa 2", "mesa2", "/spawnvehicle mesa2"],
            ["Novak", "novak", "/spawnvehicle novak"],
            ["Patriot", "patriot", "/spawnvehicle patriot"],
            ["Patriot 2", "patriot2", "/spawnvehicle patriot2"],
            ["Radi", "radi", "/spawnvehicle radi"],
            ["Rebla", "rebla", "/spawnvehicle rebla"],
            ["Rocoto", "rocoto", "/spawnvehicle rocoto"],
            ["Seminole", "seminole", "/spawnvehicle seminole"],
            ["Seminole 2", "seminole2", "/spawnvehicle seminole2"],
            ["Serrano", "serrano", "/spawnvehicle serrano"],
            ["Squaddie", "squaddie", "/spawnvehicle squaddie"],
            ["Toros", "toros", "/spawnvehicle toros"],
            ["XLS", "xls", "/spawnvehicle xls"],
            ["XLS 2", "xls2", "/spawnvehicle xls2"],
        ],
        },
        {"title": "🚐 Фургоны", "rows": [
            ["Bison", "bison", "/spawnvehicle bison"],
            ["Bison 2", "bison2", "/spawnvehicle bison2"],
            ["Bison 3", "bison3", "/spawnvehicle bison3"],
            ["Bobcat XL", "bobcatxl", "/spawnvehicle bobcatxl"],
            ["Boxville", "boxville", "/spawnvehicle boxville"],
            ["Boxville 2", "boxville2", "/spawnvehicle boxville2"],
            ["Boxville 3", "boxville3", "/spawnvehicle boxville3"],
            ["Boxville 4", "boxville4", "/spawnvehicle boxville4"],
            ["Boxville 5", "boxville5", "/spawnvehicle boxville5"],
            ["Burrito", "burrito", "/spawnvehicle burrito"],
            ["Burrito 2", "burrito2", "/spawnvehicle burrito2"],
            ["Burrito 3", "burrito3", "/spawnvehicle burrito3"],
            ["Burrito 4", "burrito4", "/spawnvehicle burrito4"],
            ["Burrito 5", "burrito5", "/spawnvehicle burrito5"],
            ["Camper", "camper", "/spawnvehicle camper"],
            ["GBurrito", "gburrito", "/spawnvehicle gburrito"],
            ["GBurrito 2", "gburrito2", "/spawnvehicle gburrito2"],
            ["Journey", "journey", "/spawnvehicle journey"],
            ["Journey 2", "journey2", "/spawnvehicle journey2"],
            ["Minivan", "minivan", "/spawnvehicle minivan"],
            ["Minivan 2", "minivan2", "/spawnvehicle minivan2"],
            ["Paradise", "paradise", "/spawnvehicle paradise"],
            ["Pony", "pony", "/spawnvehicle pony"],
            ["Pony 2", "pony2", "/spawnvehicle pony2"],
            ["Rumpo", "rumpo", "/spawnvehicle rumpo"],
            ["Rumpo 2", "rumpo2", "/spawnvehicle rumpo2"],
            ["Rumpo 3", "rumpo3", "/spawnvehicle rumpo3"],
            ["Speedo", "speedo", "/spawnvehicle speedo"],
            ["Speedo 2", "speedo2", "/spawnvehicle speedo2"],
            ["Speedo 4", "speedo4", "/spawnvehicle speedo4"],
            ["Surfer", "surfer", "/spawnvehicle surfer"],
            ["Surfer 2", "surfer2", "/spawnvehicle surfer2"],
            ["Taco Van", "taco", "/spawnvehicle taco"],
            ["Youga", "youga", "/spawnvehicle youga"],
            ["Youga 2", "youga2", "/spawnvehicle youga2"],
            ["Youga 3", "youga3", "/spawnvehicle youga3"],
            ["Youga 4", "youga4", "/spawnvehicle youga4"],
        ],
        },
        {"title": "🚛 Прицепы", "rows": [
            ["Army Tanker", "armytanker", "/spawnvehicle armytanker"],
            ["Army Trailer", "armytrailer", "/spawnvehicle armytrailer"],
            ["Army Trailer 2", "armytrailer2", "/spawnvehicle armytrailer2"],
            ["Boat Trailer", "boattrailer", "/spawnvehicle boattrailer"],
            ["Dock Trailer", "docktrailer", "/spawnvehicle docktrailer"],
            ["Freight Trailer", "freighttrailer", "/spawnvehicle freighttrailer"],
            ["Grain Trailer", "graintrailer", "/spawnvehicle graintrailer"],
            ["Prop Trailer", "proptrailer", "/spawnvehicle proptrailer"],
            ["Rake Trailer", "raketrailer", "/spawnvehicle raketrailer"],
            ["Trailer 2", "tr2", "/spawnvehicle tr2"],
            ["Trailer 3", "tr3", "/spawnvehicle tr3"],
            ["Trailer 4", "tr4", "/spawnvehicle tr4"],
            ["Flat Trailer", "trflat", "/spawnvehicle trflat"],
            ["Tanker", "tanker", "/spawnvehicle tanker"],
            ["Tanker 2", "tanker2", "/spawnvehicle tanker2"],
        ],
        },
    ],
    "weapon": [
        {"title": "🔪 Холодное оружие", "rows": [
            ["Кавалерский нож", "weapon_dagger", "/givegun id weapon_dagger 999"],
            ["Бейсбольная бита", "weapon_bat", "/givegun id weapon_bat 999"],
            ["Лом", "weapon_crowbar", "/givegun id weapon_crowbar 999"],
            ["Фонарик", "flashlight", "/givegun id flashlight 999"],
            ["Молоток", "weapon_hammer", "/givegun id weapon_hammer 999"],
            ["Кастет", "weapon_knuckle", "/givegun id weapon_knuckle 999"],
            ["Нож", "weapon_knife", "/givegun id weapon_knife 999"],
            ["Мачете", "weapon_machete", "/givegun id weapon_machete 999"],
            ["Складной нож", "weapon_switchblade", "/givegun id weapon_switchblade 999"],
            ["Полицейская дубинка", "weapon_nightstick", "/givegun id weapon_nightstick 999"],
            ["Гаечный ключ", "weapon_wrench", "/givegun id weapon_wrench 999"],
            ["Деревянная дубинка", "weapon_poolcue", "/givegun id weapon_poolcue 999"],
            ["Карамельная трость", "weapon_candycane", "/givegun id weapon_candycane 999"],
        ],
        },
        {"title": "🔫 Пистолеты", "rows": [
            ["Пистолет", "weapon_pistol", "/givegun id weapon_pistol 999"],
            ["Боевой пистолет", "weapon_combatpistol", "/givegun id weapon_combatpistol 999"],
            ["Бронебойный пистолет", "weapon_appistol", "/givegun id weapon_appistol 999"],
            ["Тайзер", "weapon_stungun", "/givegun id weapon_stungun 999"],
            ["Карманный пистолет", "weapon_snspistol", "/givegun id weapon_snspistol 999"],
            ["Тяжёлый пистолет", "weapon_heavypistol", "/givegun id weapon_heavypistol 999"],
            ["Сигнальный пистолет", "weapon_flaregun", "/givegun id weapon_flaregun 999"],
            ["Револьвер", "weapon_revolver", "/givegun id weapon_revolver 999"],
            ["Револьвер Mk II", "weapon_revolver_mk2", "/givegun id weapon_revolver_mk2 999"],
        ],
        },
        {"title": "🔫 ПП (SMG)", "rows": [
            ["Микро-ПП", "weapon_microsmg", "/givegun id weapon_microsmg 999"],
            ["Пистолет-пулемёт", "weapon_smg", "/givegun id weapon_smg 999"],
            ["ПП Mk II", "weapon_smg_mk2", "/givegun id weapon_smg_mk2 999"],
            ["Штурмовой ПП", "weapon_assaultsmg", "/givegun id weapon_assaultsmg 999"],
            ["PDW", "weapon_combatpdw", "/givegun id weapon_combatpdw 999"],
            ["Малый ПП", "weapon_machinepistol", "/givegun id weapon_machinepistol 999"],
            ["Мини ПП", "weapon_minismg", "/givegun id weapon_minismg 999"],
            ["Тактический ПП", "weapon_tecpistol", "/givegun id weapon_tecpistol 999"],
        ],
        },
        {"title": "🔫 Дробовики", "rows": [
            ["Помповый дробовик", "weapon_pumpshotgun", "/givegun id weapon_pumpshotgun 999"],
            ["Помповый Mk II", "weapon_pumpshotgun_mk2", "/givegun id weapon_pumpshotgun_mk2 999"],
            ["Обрез", "weapon_sawnoffshotgun", "/givegun id weapon_sawnoffshotgun 999"],
            ["Штурмовой дробовик", "weapon_assaultshotgun", "/givegun id weapon_assaultshotgun 999"],
            ["Буллпап дробовик", "weapon_bullpupshotgun", "/givegun id weapon_bullpupshotgun 999"],
            ["Тяжёлый дробовик", "weapon_heavyshotgun", "/givegun id weapon_heavyshotgun 999"],
            ["Двустволка", "weapon_dbshotgun", "/givegun id weapon_dbshotgun 999"],
            ["Авто дробовик", "weapon_autoshotgun", "/givegun id weapon_autoshotgun 999"],
            ["Боевой дробовик", "weapon_combatshotgun", "/givegun id weapon_combatshotgun 999"],
        ],
        },
        {"title": "🔫 Винтовки", "rows": [
            ["Штурмовая винтовка", "weapon_assaultrifle", "/givegun id weapon_assaultrifle 999"],
            ["Штурмовая Mk II", "weapon_assaultrifle_mk2", "/givegun id weapon_assaultrifle_mk2 999"],
            ["Карабин", "weapon_carbinerifle", "/givegun id weapon_carbinerifle 999"],
            ["Карабин Mk II", "weapon_carbinerifle_mk2", "/givegun id weapon_carbinerifle_mk2 999"],
            ["Улучшенная винтовка", "weapon_advancedrifle", "/givegun id weapon_advancedrifle 999"],
            ["Особый карабин", "weapon_specialcarbine", "/givegun id weapon_specialcarbine 999"],
            ["Буллпап винтовка", "weapon_bullpuprifle", "/givegun id weapon_bullpuprifle 999"],
            ["Укороченная винтовка", "weapon_compactrifle", "/givegun id weapon_compactrifle 999"],
            ["Военная винтовка", "weapon_militaryrifle", "/givegun id weapon_militaryrifle 999"],
            ["Тяжёлая винтовка", "weapon_heavyrifle", "/givegun id weapon_heavyrifle 999"],
            ["Тактический карабин", "weapon_tacticalrifle", "/givegun id weapon_tacticalrifle 999"],
        ],
        },
        {"title": "🔫 Прочее", "rows": [
            ["Пулемёт", "weapon_mg", "/givegun id weapon_mg 999"],
            ["Тяжёлый пулемёт", "weapon_combatmg", "/givegun id weapon_combatmg 999"],
            ["Томми-ган", "weapon_gusenberg", "/givegun id weapon_gusenberg 999"],
            ["Тяжёлая снайперка", "weapon_heavysniper", "/givegun id weapon_heavysniper 999"],
            ["Марксманка", "weapon_marksmanrifle", "/givegun id weapon_marksmanrifle 999"],
            ["Прецизионная винтовка", "weapon_precisionrifle", "/givegun id weapon_precisionrifle 999"],
            ["Мушкет", "weapon_musket", "/givegun id weapon_musket 999"],
            ["Липучка", "weapon_stickybomb", "/givegun id weapon_stickybomb 25"],
            ["Мяч", "weapon_ball", "/givegun id weapon_ball"],
            ["Парашют", "gadget_parachute", "/givegun id gadget_parachute"],
        ],
        },
    ],
}

#: Справочник из Google-Таблицы: те же разделы/строки, но с фото и спавном.
SECTIONS["gt"] = sheet_data.SECTIONS


def _norm(text: str) -> str:
    """Нормальный вид запроса: регистр не важен, ё = е, слэш не обязателен."""
    cleaned = str(text).lower().replace("ё", "е")
    return re.sub(r"\s+", " ", cleaned).strip().lstrip("/")


def sections(kind: str) -> list[dict]:
    """Разделы справочника («Водный транспорт», «Пистолеты» …)."""
    return SECTIONS.get(kind, [])


def count(kind: str) -> int:
    """Сколько строк в справочнике целиком."""
    return sum(len(section["rows"]) for section in sections(kind))


def summary(kind: str) -> str:
    """Подпись в шапке раздела — сколько строк и разделов."""
    return "%d строк в %d разделах" % (count(kind), len(sections(kind)))


def rows_of(kind: str, index: int) -> list[list[str]]:
    """Строки одного раздела: [наименование, ID, пример команды]."""
    items = sections(kind)
    if 0 <= index < len(items):
        return items[index]["rows"]
    return []


def get(kind: str, section_index: int, row_index: int) -> list[str]:
    """Одна строка таблицы (или пустой список)."""
    rows = rows_of(kind, section_index)
    if 0 <= row_index < len(rows):
        return rows[row_index]
    return []


def search(kind: str, query: str):
    """Поиск по наименованию, ID и команде внутри всего справочника."""
    needle = _norm(query)
    if not needle:
        return []
    found = []
    for section_index, section in enumerate(sections(kind)):
        for row_index, row in enumerate(section["rows"]):
            #: Ищут по названию, ID, команде, категории и статусу спавна.
            #: Имя файла (3-й индекс Google-Таблицы) в поиск не берём.
            cells = row[:3] + row[4:] if kind == "gt" else row
            text = " ".join(cells) + " " + str(section["title"])
            if needle in _norm(text):
                found.append((section_index, row_index, section, row))
    return found


def payload() -> str:
    """JSON для вкладок «Транспорт» и «Оружие» на сайте — те же данные."""
    def item(kind: str, si: int, ri: int, row: list[str]) -> dict:
        data = {"s": si, "r": ri, "n": row[0], "i": row[1], "c": row[2]}
        if kind == "gt":                      # фото и статус спавна — только здесь
            data["im"] = "/img/transport/" + row[3]
            data["sp"] = row[4]
            # На сайте команда тоже собирается из ID: запрет спавна в самой
            # таблице убран, иначе половина транспорта была без команды.
            data["c"] = spawn_command(row)
        return data

    data = {
        "titles": TITLES,
        "columns": COLUMNS,
        "sections": {
            kind: [{"t": sec["title"], "n": len(sec["rows"])}
                   for sec in sections(kind)]
            for kind in TITLES
        },
        "items": {
            kind: [
                item(kind, si, ri, row)
                for si, sec in enumerate(sections(kind))
                for ri, row in enumerate(sec["rows"])
            ]
            for kind in TITLES
        },
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _rgb(color: object) -> tuple[int, int, int] | None:
    """«#rrggbb» → тройка каналов; не цвет → None (тогда цвет не трогаем)."""
    value = str(color or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return None
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return None


def _luminance(rgb: tuple[int, int, int]) -> float:
    parts = []
    for channel in rgb:
        c = channel / 255
        parts.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]


def _contrast(a: object, b: object) -> float:
    """Контраст двух цветов по WCAG: 1 — одинаковые, 21 — чёрное на белом."""
    rgb_a, rgb_b = _rgb(a), _rgb(b)
    if not rgb_a or not rgb_b:
        return 0.0
    la, lb = _luminance(rgb_a), _luminance(rgb_b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _mix(a: str, b: str, part: float) -> str:
    """Смесь двух цветов: part=0 → a, part=1 → b."""
    ca, cb = _rgb(a), _rgb(b)
    if not ca or not cb:
        return a
    return "#%02x%02x%02x" % tuple(
        round(ca[i] + (cb[i] - ca[i]) * part) for i in range(3)
    )


#: Насколько контрастным должен быть текст поверх фона (WCAG AA).
_MIN_CONTRAST = 4.5


def readable_on(fg: str, bg: str) -> str:
    """Цвет текста, который действительно читается на этом фоне.

    Тёмная тема уже проходила норму и остаётся ровно такой же (функция
    возвращает цвет без изменений). В «midnight» акцент и красный статус
    давали 3.6–4.4:1, в «light» синий акцент — 3.65:1 (баг-репорт №3:
    «цвет символов не соответствует фону») — там цвет мягко осветляется
    к белому или затемняется к чёрному, пока контраст не станет нормальным.
    """
    if _contrast(fg, bg) >= _MIN_CONTRAST:
        return fg
    toward = "#ffffff" if _luminance(_rgb(bg) or (0, 0, 0)) < 0.4 else "#000000"
    for step in range(1, 21):
        candidate = _mix(str(fg), toward, step / 20)
        if _contrast(candidate, bg) >= _MIN_CONTRAST:
            return candidate
    return str(fg)


def _chip(text: str, color: str, palette: dict[str, str]) -> str:
    border = palette.get("border", "#30363d")
    card = palette.get("card", "#161b22")
    # Чип — accent поверх белой вуали 4% на карточке: именно на этом фоне
    # midnight-акцент не дотягивал до читаемости (баг-репорт №3).
    ink = readable_on(color, _mix(card, "#ffffff", 0.04))
    return ('<span style="color:%s;background:rgba(255,255,255,0.04);'
            'border:1px solid %s;border-radius:9px;padding:1px 7px;'
            'font-size:11.5px;">%s</span>') % (ink, border, _esc(text))


def row_html(kind: str, section_index: int, row_index: int,
             palette: dict[str, str]) -> str:
    """Строка справочника: наименование, ID и команда (клик копирует)."""
    row = get(kind, section_index, row_index)
    if not row:
        return ""
    accent = palette.get("accent", "#38bdf8")
    muted = palette.get("muted", "#8a8c94")
    border = palette.get("border", "#30363d")
    card = palette.get("card", "#161b22")
    text = palette.get("text", "#edeef1")
    field = palette.get("field", "#0b0c0e")
    if kind == "gt":
        return _gt_row_html(row, section_index, row_index, palette)
    #: Картинок транспорта/оружия в RMRP Study нет — только таблицы.
    #: Поэтому вместо пустого места — аккуратная заглушка с названием.
    placeholder = (
        '<div style="background:%s;border:1px dashed %s;border-radius:8px;'
        'padding:12px 10px;margin:7px 0;color:%s;font-size:12.5px;text-align:center;">'
        '📷 Нет фото · %s</div>'
    ) % (field, border, readable_on(muted, field), _esc(row[0]))
    return (
        '<div style="background:%s;border:1px solid %s;border-radius:9px;'
        'padding:8px 11px;margin:6px 0;">'
        '<span style="color:%s;font-size:15px;font-weight:700;">%s</span> '
        '%s<br/>'
        '<a href="catcopy:%s:%d:%d" style="color:%s;'
        'font-family:Consolas,monospace;font-size:13px;text-decoration:none;">'
        '%s</a>%s</div>'
    ) % (card, border, readable_on(text, card), _esc(row[0]),
         _chip(row[1], accent, palette),
         _esc(kind), section_index, row_index, readable_on(muted, card),
         _esc(row[2] or "—"), placeholder)


def spawn_command(row: list | None) -> str:
    """Команда спавна для строки Google-Таблицы.

    В самой таблице у части машин колонка с командой пустая, а в графе
    «Спавн» стоит «невозможен» — раньше программа уважала этот запрет и
    вообще не показывала команду. По просьбе пользователя запрет убран:
    команда собирается из ID, который в таблице есть у всех строк. Если
    сервер всё же запретит машину, это уже его дело — программа честно
    пишет, что в таблице спавн запрещён.
    """
    if not row:
        return ""
    given = str(row[2] or "").strip()
    if given:
        return given
    vehicle_id = str(row[1] or "").strip()
    return f"/spawnvehicle {vehicle_id}" if vehicle_id else ""


#: Ширина фото в карточке справочника (пиксели).
#: Задаётся атрибутом width, а не CSS: QTextBrowser не понимает max-width
#: и рисовал фото в полный размер — карточка разъезжалась, а текст под
#: фото оказывался перекрыт (баг-репорт).
PHOTO_WIDTH = 280


def _gt_row_html(row: list[str], section_index: int, row_index: int,
                 palette: dict[str, str]) -> str:
    """Карточка Google-Таблицы: фото, название, ID и возможность спавна."""
    accent = palette.get("accent", "#38bdf8")
    muted = palette.get("muted", "#8a8c94")
    border = palette.get("border", "#30363d")
    card = palette.get("card", "#161b22")
    text = palette.get("text", "#edeef1")
    # «success» — ключ из старых палитр (тесты), «ok» — из тем приложения.
    good = palette.get("success") or palette.get("ok") or "#3fb950"
    bad = palette.get("danger", "#f85149")
    name, rid, cmd, img, spawn_txt = row[:5]
    command = spawn_command(row)
    blocked = not str(cmd or "").strip()      # таблица запрещает спавн
    spawn_color = good if not blocked else bad
    # Цвета, читаемые на карточке: в «midnight» акцент (3.99:1) и красный
    # статус (4.44:1) не дотягивали до нормы (баг-репорт №3).
    ink_text = readable_on(text, card)
    ink_accent = readable_on(accent, card)
    ink_muted = readable_on(muted, card)
    ink_status = readable_on(spawn_color, card)
    # Фото — в отдельном блоке: img в QTextBrowser идёт строчным элементом, и
    # без обёртки название и ID вставали справа от снимка, а карточка
    # разъезжалась (баг-репорт). Размер задаём атрибутом width — CSS
    # max-width QTextBrowser не понимает.
    photo = (
        '<div style="margin:6px 0 7px 0;">'
        '<img src="/img/transport/%s" alt="%s" width="%d" '
        'style="border:1px solid %s;">'
        '</div>'
    ) % (_esc(img), _esc(name), PHOTO_WIDTH, border)
    # Пробел между командой и подписью обязателен: QTextBrowser не умеет
    # margin-left у span, и тексты склеивались — «kvadrobananклик» (баг-репорт №3).
    link = (
        '<div style="margin-top:5px;">'
        '<a href="catcopy:gt:%d:%d" style="color:%s;font-family:Consolas,'
        'monospace;font-size:13px;text-decoration:none;">%s</a> '
        '<span style="color:%s;font-size:12px;">'
        'клик — скопировать</span></div>'
    ) % (section_index, row_index, ink_accent, _esc(command),
         ink_muted) if command else \
        '<div style="margin-top:5px;color:%s;font-size:12.5px;">' \
        'В строке нет ID — команда не собирается</div>' % ink_muted
    status = spawn_txt
    if blocked:
        status = "в таблице спавн запрещён — команда собрана по ID, сервер может отказать"
    elif not command:
        status = "в строке нет ID"
    return (
        '<div style="background:%s;border:1px solid %s;border-radius:9px;'
        'padding:8px 11px;margin:6px 0;">'
        '%s'
        '<span style="color:%s;font-size:15px;font-weight:700;">%s</span> '
        '%s<br/>'
        '<span style="color:%s;font-size:12.5px;">%s</span>'
        '%s'
        '</div>'
    ) % (card, border, photo, ink_text, _esc(name), _chip(rid, accent, palette),
         ink_status, _esc(status), link)


def _back(kind: str, palette: dict[str, str]) -> str:
    # Фон вокруг — карточка панели (проверено по пикселям рендера окна).
    accent = readable_on(palette.get("accent", "#38bdf8"),
                         palette.get("card", "#161b22"))
    return ('<div style="margin:4px 0 8px 0;">'
            '<a href="cat:%s" style="color:%s;text-decoration:none;font-size:14px;">'
            '← Все разделы</a></div>') % (_esc(kind), accent)


def section_html(kind: str, index: int, palette: dict[str, str]) -> str:
    """Раздел справочника целиком — все его строки."""
    section = sections(kind)[index] if 0 <= index < len(sections(kind)) else None
    if section is None:
        return ""
    card = palette.get("card", "#161b22")
    ink_muted = readable_on(palette.get("muted", "#8a8c94"), card)
    ink_accent = readable_on(palette.get("accent", "#38bdf8"), card)
    parts = [_back(kind, palette),
             '<div style="color:%s;font-size:16px;font-weight:700;'
             'margin:2px 0 4px 0;">%s</div>' % (ink_accent, _esc(section["title"])),
             '<div style="color:%s;font-size:12.5px;margin-bottom:6px;">'
             '%d строк · колонки источника: %s</div>'
             % (ink_muted, len(section["rows"]), _esc(" | ".join(columns(kind))))]
    parts.extend(
        row_html(kind, index, row_index, palette)
        for row_index in range(len(section["rows"]))
    )
    return "".join(parts)


def sections_html(kind: str, palette: dict[str, str]) -> str:
    """Первый экран справочника — список его разделов."""
    accent = palette.get("accent", "#38bdf8")
    muted = palette.get("muted", "#8a8c94")
    border = palette.get("border", "#30363d")
    card = palette.get("card", "#161b22")
    parts = []
    for index, section in enumerate(sections(kind)):
        parts.append(
            '<div style="background:%s;border:1px solid %s;border-radius:9px;'
            'padding:9px 11px;margin:6px 0;">'
            '<a href="catsec:%s:%d" style="color:%s;font-size:15px;'
            'font-weight:700;text-decoration:none;">%s</a> '
            '<span style="color:%s;font-size:12px;">— %d строк</span></div>'
            % (card, border, _esc(kind), index, readable_on(accent, card),
               _esc(section["title"]), readable_on(muted, card),
               len(section["rows"])))
    return "".join(parts)


def list_html(kind: str, palette: dict[str, str], query: str = "",
              section: int | None = None) -> str:
    """Что показывает окно: поиск важнее открытого раздела."""
    needle = _norm(query)
    ink_muted = readable_on(palette.get("muted", "#8a8c94"),
                            palette.get("card", "#161b22"))
    if needle:
        found = search(kind, needle)
        if not found:
            return ('<p style="color:%s;margin:14px 2px;">'
                    'Ничего не нашлось — попробуй другое слово.</p>'
                    % ink_muted)
        head = ('<div style="color:%s;font-size:12.5px;margin:0 0 6px 0;">'
                'Найдено %d строк из %d — клик по команде копирует её</div>'
                % (ink_muted, len(found), count(kind)))
        body = "".join(
            '<div style="color:%s;font-size:12px;margin:8px 2px 0 0;">%s</div>'
            % (ink_muted, _esc(sec["title"]))
            + row_html(kind, si, ri, palette)
            for si, ri, sec, _row in found
        )
        return head + body
    if section is not None:
        return section_html(kind, section, palette)
    return sections_html(kind, palette)


def notes(kind: str) -> list[str]:
    """Сноска раздела: источник данных (проверка целостности)."""
    if kind == "gt":
        return [
            "Источник: Google-Таблица RMRP — " + str(count("gt")) + " строк, "
            + str(len(sections("gt"))) + " категорий.",
            "Фото скачаны в программу — раздел работает без сети.",
        ]
    titles = {"transport": "«Автомобили RMRP», " + str(count("transport")) + " строк",
              "weapon": "«Оружие RMRP», " + str(count("weapon")) + " строк"}
    return ["Источник: документ RMRP Study " + titles.get(kind, "") + ".",
            "Картинок в документе нет — только таблицы."]

