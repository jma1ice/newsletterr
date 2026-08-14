"""Per-item section heading overrides."""

_HEADING_KEY = 'heading_override'
_HIDE_KEY = 'hide_heading'


def stamp(theme, heading=None, hide=False):
    heading = (heading or '').strip()
    hide = bool(hide)
    if not heading and not hide:
        return theme
    return {**theme, _HEADING_KEY: heading, _HIDE_KEY: hide}


def resolve(theme, default_label):
    if not theme:
        return default_label
    if theme.get(_HIDE_KEY):
        return ''
    return theme.get(_HEADING_KEY) or default_label


def is_hidden(theme):
    return bool(theme and theme.get(_HIDE_KEY))
