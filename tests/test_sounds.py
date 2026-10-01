from app.ui import sounds


class FakeWinSound:
    """Что-то похожее на winsound: пишет вызовы, умеет падать по требованию."""

    def __init__(self, explode: bool = False):
        self.explode = explode
        self.calls = []
        self.SND_ALIAS = 0x00010000
        self.SND_ASYNC = 0x00000001
        self.SND_NODEFAULT = 0x00020000

    def PlaySound(self, name, flags):  # noqa: N802 (имя как в winsound)
        if self.explode:
            raise RuntimeError("динамик недоступен")
        self.calls.append(("play", name, flags))

    def Beep(self, frequency, duration):  # noqa: N802
        if self.explode:
            raise RuntimeError("динамик недоступен")
        self.calls.append(("beep", frequency, duration))


class ImmediateThread:
    """Поток, который выполняется сразу — чтобы тесты не зависели от таймингов."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None, name=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self) -> None:
        if self._target:
            self._target(*self._args, **self._kwargs)


def run_sounds_in_this_thread(monkeypatch) -> None:
    import types

    monkeypatch.setattr(sounds, "threading", types.SimpleNamespace(Thread=ImmediateThread))


def test_sound_themes_are_documented():
    assert set(sounds.THEMES) == {"off", "system", "soft"}
    assert sounds.DEFAULT_THEME in sounds.THEMES


def test_off_theme_never_touches_winsound(monkeypatch):
    fake = FakeWinSound()
    monkeypatch.setattr(sounds, "winsound", fake)
    sounds.play("off", "duty_on")
    assert fake.calls == []


def test_system_theme_uses_windows_aliases(monkeypatch):
    fake = FakeWinSound()
    monkeypatch.setattr(sounds, "winsound", fake)
    sounds.play("system", "duty_on")
    assert fake.calls and fake.calls[0][1] == "SystemAsterisk"


def test_soft_theme_beeps(monkeypatch):
    fake = FakeWinSound()
    monkeypatch.setattr(sounds, "winsound", fake)
    run_sounds_in_this_thread(monkeypatch)
    sounds.play("soft", "report_add")
    assert fake.calls and fake.calls[0][0] == "beep"
    assert fake.calls[0][1] == 880  # частота из мелодии «report_add»


def test_unknown_event_is_silent(monkeypatch):
    fake = FakeWinSound()
    monkeypatch.setattr(sounds, "winsound", fake)
    sounds.play("system", "такого_события_нет")
    assert fake.calls == []


def test_play_never_raises(monkeypatch):
    monkeypatch.setattr(sounds, "winsound", FakeWinSound(explode=True))
    run_sounds_in_this_thread(monkeypatch)
    for theme in ("system", "soft"):
        for event in sounds._SYSTEM:
            sounds.play(theme, event)   # не должно выкинуть исключение


def test_play_is_safe_when_winsound_is_missing(monkeypatch):
    monkeypatch.setattr(sounds, "winsound", None)
    sounds.play("soft", "duty_on")
    sounds.play("system", "error")
