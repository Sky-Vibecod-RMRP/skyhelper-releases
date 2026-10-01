from app.ui import theme


def test_default_stylesheet_is_built_from_dark_palette():
    assert theme.ACCENT in theme.STYLESHEET
    assert theme.BG in theme.STYLESHEET
    assert "QProgressBar::chunk" in theme.STYLESHEET


def test_every_theme_has_a_stylesheet_with_its_own_accent():
    for name, colors in theme.THEMES.items():
        qss = theme.stylesheet_for(name)
        assert colors["accent"] in qss, name
        assert colors["bg"] in qss, name
        assert "QWidget" in qss, name


def test_unknown_theme_falls_back_to_default():
    assert theme.theme_colors("нет_такой") == theme.THEMES[theme.DEFAULT_THEME]


def test_apply_switches_module_colors_and_can_be_restored():
    original = theme.ACCENT
    try:
        qss = theme.apply("light")
        assert theme.ACCENT == theme.THEMES["light"]["accent"]
        assert theme.ACCENT in qss
    finally:
        theme.apply(theme.DEFAULT_THEME)
    assert theme.ACCENT == original
