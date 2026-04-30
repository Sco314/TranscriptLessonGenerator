"""
theme.py — Module-level theme state.

Mirrors the Node template's `let THEME = {...}` mutable global. set_theme()
swaps it; helpers in components.py read it via get_theme() so they always
pick up the current theme.

Default is blue (matches Node).
"""

from .constants import THEMES

_THEME = dict(THEMES["blue"])  # copy so we never mutate the preset


def set_theme(name: str) -> dict:
    """Set the active theme by preset name. Unknown names log + keep current."""
    global _THEME
    if name not in THEMES:
        print(f"❌ Unknown theme '{name}'. Valid: {sorted(THEMES.keys())}. Keeping '{_THEME['name']}'.")
        return dict(_THEME)
    _THEME = dict(THEMES[name])
    return dict(_THEME)


def get_theme() -> dict:
    """Return a copy of the active theme dict."""
    return dict(_THEME)


def primary() -> str:
    return _THEME["primary"]


def primary_light() -> str:
    return _THEME["primary_light"]
