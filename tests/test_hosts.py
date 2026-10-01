"""Тесты прописи локального домена сайта в файл hosts (app/hosts.py)."""

from pathlib import Path

from app.hosts import ensure_local_domain


def test_adds_missing_entry(tmp_path: Path) -> None:
    hosts = tmp_path / "hosts"
    hosts.write_bytes(b"127.0.0.1 localhost\n")

    assert ensure_local_domain(hosts_path=hosts) is True

    text = hosts.read_bytes().decode("ascii")
    assert "127.0.0.1 sky-grafana.rmrp" in text
    assert text.count("sky-grafana.rmrp") == 1


def test_existing_entry_not_duplicated(tmp_path: Path) -> None:
    original = b"127.0.0.1 localhost\n127.0.0.1 sky-grafana.rmrp\n"
    hosts = tmp_path / "hosts"
    hosts.write_bytes(original)

    assert ensure_local_domain(hosts_path=hosts) is True

    assert hosts.read_bytes() == original   # ни изменений, ни дублей


def test_tab_separated_entry_recognized(tmp_path: Path) -> None:
    hosts = tmp_path / "hosts"
    hosts.write_bytes(b"127.0.0.1\tsky-grafana.rmrp\n")

    assert ensure_local_domain(hosts_path=hosts) is True
    assert hosts.read_bytes().count(b"sky-grafana.rmrp") == 1


def test_commented_domain_does_not_count(tmp_path: Path) -> None:
    hosts = tmp_path / "hosts"
    hosts.write_bytes(b"# 127.0.0.1 sky-grafana.rmrp\n")

    assert ensure_local_domain(hosts_path=hosts) is True

    assert hosts.read_bytes().count(b"sky-grafana.rmrp") == 2  # коммент + новая


def test_appends_after_line_without_newline(tmp_path: Path) -> None:
    hosts = tmp_path / "hosts"
    hosts.write_bytes(b"127.0.0.1 localhost")     # без перевода строки в конце

    assert ensure_local_domain(hosts_path=hosts) is True

    assert hosts.read_bytes() == (
        b"127.0.0.1 localhost\n127.0.0.1 sky-grafana.rmrp\n"
    )


def test_missing_file_returns_false(tmp_path: Path) -> None:
    assert ensure_local_domain(hosts_path=tmp_path / "нет-такого-файла") is False


def test_no_write_permission_returns_false(
    tmp_path: Path, monkeypatch
) -> None:
    hosts = tmp_path / "hosts"
    hosts.write_bytes(b"")

    real_open = Path.open

    def denied(self, mode="r", *args, **kwargs):    # noqa: ANN001
        if "a" in mode:
            raise PermissionError(13, "отказано в доступе")
        return real_open(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)

    # Прав нет — тихий False, без исключения наружу.
    assert ensure_local_domain(hosts_path=hosts) is False


def test_gui_main_calls_ensure_local_domain() -> None:
    """Домен прописывается при старте программы после активации."""
    root = Path(__file__).resolve().parents[1]
    src = (root / "app" / "gui_main.py").read_text(encoding="utf-8")
    assert "ensure_local_domain" in src


def test_installer_ships_site_shortcut() -> None:
    """На рабочий стол ставится ярлык сайта sky-grafana.rmrp."""
    root = Path(__file__).resolve().parents[1]
    iss = (root / "installer" / "SKYHELPER.iss").read_text(encoding="utf-8")
    assert 'sky-grafana.rmrp.url' in iss
    assert "{userdesktop}" in iss
