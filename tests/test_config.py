import json

from app.config import Config


def test_roundtrip_with_cyrillic(tmp_path):
    path = tmp_path / "config.json"
    config = Config(output_dir=r"G:\Мой диск\RMRP", ui_theme="light")
    config.save(path)

    loaded = Config.load(path)
    assert loaded.output_dir == r"G:\Мой диск\RMRP"
    assert loaded.ui_theme == "light"
    assert "Мой диск" in path.read_text(encoding="utf-8")


def test_reads_cp1251_file_and_rewrites_utf8(tmp_path):
    """Старый баг: файл в cp1251 читался как битый, настройки слетали в дефолт."""
    path = tmp_path / "config.json"
    path.write_bytes(
        json.dumps({"output_dir": r"G:\Мой диск\RMRP", "web_port": 9090},
                   ensure_ascii=False).encode("cp1251")
    )

    loaded = Config.load(path)
    assert loaded.output_dir == r"G:\Мой диск\RMRP"
    assert loaded.web_port == 9090
    # Пересохранили сразу в UTF-8, чтобы дальше читалось без колдунства.
    path.read_bytes().decode("utf-8")


def test_reads_file_with_bom(tmp_path):
    path = tmp_path / "config.json"
    path.write_bytes(
        b"\xef\xbb\xbf" + json.dumps({"weekly_reports_norm": 123}).encode("utf-8")
    )
    assert Config.load(path).weekly_reports_norm == 123


def test_unknown_keys_are_ignored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"web_port": 8081, "future_option": True}), encoding="utf-8")
    loaded = Config.load(path)
    assert loaded.web_port == 8081
    assert not hasattr(loaded, "future_option")


def test_broken_file_becomes_backup_and_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ это не json", encoding="utf-8")

    loaded = Config.load(path)
    assert loaded.weekly_hours_norm == Config().weekly_hours_norm
    assert path.with_suffix(".json.bak").exists()
    assert path.exists()          # и новый config.json на месте


def test_save_is_atomic_and_leaves_no_temp(tmp_path):
    path = tmp_path / "config.json"
    Config(web_port=7777).save(path)
    assert Config.load(path).web_port == 7777
    assert not (tmp_path / "config.json.tmp").exists()


def test_new_web_and_look_fields_have_sane_defaults():
    config = Config()
    assert config.web_enabled is False
    assert config.web_host == "127.0.0.1"
    assert config.web_port == 80
    assert config.web_pin_hash == ""
    assert config.ui_theme == "dark"
    assert config.sound_theme == "system"
