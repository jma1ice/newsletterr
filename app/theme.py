import json
import re

from app import dates
from app.settings_store import DEFAULTS, get_settings

import logging

logger = logging.getLogger(__name__)

# Custom app UI theme: a user-built palette applied via the
# .theme-custom html class (deliberately not the pride class, so the pride
# brand flourish and logo swap never trigger). Users pick six base colors per
# mode; the remaining tokens of the 13-token set derive here, mirroring the
# relationships tokens.css/pride.css use. Values are injected into a <style>
# block, so only strict #rrggbb hex ever passes through.

_HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')

CUSTOM_UI_KEYS = ('bg', 'surface', 'border', 'text', 'muted', 'accent')

_CUSTOM_UI_FALLBACK = {
    'light': {'bg': '#eef1f2', 'surface': '#fbfcfc', 'border': '#c3ced1', 'text': '#16272b', 'muted': '#51666c', 'accent': '#3e8d94'},
    'dark': {'bg': '#1d2426', 'surface': '#252d30', 'border': '#3a464a', 'text': '#e9f1f2', 'muted': '#a5b6ba', 'accent': '#62a1a4'},
}

def is_hex_color(value):
    return bool(isinstance(value, str) and _HEX_RE.match(value or ''))

def _safe_hex(value, fallback):
    return value if isinstance(value, str) and _HEX_RE.match(value or '') else fallback

def parse_custom_ui_colors(raw_json, mode):
    """Returns the six validated base colors for a mode from the stored JSON,
    falling back per-key so a bad or missing value never breaks the page."""
    fallback = _CUSTOM_UI_FALLBACK[mode]
    try:
        data = json.loads(raw_json) if raw_json else {}
    except (ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {k: _safe_hex(data.get(k), fallback[k]) for k in CUSTOM_UI_KEYS}

def _on_accent(accent_hex):
    r, g, b = (int(accent_hex[i:i + 2], 16) for i in (1, 3, 5))
    luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    return '#111417' if luminance > 0.55 else '#ffffff'

def is_dark_background(hex_color):
    if not is_hex_color(hex_color):
        return True  # every preset is dark, so that is the safer default
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 <= 0.5

def _custom_token_block(c, mode):
    # accent-strong pushes toward black in light mode and white in dark mode,
    # matching how the pride palettes step their accents per mode
    strong_mix = '#000000' if mode == 'light' else '#ffffff'
    return (
        f"--bg: {c['bg']};"
        f" --surface-1: {c['surface']};"
        f" --surface-2: color-mix(in srgb, {c['surface']} 88%, {c['bg']});"
        f" --surface-3: color-mix(in srgb, {c['surface']} 76%, {c['bg']});"
        f" --border: {c['border']};"
        f" --border-soft: color-mix(in srgb, {c['border']} 55%, {c['surface']});"
        f" --text: {c['text']};"
        f" --text-muted: {c['muted']};"
        f" --text-faint: color-mix(in srgb, {c['muted']} 65%, {c['surface']});"
        f" --accent: {c['accent']};"
        f" --accent-strong: color-mix(in srgb, {c['accent']} 78%, {strong_mix});"
        f" --accent-soft: color-mix(in srgb, {c['accent']} 14%, {c['surface']});"
        f" --on-accent: {_on_accent(c['accent'])};"
    )

def build_custom_ui_theme_css(light_json, dark_json):
    """CSS text for the custom UI theme: a .theme-custom block and a
    token-for-token symmetric .theme-custom.dark block (same invariant the
    pride.css blocks keep, so the result is order-independent)."""
    light = parse_custom_ui_colors(light_json, 'light')
    dark = parse_custom_ui_colors(dark_json, 'dark')
    return (
        f".theme-custom {{ {_custom_token_block(light, 'light')} }}\n"
        f".theme-custom.dark {{ {_custom_token_block(dark, 'dark')} }}"
    )

THEME_KEYS = ('primary_color', 'secondary_color', 'accent_color', 'background_color', 'text_color', 'email_theme')

def get_theme_settings():
    try:
        s = get_settings(decrypt_secrets=False)
        return {key: s[key] for key in THEME_KEYS}
    except Exception as e:
        logger.error(f"Error getting theme settings: {e}")
        return {key: DEFAULTS[key] for key in THEME_KEYS}

def get_email_theme_colors():
    theme_settings = get_theme_settings()
    
    return {
        'background': theme_settings['background_color'],
        'text': theme_settings['text_color'],
        'primary': theme_settings['primary_color'],
        'secondary': theme_settings['secondary_color'],
        'accent': theme_settings['accent_color'],
        'card_bg': '#2d2d2d',
        'border': '#404040',
        'muted_text': '#cccccc',
        'email_theme': theme_settings['email_theme']
    }

def get_email_chrome_settings():
    try:
        s = get_settings(decrypt_secrets=False)
    except Exception as e:
        logger.error(f"Error getting email chrome settings: {e}")
        s = {}
    header_bg = (s.get('email_header_bg') or '').strip()
    server_type = (s.get('media_server_type') or 'plex')
    jellyfin = server_type in ('jellyfin', 'emby')
    # Standalone mode has no server to open, so the spotlight call to
    # action drops out rather than pointing at an unconfigured Plex.
    if server_type == 'none':
        server_url = ''
    else:
        server_url = (s.get('jellyfin_web_url') if jellyfin else s.get('plex_web_url')) or ''
    return {
        'show_server_name': s.get('email_show_server_name') == 'enabled',
        # blank (or anything not #rrggbb) keeps the default gradient
        'header_bg': header_bg if is_hex_color(header_bg) else '',
        # the small uppercase line above the header title in the editorial and
        # spotlight layouts; blank falls through to the server name or the
        # auto text below
        'eyebrow_text': (s.get('email_eyebrow_text') or '').strip(),
        # off by default: a blank header title (or eyebrow) then renders
        # nothing instead of newsletterr's stock filler phrases
        'auto_header_text': s.get('email_auto_header_text') == 'enabled',
        # the spotlight layout's call to action; blank hides the button
        'server_url': server_url.strip(),
        'server_cta': 'Open Jellyfin' if jellyfin else 'Open Plex',
        # display formats. The email shell renders its own dates, so it
        # needs these here as well as on the stamped theme dict.
        'date_format': dates.resolve_date_format(s.get('date_format')),
        'time_format': dates.resolve_time_format(s.get('time_format')),
        'week_start': dates.resolve_week_start(s.get('week_start_day')),
    }

def build_email_css_from_theme(theme_colors, logo_width, container_width=800):
    _scheme = "dark" if is_dark_background(theme_colors.get('background')) else "light"
    return f"""
        <style>
            :root {{
                color-scheme: {_scheme}!important;
            }}

            body {{
                margin: 0!important;
                padding: 0!important;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif!important;
                background-color: {theme_colors['background']}!important;
                line-height: 1.6!important;
                color: {theme_colors['text']}!important;
                -webkit-text-size-adjust: 100%!important;
                -ms-text-size-adjust: 100%!important;
            }}
            
            table, td {{
                border-collapse: collapse!important;
                mso-table-lspace: 0pt!important;
                mso-table-rspace: 0pt!important;
            }}
            
            img {{
                border: 0!important;
                height: auto!important;
                line-height: 100%!important;
                outline: none!important;
                text-decoration: none!important;
                -ms-interpolation-mode: bicubic!important;
            }}
            
            .ReadMsgBody {{ width: 100%!important; }}
            .ExternalClass {{ width: 100%!important; }}
            .ExternalClass * {{ line-height: 100%!important; }}

            .email-container {{
                max-width: {container_width}px!important;
                width: 100%!important;
                margin: 0 auto!important;
            }}
            
            .email-logo {{
                max-width: {logo_width}px!important;
                width: {logo_width}px!important;
                height: auto!important;
            }}

            .card-poster-img {{
                width: 100%!important;
                height: auto!important;
                display: block!important;
                object-fit: cover!important;
                background-color: #f8f9fa!important;
                border-radius: 10px 10px 0 0!important;
            }}

            @media only screen and (max-width: 600px) {{
                .email-container {{
                    width: 100%!important;
                    max-width: 100%!important;
                    margin: 0!important;
                }}
                
                .email-logo {{
                    max-width: 60px!important;
                    width: 60px!important;
                }}

                .nl-grid {{
                    display: block!important;
                    width: 100%!important;
                    text-align: center!important;
                }}

                .nl-grid-row {{
                    display: inline!important;
                }}

                .nl-grid td {{
                    width: 30%!important;
                    padding: 6px!important;
                    display: inline-block!important;
                    vertical-align: top!important;
                    box-sizing: border-box!important;
                }}

                .nl-grid-card {{
                    width: 100%!important;
                    max-width: 150px!important;
                    height: auto!important;
                    margin: 0 auto 10px auto!important;
                    overflow: hidden!important;
                    border-radius: 10px!important;
                    display: block!important;
                }}

                .nl-stats-table th:nth-child(n+5),
                .nl-stats-table td:nth-child(n+5) {{
                    display: none!important;
                }}

                .card-content {{
                    height: auto!important;
                    min-height: 165px!important;
                    text-align: left!important;
                }}

                .cs-cal-table,
                .cs-cal-table tbody,
                .cs-cal-row {{
                    display: block!important;
                    width: 100%!important;
                }}

                .cs-cal-head {{
                    display: none!important;
                }}

                .cs-cal-cell {{
                    display: block!important;
                    width: 100%!important;
                    box-sizing: border-box!important;
                    border-left: 0!important;
                    border-right: 0!important;
                    border-top: 0!important;
                    padding: 10px 12px!important;
                }}

                .cs-cal-empty {{
                    display: none!important;
                }}

                .cs-cal-daynum {{
                    display: none!important;
                }}

                .cs-cal-daylong {{
                    display: block!important;
                }}

                .cs-cal-event {{
                    margin: 0 0 10px 0!important;
                }}

                .cs-cal-poster {{
                    width: 56px!important;
                    display: inline-block!important;
                    vertical-align: top!important;
                    margin: 0 10px 0 0!important;
                }}

                .cs-cal-event-text {{
                    display: inline-block!important;
                    vertical-align: top!important;
                    max-width: 70%!important;
                    text-align: left!important;
                }}

                .cs-agenda-table,
                .cs-agenda-table tbody,
                .cs-agenda-row {{
                    display: block!important;
                    width: 100%!important;
                }}

                .cs-agenda-date,
                .cs-agenda-items {{
                    display: block!important;
                    width: 100%!important;
                    box-sizing: border-box!important;
                }}

                .cs-agenda-items {{
                    border-top: 0!important;
                    padding-top: 0!important;
                }}
            }}
        </style>
    """
