"""Palette-driven theming. Both modes are defined here; nothing else hardcodes a color."""
from __future__ import annotations
from string import Template

DARK = {
    'bg': '#131316', 'sidebar': '#1a1a1f', 'surface': '#202025', 'surface_hi': '#26262c',
    'card': '#1e1e23', 'preview': '#17171b', 'border': '#2d2d35', 'border_hi': '#3c3c46',
    'text': '#ededf2', 'muted': '#9a9aa6', 'faint': '#6d6d79',
    'accent': '#b69cf5', 'accent_hover': '#c9b4ff', 'accent_text': '#1b1526',
    'accent_soft': '#2b2340', 'accent_line': '#4b3f6b',
    'like': '#ff7aa8', 'like_soft': '#3b2130', 'like_line': '#5f3348',
    'hover': '#2a2a31', 'pressed': '#343240', 'scroll': '#43434d',
    'shadow': 'rgba(0,0,0,0.45)', 'nav_on': '#332e42', 'ok': '#7fd6a8',
}

LIGHT = {
    'bg': '#f6f6f8', 'sidebar': '#ffffff', 'surface': '#ffffff', 'surface_hi': '#f0f0f4',
    'card': '#ffffff', 'preview': '#f1f1f5', 'border': '#e4e4ea', 'border_hi': '#cfcfda',
    'text': '#1b1b21', 'muted': '#6a6a76', 'faint': '#92929e',
    'accent': '#7a55d6', 'accent_hover': '#6a45c9', 'accent_text': '#ffffff',
    'accent_soft': '#eee7ff', 'accent_line': '#cdbcf6',
    'like': '#e34b83', 'like_soft': '#ffe9f1', 'like_line': '#f6c2d6',
    'hover': '#eeeef3', 'pressed': '#e3e3ec', 'scroll': '#c6c6d2',
    'shadow': 'rgba(20,18,30,0.10)', 'nav_on': '#ece6fb', 'ok': '#2f9c6b',
}

PALETTES = {'dark': DARK, 'light': LIGHT}
DEFAULT_MODE = 'dark'

TEMPLATE = Template('''
QWidget { color:$text; font-family:"Apple SD Gothic Neo","Noto Sans CJK KR","Segoe UI",sans-serif; font-size:14px; }
QMainWindow, QDialog { background:$bg; }
QWidget#sidebar { background:$sidebar; border-right:1px solid $border; }
QLabel { background:transparent; }
QLabel#brand { font-size:20px; font-weight:700; letter-spacing:-0.5px; }
QLabel#muted { color:$muted; font-size:12px; }
QLabel#faint { color:$faint; font-size:11px; }
QLabel#section { color:$faint; font-size:11px; font-weight:700; letter-spacing:1.1px; }
QLabel#title { font-size:26px; font-weight:650; letter-spacing:-0.6px; }
QLabel#hero { font-size:30px; font-weight:600; letter-spacing:-0.9px; }
QLabel#heroIcon { background:$accent_soft; border:1px solid $accent_line; border-radius:26px; }
QLabel#badge { color:$muted; background:$surface_hi; border:1px solid $border; border-radius:6px; padding:1px 6px; font-size:11px; }

QPushButton { background:$surface_hi; border:1px solid $border_hi; padding:9px 13px; border-radius:9px; color:$text; }
QPushButton:hover { background:$hover; border-color:$accent_line; }
QPushButton:pressed { background:$pressed; }
QPushButton:disabled { color:$faint; background:$surface; border-color:$border; }
QPushButton#nav { background:transparent; border:0; padding:10px 12px; text-align:left; color:$muted; }
QPushButton#nav:hover { background:$hover; color:$text; }
QPushButton#nav:checked { background:$nav_on; color:$text; font-weight:600; }
QPushButton#history { background:transparent; border:0; text-align:left; color:$muted; padding:8px 12px; font-size:12.5px; }
QPushButton#history:hover { background:$hover; color:$text; }
QPushButton#accent { background:$accent; color:$accent_text; border:0; font-weight:700; }
QPushButton#accent:hover { background:$accent_hover; }
QPushButton#accent:disabled { background:$surface_hi; color:$faint; }
QPushButton#ghost { background:transparent; border:1px solid $border_hi; color:$muted; }
QPushButton#ghost:hover { background:$hover; color:$text; }
QPushButton#heart { background:$surface_hi; border:1px solid $border_hi; padding:0; }
QPushButton#heart:hover { border-color:$like_line; }
QPushButton#heart:checked { background:$like_soft; border-color:$like_line; }
QPushButton#chip { background:$surface; border:1px solid $border_hi; border-radius:16px; padding:8px 15px; color:$muted; }
QPushButton#chip:hover { background:$accent_soft; border-color:$accent_line; color:$text; }
QPushButton#small { padding:5px 9px; font-size:12px; border-radius:8px; }
QPushButton#more { background:$surface; border:1px solid $border_hi; border-radius:11px; padding:12px 22px; color:$muted; font-weight:600; }
QPushButton#more:hover { background:$accent_soft; border-color:$accent_line; color:$text; }

QLineEdit, QPlainTextEdit { background:$surface_hi; border:1px solid $border_hi; border-radius:9px; padding:8px 10px;
    color:$text; selection-background-color:$accent; selection-color:$accent_text; }
QLineEdit:focus, QPlainTextEdit:focus { border-color:$accent; }
QPlainTextEdit#composerInput { border:0; background:transparent; font-size:15.5px; padding:2px; }
QFrame#composer { background:$surface; border:1px solid $border_hi; border-radius:18px; }
QFrame#card { background:$card; border:1px solid $border; border-radius:14px; }
QFrame#card:hover { border-color:$accent_line; }
QLabel#preview { background:$preview; border:0; border-radius:10px; color:$faint; font-size:12px; }
QFrame#line { background:$border; border:0; max-height:1px; }

QScrollArea { border:0; background:transparent; }
QScrollArea > QWidget > QWidget { background:transparent; }
QScrollBar:vertical { background:transparent; width:9px; margin:3px; }
QScrollBar::handle:vertical { background:$scroll; border-radius:4px; min-height:34px; }
QScrollBar::handle:vertical:hover { background:$accent_line; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }

QCheckBox { spacing:8px; color:$muted; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid $border_hi; border-radius:4px; background:$surface_hi; }
QCheckBox::indicator:checked { background:$accent; border-color:$accent; image:none; }
QComboBox { background:$surface_hi; border:1px solid $border_hi; padding:7px 10px; border-radius:8px; color:$text; }
QComboBox QAbstractItemView { background:$surface; border:1px solid $border_hi; selection-background-color:$accent_soft; color:$text; }
QMenu { background:$surface; border:1px solid $border_hi; padding:5px; }
QMenu::item { padding:8px 18px; color:$text; }
QMenu::item:selected { background:$accent_soft; }
QToolTip { color:$text; background:$surface; border:1px solid $border_hi; padding:6px; }
QProgressBar { background:$surface_hi; border:0; border-radius:2px; max-height:3px; }
QProgressBar::chunk { background:$accent; border-radius:2px; }
''')


def palette(mode: str) -> dict:
    return PALETTES.get(mode, DARK)


def build_style(mode: str) -> str:
    return TEMPLATE.substitute(palette(mode))


# Kept for callers that only need the default look.
STYLE = build_style(DEFAULT_MODE)
