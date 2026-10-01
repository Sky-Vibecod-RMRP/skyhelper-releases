# -*- coding: utf-8 -*-
"""База серверных событий RMRP — один источник для окна и сайта.

Категории и события взяты дословно из документов RMRP Study
(«Мероприятия и серверные события»): названия, подписи и команды
телепортации перенесены как есть, координаты не пересчитываются.
Скриншоты скачаны из той же документации и лежат в
``app/web/static/img/events`` — они показываются и в окне, и на сайте.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.paths import resource_dir

#: Пять категорий серверных событий (порядок как в документации).
CATEGORIES = [
    {"slug": "kraz-airdrop", "name": "Война за КрАЗ и AirDrop"},
    {"slug": "nalyoty", "name": "Налёты"},
    {"slug": "postavki", "name": "Поставки/ограбления"},
    {"slug": "semeynye", "name": "Семейные захваты территорий"},
    {"slug": "fraktsionnye", "name": "Фракционные захваты"},
]

#: Все события: категория, название, команда, координаты и скриншот.
EVENTS = [
    {
        "id": "kraz-airdrop-1",
        "cat": "kraz-airdrop",
        "name": "ВЗК 1/3",
        "group": "Война за КрАЗ",
        "cmd": "/setpos 580, 1570, 170, 155.21",
        "coords": [580.0, 1570.0, 170.0, 155.21],
        "img": "/img/events/kraz-airdrop-1.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773792437155-f0b5dbe8.png",
        "iw": 800,
        "ih": 457,
    },
    {
        "id": "kraz-airdrop-2",
        "cat": "kraz-airdrop",
        "name": "ВЗК 2/3",
        "group": "Война за КрАЗ",
        "cmd": "/setpos 100, 1955, 150, 155.21",
        "coords": [100.0, 1955.0, 150.0, 155.21],
        "img": "/img/events/kraz-airdrop-2.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773792537644-6b602982.png",
        "iw": 800,
        "ih": 457,
    },
    {
        "id": "kraz-airdrop-3",
        "cat": "kraz-airdrop",
        "name": "ВЗК 3/3",
        "group": "Война за КрАЗ",
        "cmd": "/setpos 600.15, 2250, 180, 155.21",
        "coords": [600.15, 2250.0, 180.0, 155.21],
        "img": "/img/events/kraz-airdrop-3.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773792585486-9cd7bf2b.png",
        "iw": 800,
        "ih": 457,
    },
    {
        "id": "kraz-airdrop-4",
        "cat": "kraz-airdrop",
        "name": "ВЗА 1/5",
        "group": "Война за AirDrop",
        "cmd": "/setpos 1040, 830, 170, 155.21",
        "coords": [1040.0, 830.0, 170.0, 155.21],
        "img": "/img/events/kraz-airdrop-4.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773792745667-91654a66.png",
        "iw": 800,
        "ih": 457,
    },
    {
        "id": "kraz-airdrop-5",
        "cat": "kraz-airdrop",
        "name": "ВЗА 2/5",
        "group": "Война за AirDrop",
        "cmd": "/setpos -1332.15, 960, 165, 155.21",
        "coords": [-1332.15, 960.0, 165.0, 155.21],
        "img": "/img/events/kraz-airdrop-5.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773792829301-3941d536.png",
        "iw": 800,
        "ih": 458,
    },
    {
        "id": "kraz-airdrop-6",
        "cat": "kraz-airdrop",
        "name": "ВЗА 3/5",
        "group": "Война за AirDrop",
        "cmd": "/setpos -195, 1860, 150, 155.21",
        "coords": [-195.0, 1860.0, 150.0, 155.21],
        "img": "/img/events/kraz-airdrop-6.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773792929669-252309a6.png",
        "iw": 800,
        "ih": 457,
    },
    {
        "id": "kraz-airdrop-7",
        "cat": "kraz-airdrop",
        "name": "ВЗА 4/5",
        "group": "Война за AirDrop",
        "cmd": "/setpos -80, 1265, 130, 155.21",
        "coords": [-80.0, 1265.0, 130.0, 155.21],
        "img": "/img/events/kraz-airdrop-7.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773793026918-0da3e3cc.png",
        "iw": 800,
        "ih": 458,
    },
    {
        "id": "kraz-airdrop-8",
        "cat": "kraz-airdrop",
        "name": "ВЗА 5/5",
        "group": "Война за AirDrop",
        "cmd": "/setpos -80, 1265, 130, 155.21",
        "coords": [-80.0, 1265.0, 130.0, 155.21],
        "img": "/img/events/kraz-airdrop-8.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773793069518-6095b1a1.png",
        "iw": 800,
        "ih": 458,
    },
    {
        "id": "nalyoty-1",
        "cat": "nalyoty",
        "name": "Гараж самогонщика",
        "group": None,
        "cmd": "/setpos 160.15, 2710, 150, 155.21",
        "coords": [160.15, 2710.0, 150.0, 155.21],
        "img": "/img/events/nalyoty-1.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773786997815-947de05b.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-2",
        "cat": "nalyoty",
        "name": "Гараж СОБРа",
        "group": None,
        "cmd": "/setpos 1495, 2000, 170, 155.21",
        "coords": [1495.0, 2000.0, 170.0, 155.21],
        "img": "/img/events/nalyoty-2.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773787357774-0cf82db6.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-3",
        "cat": "nalyoty",
        "name": "ГК Солнышко",
        "group": None,
        "cmd": "/setpos 850.15, 3910, 180, 155.21",
        "coords": [850.15, 3910.0, 180.0, 155.21],
        "img": "/img/events/nalyoty-3.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773787459026-8dc8803c.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-4",
        "cat": "nalyoty",
        "name": "Грузовое отделение",
        "group": None,
        "cmd": "/setpos 1130.15, 4050, 165, 155.21",
        "coords": [1130.15, 4050.0, 165.0, 155.21],
        "img": "/img/events/nalyoty-4.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773787523277-1a2005b2.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-5",
        "cat": "nalyoty",
        "name": "Дача бабки самогонщицы",
        "group": None,
        "cmd": "/setpos -1590.15, 600, 165, 155.21",
        "coords": [-1590.15, 600.0, 165.0, 155.21],
        "img": "/img/events/nalyoty-5.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773787616849-1b5e388a.png",
        "iw": 800,
        "ih": 496,
    },
    {
        "id": "nalyoty-6",
        "cat": "nalyoty",
        "name": "Дом рыбака",
        "group": None,
        "cmd": "/setpos 1495, 1650, 170, 155.21",
        "coords": [1495.0, 1650.0, 170.0, 155.21],
        "img": "/img/events/nalyoty-6.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773787905339-e6fb1761.png",
        "iw": 800,
        "ih": 501,
    },
    {
        "id": "nalyoty-7",
        "cat": "nalyoty",
        "name": "Заброшенная мастерская",
        "group": None,
        "cmd": "/setpos -42.379, 1464.014, 154.311",
        "coords": [-42.379, 1464.014, 154.311],
        "img": "/img/events/nalyoty-7.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773788033469-0021b06c.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-8",
        "cat": "nalyoty",
        "name": "Заброшка у реки",
        "group": None,
        "cmd": "/setpos -500.15, 600, 165, 155.21",
        "coords": [-500.15, 600.0, 165.0, 155.21],
        "img": "/img/events/nalyoty-8.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773788392474-02ab6e7b.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-9",
        "cat": "nalyoty",
        "name": "МХФП Семашко",
        "group": None,
        "cmd": "/setpos 885.15, 3895, 190, 155.21",
        "coords": [885.15, 3895.0, 190.0, 155.21],
        "img": "/img/events/nalyoty-9.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773788491582-c02ecbaf.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-10",
        "cat": "nalyoty",
        "name": "Промышленная стройка",
        "group": None,
        "cmd": "/setpos 580.15, 2350, 180, 155.21",
        "coords": [580.15, 2350.0, 180.0, 155.21],
        "img": "/img/events/nalyoty-10.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773788553602-f0841405.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-11",
        "cat": "nalyoty",
        "name": "Рублёвская Веб-кам студия",
        "group": None,
        "cmd": "/setpos 1550, 670, 170, 155.21",
        "coords": [1550.0, 670.0, 170.0, 155.21],
        "img": "/img/events/nalyoty-11.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773788633027-e2a72a50.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-12",
        "cat": "nalyoty",
        "name": "Северный схрон",
        "group": None,
        "cmd": "/setpos -195.15, 10, 185, 155.21",
        "coords": [-195.15, 10.0, 185.0, 155.21],
        "img": "/img/events/nalyoty-12.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773788725512-084535f0.png",
        "iw": 800,
        "ih": 492,
    },
    {
        "id": "nalyoty-13",
        "cat": "nalyoty",
        "name": "Склад Ашот",
        "group": None,
        "cmd": "/setpos 590.15, 2920, 200, 155.21",
        "coords": [590.15, 2920.0, 200.0, 155.21],
        "img": "/img/events/nalyoty-13.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773788796343-bc13ee75.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-14",
        "cat": "nalyoty",
        "name": "Склад комеррсов",
        "group": None,
        "cmd": "/setpos -275.15, 2110, 180, 155.21",
        "coords": [-275.15, 2110.0, 180.0, 155.21],
        "img": "/img/events/nalyoty-14.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773789093049-1c2a10a3.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-15",
        "cat": "nalyoty",
        "name": "Склад МеруаЛерлен",
        "group": None,
        "cmd": "/setpos 488, 4388, 155.21",
        "coords": [488.0, 4388.0, 155.21],
        "img": "/img/events/nalyoty-15.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773789187696-fc7bbd3a.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-16",
        "cat": "nalyoty",
        "name": "Склад НИИ Химза",
        "group": None,
        "cmd": "/setpos 550.15, 2620, 200, 155.21",
        "coords": [550.15, 2620.0, 200.0, 155.21],
        "img": "/img/events/nalyoty-16.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773789262302-11d734ec.png",
        "iw": 800,
        "ih": 498,
    },
    {
        "id": "nalyoty-17",
        "cat": "nalyoty",
        "name": "Склад Шереметьево",
        "group": None,
        "cmd": "/setpos -2185, 4270, 190, 115.20",
        "coords": [-2185.0, 4270.0, 190.0, 115.2],
        "img": "/img/events/nalyoty-17.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773789311713-14ce0117.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-18",
        "cat": "nalyoty",
        "name": "Стройплощадка Лавир",
        "group": None,
        "cmd": "/setpos -102.15, 2650, 250, 155.21",
        "coords": [-102.15, 2650.0, 250.0, 155.21],
        "img": "/img/events/nalyoty-18.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773789390916-f8fb98aa.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-19",
        "cat": "nalyoty",
        "name": "Схрон лунных",
        "group": None,
        "cmd": "/setpos 1100.15, 2940, 190, 155.21",
        "coords": [1100.15, 2940.0, 190.0, 155.21],
        "img": "/img/events/nalyoty-19.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773789453299-d984b71a.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-20",
        "cat": "nalyoty",
        "name": "Схрон южан",
        "group": None,
        "cmd": "/setpos 1140, 951, 170, 155.21",
        "coords": [1140.0, 951.0, 170.0, 155.21],
        "img": "/img/events/nalyoty-20.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773789528808-e3c453ab.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-21",
        "cat": "nalyoty",
        "name": "Терминал",
        "group": None,
        "cmd": "/setpos -1500.15, 4230, 190, 155.21",
        "coords": [-1500.15, 4230.0, 190.0, 155.21],
        "img": "/img/events/nalyoty-21.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773789607786-a171852b.png",
        "iw": 800,
        "ih": 502,
    },
    {
        "id": "nalyoty-22",
        "cat": "nalyoty",
        "name": "Топливный склад Шереметьево",
        "group": None,
        "cmd": "/setpos -1980, 4600, 190, 100",
        "coords": [-1980.0, 4600.0, 190.0, 100.0],
        "img": "/img/events/nalyoty-22.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773789819484-6d76b70e.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-23",
        "cat": "nalyoty",
        "name": "Топливный склад",
        "group": None,
        "cmd": "/setpos -1565.15, 4380, 190, 155.21",
        "coords": [-1565.15, 4380.0, 190.0, 155.21],
        "img": "/img/events/nalyoty-23.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773789882559-da39bcb1.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-24",
        "cat": "nalyoty",
        "name": "Турбопровод МосЭнерго",
        "group": None,
        "cmd": "/setpos 800.15, 2650, 190, 155.21",
        "coords": [800.15, 2650.0, 190.0, 155.21],
        "img": "/img/events/nalyoty-24.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773790011586-03713f08.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-25",
        "cat": "nalyoty",
        "name": "ТЦ Рублёвский",
        "group": None,
        "cmd": "/setpos 1460, 980, 170, 155.21",
        "coords": [1460.0, 980.0, 170.0, 155.21],
        "img": "/img/events/nalyoty-25.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773790053469-57558fed.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-26",
        "cat": "nalyoty",
        "name": "Фармацевтический склад",
        "group": None,
        "cmd": "/setpos 100.15, 2890, 150, 155.21",
        "coords": [100.15, 2890.0, 150.0, 155.21],
        "img": "/img/events/nalyoty-26.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773790092019-2ae249c9.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-27",
        "cat": "nalyoty",
        "name": "Фруктовый прилавок",
        "group": None,
        "cmd": "/setpos 640, 1060, 170, 155.21",
        "coords": [640.0, 1060.0, 170.0, 155.21],
        "img": "/img/events/nalyoty-27.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773790149238-03f5270f.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-28",
        "cat": "nalyoty",
        "name": "Хаб сотовой связи",
        "group": None,
        "cmd": "/setpos 150, 15, 185, 155.21",
        "coords": [150.0, 15.0, 185.0, 155.21],
        "img": "/img/events/nalyoty-28.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773790187910-b0275ebc.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-29",
        "cat": "nalyoty",
        "name": "Химическая лаборатория у реки",
        "group": None,
        "cmd": "/setpos 300, 650, 170, 155.21",
        "coords": [300.0, 650.0, 170.0, 155.21],
        "img": "/img/events/nalyoty-29.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773790235699-df5f4ff2.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "nalyoty-30",
        "cat": "nalyoty",
        "name": "Шахта №3",
        "group": None,
        "cmd": "/setpos -820.15, 10, 195, 155.21",
        "coords": [-820.15, 10.0, 195.0, 155.21],
        "img": "/img/events/nalyoty-30.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773790279281-0830aaf8.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "postavki-1",
        "cat": "postavki",
        "name": "Центральный Мед.Склад",
        "group": None,
        "cmd": "/setpos -850.15, 3150, 190, 155.21",
        "coords": [-850.15, 3150.0, 190.0, 155.21],
        "img": "/img/events/postavki-1.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773791576180-b3a84fcc.png",
        "iw": 800,
        "ih": 458,
    },
    {
        "id": "postavki-2",
        "cat": "postavki",
        "name": "РЛС Орбита",
        "group": None,
        "cmd": "/setpos -850.15, 3680, 250, 155.21",
        "coords": [-850.15, 3680.0, 250.0, 155.21],
        "img": "/img/events/postavki-2.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773791628498-61894194.png",
        "iw": 800,
        "ih": 458,
    },
    {
        "id": "postavki-3",
        "cat": "postavki",
        "name": "Медицинские склады",
        "group": None,
        "cmd": "/setpos 140.15, 2720, 200, 155.21",
        "coords": [140.15, 2720.0, 200.0, 155.21],
        "img": "/img/events/postavki-3.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773791803941-bbd8710d.png",
        "iw": 800,
        "ih": 457,
    },
    {
        "id": "postavki-4",
        "cat": "postavki",
        "name": "Мед Склад",
        "group": None,
        "cmd": "/setpos 240, 1030, 160, 155.21",
        "coords": [240.0, 1030.0, 160.0, 155.21],
        "img": "/img/events/postavki-4.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773791850682-43f4abe1.png",
        "iw": 800,
        "ih": 457,
    },
    {
        "id": "postavki-5",
        "cat": "postavki",
        "name": "Зарайское мед. хранилище",
        "group": None,
        "cmd": "/setpos -1450.15, 2150, 195, 155.21",
        "coords": [-1450.15, 2150.0, 195.0, 155.21],
        "img": "/img/events/postavki-5.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773791894582-69ea2321.png",
        "iw": 800,
        "ih": 457,
    },
    {
        "id": "postavki-6",
        "cat": "postavki",
        "name": "Зарайский Кремль",
        "group": None,
        "cmd": "/setpos -1450.15, 1505, 165, 155.21",
        "coords": [-1450.15, 1505.0, 165.0, 155.21],
        "img": "/img/events/postavki-6.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773791943514-2f8e2d83.png",
        "iw": 800,
        "ih": 458,
    },
    {
        "id": "postavki-7",
        "cat": "postavki",
        "name": "Гос. склады мед. обеспечения",
        "group": None,
        "cmd": "/setpos 240, 1030, 160, 155.21",
        "coords": [240.0, 1030.0, 160.0, 155.21],
        "img": "/img/events/postavki-7.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773791981353-336342c1.png",
        "iw": 800,
        "ih": 458,
    },
    {
        "id": "postavki-8",
        "cat": "postavki",
        "name": "Военные склады",
        "group": None,
        "cmd": "/setpos 240, 1030, 160, 155.21",
        "coords": [240.0, 1030.0, 160.0, 155.21],
        "img": "/img/events/postavki-8.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773792032434-6962ae65.png",
        "iw": 800,
        "ih": 457,
    },
    {
        "id": "postavki-9",
        "cat": "postavki",
        "name": "Объект 7",
        "group": None,
        "cmd": "/setpos 600, 1800, 170, 155.21",
        "coords": [600.0, 1800.0, 170.0, 155.21],
        "img": "/img/events/postavki-9.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773792130909-729eb9c7.png",
        "iw": 800,
        "ih": 458,
    },
    {
        "id": "semeynye-1",
        "cat": "semeynye",
        "name": "Топливное хранилище",
        "group": None,
        "cmd": "/setpos -2251.06, 4300.78, 144.69",
        "coords": [-2251.06, 4300.78, 144.69],
        "img": "/img/events/semeynye-1.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788447945009-b23ecca0.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "semeynye-2",
        "cat": "semeynye",
        "name": "Хрущёвский",
        "group": None,
        "cmd": "/setpos -1988.85, 4073.90, 144.71",
        "coords": [-1988.85, 4073.9, 144.71],
        "img": "/img/events/semeynye-2.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788448002727-b99d27c9.png",
        "iw": 800,
        "ih": 493,
    },
    {
        "id": "semeynye-3",
        "cat": "semeynye",
        "name": "Заброшенная стройка",
        "group": None,
        "cmd": "/setpos 1264.82, 2313.89, 137.15",
        "coords": [1264.82, 2313.89, 137.15],
        "img": "/img/events/semeynye-3.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788448058495-8bca1d22.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "semeynye-4",
        "cat": "semeynye",
        "name": "Южнопортовая",
        "group": None,
        "cmd": "/setpos 2537.77, 1817.65, 137.05",
        "coords": [2537.77, 1817.65, 137.05],
        "img": "/img/events/semeynye-4.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788448138899-815c3434.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "semeynye-5",
        "cat": "semeynye",
        "name": "Лужники",
        "group": None,
        "cmd": "/setpos 1424.53, 3026.06, 132.48",
        "coords": [1424.53, 3026.06, 132.48],
        "img": "/img/events/semeynye-5.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788448322951-b0688650.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "semeynye-6",
        "cat": "semeynye",
        "name": "Ресторан «Чертог Ашотика»",
        "group": None,
        "cmd": "/setpos -1377.58, 3026.08, 138.43",
        "coords": [-1377.58, 3026.08, 138.43],
        "img": "/img/events/semeynye-6.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788448408919-b66850d3.png",
        "iw": 800,
        "ih": 485,
    },
    {
        "id": "semeynye-7",
        "cat": "semeynye",
        "name": "МосЭнерго",
        "group": None,
        "cmd": "/setpos 861.99, 2414.01, 138.20",
        "coords": [861.99, 2414.01, 138.2],
        "img": "/img/events/semeynye-7.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788448443669-aba99be1.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "semeynye-8",
        "cat": "semeynye",
        "name": "НПЗ Лукоел",
        "group": None,
        "cmd": "/setpos 133, 3738, 150.21",
        "coords": [133.0, 3738.0, 150.21],
        "img": "/img/events/semeynye-8.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773793542802-17b7796d.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "semeynye-9",
        "cat": "semeynye",
        "name": "Строящийся мост",
        "group": None,
        "cmd": "/setpos -132, 513, 145.21",
        "coords": [-132.0, 513.0, 145.21],
        "img": "/img/events/semeynye-9.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773793801862-b267a349.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "fraktsionnye-1",
        "cat": "fraktsionnye",
        "name": "Пиковый Двор",
        "group": None,
        "cmd": "/setpos 194.74, 3324.04, 138.96",
        "coords": [194.74, 3324.04, 138.96],
        "img": "/img/events/fraktsionnye-1.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788442973654-0861e065.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "fraktsionnye-2",
        "cat": "fraktsionnye",
        "name": "Порт Исаково",
        "group": None,
        "cmd": "/setpos -912.78, 4497.64, 133.75",
        "coords": [-912.78, 4497.64, 133.75],
        "img": "/img/events/fraktsionnye-2.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788443032727-98b03ff6.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "fraktsionnye-3",
        "cat": "fraktsionnye",
        "name": "Мухоморы",
        "group": None,
        "cmd": "/setpos 739.11, 3629.82, 135.72",
        "coords": [739.11, 3629.82, 135.72],
        "img": "/img/events/fraktsionnye-3.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788443126893-93273869.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "fraktsionnye-4",
        "cat": "fraktsionnye",
        "name": "Академический",
        "group": None,
        "cmd": "/setpos 2319, 2332, 150.21",
        "coords": [2319.0, 2332.0, 150.21],
        "img": "/img/events/fraktsionnye-4.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788446849717-93120d1d.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "fraktsionnye-5",
        "cat": "fraktsionnye",
        "name": "Бизнес-академ",
        "group": None,
        "cmd": "/setpos 2233, 2973, 150.21",
        "coords": [2233.0, 2973.0, 150.21],
        "img": "/img/events/fraktsionnye-5.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788447041999-f5eab08d.png",
        "iw": 800,
        "ih": 475,
    },
    {
        "id": "fraktsionnye-6",
        "cat": "fraktsionnye",
        "name": "Западный",
        "group": None,
        "cmd": "/setpos 549, 2779, 155.21",
        "coords": [549.0, 2779.0, 155.21],
        "img": "/img/events/fraktsionnye-6.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788447069800-f87c775a.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "fraktsionnye-7",
        "cat": "fraktsionnye",
        "name": "Захват Зарайска",
        "group": None,
        "cmd": "/setpos -1447, 1923, 150.21",
        "coords": [-1447.0, 1923.0, 150.21],
        "img": "/img/events/fraktsionnye-7.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788447171795-f3e42720.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "fraktsionnye-8",
        "cat": "fraktsionnye",
        "name": "Индустриальный",
        "group": None,
        "cmd": "/setpos 620.15, 2400, 140, 155.21",
        "coords": [620.15, 2400.0, 140.0, 155.21],
        "img": "/img/events/fraktsionnye-8.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/03/1773795435752-f6229471.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "fraktsionnye-9",
        "cat": "fraktsionnye",
        "name": "Речной порт",
        "group": None,
        "cmd": "/setpos 210.15, 4385, 135, 155.21",
        "coords": [210.15, 4385.0, 135.0, 155.21],
        "img": "/img/events/fraktsionnye-9.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788447230271-27a7dc29.png",
        "iw": 800,
        "ih": 500,
    },
    {
        "id": "fraktsionnye-10",
        "cat": "fraktsionnye",
        "name": "Сталинский дворик",
        "group": None,
        "cmd": "/setpos -2055, 4007, 150.21",
        "coords": [-2055.0, 4007.0, 150.21],
        "img": "/img/events/fraktsionnye-10.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788447289710-0a264a33.png",
        "iw": 800,
        "ih": 515,
    },
    {
        "id": "fraktsionnye-11",
        "cat": "fraktsionnye",
        "name": "Трасса Москва-Зарайск",
        "group": None,
        "cmd": "/setpos -8.51, 1960, 150.21",
        "coords": [-8.51, 1960.0, 150.21],
        "img": "/img/events/fraktsionnye-11.jpg",
        "src": "https://rmrp-study.ru/uploads/images/2026/09/1788447334536-41eaf227.png",
        "iw": 800,
        "ih": 488,
    },
]

#: Замечания к исходным данным (координаты не дополняются).
NOTES = []


def category(slug: str) -> dict | None:
    """Категория по её slug (или None)."""
    for cat in CATEGORIES:
        if cat["slug"] == slug:
            return cat
    return None


def events_of(slug: str) -> list[dict]:
    """События одной категории — в том порядке, в каком они в документе."""
    return [ev for ev in EVENTS if ev["cat"] == slug]


def get(event_id: str) -> dict | None:
    """Событие по id (например, "nalyoty-3")."""
    for ev in EVENTS:
        if ev["id"] == event_id:
            return ev
    return None


def _norm(text: str) -> str:
    """Поиск без учёта регистра, ё/е, слэша и лишних пробелов."""
    text = str(text or "").replace("ё", "е").lower()
    return re.sub(r"\s+", " ", text).strip()


def search(query: str, slug: str | None = None) -> list[dict]:
    """Поиск по названию события и по названию категории.

    Пустой запрос — все события (в пределах категории, если она указана).
    """
    needle = _norm(query).lstrip("/")
    out = []
    for ev in EVENTS:
        if slug and ev["cat"] != slug:
            continue
        if not needle:
            out.append(ev)
            continue
        cat = category(ev["cat"])
        hay = _norm(ev["name"])
        if ev["group"]:
            hay += " " + _norm(ev["group"])
        if cat:
            hay += " " + _norm(cat["name"])
        if needle in hay:
            out.append(ev)
    return out


def category_count(slug: str) -> int:
    """Сколько событий в категории."""
    return len(events_of(slug))


def payload() -> str:
    """JSON для вкладки «Серверные события» на сайте — те же данные."""
    data = {
        "categories": CATEGORIES,
        "events": [
            {
                "i": ev["id"],
                "c": ev["cat"],
                "n": ev["name"],
                "g": ev["group"],
                "m": ev["cmd"],
                "x": ev["coords"],
                "s": ev["img"],
                "u": ev["src"],
                "w": ev["iw"],
                "h": ev["ih"],
            }
            for ev in EVENTS
        ],
        "notes": NOTES,
    }
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def image_file(ev: dict) -> Path | None:
    """Локальный файл скриншота события (папка приложения или None)."""
    path = resource_dir("web", "static") / ev["img"].lstrip("/")
    return path if path.exists() else None


def image_tag(ev: dict, width: int = 400) -> str:
    """Скриншот события для окна программы (размеры известны заранее)."""
    if not image_file(ev):
        return ""
    height = max(1, round(width * ev["ih"] / max(1, ev["iw"])))
    style = "border:1px solid #30363d;border-radius:8px;"
    return ('<img src="%s" width="%d" height="%d" style="%s">'
            % (ev["img"], width, height, style))


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _chip(text: str, color: str, palette: dict[str, str]) -> str:
    """Маленькая плашка (категория или раздел события)."""
    return ('<span style="color:%s;border:1px solid %s;background:%s;'
            'border-radius:9px;padding:1px 8px;font-size:12px;">%s</span>'
            % (color, palette.get("border", "#30363d"),
               palette.get("card", "#161b22"), _esc(text)))


def event_html(ev: dict, palette: dict[str, str]) -> str:
    """Карточка события в окне: название, плашки, скриншот, координаты."""
    accent = palette.get("accent", "#38bdf8")
    muted = palette.get("muted", "#8a8c94")
    border = palette.get("border", "#30363d")
    card = palette.get("card", "#161b22")
    text = palette.get("text", "#edeef1")
    chips = []
    cat = category(ev["cat"])
    if cat:
        chips.append(_chip(cat["name"], muted, palette))
    if ev["group"]:
        chips.append(_chip(ev["group"], accent, palette))
    shot = image_tag(ev, 400)
    return (
        '<div style="background:%s;border:1px solid %s;border-radius:9px;'
        'padding:9px 11px;margin:6px 0;">'
        '<a href="evt:%s" style="color:%s;font-size:15px;font-weight:700;'
        'text-decoration:none;">%s</a><br/>%s<br/>%s<br/>'
        '<code style="color:%s;font-family:Consolas,monospace;font-size:13px;">'
        '%s</code><br/>'
        '<a href="evttp:%s" style="color:%s;font-size:12.5px;font-weight:700;'
        'text-decoration:none;">Телепортироваться на событие</a></div>'
    ) % (card, border, _esc(ev["id"]), accent, _esc(ev["name"]),
         " ".join(chips), shot, text, _esc(ev["cmd"]),
         _esc(ev["id"]), accent)


def _block(cat: dict, events: list[dict], palette: dict[str, str],
           link: bool = True, count: int | None = None) -> str:
    """Блок категории: заголовок (ссылка в окне) и её события."""
    accent = palette.get("accent", "#38bdf8")
    muted = palette.get("muted", "#8a8c94")
    border = palette.get("border", "#30363d")
    card = palette.get("card", "#161b22")
    total = category_count(cat["slug"]) if count is None else count
    title = _esc(cat["name"])
    if link:
        title = ('<a href="evtcat:%s" style="color:%s;font-size:15px;'
                 'font-weight:700;text-decoration:none;">%s</a>'
                 % (_esc(cat["slug"]), accent, title))
    head = ('<div style="background:%s;border:1px solid %s;border-radius:10px;'
            'padding:9px 12px;margin:7px 0;">'
            '%s <span style="color:%s;font-size:12px;">— %%d событий</span>'
            '<div style="margin-top:4px;">%%s</div></div>'
            % (card, border, title, muted))
    return head % (total,
                   "".join(event_html(ev, palette) for ev in events))


def list_html(query: str = "", slug: str | None = None,
              palette: dict[str, str] | None = None) -> str:
    """HTML для окна: категории, события категории или результаты поиска."""
    palette = palette or {}
    want = (query or "").strip()
    if want:
        found = search(want)
        if not found:
            return _empty(palette.get("muted", "#8a8c94"))
        return "".join(
            _block(cat, [ev for ev in found if ev["cat"] == cat["slug"]], palette)
            for cat in CATEGORIES
            if any(ev["cat"] == cat["slug"] for ev in found)
        )
    if slug:
        cat = category(slug)
        if not cat:
            return _empty(palette.get("muted", "#8a8c94"))
        events = events_of(slug)
        back = ('<p style="margin:2px 0 6px 0;"><a href="evtcat:" style="color:%s;">'
                '← Все категории</a></p>' % palette.get("accent", "#38bdf8"))
        return back + _block(cat, events, palette, link=False)
    return "".join(
        _block(cat, [], palette, count=category_count(cat["slug"]))
        for cat in CATEGORIES)


def _empty(muted: str) -> str:
    return ('<p style="color:%s;margin:14px 2px;">Событий не нашлось — '
            'попробуй другое название.</p>' % muted)


def summary() -> str:
    """Строка «сколько чего» для заголовка раздела."""
    return "%d событий в %d категориях" % (len(EVENTS), len(CATEGORIES))

