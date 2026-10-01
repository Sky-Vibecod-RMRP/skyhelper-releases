from app.util import (
    format_duration, format_hm, format_signed_duration, local_ip, percent_change,
)


def test_format_duration():
    assert format_duration(0) == "0 ч 00 мин"
    assert format_duration(3 * 3600 + 36 * 60 + 59) == "3 ч 36 мин"
    assert format_duration(86400) == "24 ч 00 мин"


def test_format_hm_keeps_hours_over_24():
    assert format_hm(3 * 3600 + 5 * 60) == "3:05"
    assert format_hm(26 * 3600) == "26:00"


def test_signed_values():
    assert format_signed_duration(-1800) == "−0 ч 30 мин"
    assert format_signed_duration(0) == "0 ч 00 мин"
    assert percent_change(150, 100) == 50.0
    assert percent_change(10, 0) is None


def test_local_ip_does_not_raise_and_is_coherent():
    ip = local_ip()
    assert isinstance(ip, str)
    if ip:
        parts = ip.split(".")
        assert len(parts) == 4
        assert all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)
