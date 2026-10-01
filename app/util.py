MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


def local_ip() -> str:
    """IP этого компьютера в локальной сети ('' — если узнать не удалось).

    Сокет «в никуда» с UDP ничего не отправляет по сети: он только заставляет
    ОС выбрать интерфейс, через который идёт трафик.
    """
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
        finally:
            sock.close()
    except OSError:
        return ""


def format_duration(seconds: int) -> str:
    """12345 -> '3 ч 25 мин'."""
    minutes_total = int(seconds) // 60
    hours, minutes = divmod(minutes_total, 60)
    return f"{hours} ч {minutes:02d} мин"


def format_hm(seconds: float) -> str:
    """12345 -> '3:25' (часы:минуты, часов может быть больше 24)."""
    minutes_total = int(seconds) // 60
    hours, minutes = divmod(minutes_total, 60)
    return f"{hours}:{minutes:02d}"


def format_signed_duration(seconds: int) -> str:
    """Разница во времени со знаком: '+2 ч 10 мин', '−0 ч 30 мин', '0 ч 00 мин'."""
    seconds = int(seconds)
    sign = "+" if seconds > 0 else "\u2212" if seconds < 0 else ""
    return sign + format_duration(abs(seconds))


def format_signed_int(value: int) -> str:
    value = int(value)
    return f"+{value}" if value > 0 else f"\u2212{-value}" if value < 0 else "0"


def percent_change(current: float, previous: float) -> float | None:
    """Изменение в процентах к прошлому периоду; None, если сравнивать не с чем."""
    if previous <= 0:
        return None
    return (current - previous) / previous * 100


def format_percent_change(current: float, previous: float) -> str:
    change = percent_change(current, previous)
    if change is None:
        return "\u2014"
    sign = "+" if change > 0 else "\u2212" if change < 0 else ""
    return f"{sign}{abs(change):.0f}%"
