import json
import re

from app.theme import CUSTOM_UI_KEYS, build_custom_ui_theme_css, parse_custom_ui_colors

# The mandatory token set every pride block defines (see pride.css); the
# custom theme blocks must stay symmetric the same way.
REQUIRED_TOKENS = [
    '--bg', '--surface-1', '--surface-2', '--surface-3', '--border',
    '--border-soft', '--text', '--text-muted', '--text-faint', '--accent',
    '--accent-strong', '--accent-soft', '--on-accent',
]

def test_custom_theme_css_shape_and_symmetry():
    light = json.dumps({'bg': '#ffffff', 'surface': '#f0f0f0', 'border': '#cccccc', 'text': '#111111', 'muted': '#555555', 'accent': '#ff8800'})
    dark = json.dumps({'bg': '#101010', 'surface': '#181818', 'border': '#333333', 'text': '#eeeeee', 'muted': '#aaaaaa', 'accent': '#22ccff'})
    css = build_custom_ui_theme_css(light, dark)
    light_block, dark_block = css.split('\n')
    assert light_block.startswith('.theme-custom {')
    assert dark_block.startswith('.theme-custom.dark {')
    for token in REQUIRED_TOKENS:
        assert f'{token}:' in light_block
        assert f'{token}:' in dark_block
    assert sorted(re.findall(r'--[a-z0-9-]+(?=:)', light_block)) == sorted(re.findall(r'--[a-z0-9-]+(?=:)', dark_block))
    # user hex values pass through verbatim
    assert '--bg: #ffffff;' in light_block
    assert '--accent: #22ccff;' in dark_block

def test_custom_theme_rejects_bad_hex():
    # Values land in a <style> block, so anything but #rrggbb must be dropped
    bad = json.dumps({'bg': 'red; } body { background: url(x)', 'accent': '#zzzzzz', 'text': '#12345'})
    css = build_custom_ui_theme_css(bad, None)
    assert 'url(' not in css
    assert '#zzzzzz' not in css
    colors = parse_custom_ui_colors(bad, 'light')
    assert all(re.match(r'^#[0-9a-fA-F]{6}$', colors[k]) for k in CUSTOM_UI_KEYS)

def test_custom_theme_handles_missing_and_garbage_json():
    for raw in (None, '', 'not json', '[]', '42'):
        colors = parse_custom_ui_colors(raw, 'dark')
        assert set(colors) == set(CUSTOM_UI_KEYS)
        assert all(re.match(r'^#[0-9a-fA-F]{6}$', colors[k]) for k in CUSTOM_UI_KEYS)

def test_on_accent_contrast_flips_with_luminance():
    bright = json.dumps({'accent': '#ffff00'})
    dark_accent = json.dumps({'accent': '#112233'})
    css_bright = build_custom_ui_theme_css(bright, None).split('\n')[0]
    css_dark = build_custom_ui_theme_css(dark_accent, None).split('\n')[0]
    assert '--on-accent: #111417;' in css_bright
    assert '--on-accent: #ffffff;' in css_dark
