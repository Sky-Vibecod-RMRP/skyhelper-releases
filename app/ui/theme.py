"""Оформление приложения: цвета и QSS-стили, несколько тем.

Тёмная тема «dark» сделана в стиле меню MIDNIGHT: почти чёрный фон,
нейтральные серые панели без синего отлива, тонкие рамки и один яркий
циановый акцент — на нём активные элементы, кнопки и полосы.
"""
from __future__ import annotations

# Базовые цвета (используются в коде, например в трее и окне).
ACCENT = "#4ec3f0"
OK = "#3ddc97"
WARN = "#ffb547"
BG = "#0b0c0e"
CARD = "#141519"
BORDER = "#24262b"
TEXT = "#edeef1"
MUTED = "#8a8c94"

THEMES: dict[str, dict[str, str]] = {
    # Как в меню MIDNIGHT: чёрное, серое, один циан.
    "dark": {
        "label": "Тёмная (как в Midnight)",
        "bg": "#0b0c0e", "card": "#141519", "border": "#24262b",
        "text": "#edeef1", "muted": "#8a8c94", "accent": "#4ec3f0",
        "accent2": "#2fa6d8", "accent_hi": "#79d5f8", "ok": "#3ddc97", "ok_text": "#06210f",
        "field": "#101115", "bar_bg": "#1e2025", "warn": "#ffb547",
        "danger": "#e5484d", "top": "#0f1013",
    },
    "midnight": {
        "label": "Полночь (сине-фиолетовая)",
        "bg": "#0a0e1a", "card": "#121a2c", "border": "#26304a",
        "text": "#eaeefb", "muted": "#8f9bb8", "accent": "#7c5cff",
        "accent2": "#2fd6ff", "accent_hi": "#9d85ff", "ok": "#3ddc97", "ok_text": "#06210f",
        "field": "#0e1424", "bar_bg": "#1a2237", "warn": "#ffb547",
        "danger": "#e5484d", "top": "#0d1322",
    },
    "light": {
        "label": "Светлая",
        "bg": "#f4f6fa", "card": "#ffffff", "border": "#d7dce5",
        "text": "#16202e", "muted": "#5d6b80", "accent": "#0a84ff",
        "accent2": "#4f8cff", "accent_hi": "#3da2ff", "ok": "#16a34a", "ok_text": "#ffffff",
        "field": "#ffffff", "bar_bg": "#e6eaf1", "warn": "#d97706",
        "danger": "#dc2626", "top": "#ffffff",
    },
}

DEFAULT_THEME = "dark"


def theme_colors(name: str) -> dict[str, str]:
    """Цвета темы; неизвестное имя → тема по умолчанию."""
    return THEMES.get(name, THEMES[DEFAULT_THEME])


def stylesheet_for(name: str) -> str:
    """Собрать QSS для выбранной темы."""
    c = theme_colors(name)
    top = c.get("top", c["card"])          # шапка/панели темнее карточек
    return f"""
    QMainWindow, QDialog, QWidget#central {{ background: {c['bg']}; }}
    QWidget {{ color: {c['text']}; font-family: "Segoe UI"; font-size: 14px; }}
    QFrame#card {{ background: {c['card']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QLabel {{ background: transparent; }}
    QLabel#caption {{ color: {c['muted']}; font-size: 12px; }}
    QLabel#value {{ font-size: 24px; font-weight: 600; }}
    QLabel#percent {{ color: {c['accent']}; font-size: 16px; font-weight: 600; }}
    QLabel#percent[done="true"] {{ color: {c['ok']}; }}
    QLabel#hint {{ color: {c['muted']}; font-size: 12px; }}
    QLabel#section {{ color: {c['accent']}; font-size: 12px; font-weight: 700; }}
    QLabel#brand {{ color: {c['text']}; font-size: 14px; font-weight: 800; }}
    QLabel#brand-sub {{ color: {c['muted']}; font-size: 11px; }}
    QFrame#brand-rule {{ background: {c['accent']}; border: none; border-radius: 1px; }}
    QFrame#sidebar {{
        background: {c['field']}; border: 1px solid {c['border']}; border-radius: 12px;
    }}

    QPushButton#duty {{
        background: {c['accent']}; border: none; border-radius: 10px;
        padding: 13px; font-size: 15px; font-weight: 700; color: {c['bg']};
    }}
    QPushButton#duty:hover {{ background: {c['accent_hi']}; }}
    QPushButton#duty:pressed {{ background: {c['accent2']}; }}
    QPushButton#duty:checked {{ background: {c['ok']}; color: {c['ok_text']}; }}
    QPushButton#duty:disabled {{ background: {c['card']}; color: {c['muted']}; }}

    QPushButton {{
        background: {c['card']}; border: 1px solid {c['border']}; border-radius: 7px;
        padding: 8px 14px; font-size: 13px;
    }}
    QPushButton:hover {{ border-color: {c['accent']}; color: {c['accent']}; }}
    QPushButton:pressed {{ background: {c['field']}; }}
    QPushButton#primary {{ background: {c['accent']}; border: none; color: {c['bg']}; font-weight: 700; }}
    QPushButton:disabled {{ color: {c['muted']}; border-color: {c['border']}; }}

    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {{
        background: {c['field']}; border: 1px solid {c['border']}; border-radius: 8px;
        padding: 7px 9px; selection-background-color: {c['accent']};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {{ border-color: {c['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {c['card']}; border: 1px solid {c['border']};
        selection-background-color: {c['accent']}; selection-color: {c['bg']};
    }}

    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;
        border: 1px solid {c['border']}; background: {c['field']}; }}
    QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
    QCheckBox:hover::indicator {{ border-color: {c['accent']}; }}

    QSlider::groove:horizontal {{ height: 4px; background: {c['bar_bg']}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        width: 14px; height: 14px; margin: -5px 0;
        border-radius: 7px; background: {c['accent']}; border: none;
    }}

    QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 8px;
        background: {c['card']}; top: -1px; }}
    QTabBar::tab {{ background: transparent; color: {c['muted']}; padding: 8px 16px;
        font-size: 13px; font-weight: 600; }}
    QTabBar::tab:selected {{ color: {c['accent']}; border-bottom: 2px solid {c['accent']}; }}
    QTabBar::tab:hover {{ color: {c['text']}; }}

    QProgressBar {{ background: {c['bar_bg']}; border: none; border-radius: 5px;
        max-height: 10px; min-height: 10px; }}
    QProgressBar::chunk {{
        border-radius: 5px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c['accent']}, stop:1 {c['accent2']});
    }}
    QProgressBar[done="true"]::chunk {{ background: {c['ok']}; }}

    QMenuBar {{ background: {top}; color: {c['text']}; border-bottom: 1px solid {c['border']}; }}
    QMenu {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']};
        padding: 4px; }}
    QMenu::item {{ padding: 7px 22px 7px 12px; border-radius: 6px; }}
    QMenu::item:selected {{ background: {c['accent']}; color: {c['bg']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
    QToolTip {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; }}

    QGroupBox {{
        background: {c['card']}; border: 1px solid {c['border']};
        border-radius: 8px; margin-top: 12px; padding-top: 6px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; left: 10px; padding: 0 4px;
        color: {c['muted']}; font-size: 12px; font-weight: 700;
    }}
    QRadioButton {{ spacing: 7px; }}
    QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 7px;
        border: 1px solid {c['border']}; background: {c['field']}; }}
    QRadioButton::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}

    QFrame#titlebar {{
        background: {top}; border: none;
        border-bottom: 1px solid {c['border']};
    }}
    QLabel#titlebar-label {{ color: {c['text']}; font-size: 13px; font-weight: 600; }}
    QPushButton#titlebar-btn {{
        background: transparent; border: none; border-radius: 6px;
        color: {c['muted']}; font-size: 13px; padding: 0;
    }}
    QPushButton#titlebar-btn:hover {{ background: {c['bar_bg']}; color: {c['text']}; }}
    QPushButton#titlebar-btn[role="close"]:hover {{
        background: {c['danger']}; color: #ffffff;
    }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 24px; }}
    """


# Совместимость: прежний модуль отдавал готовую строку стилей.
STYLESHEET = stylesheet_for(DEFAULT_THEME)


def apply(name: str) -> str:
    """Вернуть QSS для темы и обновить модульные цвета (ACCENT, OK и т.д.)."""
    global ACCENT, OK, WARN, BG, CARD, BORDER, TEXT, MUTED
    c = theme_colors(name)
    ACCENT, OK, WARN = c["accent"], c["ok"], c["warn"]
    BG, CARD, BORDER = c["bg"], c["card"], c["border"]
    TEXT, MUTED = c["text"], c["muted"]
    return stylesheet_for(name)
