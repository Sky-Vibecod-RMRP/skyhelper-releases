"""Фикс AppHang: цифры считаются в фоне, Insert идёт через сигнал."""
import os
import threading
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # без экрана, как в других тестах

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture()
def qapp():
    yield QApplication.instance() or QApplication([])


def _fake_core(monkeypatch):
    from app.ui import dashboard as dash

    monkeypatch.setattr(
        dash,
        "current_streak",
        lambda *a, **k: SimpleNamespace(
            plan_hours=0, plan_reports=0, days=0, today_done=False
        ),
    )
    core = SimpleNamespace(
        config=SimpleNamespace(
            require_duty=False,
            weekly_hours_norm=70,
            weekly_reports_norm=600,
            hotkey_add="f9",
            hotkey_remove="ctrl+f9",
        ),
        stats=SimpleNamespace(
            week_progress=lambda now: SimpleNamespace(
                stats=SimpleNamespace(online_seconds=0, reports=0),
                hours_percent=0.0,
                reports_percent=0.0,
            ),
            today=lambda now: SimpleNamespace(online_seconds=0, reports=0),
        ),
        session=SimpleNamespace(
            is_counting=False, is_game_running=False, is_on_duty=False
        ),
    )
    return core


def test_stats_are_computed_off_the_main_thread(qapp, monkeypatch):
    """Секундный refresh не читает базу на главном потоке."""
    from app.ui import dashboard as dash

    core = _fake_core(monkeypatch)
    main_ident = threading.get_ident()
    seen = {}

    def today(now):
        seen["ident"] = threading.get_ident()
        return SimpleNamespace(online_seconds=0, reports=0)

    core.stats.today = today
    panel = dash.DashboardPanel(core)

    deadline = time.time() + 5
    while panel.stats_snapshot is None and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)

    assert panel.stats_snapshot is not None, "фоновый снимок должен доехать"
    assert seen.get("ident") != main_ident, "цифры должен считать фон, не главный"
    texts = [w.text() for w in panel.findChildren(QLabel)]
    assert any(t.startswith("Сегодня:") for t in texts), "снимок должен обновить цифры"


def test_broken_stats_do_not_crash_the_panel(qapp, monkeypatch):
    """Ошибка расчёта в фоне не роняет интерфейс и не показывает битые цифры."""
    from app.ui import dashboard as dash

    core = _fake_core(monkeypatch)

    def boom(now):
        raise RuntimeError("база недоступна")

    core.stats.week_progress = boom
    panel = dash.DashboardPanel(core)

    deadline = time.time() + 5
    while panel._stats_pending and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    qapp.processEvents()

    assert panel.stats_snapshot is None


def test_insert_hotkey_goes_through_bridge_signal():
    """Insert из хук-потока не трогает окно напрямую — только через сигнал."""
    import inspect

    from app import gui_main

    src = inspect.getsource(gui_main)
    assert "toggle_request = Signal()" in src
    assert "core.toggle_window = lambda: bridge.toggle_request.emit()" in src
    assert "bridge.toggle_request.connect(toggle_window)" in src
    assert "core.toggle_window = toggle_window" not in src


def test_bridge_toggle_slot_runs_on_main_thread(qapp):
    """Слот toggle_request выполняется в главном потоке даже из чужого.

    Это ядро фикса Insert: слушатель клавиш живёт в хук-потоке и раньше
    вызывал окно напрямую; теперь его emit обязан приехать в главный поток
    (иначе — вложение вызовов и AppHang).
    """
    from app.gui_main import Bridge

    main_ident = threading.get_ident()
    seen = {}
    bridge = Bridge()
    bridge.toggle_request.connect(
        lambda: seen.setdefault("ident", threading.get_ident())
    )

    emitter = threading.Thread(target=bridge.toggle_request.emit)
    emitter.start()
    emitter.join(2)

    deadline = time.time() + 2
    while "ident" not in seen and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert "ident" in seen, "сигнал должен дойти до слота"
    assert seen["ident"] == main_ident, "слот должен жить в главном потоке"


def test_stop_updates_stops_stats_feed(qapp):
    """Порядок остановки: stop_updates гасит и таймеры, и фоновый расчёт."""
    from types import SimpleNamespace

    from app.ui.helper_window import HelperWindow

    win = HelperWindow()
    stopped = []
    win._home = SimpleNamespace(
        stop_stats=lambda: stopped.append(True), stats_snapshot=None
    )
    win.stop_updates()
    assert stopped == [True], "stop_updates должен гасить фоновый расчёт"
