"""Email layout variants: classic (A), editorial (B), digest (C).

One renderer per section per layout, reached only through the assemble
pipeline, so every surface (manual sends, scheduled sends, /preview_email,
schedule preview) shares this single source. 'legacy' never routes here; the
pre-v2026.4 builders stay untouched so existing output and goldens hold byte
for byte. Sections the mockups did not restyle (graphs, recommendations,
collections, users, per-user DN wrapped, text/image blocks) intentionally
render legacy in every layout.

All markup is email-safe: tables, inline styles, no flex/grid.
"""
from datetime import datetime

from app.emails.builders.card_grid import (
    format_relative_date as _relative,
    empty_state_html as _empty_state_html,
    build_card_html as _build_card_html,
    effective_columns as _effective_columns,
)
from app.emails.builders.coming_soon import (
    _poster_url as _arr_poster_url,
    _arr_poster_src,
    radarr_events,
    radarr_upcoming,
    render_view_html,
    resolve_view,
    sonarr_events,
    sonarr_groups,
    upcoming_release_date,
)
from app.emails.builders.most_watched import (
    most_watched_heading,
    most_watched_items,
    most_watched_poster,
    play_count_text,
)
from app.emails.builders.ombi_requests import filter_ombi_pending
from app.emails.builders.random_pick import (
    random_pick_heading,
    random_pick_meta_text,
    attach_random_pick_poster,
)
from app.emails.builders.seerr_requests import filter_seerr_pending, TMDB_POSTER_BASE
from app.emails.builders.top_viewer import (
    ANONYMOUS_SUBJECT,
    attach_top_viewer_avatar,
    top_viewer_heading,
    top_viewer_metrics,
)
from app.emails.images import (
    fetch_and_attach_blurred_image,
    fetch_and_attach_image,
    fetch_and_attach_small_thumbnail,
    email_icon_img,
    truncate_text,
)
from app.emails import density, headings
from app.security import escape_html_output as esc

import logging

logger = logging.getLogger(__name__)

LAYOUTS = ('classic', 'editorial', 'digest', 'spotlight')

FONT = "'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif"

_CARD_LAYOUTS = ('classic', 'spotlight')

_SPOTLIGHT_NEUTRALS = {
    'background': '#0f0f0f',
    'card_bg': '#181818',
    'border': '#2b2b2b',
    'muted_text': '#8e8e8e',
    'text': '#c9c9c9',
}

def is_layout(layout):
    return layout in LAYOUTS

def apply_theme(layout, theme):
    """Theme colors adjusted for a layout's chassis. Every renderer and the
    email shell must go through this so section cards and the page they sit on
    agree; returns the theme untouched for layouts that have no overrides."""
    if layout != 'spotlight':
        return theme
    merged = dict(theme)
    merged.update(_SPOTLIGHT_NEUTRALS)
    return merged

def spotlight_eyebrow(theme, text, size=11):
    return (f'<div style="font-size: {size}px; font-weight: 800; letter-spacing: 1.5px; '
            f'text-transform: uppercase; color: {theme["accent"]}; font-family: {FONT};">{esc(text)}</div>')

def _spotlight_row(theme, art_html, title_html, meta, value_html, last=False):
    # spotlight-only helper, so the picker keys off that layout directly
    p = density.picker(theme, 'spotlight')
    pad = p('6px', '9px')
    border = "" if last else f" border-bottom: 1px solid {theme['border']};"
    art_cell = f'<td width="52" valign="middle" style="padding: {pad} 12px {pad} 0;{border}">{art_html}</td>' if art_html else ''
    value_cell = (f'<td align="right" valign="middle" style="padding: {pad} 0;{border} white-space: nowrap; '
                  f'font-family: {FONT};">{value_html}</td>') if value_html else ''
    return f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            {art_cell}
            <td valign="middle" style="padding: {pad} 0;{border} font-family: {FONT};">
                <div style="font-size: {p('13px', '14px')}; font-weight: 700; color: #ffffff; line-height: 1.25;">{title_html}</div>
                {f'<div style="padding-top: {p("2px", "3px")}; font-size: {p("11px", "11.5px")}; color: {theme["muted_text"]};">{meta}</div>' if meta else ''}
            </td>
            {value_cell}
        </tr></table>
    """

def _plain_label(label):
    return label.split('</img>')[-1].split('> ')[-1] if '<' in label else label

def _spotlight_meta(bits, value=None):
    v = str(value) if value not in (None, '') else None
    keep = []
    for b in bits:
        b = str(b or '')
        if not b:
            continue
        parts = b.split()
        if v is not None and len(parts) > 1 and parts[0] == v:
            continue
        keep.append(b)
    return ' &middot; '.join(esc(b) for b in keep)

def _spotlight_value(theme, value, unit):
    if not value:
        return ""
    return (f'<div style="font-size: 18px; font-weight: 800; color: {theme["accent"]}; line-height: 1;">{esc(str(value))}</div>'
            f'<div style="padding-top: 3px; font-size: 9.5px; letter-spacing: .6px; text-transform: uppercase; '
            f'color: {theme["muted_text"]};">{esc(unit)}</div>')

# ---------------------------------------------------------------- shells

def _shell(layout, theme, label, inner, range_text="", overline="", bg_src=""):
    """Per-layout section chrome around a section's inner HTML. Density only
    moves the chrome when this render is the layout's newly authored variant;
    p(variant, natural) is what guarantees the natural side stays untouched.

    The label is the item's override when it set one; an empty
    label means the heading is hidden and only the chrome is drawn.
    """
    label = headings.resolve(theme, label)
    p = density.picker(theme, layout)
    if not density.show_art(theme, layout):
        # compact variants carry no section artwork, background art included
        bg_src = ""
    if not label:
        return _shell_headless(layout, theme, inner, bg_src, p)
    if layout == 'spotlight':
        range_html = (f'<td align="right" valign="middle" style="font-size: 11px; color: {theme["muted_text"]}; '
                      f'white-space: nowrap; font-family: {FONT};">{esc(range_text)}</td>') if range_text else ''
        art = f" background-image: url('{bg_src}'); background-size: cover; background-position: center; background-repeat: no-repeat;" if bg_src else ""
        return f"""
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: {theme['card_bg']};{art} border: 1px solid {theme['border']}; border-radius: {p('8px', '10px')}; border-collapse: separate; margin: 0 0 {p('8px', '12px')} 0;">
                <tr><td style="padding: {p('11px 14px 0 14px', '16px 18px 0 18px')};">
                    <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                        <td valign="middle">{spotlight_eyebrow(theme, label)}</td>
                        {range_html}
                    </tr></table>
                </td></tr>
                <tr><td style="padding: {p('8px 14px 12px 14px', '12px 18px 16px 18px')};">{inner}</td></tr>
            </table>
        """
    if layout == 'classic':
        range_html = f'<span style="font-weight: 500; letter-spacing: 0; text-transform: none; color: {theme["muted_text"]}; font-size: 11px;">{esc(range_text)}</span>' if range_text else ''
        art = f" background-image: url('{bg_src}'); background-size: cover; background-position: center; background-repeat: no-repeat;" if bg_src else ""
        scrim_open = '<div style="background-color: rgba(28, 28, 28, 0.74);">' if bg_src else ''
        scrim_close = '</div>' if bg_src else ''
        return f"""
            <div style="background-color: {theme['card_bg']};{art} border: 1px solid {theme['border']}; border-radius: {p('8px', '10px')}; margin: 0 0 {p('10px', '16px')} 0; overflow: hidden; font-family: {FONT};">
                {scrim_open}<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                    <td style="padding: {p('7px 12px', '10px 16px')}; font-size: {p('10.5px', '11px')}; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: {theme['text']}; border-bottom: 1px solid {theme['border']}; font-family: {FONT};">{esc(label)}</td>
                    <td align="right" style="padding: {p('7px 12px', '10px 16px')}; border-bottom: 1px solid {theme['border']};">{range_html}</td>
                </tr></table>
                {inner}{scrim_close}
            </div>
        """
    if layout == 'editorial':
        over = overline or label
        head_range = f" &middot; {esc(range_text)}" if range_text else ""
        return f"""
            <div style="padding: {p('30px 0 16px 0', '20px 0 10px 0')}; border-bottom: 1px solid {theme['border']}; font-family: {FONT};">
                <div style="font-size: {p('11.5px', '10.5px')}; letter-spacing: .18em; text-transform: uppercase; color: {theme['primary']}; font-weight: 700;">{esc(over)}{head_range}</div>
                <div style="font-size: {p('25px', '19px')}; font-weight: 700; color: #ffffff; margin: {p('4px 0 18px 0', '2px 0 12px 0')};">{esc(label)}</div>
                {inner}
            </div>
        """
    # digest
    range_html = f' &middot; {esc(range_text)}' if range_text else ''
    return f"""
        <div style="margin: 0 0 {p('22px', '14px')} 0; font-family: {FONT};">
            <div style="font-size: {p('12.5px', '10.5px')}; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: {theme['text']}; border-bottom: 1px solid {theme['border']}; padding-bottom: {p('8px', '5px')}; margin-bottom: {p('12px', '7px')};">{esc(label)}{range_html}</div>
            {inner}
        </div>
    """

def _shell_headless(layout, theme, inner, bg_src, p):
    """Section chrome with the heading suppressed (hideHeading on the item).

    The card, its border and its outer spacing all stay: hiding the heading is
    meant to drop a redundant label, not to strip the section out of the
    layout. Each layout loses only the row that carried the text, so the top
    padding takes over the space the heading used to hold open.
    """
    if layout == 'spotlight':
        art = f" background-image: url('{bg_src}'); background-size: cover; background-position: center; background-repeat: no-repeat;" if bg_src else ""
        return f"""
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: {theme['card_bg']};{art} border: 1px solid {theme['border']}; border-radius: {p('8px', '10px')}; border-collapse: separate; margin: 0 0 {p('8px', '12px')} 0;">
                <tr><td style="padding: {p('11px 14px 12px 14px', '16px 18px 16px 18px')};">{inner}</td></tr>
            </table>
        """
    if layout == 'classic':
        art = f" background-image: url('{bg_src}'); background-size: cover; background-position: center; background-repeat: no-repeat;" if bg_src else ""
        scrim_open = '<div style="background-color: rgba(28, 28, 28, 0.74);">' if bg_src else ''
        scrim_close = '</div>' if bg_src else ''
        return f"""
            <div style="background-color: {theme['card_bg']};{art} border: 1px solid {theme['border']}; border-radius: {p('8px', '10px')}; margin: 0 0 {p('10px', '16px')} 0; overflow: hidden; font-family: {FONT};">
                {scrim_open}{inner}{scrim_close}
            </div>
        """
    if layout == 'editorial':
        return f"""
            <div style="padding: {p('30px 0 16px 0', '20px 0 10px 0')}; border-bottom: 1px solid {theme['border']}; font-family: {FONT};">
                {inner}
            </div>
        """
    # digest
    return f"""
        <div style="margin: 0 0 {p('22px', '14px')} 0; font-family: {FONT};">
            {inner}
        </div>
    """

def _digest_row(theme, left_html, right_html):
    # digest-only helper; its variant is the expanded (roomy) one
    p = density.picker(theme, 'digest')
    pad = p('9px', '5px')
    return f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            <td style="padding: {pad} 0; border-bottom: 1px dotted {theme['border']}; font-size: {p('14px', '12.5px')}; color: #ffffff; font-family: {FONT};">{left_html}</td>
            <td align="right" style="padding: {pad} 0; border-bottom: 1px dotted {theme['border']}; font-size: {p('13px', '12px')}; color: {theme['muted_text']}; white-space: nowrap; font-family: {FONT};">{right_html}</td>
        </tr></table>
    """

def _linked(title, url, underline=True):
    t = esc(title)
    if url:
        decoration = 'underline' if underline else 'none'
        return f'<a href="{esc(url)}" target="_blank" style="color: inherit; text-decoration: {decoration};" title="Open in Plex">{t}</a>'
    return t

# ---------------------------------------------------------------- stats

_COVER_ART_TITLES = frozenset({
    "Most Watched Movies", "Most Watched TV Shows",
    "Most Popular Movies", "Most Popular TV Shows",
    "Most Played Artists", "Most Popular Artists",
    "Recently Watched",
})

_STAT_THUMB_PX = {'classic': (26, 32), 'editorial': (30, 38), 'spotlight': (42, 36)}
_STAT_THUMB_DIGEST = (18, 22)
_STAT_THUMB_DIGEST_EXPANDED = (30, 34)

# Aggregate stats key off a user/library/platform, but Tautulli still ships the
# last-watched item on the row (title, year, plex_url, artwork). Naming those
# rows by 'title' would label a user with a show name, so the label field is
# pinned per stat exactly as the legacy table does it.
_STAT_NAME_KEYS = {
    "Most Active Libraries": 'section_name',
    "Library Item Counts": 'section_name',
    "Most Active Users": 'user',
    "Most Active Platforms": 'platform',
}

_STAT_SKIP_YEAR = frozenset({
    "Most Active Libraries", "Library Item Counts", "Most Active Users",
    "Most Active Platforms", "Most Concurrent Streams",
})

def _stat_row_thumb(row, title, msg_root, cid, base_url, poster_w, avatar_px, show_cover_art,
                    include_user_info, hosted_images_enabled, hosted_base_url):
    if title == "Most Active Users":
        if not include_user_info:
            return ""
        thumb_url = row.get('user_thumb') or ''
        if not thumb_url:
            return ""
        src = fetch_and_attach_small_thumbnail(thumb_url, msg_root, cid, base_url, height=avatar_px,
                                               hosted_images_enabled=hosted_images_enabled,
                                               hosted_base_url=hosted_base_url)
        if not src:
            return ""
        return (f'<img src="{src}" alt="" width="{avatar_px}" height="{avatar_px}" '
                f'style="height: {avatar_px}px; width: {avatar_px}px; border-radius: 50%; '
                f'object-fit: cover; margin-right: 8px; vertical-align: middle;">')

    if not show_cover_art or title not in _COVER_ART_TITLES:
        return ""
    thumb_path = row.get('thumb') or row.get('grandparent_thumb') or ''
    if not thumb_path:
        return ""
    proxy_path = thumb_path if thumb_path.startswith('/proxy-art') else f"/proxy-art{thumb_path}"
    src = fetch_and_attach_small_thumbnail(proxy_path, msg_root, cid, base_url,
                                           height=round(poster_w * 1.5),
                                           hosted_images_enabled=hosted_images_enabled,
                                           hosted_base_url=hosted_base_url)
    if not src:
        return ""
    return (f'<img src="{src}" alt="" width="{poster_w}" style="width: {poster_w}px; height: auto; '
            f'border-radius: 3px; margin-right: 8px; vertical-align: middle;">')

def render_stats(layout, stat_data, msg_root, theme, base_url="", date_range="", hide_play_counts=False, include_user_info=True, show_cover_art=False, hosted_images_enabled=False, hosted_base_url=""):
    if not stat_data or not stat_data.get('rows'):
        return ""
    title = stat_data.get('stat_title', 'Statistics')
    rows = stat_data['rows']
    if title == "Most Active Users" and not include_user_info:
        return ""

    name_key = _STAT_NAME_KEYS.get(title)
    skip_year = title in _STAT_SKIP_YEAR

    def _name(row):
        return (row.get(name_key) if name_key else row.get('title')) or ''

    def _row_url(row):
        # the row's plex_url points at the last-watched item, which is not what
        # an aggregate row is named after
        return '' if name_key else row.get('plex_url')

    def _year(row):
        return '' if skip_year else str(row.get('year') or '')

    def _meta_bits(row):
        bits = []
        if _year(row):
            bits.append(_year(row))
        if not hide_play_counts and row.get('total_plays'):
            bits.append(f"{row['total_plays']} plays")
        if row.get('total_duration'):
            bits.append(f"{round(row['total_duration'] / 3600)}h")
        if row.get('users_watched'):
            bits.append(f"{row['users_watched']} users")
        if row.get('count'):
            bits.append(f"{row['count']} items" if title == "Library Item Counts" else str(row['count']))
        return bits

    range_text = "" if title == "Library Item Counts" else (f"Last {date_range} days" if date_range else "")

    p = density.picker(theme, layout)
    art_on = density.show_art(theme, layout)

    poster_w, avatar_px = _STAT_THUMB_PX.get(layout, p(_STAT_THUMB_DIGEST_EXPANDED, _STAT_THUMB_DIGEST))

    def thumb(row, i):
        if not art_on:
            return ""
        return _stat_row_thumb(row, title, msg_root, f"l-stat-{layout}-{i}-{len(msg_root.get_payload())}",
                               base_url, poster_w, avatar_px, show_cover_art, include_user_info,
                               hosted_images_enabled, hosted_base_url)

    if layout == 'spotlight':
        rows_html = ""
        for i, row in enumerate(rows):
            meta_bits = _meta_bits(row)
            plays = row.get('total_plays') if not hide_play_counts else None
            unit = 'plays' if str(plays) != '1' else 'play'
            if not plays and row.get('count'):
                plays, unit = row.get('count'), 'items' if title == "Library Item Counts" else 'total'
            rows_html += _spotlight_row(
                theme,
                thumb(row, i),
                _linked(_name(row), _row_url(row), underline=False),
                _spotlight_meta(meta_bits, plays),
                _spotlight_value(theme, plays, unit),
                last=(i == len(rows) - 1),
            )
        return _shell(layout, theme, title, rows_html, range_text)

    if layout == 'classic':
        bg_art = (rows[0].get('art') or rows[0].get('grandparent_thumb') or '') if art_on else ''
        bg_src = ""
        if bg_art:
            bg_url = bg_art if bg_art.startswith('/proxy-art') else f"/proxy-art{bg_art}"
            bg_src = fetch_and_attach_blurred_image(
                bg_url, msg_root, f"l-stat-bg-{len(msg_root.get_payload())}", base_url,
                hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url) or ""
        body_rows = ""
        for i, row in enumerate(rows):
            meta = _meta_bits(row)
            year = _year(row)
            nums = ' &middot; '.join(esc(b) for b in meta if b != year)
            body_rows += f"""
                <tr>
                    <td style="padding: {p('5px 12px', '8px 16px')}; border-top: 1px solid {theme['border']}; font-size: {p('12px', '12.5px')}; color: #ffffff; font-family: {FONT};">{thumb(row, i)}{_linked(_name(row), _row_url(row))}{f' <span style="color: {theme["muted_text"]};">({esc(year)})</span>' if year else ''}</td>
                    <td align="right" style="padding: {p('5px 12px', '8px 16px')}; border-top: 1px solid {theme['border']}; font-size: {p('12px', '12.5px')}; color: {theme['muted_text']}; white-space: nowrap; font-family: {FONT};">{nums}</td>
                </tr>
            """
        inner = f'<table width="100%" cellpadding="0" cellspacing="0" border="0">{body_rows}</table>'
        return _shell(layout, theme, title, inner, range_text, bg_src=bg_src)

    if layout == 'editorial':
        max_plays = max((int(r.get('total_plays') or r.get('count') or 0) for r in rows), default=0)
        items = ""
        for i, row in enumerate(rows, 1):
            meta = ' &middot; '.join(esc(b) for b in _meta_bits(row))
            value = int(row.get('total_plays') or row.get('count') or 0)
            pct = int(value / max_plays * 100) if max_plays else 0
            _bar_h = p('4px', '3px')
            bar = f'<div style="height: {_bar_h}; background-color: {theme["border"]}; border-radius: 2px; margin-top: {p("6px", "4px")};"><div style="height: {_bar_h}; width: {max(pct, 4)}%; background-color: {theme["primary"]}; border-radius: 2px; font-size: 0; line-height: 0;">&nbsp;</div></div>' if max_plays else ''
            items += f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                    <td width="{p('36', '30')}" valign="top" align="right" style="padding: {p('11px 16px 11px 0', '7px 14px 7px 0')}; font-size: {p('25px', '20px')}; font-weight: 800; color: {theme['primary']}; font-family: {FONT};">{i}</td>
                    <td style="padding: {p('11px 0', '7px 0')}; font-family: {FONT};">
                        <span style="color: #ffffff; font-weight: 600; font-size: {p('15.5px', '13.5px')};">{thumb(row, i)}{_linked(_name(row), _row_url(row))}</span>
                        <span style="color: {theme['muted_text']}; font-size: {p('12.5px', '11.5px')};"> {meta}</span>
                        {bar}
                    </td>
                </tr></table>
            """
        return _shell(layout, theme, title, items, range_text, overline="The charts")

    # digest
    inner = ""
    for i, row in enumerate(rows):
        year = f" ({_year(row)})" if _year(row) else ""
        meta = ' &middot; '.join(esc(b) for b in _meta_bits(row) if b != _year(row))
        inner += _digest_row(theme, f"{thumb(row, i)}{_linked(_name(row), _row_url(row))}{esc(year)}", meta)
    return _shell(layout, theme, title, inner, range_text)

# ---------------------------------------------------------------- wrapped

def _wrapped_tops(stats_data):
    def first_row(t):
        for stat in stats_data or []:
            if stat.get('stat_title') == t and stat.get('rows'):
                return stat['rows'][0]
        return None
    total = 0
    for stat in stats_data or []:
        if stat.get('stat_title') in ('Most Watched Movies', 'Most Watched TV Shows', 'Most Played Artists'):
            for row in stat.get('rows', []):
                total += int(row.get('total_plays', 0) or 0)
    return first_row('Most Watched Movies'), first_row('Most Watched TV Shows'), first_row('Most Played Artists'), first_row('Most Active Users'), total

def render_wrapped(layout, stats_data, msg_root, theme, year=None, base_url="", include_user_info=True, hosted_images_enabled=False, hosted_base_url=""):
    if not stats_data:
        return ""
    top_movie, top_show, top_artist, top_user, total_plays = _wrapped_tops(stats_data)
    display_year = year or datetime.now().year

    def icon(name):
        return email_icon_img(name, msg_root, base_url, tint='white', size=12, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

    p = density.picker(theme, layout)
    art_on = density.show_art(theme, layout)
    art_w = p(76, 56) if layout == 'editorial' else 44

    def art(row, cid, round_=False):
        if layout == 'digest' or not row or not art_on:
            return ""
        source = row.get('user_thumb') if round_ else (row.get('thumb') or row.get('grandparent_thumb'))
        if not source:
            return ""
        path = source if (round_ or source.startswith('/proxy-art')) else f"/proxy-art{source}"
        src = fetch_and_attach_small_thumbnail(path, msg_root, cid, base_url,
                                               height=round(art_w * 1.5),
                                               hosted_images_enabled=hosted_images_enabled,
                                               hosted_base_url=hosted_base_url)
        if not src:
            return ""
        if round_:
            return (f'<img src="{src}" alt="" width="{art_w}" height="{art_w}" '
                    f'style="width: {art_w}px; height: {art_w}px; border-radius: 50%; '
                    f'object-fit: cover; display: block; margin: 4px auto 5px auto;">')
        return (f'<img src="{src}" alt="" width="{art_w}" style="width: {art_w}px; height: auto; '
                f'border-radius: 4px; display: block; margin: 4px auto 5px auto;">')

    highlights = []
    if top_movie:
        highlights.append((f"{icon('film')} Top Movie", top_movie.get('title', ''), art(top_movie, 'l-wrapped-movie')))
    if top_show:
        highlights.append((f"{icon('tv')} Top Show", top_show.get('title', ''), art(top_show, 'l-wrapped-show')))
    if top_artist:
        highlights.append((f"{icon('music')} Top Artist", top_artist.get('title', ''), art(top_artist, 'l-wrapped-artist')))
    if top_user and include_user_info:
        highlights.append((f"{icon('users')} Most Active", top_user.get('user', ''), art(top_user, 'l-wrapped-user', round_=True)))
    if not highlights and not total_plays:
        return ""

    gradient = f"background: linear-gradient(135deg, {theme['accent']} 0%, {theme['primary']} 100%);"

    if layout == 'spotlight':
        cells = "".join(
            f'<td align="center" valign="top" style="padding: {p("3px 8px", "4px 12px")}; font-family: {FONT};">'
            f'<div style="font-size: 10px; font-weight: 800; letter-spacing: 1.2px; text-transform: uppercase; color: {theme["muted_text"]};">{_plain_label(label)}</div>'
            f'{art_html}<div style="padding-top: {p("3px", "4px")}; font-size: {p("12.5px", "13.5px")}; font-weight: 700; color: #ffffff;">{esc(truncate_text(value, 22))}</div></td>'
            for label, value, art_html in highlights
        )
        plays_html = (f'<div style="padding-top: 6px; font-size: 13px; color: {theme["muted_text"]};">'
                      f'~{total_plays} plays this year</div>') if total_plays else ''
        return f"""
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: {theme['card_bg']}; border: 1px solid {theme['accent']}; border-radius: 10px; border-collapse: separate; margin: 0 0 12px 0;">
                <tr><td align="center" style="padding: {p('15px 14px 13px 14px', '22px 18px 18px 18px')}; font-family: {FONT};">
                    {spotlight_eyebrow(theme, 'Year in review')}
                    <div style="padding-top: {p('4px', '6px')}; font-size: {p('30px', '40px')}; line-height: 1; font-weight: 800; color: #ffffff;">{display_year}</div>
                    {plays_html}
                    <table align="center" cellpadding="0" cellspacing="0" border="0" style="margin-top: 14px;"><tr>{cells}</tr></table>
                </td></tr>
            </table>
        """

    if layout == 'classic':
        cells = "".join(
            f'<td align="center" valign="top" style="padding: {p("5px 8px", "8px 10px")}; font-size: 11px; color: rgba(255,255,255,.92); font-family: {FONT};">{label}{art_html or "<br>"}<b style="font-size: {p("12.5px", "13px")};">{esc(value)}</b></td>'
            for label, value, art_html in highlights
        )
        inner = f"""
            <div style="{gradient} color: #ffffff; text-align: center; padding: {p('12px 14px 10px 14px', '18px 16px 14px 16px')}; font-family: {FONT};">
                <div style="font-size: 11px; letter-spacing: .18em; text-transform: uppercase; opacity: .85;">Year in Plex</div>
                <div style="font-size: {p('21px', '26px')}; font-weight: 700;">{display_year} Wrapped</div>
                {f'<div style="font-size: 12px; opacity: .85;">~{total_plays} plays this year</div>' if total_plays else ''}
                <table align="center" cellpadding="0" cellspacing="0" border="0" style="margin-top: 8px;"><tr>{cells}</tr></table>
            </div>
        """
        return f'<div style="border-radius: {p("8px", "10px")}; overflow: hidden; margin: 0 0 {p("10px", "16px")} 0; border: 1px solid {theme["border"]};">{inner}</div>'

    if layout == 'editorial':
        cells = "".join(
            f'<td align="center" valign="top" style="padding: {p("0 18px", "0 13px")}; font-size: {p("13px", "12px")}; color: rgba(255,255,255,.9); font-family: {FONT};">{label}{art_html or "<br>"}<b style="font-size: {p("15px", "13.5px")};">{esc(value)}</b></td>'
            for label, value, art_html in highlights
        )
        return f"""
            <div style="{gradient} color: #ffffff; text-align: center; padding: {p('36px', '26px')}; margin: {p('24px 0 0 0', '18px 0 0 0')}; font-family: {FONT};">
                <div style="font-size: 11px; letter-spacing: .2em; text-transform: uppercase; opacity: .8;">Year in Plex</div>
                <div style="font-size: {p('56px', '44px')}; font-weight: 800; line-height: 1;">{display_year}</div>
                {f'<div style="font-size: 12.5px; opacity: .9; margin-top: 4px;">~{total_plays} plays and counting</div>' if total_plays else ''}
                <table align="center" cellpadding="0" cellspacing="0" border="0" style="margin-top: 14px;"><tr>{cells}</tr></table>
            </div>
        """

    # digest: stat tile strip, gradient reserved for the plays tile
    tiles = ""
    if total_plays:
        tiles += f'<td style="padding-right: 8px;"><div style="{gradient} border-radius: 8px; padding: {p("13px 15px", "8px 10px")}; font-family: {FONT};"><div style="font-size: {p("10.5px", "9.5px")}; letter-spacing: .1em; text-transform: uppercase; color: #ffffff;">Plays</div><div style="color: #ffffff; font-weight: 700; font-size: {p("14.5px", "12.5px")}; margin-top: {p("4px", "2px")};">~{total_plays}</div></div></td>'
    for label, value, _art in highlights:
        plain_label = _plain_label(label)
        tiles += f'<td style="padding-right: 8px;"><div style="background-color: {theme["card_bg"]}; border: 1px solid {theme["border"]}; border-radius: 8px; padding: {p("13px 15px", "8px 10px")}; font-family: {FONT};"><div style="font-size: {p("10.5px", "9.5px")}; letter-spacing: .1em; text-transform: uppercase; color: {theme["muted_text"]};">{plain_label}</div><div style="color: #ffffff; font-weight: 700; font-size: {p("14.5px", "12.5px")}; margin-top: {p("4px", "2px")};">{esc(truncate_text(value, 18))}</div></div></td>'
    inner = f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>{tiles}</tr></table>'
    return _shell(layout, theme, f'{display_year} Wrapped', inner)

# ---------------------------------------------------------------- top viewer

def render_top_viewer(layout, row, msg_root, theme, base_url="", range_text="",
                      include_user_info=True, hosted_images_enabled=False, hosted_base_url=""):
    if not row:
        return ""
    metrics = top_viewer_metrics(row)
    if not metrics:
        return ""

    p = density.picker(theme, layout)
    label = top_viewer_heading()
    name = row.get('user') or row.get('friendly_name') or ''
    subject = name if (include_user_info and name) else ANONYMOUS_SUBJECT
    # the avatar is artwork, so it comes out in the compact densities; the
    # name itself still follows the user-info setting
    named = bool(include_user_info and name and density.show_art(theme, layout))
    avatar_px = 56 if layout != 'digest' else p(44, 30)
    avatar_src = attach_top_viewer_avatar(
        row, msg_root, base_url, size=avatar_px,
        hosted_images_enabled=hosted_images_enabled,
        hosted_base_url=hosted_base_url) if named else None
    _fit = ('display: block;' if layout != 'digest'
            else 'display: inline-block; vertical-align: middle; margin-right: 8px;')
    avatar_html = (f'<img src="{avatar_src}" alt="" width="{avatar_px}" height="{avatar_px}" '
                   f'style="width: {avatar_px}px; height: {avatar_px}px; border-radius: 50%; '
                   f'object-fit: cover; {_fit}">') if avatar_src else ''
    metrics_html = ' &middot; '.join(esc(bit) for bit in metrics)

    if layout == 'digest':
        return _shell(layout, theme, label, _digest_row(theme, f'{avatar_html}{esc(subject)}', metrics_html),
                      range_text=range_text)

    if layout == 'spotlight':
        inner = f"""
            <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                {f'<td width="{avatar_px}" valign="middle" style="padding-right: 14px;">{avatar_html}</td>' if avatar_html else ''}
                <td valign="middle" style="font-family: {FONT};">
                    <div style="font-size: {p('16px', '19px')}; font-weight: 800; color: #ffffff; line-height: 1.2;">{esc(subject)}</div>
                    <div style="padding-top: {p('3px', '4px')}; font-size: {p('11.5px', '12px')}; color: {theme['muted_text']};">{metrics_html}</div>
                </td>
            </tr></table>
        """
        return _shell(layout, theme, label, inner, range_text=range_text)

    if layout == 'editorial':
        inner = f"""
            <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                {f'<td width="{avatar_px}" valign="middle" style="padding-right: 16px;">{avatar_html}</td>' if avatar_html else ''}
                <td valign="middle" style="font-family: {FONT};">
                    <div style="font-size: {p('33px', '26px')}; font-weight: 800; color: #ffffff; line-height: 1.1;">{esc(subject)}</div>
                    <div style="padding-top: {p('8px', '5px')}; font-size: {p('13px', '12px')}; color: {theme['muted_text']};">{metrics_html}</div>
                </td>
            </tr></table>
        """
        return _shell(layout, theme, label, inner, range_text=range_text, overline="Screen time")

    # classic
    inner = f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            <td style="padding: {p('9px 12px', '14px 16px')}; font-family: {FONT};">
                <table cellpadding="0" cellspacing="0" border="0"><tr>
                    {f'<td width="{avatar_px}" valign="middle" style="padding-right: 14px;">{avatar_html}</td>' if avatar_html else ''}
                    <td valign="middle" style="font-family: {FONT};">
                        <div style="font-size: {p('15px', '18px')}; font-weight: 700; color: #ffffff; line-height: 1.2;">{esc(subject)}</div>
                        <div style="padding-top: {p('3px', '4px')}; font-size: {p('11.5px', '12px')}; color: {theme['muted_text']};">{metrics_html}</div>
                    </td>
                </tr></table>
            </td>
        </tr></table>
    """
    return _shell(layout, theme, label, inner, range_text=range_text)

# ---------------------------------------------------------------- recently added

def _ra_items(recent_data, library_filter, max_items, recently_added_mode, library_item_cap):
    items = []
    if isinstance(recent_data, list):
        for entry in recent_data:
            if isinstance(entry, dict) and 'recently_added' in entry:
                items.extend(entry['recently_added'])
            elif isinstance(entry, dict) and 'title' in entry:
                items.append(entry)
    if library_filter:
        items = [i for i in items if library_filter.lower() == i.get('library_name', '').lower()]
    if library_item_cap and len(items) > library_item_cap:
        items = items[:library_item_cap]
    elif recently_added_mode != "days" and max_items and len(items) > max_items:
        items = items[:max_items]
    return items

def _ra_poster(item, msg_root, cid, base_url, hosted_images_enabled, hosted_base_url, target=None):
    thumb = item.get('thumb') or item.get('art') or item.get('parent_thumb') or item.get('grandparent_thumb')
    if not thumb:
        return None
    proxy = thumb if thumb.startswith('/proxy-art') else f"/proxy-art{thumb if thumb.startswith('/') else '/' + thumb}"
    return fetch_and_attach_image(proxy, msg_root, cid, base_url, target=target, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

def _ra_duration(item):
    try:
        ms = int(item.get('duration') or 0)
    except (TypeError, ValueError):
        return ""
    if not ms:
        return ""
    s = round(ms / 1000)
    h, m = s // 3600, (s % 3600) // 60
    return f"{h}h {m}m" if h else f"{m}m"

# Each layout's designed treatment for recently added. A builder item may
# override it per snap-in with orientation='grid'/'list’.
_RA_NATURAL_ORIENTATION = {'classic': 'grid', 'editorial': 'list', 'digest': 'grid', 'spotlight': 'list'}

def ra_orientation(layout, orientation):
    """Resolved orientation: '' keeps the layout's own treatment."""
    if orientation in ('grid', 'list'):
        return orientation
    return _RA_NATURAL_ORIENTATION.get(layout, 'grid')

def ra_hero_index(items, hero_key):
    """Index of the builder-chosen spotlight hero. Matches on rating_key first
    (stable across pulls), then title; 0 when unset or no longer in the pull."""
    if not hero_key:
        return 0
    key = str(hero_key)
    for i, item in enumerate(items):
        if str(item.get('rating_key') or '') == key or (item.get('title') or '') == key:
            return i
    return 0

def _ra_stacked_row(theme, poster_html, title_html, meta, summary, poster_px, last=False):
    """One recently-added item as a full-width row (list orientation). Only
    the classic layout reaches this, so the picker keys off that layout."""
    p = density.picker(theme, 'classic')
    pad = p('6px', '10px')
    border = "" if last else f" border-bottom: 1px solid {theme['border']};"
    poster_cell = (f'<td width="{poster_px}" valign="top" style="padding: {pad} 14px {pad} 0;{border}">{poster_html}</td>'
                   if poster_html else '')
    return f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            {poster_cell}
            <td valign="top" style="padding: {pad} 0;{border} font-family: {FONT};">
                <div style="font-size: {p('13px', '14px')}; font-weight: 700; color: #ffffff; line-height: 1.25;">{title_html}</div>
                {f'<div style="padding-top: {p("2px", "3px")}; font-size: {p("11px", "11.5px")}; color: {theme["muted_text"]};">{meta}</div>' if meta else ''}
                {f'<div style="padding-top: {p("4px", "6px")}; font-size: {p("11.5px", "12px")}; line-height: 1.4; color: {theme["text"]};">{esc(truncate_text(summary, p(110, 180)))}</div>' if summary else ''}
            </td>
        </tr></table>
    """

def render_recently_added(layout, recent_data, msg_root, theme, library_filter=None, base_url="", max_items=None, recently_added_mode="items", ra_grid_columns=5, poster_max_height=0, show_description=True, library_item_cap=0, hosted_images_enabled=False, hosted_base_url="", orientation="", hero_key=""):
    items = _ra_items(recent_data, library_filter, max_items, recently_added_mode, library_item_cap)
    label = f"Recently Added{f' - {library_filter}' if library_filter else ''}"
    if not items:
        return _shell(layout, theme, label, _empty_state_html(theme, f"No recently added items found{f' for {esc(library_filter)}' if library_filter else ''}."))

    p = density.picker(theme, layout)
    art_on = density.show_art(theme, layout)
    # without posters a grid is just a list with borders, so the compact
    # densities always take the row treatment
    mode = ra_orientation(layout, orientation) if art_on else 'list'
    cols = density.columns(theme, layout, max(1, int(ra_grid_columns) if ra_grid_columns else 5))

    if layout == 'spotlight':
        hero_i = ra_hero_index(items, hero_key)
        hero, rest = items[hero_i], items[:hero_i] + items[hero_i + 1:]
        hero_title = hero.get('title') or hero.get('grandparent_title') or '(untitled)'
        hero_meta = ' &middot; '.join(esc(b) for b in [
            str(hero.get('year') or ''), str(hero.get('content_rating') or ''),
            _ra_duration(hero), _relative_added(hero)] if b)
        hero_summary = (hero.get('tagline') or hero.get('summary') or '') if show_description else ''
        hero_src = _ra_poster(hero, msg_root, "ld-ra-hero", base_url, hosted_images_enabled, hosted_base_url, target=(150, 225)) if art_on else None
        hero_poster = f'<img src="{hero_src}" alt="{esc(hero_title)}" width="150" style="width: 150px; height: auto; border-radius: 8px; display: block;">' if hero_src else ''
        hero_html = f"""
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: {theme['card_bg']}; border: 1px solid {theme['accent']}; border-radius: 10px; border-collapse: separate; margin: 0 0 12px 0;">
                <tr>
                    {f'<td width="150" valign="top" style="padding: 18px 0 18px 18px;">{hero_poster}</td>' if hero_poster else ''}
                    <td valign="middle" style="padding: {p('13px 14px', '18px')}; font-family: {FONT};">
                        {spotlight_eyebrow(theme, label)}
                        <div style="padding-top: {p('5px', '7px')}; font-size: {p('17px', '21px')}; line-height: 1.2; font-weight: 800; color: #ffffff;">{_linked(hero_title, hero.get('plex_url'), underline=False)}</div>
                        {f'<div style="padding-top: {p("4px", "6px")}; font-size: {p("11.5px", "12px")}; color: {theme["muted_text"]};">{hero_meta}</div>' if hero_meta else ''}
                        {f'<div style="padding-top: {p("6px", "9px")}; font-size: {p("12px", "12.5px")}; line-height: 1.45; color: {theme["text"]};">{esc(truncate_text(hero_summary, p(140, 200)))}</div>' if hero_summary else ''}
                    </td>
                </tr>
            </table>
        """
        if mode == 'grid':
            cards = []
            for i, item in enumerate(rest):
                title = item.get('title') or item.get('grandparent_title') or '(untitled)'
                sub_bits = [str(item.get('year') or item.get('grandparent_title') or item.get('parent_title') or ''), _ra_duration(item)]
                poster_src = _ra_poster(item, msg_root, f"ld-ra-{i}", base_url, hosted_images_enabled, hosted_base_url)
                cards.append(_build_card_html(theme, truncate_text(title, 23), truncate_text(' · '.join(b for b in sub_bits if b), 30), _relative_added(item), poster_src))
            inner = _grid(cards, cols)
        else:
            inner = ""
            for i, item in enumerate(rest):
                title = item.get('title') or item.get('grandparent_title') or '(untitled)'
                src = _ra_poster(item, msg_root, f"ld-ra-{i}", base_url, hosted_images_enabled, hosted_base_url, target=(42, 63)) if art_on else None
                art = f'<img src="{src}" alt="{esc(title)}" width="42" style="width: 42px; height: auto; border-radius: 5px; display: block;">' if src else ''
                meta = ' &middot; '.join(esc(b) for b in [
                    str(item.get('year') or ''), _ra_duration(item), _relative_added(item)] if b)
                inner += _spotlight_row(theme, art, _linked(title, item.get('plex_url'), underline=False), meta, "",
                                        last=(i == len(rest) - 1))
        body = _shell(layout, theme, 'Also new this week', inner) if rest else ""
        return hero_html + body

    if layout == 'classic':
        if mode == 'grid':
            cards = []
            for i, item in enumerate(items):
                title = item.get('title') or item.get('grandparent_title') or '(untitled)'
                sub_bits = [str(item.get('year') or item.get('grandparent_title') or item.get('parent_title') or ''), _ra_duration(item)]
                meta = _relative_added(item)
                poster_src = _ra_poster(item, msg_root, f"la-ra-{i}", base_url, hosted_images_enabled, hosted_base_url) if art_on else None
                cards.append(_build_card_html(theme, truncate_text(title, 23), truncate_text(' · '.join(b for b in sub_bits if b), 30), meta, poster_src, compact=not art_on))
            inner = _grid(cards, cols)
        else:
            inner = f'<div style="padding: {p("3px 12px 7px 12px", "4px 16px 10px 16px")};">'
            for i, item in enumerate(items):
                title = item.get('title') or item.get('grandparent_title') or '(untitled)'
                meta = ' &middot; '.join(esc(b) for b in [
                    str(item.get('year') or ''), str(item.get('content_rating') or ''),
                    _ra_duration(item), _relative_added(item)] if b)
                summary = (item.get('tagline') or item.get('summary') or '') if show_description else ''
                poster_src = _ra_poster(item, msg_root, f"la-ra-{i}", base_url, hosted_images_enabled, hosted_base_url, target=(60, 90)) if art_on else None
                poster_html = f'<img src="{poster_src}" alt="{esc(title)}" width="60" style="width: 60px; height: auto; border-radius: 6px; display: block;">' if poster_src else ''
                inner += _ra_stacked_row(theme, poster_html, _linked(title, item.get('plex_url'), underline=False),
                                         meta, summary, 60, last=(i == len(items) - 1))
            inner += '</div>'
        return _shell(layout, theme, label, inner)

    if layout == 'editorial':
        if mode == 'grid':
            cards = []
            for i, item in enumerate(items):
                title = item.get('title') or item.get('grandparent_title') or '(untitled)'
                sub_bits = [str(item.get('year') or item.get('grandparent_title') or item.get('parent_title') or ''), _ra_duration(item)]
                poster_src = _ra_poster(item, msg_root, f"lb-ra-{i}", base_url, hosted_images_enabled, hosted_base_url) if art_on else None
                cards.append(_build_card_html(theme, truncate_text(title, 23), truncate_text(' · '.join(b for b in sub_bits if b), 30), _relative_added(item), poster_src, compact=not art_on))
            return _shell(layout, theme, label, _grid(cards, cols), overline="New on the shelf")
        rows = ""
        for i, item in enumerate(items):
            title = item.get('title') or item.get('grandparent_title') or '(untitled)'
            meta_bits = [str(item.get('content_rating') or ''), _ra_duration(item), _relative_added(item)]
            summary = (item.get('tagline') or item.get('summary') or '') if show_description else ''
            _ra_w = p(132, 96)
            poster_src = _ra_poster(item, msg_root, f"lb-ra-{i}", base_url, hosted_images_enabled, hosted_base_url, target=(_ra_w, int(_ra_w * 1.5))) if art_on else None
            poster_html = f'<img src="{poster_src}" alt="{esc(title)}" width="{_ra_w}" style="width: {_ra_w}px; height: auto; border-radius: 6px; display: block;">' if poster_src else ''
            rows += f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                    <td width="{_ra_w}" valign="top" style="padding: 0 {p('22px', '16px')} {p('20px', '12px')} 0;">{poster_html}</td>
                    <td valign="top" style="padding-bottom: {p('20px', '12px')}; font-size: {p('13.5px', '12.5px')}; color: {theme['text']}; font-family: {FONT};">
                        <b style="color: #ffffff; font-size: {p('17px', '14px')};">{esc(title)}</b><br>
                        <span style="color: {theme['muted_text']}; font-size: {p('12px', '11px')};">{' &middot; '.join(esc(b) for b in meta_bits if b)}</span>
                        {f'<div style="margin-top: {p("9px", "6px")};">{esc(truncate_text(summary, p(320, 180)))}</div>' if summary else ''}
                    </td>
                </tr></table>
            """
        return _shell(layout, theme, label, rows, overline="New on the shelf")

    # digest: ledger rows, or a poster strip that wraps at the column count
    if mode == 'list':
        rows = ""
        for item in items:
            title = item.get('title') or item.get('grandparent_title') or '(untitled)'
            right = ' &middot; '.join(esc(b) for b in [_ra_duration(item), _relative_added(item)] if b)
            year = item.get('year')
            left = _linked(title, item.get('plex_url')) + (f' <span style="color: {theme["muted_text"]};">{esc(str(year))}</span>' if year else '')
            rows += _digest_row(theme, left, right)
        return _shell(layout, theme, label, rows)

    # The strip used to hard-stop at six posters in a single row; it now wraps
    # every item into rows of ra_grid_columns like the other grid layouts.
    cols = _effective_columns(cols, len(items))
    poster_px = max(40, min(p(112, 74), int(740 / cols) - 10))
    caption_len = max(10, int(120 / cols) + p(12, 6))
    cell_pct = f"{100 / cols:.4f}%"
    rows_html = ""
    for start in range(0, len(items), cols):
        cells = ""
        chunk = items[start:start + cols]
        for offset, item in enumerate(chunk):
            i = start + offset
            title = item.get('title') or item.get('grandparent_title') or '(untitled)'
            poster_src = _ra_poster(item, msg_root, f"lc-ra-{i}", base_url, hosted_images_enabled, hosted_base_url, target=(poster_px, int(round(poster_px * 1.5))))
            poster_html = (f'<img src="{poster_src}" alt="{esc(title)}" width="{poster_px}" style="width: 100%; max-width: {poster_px}px; height: auto; border-radius: 6px; display: block;">'
                           if poster_src else
                           f'<div style="width: 100%; max-width: {poster_px}px; height: {int(round(poster_px * 1.5))}px; background-color: {theme["card_bg"]}; border: 1px solid {theme["border"]}; border-radius: 6px;">&nbsp;</div>')
            cells += (f'<td valign="top" style="width: {cell_pct}; padding: 0 8px 10px 0;">{poster_html}'
                      f'<div style="font-size: 10px; color: {theme["muted_text"]}; max-width: {poster_px}px; padding-top: 3px; font-family: {FONT};">{esc(truncate_text(title, caption_len))}</div></td>')
        cells += "".join(f'<td style="width: {cell_pct}; padding: 0 8px 10px 0;"></td>' for _ in range(cols - len(chunk)))
        rows_html += f'<tr>{cells}</tr>'
    inner = f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="table-layout: fixed;">{rows_html}</table>'
    return _shell(layout, theme, label, inner)

def _relative_added(item):
    added = item.get('updated_at') or item.get('originally_available_at')
    if added and str(added).isdigit():
        added = datetime.fromtimestamp(int(added)).isoformat()
    rel = _relative(str(added)) if added else ""
    return f"added {rel}" if rel else ""

def _grid(cards, cols):
    # A snap-in with fewer cards than columns lays out across its own count so
    # it fills the row instead of inheriting the widest snap-in's cell width.
    cols = _effective_columns(cols, len(cards))
    rows_html = ""
    width_pct = f"{100 / cols:.4f}%"
    for i in range(0, len(cards), cols):
        row = cards[i:i + cols]
        cells = "".join(f'<td valign="top" style="width: {width_pct}; padding: 8px; font-family: {FONT};">{c}</td>' for c in row)
        cells += "".join(f'<td style="width: {width_pct}; padding: 8px;"></td>' for _ in range(cols - len(row)))
        rows_html += f'<tr>{cells}</tr>'
    return f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="table-layout: fixed;">{rows_html}</table>'

# ---------------------------------------------------------------- most watched

def render_most_watched(layout, most_watched_data, msg_root, theme, library_filter=None, base_url="", grid_columns=5, item_cap=0, range_text="", hosted_images_enabled=False, hosted_base_url=""):
    p = density.picker(theme, layout)
    art_on = density.show_art(theme, layout)
    label = most_watched_heading(library_filter)
    items = most_watched_items(most_watched_data, library_filter, item_cap)
    if not items:
        return _shell(layout, theme, label, _empty_state_html(theme, f"No most watched items found{f' for {esc(library_filter)}' if library_filter else ''}{f' ({range_text})' if range_text else ''}."), range_text=range_text)

    if layout == 'spotlight':
        rows_html = ""
        for i, item in enumerate(items):
            title = item.get('title', 'Unknown')
            src = most_watched_poster(item, msg_root, f"ld-mw-{i}", base_url,
                                      hosted_images_enabled=hosted_images_enabled,
                                      hosted_base_url=hosted_base_url, target=(42, 63)) if art_on else None
            art = f'<img src="{src}" alt="{esc(title)}" width="42" style="width: 42px; height: auto; border-radius: 5px; display: block;">' if src else ''
            plays = item.get('play_count') or 0
            rows_html += _spotlight_row(
                theme, art, _linked(title, item.get('plex_url', ''), underline=False),
                esc(str(item.get('year') or '')),
                _spotlight_value(theme, plays, 'play' if plays == 1 else 'plays'),
                last=(i == len(items) - 1))
        return _shell(layout, theme, label, rows_html, range_text=range_text)

    if layout == 'classic':
        cols = density.columns(theme, layout, max(1, int(grid_columns) if grid_columns else 5))
        cards = []
        for i, item in enumerate(items):
            title = item.get('title', 'Unknown')
            poster_src = most_watched_poster(item, msg_root, f"la-mw-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url) if art_on else None
            cards.append(_build_card_html(theme, truncate_text(title, 23), str(item.get('year') or ''), play_count_text(item), poster_src, compact=not art_on))
        return _shell(layout, theme, label, _grid(cards, cols), range_text=range_text)

    if layout == 'editorial':
        rows = ""
        for i, item in enumerate(items):
            title = item.get('title', 'Unknown')
            _mw_w = p(132, 96)
            poster_src = most_watched_poster(item, msg_root, f"lb-mw-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url, target=(_mw_w, int(_mw_w * 1.5))) if art_on else None
            poster_html = f'<img src="{poster_src}" alt="{esc(title)}" width="{_mw_w}" style="width: {_mw_w}px; height: auto; border-radius: 6px; display: block;">' if poster_src else ''
            meta_bits = [str(item.get('year') or ''), play_count_text(item)]
            rows += f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                    <td width="{_mw_w}" valign="top" style="padding: 0 {p('22px', '16px')} {p('20px', '12px')} 0;">{poster_html}</td>
                    <td valign="top" style="padding-bottom: {p('20px', '12px')}; font-size: {p('13.5px', '12.5px')}; color: {theme['text']}; font-family: {FONT};">
                        <b style="color: #ffffff; font-size: {p('17px', '14px')};">{_linked(title, item.get('plex_url', ''))}</b><br>
                        <span style="color: {theme['muted_text']}; font-size: {p('12px', '11px')};">{' &middot; '.join(esc(b) for b in meta_bits if b)}</span>
                    </td>
                </tr></table>
            """
        return _shell(layout, theme, label, rows, range_text=range_text, overline="Crowd favorites")

    # digest: ranked rows, title left / plays right
    rows = ""
    for item in items:
        rows += _digest_row(theme, _linked(item.get('title', 'Unknown'), item.get('plex_url', '')), esc(play_count_text(item)))
    return _shell(layout, theme, label, rows, range_text=range_text)

# ---------------------------------------------------------------- random pick

def render_random_pick(layout, pick, msg_root, theme, base_url="", library_label="", genre_label="", hosted_images_enabled=False, hosted_base_url="", heading=None):
    p = density.picker(theme, layout)
    art_on = density.show_art(theme, layout)
    label = heading or random_pick_heading(library_label, genre_label)
    if not pick:
        return _shell(layout, theme, label, _empty_state_html(theme, f"No random pick available{f' for {esc(library_label)}' if library_label else ''}."))

    title = pick.get('title', 'Unknown')
    meta_text = random_pick_meta_text(pick)
    summary = pick.get('tagline') or pick.get('summary', '')
    plex_url = pick.get('plex_url', '')

    if layout == 'digest':
        right = esc(meta_text) if meta_text else ''
        return _shell(layout, theme, label, _digest_row(theme, _linked(title, plex_url), right))

    poster_w = 140 if layout in _CARD_LAYOUTS else p(150, 110)
    poster_src = attach_random_pick_poster(pick, msg_root, base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url, target=(poster_w, int(poster_w * 1.5))) if art_on else None
    poster_html = f'<img src="{poster_src}" alt="{esc(title)}" width="{poster_w}" style="width: {poster_w}px; height: auto; border-radius: 8px; display: block;">' if poster_src else ''

    open_link = f'<div style="margin-top: 8px;"><a href="{esc(plex_url)}" target="_blank" style="color: {theme["primary"]}; font-size: 12px; font-weight: 700; text-decoration: underline; font-family: {FONT};">Open in Plex</a></div>' if plex_url else ''

    # This block serves classic, spotlight and editorial, whose variants pull
    # in opposite directions (classic/spotlight tighten, editorial opens up),
    # so the knobs are picked per layout rather than in one shared p() call.
    if layout in _CARD_LAYOUTS:
        cell_pad, title_px, body_px, meta_px, summary_cap = p(('9px 12px', '15px', '12px', '10.5px', 170), ('14px 16px', '17px', '12.5px', '11px', 300))
    else:
        cell_pad, title_px, body_px, meta_px, summary_cap = p(('0 0 18px 0', '21px', '13.5px', '12px', 420), ('0 0 12px 0', '17px', '12.5px', '11px', 300))

    inner = f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            {f'<td width="{poster_w}" valign="top" style="padding: {"14px 16px 14px 16px" if layout in _CARD_LAYOUTS else "0 16px 12px 0"};">{poster_html}</td>' if poster_html else ''}
            <td valign="top" style="padding: {cell_pad}; font-size: {body_px}; color: {theme['text']}; font-family: {FONT};">
                <b style="color: #ffffff; font-size: {title_px};">{_linked(title, plex_url)}</b><br>
                {f'<span style="color: {theme["muted_text"]}; font-size: {meta_px};">{esc(meta_text)}</span>' if meta_text else ''}
                {f'<div style="margin-top: 6px; line-height: 1.4;">{esc(truncate_text(summary, summary_cap))}</div>' if summary else ''}
                {open_link}
            </td>
        </tr></table>
    """
    if layout == 'editorial':
        return _shell(layout, theme, label, inner, overline="From the vault")
    return _shell(layout, theme, label, inner)

# ---------------------------------------------------------------- coming soon

def _coming_soon_view_html(layout, theme, label, events, view):
    """Calendar/agenda HTML inside this layout's section chrome, or None when
    no event carried a date to place it on."""
    def container(inner):
        if layout == 'editorial':
            return _shell(layout, theme, label, inner, overline="Mark the calendar")
        return _shell(layout, theme, label, inner)
    return render_view_html(events, theme, view, label, container=container)

def render_sonarr_coming_soon(layout, episodes, msg_root, theme, base_url="", grid_columns=5, hosted_images_enabled=False, hosted_base_url="", view="", kind="", limit=0):
    if not episodes:
        return _shell(layout, theme, "Coming Soon (TV)", _empty_state_html(theme, "No upcoming episodes found."))
    art_on = density.show_art(theme, layout)
    view = resolve_view(view)
    if view in ('calendar', 'agenda'):
        events = sonarr_events(episodes, msg_root, view, base_url, cid_prefix=f"l-cs-tv-{view}",
                               hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url,
                               with_posters=art_on, kind=kind, limit=limit)
        html = _coming_soon_view_html(layout, theme, "Coming Soon (TV)", events, view)
        if html:
            return html
        return _shell(layout, theme, "Coming Soon (TV)", _empty_state_html(theme, "No upcoming episodes found."))
    groups = sonarr_groups(episodes, kind, limit)
    if not groups:
        # Every episode was filtered out (NEWS-55), which is not the same as
        # the calendar being empty, but reads the same to the reader.
        return _shell(layout, theme, "Coming Soon (TV)", _empty_state_html(theme, "No upcoming episodes found."))

    def entry(group):
        series = group['series']
        eps = group['episodes']
        first = eps[0]
        title = series.get('title') or first.get('title', 'Unknown')
        season = group['season']
        if len(eps) >= 2:
            sub = f"Season {season} ({len(eps)} episodes)" if season is not None else f"New episodes ({len(eps)})"
        else:
            num = first.get('episodeNumber')
            sub = f"S{int(season):02d}E{int(num):02d}" if season is not None and num is not None else (first.get('title') or '')
        when = first.get('airDateUtc') or first.get('airDate')
        return title, sub, when, series, first

    if view == 'grid' or layout in _CARD_LAYOUTS:
        cards = []
        for i, group in enumerate(groups):
            title, sub, when, series, first = entry(group)
            rel = _relative(when)
            poster = _arr_poster_url(series.get('images')) or _arr_poster_url(first.get('images'))
            src = fetch_and_attach_image(_arr_poster_src(poster, '/proxy-sonarr-art'), msg_root, f"la-tv-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url) if (poster and art_on) else None
            cards.append(_build_card_html(theme, truncate_text(title, 23), truncate_text(sub, 30), f"Airs {rel}" if rel else "", src, compact=not art_on))
        return _shell(layout, theme, "Coming Soon (TV)", _grid(cards, density.columns(theme, layout, max(1, int(grid_columns or 5)))))

    rows = ""
    for group in groups:
        title, sub, when, _series, _first = entry(group)
        date_label = _short_date(when)
        if layout == 'editorial':
            rows += _dated_row(theme, date_label, title, sub)
        else:
            rows += _digest_row(theme, f"{esc(title)}{f' &middot; {esc(sub)}' if sub else ''}", date_label)
    if layout == 'editorial':
        return _shell(layout, theme, "Coming Soon (TV)", rows, overline="Mark the calendar")
    return _shell(layout, theme, "Coming Soon (TV)", rows)

def render_radarr_coming_soon(layout, movies, msg_root, theme, base_url="", grid_columns=5, hosted_images_enabled=False, hosted_base_url="", view="", limit=0):
    upcoming = radarr_upcoming(movies, limit)
    if not upcoming:
        return _shell(layout, theme, "Coming Soon (Movies)", _empty_state_html(theme, "No upcoming movies found."))

    art_on = density.show_art(theme, layout)
    view = resolve_view(view)
    if view in ('calendar', 'agenda'):
        events = radarr_events(movies, msg_root, view, base_url, cid_prefix=f"l-cs-mv-{view}",
                               hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url,
                               with_posters=art_on, limit=limit)
        html = _coming_soon_view_html(layout, theme, "Coming Soon (Movies)", events, view)
        if html:
            return html
        return _shell(layout, theme, "Coming Soon (Movies)", _empty_state_html(theme, "No upcoming movies found."))

    if view == 'grid' or layout in _CARD_LAYOUTS:
        cards = []
        for i, movie in enumerate(upcoming):
            rel = _relative(str(upcoming_release_date(movie) or ''))
            poster = _arr_poster_url(movie.get('images'))
            src = fetch_and_attach_image(_arr_poster_src(poster, '/proxy-radarr-art'), msg_root, f"la-mv-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url) if (poster and art_on) else None
            cards.append(_build_card_html(theme, truncate_text(movie.get('title', 'Unknown'), 23), str(movie.get('year') or ''), f"Releases {rel}" if rel else "", src, compact=not art_on))
        return _shell(layout, theme, "Coming Soon (Movies)", _grid(cards, density.columns(theme, layout, max(1, int(grid_columns or 5)))))

    rows = ""
    for movie in upcoming:
        date_label = _short_date(str(upcoming_release_date(movie) or ''))
        title = movie.get('title', 'Unknown')
        sub = str(movie.get('year') or '')
        if layout == 'editorial':
            rows += _dated_row(theme, date_label, title, sub)
        else:
            rows += _digest_row(theme, esc(title), date_label)
    if layout == 'editorial':
        return _shell(layout, theme, "Coming Soon (Movies)", rows, overline="Mark the calendar")
    return _shell(layout, theme, "Coming Soon (Movies)", rows)

def _short_date(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
        return dt.strftime('%b %-d')
    except Exception:
        return ""

def _dated_row(theme, date_label, title, sub):
    # editorial-only helper; its variant is the expanded (roomy) one. The
    # separator space lives inside the span: minify_email_html() collapses
    # whitespace that sits between two tags, which used to jam the title
    # against its meta text.
    p = density.picker(theme, 'editorial')
    pad = p('11px', '7px')
    return f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            <td width="64" valign="top" align="right" style="padding: {pad} 14px {pad} 0; color: {theme['primary']}; font-weight: 700; font-size: {p('13px', '12px')}; white-space: nowrap; font-family: {FONT};">{esc(date_label)}</td>
            <td style="padding: {pad} 0; font-size: {p('14.5px', '13px')}; font-family: {FONT};"><b style="color: #ffffff; font-weight: 600;">{esc(title)}</b><span style="color: {theme['muted_text']}; font-size: {p('12.5px', '11.5px')};"> {esc(sub)}</span></td>
        </tr></table>
    """

# ---------------------------------------------------------------- droppedneedle server stats

def render_dn_server(layout, server_data, theme):
    if not server_data:
        return ""
    top_artist = server_data.get('top_artist_sitewide') or {}
    top_album = server_data.get('top_album_sitewide') or {}
    leaderboard = server_data.get('leaderboard') or []
    top_listener = leaderboard[0] if leaderboard else {}
    total = server_data.get('total_listens_estimated', 0)
    listeners = server_data.get('total_users_tracked', 0)
    year = server_data.get('year', '')
    label = f"Listening Stats{f' - {year}' if year else ''}"

    p = density.picker(theme, layout)

    if layout in _CARD_LAYOUTS:
        def ledger(k, v):
            return f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                    <td style="padding: {p('5px 12px', '8px 16px')}; font-size: {p('12px', '12.5px')}; color: {theme['text']}; border-top: 1px solid {theme['border']}; font-family: {FONT};">{esc(k)}</td>
                    <td align="right" style="padding: {p('5px 12px', '8px 16px')}; font-size: {p('12px', '12.5px')}; color: {theme['muted_text']}; border-top: 1px solid {theme['border']}; font-family: {FONT};">{v}</td>
                </tr></table>
            """
        inner = ""
        if top_artist:
            inner += ledger("Top artist", f'<b style="color: #ffffff;">{esc(top_artist.get("name", ""))}</b> &middot; {top_artist.get("listen_count", 0)} plays')
        if top_album:
            inner += ledger("Top album", f'<b style="color: #ffffff;">{esc(top_album.get("name", ""))}</b> &middot; {top_album.get("listen_count", 0)}')
        if top_listener:
            inner += ledger("Top listener", f'<b style="color: #ffffff;">{esc(top_listener.get("display_name", ""))}</b>')
        inner += ledger("Server total", f'~{total} plays &middot; {listeners} listeners')
        return _shell(layout, theme, label, inner, "DroppedNeedle")

    if layout == 'editorial':
        board = ""
        for k, v in (("Top album", top_album.get('name', '')), ("Top listener", top_listener.get('display_name', '')), ("Server total", f"~{total} plays")):
            if v:
                board += f'<td align="center" style="padding: {p("0 18px", "0 12px")}; font-size: {p("13px", "12px")}; color: {theme["muted_text"]}; font-family: {FONT};">{esc(k).upper()}<br><b style="color: {theme["text"]};">{esc(str(v))}</b></td>'
        centerpiece = f"""
            <div style="text-align: center; padding: {p('12px 0 16px 0', '6px 0 10px 0')}; font-family: {FONT};">
                <div style="font-size: {p('28px', '22px')}; font-weight: 800; color: #ffffff;">{esc(top_artist.get('name', ''))}</div>
                <div style="color: {theme['muted_text']}; font-size: 12px;">artist of the moment &middot; {top_artist.get('listen_count', 0)} plays across {listeners} listeners</div>
            </div>
        """ if top_artist else ""
        inner = centerpiece + f'<table align="center" cellpadding="0" cellspacing="0" border="0"><tr>{board}</tr></table>'
        return _shell(layout, theme, "What the server listened to", inner, overline="Liner notes &middot; DroppedNeedle")

    # digest: two mini ledgers side by side
    def mini(rows):
        cells = "".join(_digest_row(theme, esc(k), esc(str(v))) for k, v in rows if v)
        return f'<div style="background-color: {theme["card_bg"]}; border: 1px solid {theme["border"]}; border-radius: 8px; padding: {p("8px 16px", "4px 12px")};">{cells}</div>'
    left = mini([("Top artist", top_artist.get('name', '')), ("Top album", truncate_text(top_album.get('name', ''), 18))])
    right = mini([("Top listener", top_listener.get('display_name', '')), ("Server plays", f"~{total}")])
    inner = f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td valign="top" width="50%" style="padding-right: 6px;">{left}</td><td valign="top" width="50%" style="padding-left: 6px;">{right}</td></tr></table>'
    return _shell(layout, theme, "Listening &middot; DroppedNeedle", inner)

# ---------------------------------------------------------------- requests

def render_requests(layout, source, data, msg_root, theme, base_url="", grid_columns=5, include_user_info=True, hosted_images_enabled=False, hosted_base_url=""):
    entries = filter_ombi_pending(data) if source == 'ombi' else filter_seerr_pending(data)
    if not entries:
        return _shell(layout, theme, "Recent Requests", _empty_state_html(theme, "No pending or approved requests found."))

    p = density.picker(theme, layout)
    art_on = density.show_art(theme, layout)

    def poster_src(entry, i):
        poster = entry.get('poster')
        if not poster or not art_on:
            return None
        url = poster if poster.startswith('http') else f"{TMDB_POSTER_BASE}{poster}"
        return fetch_and_attach_image(url, msg_root, f"l-{source}-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

    if layout in _CARD_LAYOUTS:
        cards = []
        for i, entry in enumerate(entries):
            status = "Approved" if entry['approved'] else "Pending Approval"
            rel = _relative(entry['requested_date'])
            meta = truncate_text(' · '.join(b for b in [status, f'Requested {rel}' if rel else ''] if b), 46)
            extra = truncate_text(f"Requested by {entry['requested_by']}", 46) if include_user_info and entry.get('requested_by') else None
            cards.append(_build_card_html(theme, truncate_text(entry['title'], 23), entry['year'], meta, poster_src(entry, i), extra_line=extra, compact=not art_on))
        return _shell(layout, theme, "Recent Requests", _grid(cards, density.columns(theme, layout, max(1, int(grid_columns or 5)))))

    rows = ""
    for entry in entries:
        status = "APPROVED" if entry['approved'] else "PENDING"
        rel = _relative(entry['requested_date'])
        by = f"requested by {entry['requested_by']}" if include_user_info and entry.get('requested_by') else "requested"
        if layout == 'editorial':
            rows += f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                    <td width="82" valign="top" align="right" style="padding: {p('11px', '7px')} 14px {p('11px', '7px')} 0; color: {theme['primary']}; font-weight: 700; font-size: {p('12px', '11px')}; letter-spacing: .06em; font-family: {FONT};">{status}</td>
                    <td style="padding: {p('11px', '7px')} 0; font-size: {p('14.5px', '13px')}; font-family: {FONT};"><b style="color: #ffffff; font-weight: 600;">{esc(entry['title'])}</b><span style="color: {theme['muted_text']}; font-size: {p('12.5px', '11.5px')};"> {esc(by)}{f', {rel}' if rel else ''}</span></td>
                </tr></table>
            """
        else:
            right = ' &middot; '.join(b for b in [status.lower(), esc(f"by {entry['requested_by']}") if include_user_info and entry.get('requested_by') else ''] if b)
            rows += _digest_row(theme, esc(entry['title']), right)
    if layout == 'editorial':
        return _shell(layout, theme, "Recent Requests", rows, overline="The queue")
    return _shell(layout, theme, "Requests", rows)
