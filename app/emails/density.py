"""Email density (compact vs expanded), the axis that runs across every layout."""

COMPACT = 'compact'
EXPANDED = 'expanded'
DENSITIES = (COMPACT, EXPANDED)

NATURAL = {
    'legacy': EXPANDED,
    'classic': EXPANDED,
    'spotlight': EXPANDED,
    'editorial': COMPACT,
    'digest': COMPACT,
}

def resolve(layout, value):
    if value in DENSITIES:
        return value
    return NATURAL.get(layout, EXPANDED)

def stamp(theme, layout, value):
    merged = dict(theme)
    merged['density'] = resolve(layout, value)
    merged['density_layout'] = layout
    return merged

def layout_of(theme):
    return (theme or {}).get('density_layout') or 'legacy'

def of(theme, layout=None):
    return resolve(layout or layout_of(theme), (theme or {}).get('density'))

def is_compact(theme, layout=None):
    return of(theme, layout) == COMPACT

def is_variant(theme, layout=None):
    layout = layout or layout_of(theme)
    return of(theme, layout) != NATURAL.get(layout, EXPANDED)

def picker(theme, layout=None):
    on = is_variant(theme, layout)

    def p(variant_value, natural_value):
        return variant_value if on else natural_value

    return p

def picker3(theme, layout=None):
    if not is_variant(theme, layout):
        step = 0
    else:
        step = -1 if is_compact(theme, layout) else 1

    def p3(tight_value, natural_value, roomy_value):
        return tight_value if step < 0 else (roomy_value if step > 0 else natural_value)

    return p3

def show_art(theme, layout=None):
    return not (is_compact(theme, layout) and is_variant(theme, layout))

def columns(theme, layout, cols):
    return 1 if not show_art(theme, layout) else cols
