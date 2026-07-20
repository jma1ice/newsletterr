"""Email layout variants (NEWS-30): classic (A), editorial (B), digest (C).

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
)
from app.emails.builders.coming_soon import (
    _poster_url as _arr_poster_url,
    _arr_poster_src,
    group_sonarr_episodes,
    filter_radarr_upcoming,
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
from app.emails.images import fetch_and_attach_image, email_icon_img, truncate_text
from app.security import escape_html_output as esc

import logging

logger = logging.getLogger(__name__)

LAYOUTS = ('classic', 'editorial', 'digest')

FONT = "'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif"

def is_layout(layout):
    return layout in LAYOUTS

# ---------------------------------------------------------------- shells

def _shell(layout, theme, label, inner, range_text="", overline=""):
    """Per-layout section chrome around a section's inner HTML."""
    if layout == 'classic':
        range_html = f'<span style="font-weight: 500; letter-spacing: 0; text-transform: none; color: {theme["muted_text"]}; font-size: 11px;">{esc(range_text)}</span>' if range_text else ''
        return f"""
            <div style="background-color: {theme['card_bg']}; border: 1px solid {theme['border']}; border-radius: 10px; margin: 0 0 16px 0; overflow: hidden; font-family: {FONT};">
                <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                    <td style="padding: 10px 16px; font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: {theme['text']}; border-bottom: 1px solid {theme['border']}; font-family: {FONT};">{esc(label)}</td>
                    <td align="right" style="padding: 10px 16px; border-bottom: 1px solid {theme['border']};">{range_html}</td>
                </tr></table>
                {inner}
            </div>
        """
    if layout == 'editorial':
        over = overline or label
        head_range = f" &middot; {esc(range_text)}" if range_text else ""
        return f"""
            <div style="padding: 20px 0 10px 0; border-bottom: 1px solid {theme['border']}; font-family: {FONT};">
                <div style="font-size: 10.5px; letter-spacing: .18em; text-transform: uppercase; color: {theme['primary']}; font-weight: 700;">{esc(over)}{head_range}</div>
                <div style="font-size: 19px; font-weight: 700; color: #ffffff; margin: 2px 0 12px 0;">{esc(label)}</div>
                {inner}
            </div>
        """
    # digest
    range_html = f' &middot; {esc(range_text)}' if range_text else ''
    return f"""
        <div style="margin: 0 0 14px 0; font-family: {FONT};">
            <div style="font-size: 10.5px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: {theme['text']}; border-bottom: 1px solid {theme['border']}; padding-bottom: 5px; margin-bottom: 7px;">{esc(label)}{range_html}</div>
            {inner}
        </div>
    """

def _digest_row(theme, left_html, right_html):
    return f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            <td style="padding: 5px 0; border-bottom: 1px dotted {theme['border']}; font-size: 12.5px; color: #ffffff; font-family: {FONT};">{left_html}</td>
            <td align="right" style="padding: 5px 0; border-bottom: 1px dotted {theme['border']}; font-size: 12px; color: {theme['muted_text']}; white-space: nowrap; font-family: {FONT};">{right_html}</td>
        </tr></table>
    """

def _linked(title, url):
    t = esc(title)
    if url:
        return f'<a href="{esc(url)}" target="_blank" style="color: inherit; text-decoration: underline;" title="Open in Plex">{t}</a>'
    return t

# ---------------------------------------------------------------- stats

def render_stats(layout, stat_data, msg_root, theme, base_url="", date_range="", hide_play_counts=False, include_user_info=True, hosted_images_enabled=False, hosted_base_url=""):
    if not stat_data or not stat_data.get('rows'):
        return ""
    title = stat_data.get('stat_title', 'Statistics')
    rows = stat_data['rows']
    if title == "Most Active Users" and not include_user_info:
        return ""

    def _name(row):
        return row.get('title') or row.get('user') or row.get('platform') or row.get('section_name') or ''

    def _meta_bits(row):
        bits = []
        if row.get('year'):
            bits.append(str(row['year']))
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

    if layout == 'classic':
        body_rows = ""
        for row in rows:
            meta = _meta_bits(row)
            year = str(row.get('year', '')) if row.get('year') else ''
            nums = ' &middot; '.join(esc(b) for b in meta if b != year)
            body_rows += f"""
                <tr>
                    <td style="padding: 8px 16px; border-top: 1px solid {theme['border']}; font-size: 12.5px; color: #ffffff; font-family: {FONT};">{_linked(_name(row), row.get('plex_url'))}{f' <span style="color: {theme["muted_text"]};">({esc(year)})</span>' if year else ''}</td>
                    <td align="right" style="padding: 8px 16px; border-top: 1px solid {theme['border']}; font-size: 12.5px; color: {theme['muted_text']}; white-space: nowrap; font-family: {FONT};">{nums}</td>
                </tr>
            """
        inner = f'<table width="100%" cellpadding="0" cellspacing="0" border="0">{body_rows}</table>'
        return _shell(layout, theme, title, inner, range_text)

    if layout == 'editorial':
        max_plays = max((int(r.get('total_plays') or r.get('count') or 0) for r in rows), default=0)
        items = ""
        for i, row in enumerate(rows, 1):
            meta = ' &middot; '.join(esc(b) for b in _meta_bits(row))
            value = int(row.get('total_plays') or row.get('count') or 0)
            pct = int(value / max_plays * 100) if max_plays else 0
            bar = f'<div style="height: 3px; background-color: {theme["border"]}; border-radius: 2px; margin-top: 4px;"><div style="height: 3px; width: {max(pct, 4)}%; background-color: {theme["primary"]}; border-radius: 2px; font-size: 0; line-height: 0;">&nbsp;</div></div>' if max_plays else ''
            items += f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                    <td width="30" valign="top" align="right" style="padding: 7px 14px 7px 0; font-size: 20px; font-weight: 800; color: {theme['primary']}; font-family: {FONT};">{i}</td>
                    <td style="padding: 7px 0; font-family: {FONT};">
                        <span style="color: #ffffff; font-weight: 600; font-size: 13.5px;">{_linked(_name(row), row.get('plex_url'))}</span>
                        <span style="color: {theme['muted_text']}; font-size: 11.5px;"> {meta}</span>
                        {bar}
                    </td>
                </tr></table>
            """
        return _shell(layout, theme, title, items, range_text, overline="The charts")

    # digest
    inner = ""
    for row in rows:
        year = f" ({row.get('year')})" if row.get('year') else ""
        meta = ' &middot; '.join(esc(b) for b in _meta_bits(row) if str(b) != str(row.get('year', '')))
        inner += _digest_row(theme, f"{_linked(_name(row), row.get('plex_url'))}{esc(year)}", meta)
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

    highlights = []
    if top_movie:
        highlights.append((f"{icon('film')} Top Movie", top_movie.get('title', '')))
    if top_show:
        highlights.append((f"{icon('tv')} Top Show", top_show.get('title', '')))
    if top_artist:
        highlights.append((f"{icon('music')} Top Artist", top_artist.get('title', '')))
    if top_user and include_user_info:
        highlights.append((f"{icon('users')} Most Active", top_user.get('user', '')))
    if not highlights and not total_plays:
        return ""

    gradient = f"background: linear-gradient(135deg, {theme['accent']} 0%, {theme['primary']} 100%);"

    if layout == 'classic':
        cells = "".join(
            f'<td align="center" style="padding: 8px 10px; font-size: 11px; color: rgba(255,255,255,.92); font-family: {FONT};">{label}<br><b style="font-size: 13px;">{esc(value)}</b></td>'
            for label, value in highlights
        )
        inner = f"""
            <div style="{gradient} color: #ffffff; text-align: center; padding: 18px 16px 14px 16px; font-family: {FONT};">
                <div style="font-size: 11px; letter-spacing: .18em; text-transform: uppercase; opacity: .85;">Year in Plex</div>
                <div style="font-size: 26px; font-weight: 700;">{display_year} Wrapped</div>
                {f'<div style="font-size: 12px; opacity: .85;">~{total_plays} plays this year</div>' if total_plays else ''}
                <table align="center" cellpadding="0" cellspacing="0" border="0" style="margin-top: 8px;"><tr>{cells}</tr></table>
            </div>
        """
        return f'<div style="border-radius: 10px; overflow: hidden; margin: 0 0 16px 0; border: 1px solid {theme["border"]};">{inner}</div>'

    if layout == 'editorial':
        cells = "".join(
            f'<td align="center" style="padding: 0 13px; font-size: 12px; color: rgba(255,255,255,.9); font-family: {FONT};">{label}<br><b style="font-size: 13.5px;">{esc(value)}</b></td>'
            for label, value in highlights
        )
        return f"""
            <div style="{gradient} color: #ffffff; text-align: center; padding: 26px; margin: 18px 0 0 0; font-family: {FONT};">
                <div style="font-size: 11px; letter-spacing: .2em; text-transform: uppercase; opacity: .8;">Year in Plex</div>
                <div style="font-size: 44px; font-weight: 800; line-height: 1;">{display_year}</div>
                {f'<div style="font-size: 12.5px; opacity: .9; margin-top: 4px;">~{total_plays} plays and counting</div>' if total_plays else ''}
                <table align="center" cellpadding="0" cellspacing="0" border="0" style="margin-top: 14px;"><tr>{cells}</tr></table>
            </div>
        """

    # digest: stat tile strip, gradient reserved for the plays tile
    tiles = ""
    if total_plays:
        tiles += f'<td style="padding-right: 8px;"><div style="{gradient} border-radius: 8px; padding: 8px 10px; font-family: {FONT};"><div style="font-size: 9.5px; letter-spacing: .1em; text-transform: uppercase; color: #ffffff;">Plays</div><div style="color: #ffffff; font-weight: 700; font-size: 12.5px; margin-top: 2px;">~{total_plays}</div></div></td>'
    for label, value in highlights:
        plain_label = label.split('</img>')[-1].split('> ')[-1] if '<' in label else label
        tiles += f'<td style="padding-right: 8px;"><div style="background-color: {theme["card_bg"]}; border: 1px solid {theme["border"]}; border-radius: 8px; padding: 8px 10px; font-family: {FONT};"><div style="font-size: 9.5px; letter-spacing: .1em; text-transform: uppercase; color: {theme["muted_text"]};">{plain_label}</div><div style="color: #ffffff; font-weight: 700; font-size: 12.5px; margin-top: 2px;">{esc(truncate_text(value, 18))}</div></div></td>'
    inner = f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>{tiles}</tr></table>'
    return _shell(layout, theme, f'{display_year} Wrapped', inner)

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

def render_recently_added(layout, recent_data, msg_root, theme, library_filter=None, base_url="", max_items=None, recently_added_mode="items", ra_grid_columns=5, poster_max_height=0, show_description=True, library_item_cap=0, hosted_images_enabled=False, hosted_base_url=""):
    items = _ra_items(recent_data, library_filter, max_items, recently_added_mode, library_item_cap)
    label = f"Recently Added{f' - {library_filter}' if library_filter else ''}"
    if not items:
        return _shell(layout, theme, label, _empty_state_html(theme, f"No recently added items found{f' for {esc(library_filter)}' if library_filter else ''}."))

    if layout == 'classic':
        cols = max(1, int(ra_grid_columns) if ra_grid_columns else 5)
        cards = []
        for i, item in enumerate(items):
            title = item.get('title') or item.get('grandparent_title') or '(untitled)'
            sub_bits = [str(item.get('year') or item.get('grandparent_title') or item.get('parent_title') or ''), _ra_duration(item)]
            meta = _relative_added(item)
            poster_src = _ra_poster(item, msg_root, f"la-ra-{i}", base_url, hosted_images_enabled, hosted_base_url)
            cards.append(_build_card_html(theme, truncate_text(title, 23), truncate_text(' &middot; '.join(b for b in sub_bits if b), 30), meta, poster_src))
        inner = _grid(cards, cols)
        return _shell(layout, theme, label, inner)

    if layout == 'editorial':
        rows = ""
        for i, item in enumerate(items):
            title = item.get('title') or item.get('grandparent_title') or '(untitled)'
            meta_bits = [str(item.get('content_rating') or ''), _ra_duration(item), _relative_added(item)]
            summary = (item.get('tagline') or item.get('summary') or '') if show_description else ''
            poster_src = _ra_poster(item, msg_root, f"lb-ra-{i}", base_url, hosted_images_enabled, hosted_base_url, target=(96, 144))
            poster_html = f'<img src="{poster_src}" alt="{esc(title)}" width="96" style="width: 96px; height: auto; border-radius: 6px; display: block;">' if poster_src else ''
            rows += f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                    <td width="96" valign="top" style="padding: 0 16px 12px 0;">{poster_html}</td>
                    <td valign="top" style="padding-bottom: 12px; font-size: 12.5px; color: {theme['text']}; font-family: {FONT};">
                        <b style="color: #ffffff; font-size: 14px;">{esc(title)}</b><br>
                        <span style="color: {theme['muted_text']}; font-size: 11px;">{' &middot; '.join(esc(b) for b in meta_bits if b)}</span>
                        {f'<div style="margin-top: 6px;">{esc(truncate_text(summary, 180))}</div>' if summary else ''}
                    </td>
                </tr></table>
            """
        return _shell(layout, theme, label, rows, overline="New on the shelf")

    # digest: poster strip with tiny captions
    strip_items = items[:6]
    cells = ""
    for i, item in enumerate(strip_items):
        title = item.get('title') or item.get('grandparent_title') or '(untitled)'
        poster_src = _ra_poster(item, msg_root, f"lc-ra-{i}", base_url, hosted_images_enabled, hosted_base_url, target=(74, 111))
        poster_html = f'<img src="{poster_src}" alt="{esc(title)}" width="74" style="width: 74px; height: auto; border-radius: 6px; display: block;">' if poster_src else f'<div style="width: 74px; height: 111px; background-color: {theme["card_bg"]}; border: 1px solid {theme["border"]}; border-radius: 6px;">&nbsp;</div>'
        cells += f'<td valign="top" style="padding-right: 8px;">{poster_html}<div style="font-size: 10px; color: {theme["muted_text"]}; max-width: 74px; padding-top: 3px; font-family: {FONT};">{esc(truncate_text(title, 20))}</div></td>'
    inner = f'<table cellpadding="0" cellspacing="0" border="0"><tr>{cells}</tr></table>'
    return _shell(layout, theme, label, inner)

def _relative_added(item):
    added = item.get('updated_at') or item.get('originally_available_at')
    if added and str(added).isdigit():
        added = datetime.fromtimestamp(int(added)).isoformat()
    rel = _relative(str(added)) if added else ""
    return f"added {rel}" if rel else ""

def _grid(cards, cols):
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
    label = most_watched_heading(library_filter)
    items = most_watched_items(most_watched_data, library_filter, item_cap)
    if not items:
        return _shell(layout, theme, label, _empty_state_html(theme, f"No most watched items found{f' for {esc(library_filter)}' if library_filter else ''}{f' ({range_text})' if range_text else ''}."), range_text=range_text)

    if layout == 'classic':
        cols = max(1, int(grid_columns) if grid_columns else 5)
        cards = []
        for i, item in enumerate(items):
            title = item.get('title', 'Unknown')
            poster_src = most_watched_poster(item, msg_root, f"la-mw-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)
            cards.append(_build_card_html(theme, truncate_text(title, 23), str(item.get('year') or ''), play_count_text(item), poster_src))
        return _shell(layout, theme, label, _grid(cards, cols), range_text=range_text)

    if layout == 'editorial':
        rows = ""
        for i, item in enumerate(items):
            title = item.get('title', 'Unknown')
            poster_src = most_watched_poster(item, msg_root, f"lb-mw-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url, target=(96, 144))
            poster_html = f'<img src="{poster_src}" alt="{esc(title)}" width="96" style="width: 96px; height: auto; border-radius: 6px; display: block;">' if poster_src else ''
            meta_bits = [str(item.get('year') or ''), play_count_text(item)]
            rows += f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                    <td width="96" valign="top" style="padding: 0 16px 12px 0;">{poster_html}</td>
                    <td valign="top" style="padding-bottom: 12px; font-size: 12.5px; color: {theme['text']}; font-family: {FONT};">
                        <b style="color: #ffffff; font-size: 14px;">{_linked(title, item.get('plex_url', ''))}</b><br>
                        <span style="color: {theme['muted_text']}; font-size: 11px;">{' &middot; '.join(esc(b) for b in meta_bits if b)}</span>
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

def render_random_pick(layout, pick, msg_root, theme, base_url="", library_label="", genre_label="", hosted_images_enabled=False, hosted_base_url=""):
    label = random_pick_heading(library_label, genre_label)
    if not pick:
        return _shell(layout, theme, label, _empty_state_html(theme, f"No random pick available{f' for {esc(library_label)}' if library_label else ''}."))

    title = pick.get('title', 'Unknown')
    meta_text = random_pick_meta_text(pick)
    summary = pick.get('tagline') or pick.get('summary', '')
    plex_url = pick.get('plex_url', '')

    if layout == 'digest':
        right = esc(meta_text) if meta_text else ''
        return _shell(layout, theme, label, _digest_row(theme, _linked(title, plex_url), right))

    poster_w = 140 if layout == 'classic' else 110
    poster_src = attach_random_pick_poster(pick, msg_root, base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url, target=(poster_w, int(poster_w * 1.5)))
    poster_html = f'<img src="{poster_src}" alt="{esc(title)}" width="{poster_w}" style="width: {poster_w}px; height: auto; border-radius: 8px; display: block;">' if poster_src else ''

    open_link = f'<div style="margin-top: 8px;"><a href="{esc(plex_url)}" target="_blank" style="color: {theme["primary"]}; font-size: 12px; font-weight: 700; text-decoration: underline; font-family: {FONT};">Open in Plex</a></div>' if plex_url else ''

    inner = f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            {f'<td width="{poster_w}" valign="top" style="padding: {"14px 16px 14px 16px" if layout == "classic" else "0 16px 12px 0"};">{poster_html}</td>' if poster_html else ''}
            <td valign="top" style="padding: {'14px 16px' if layout == 'classic' else '0 0 12px 0'}; font-size: 12.5px; color: {theme['text']}; font-family: {FONT};">
                <b style="color: #ffffff; font-size: 17px;">{_linked(title, plex_url)}</b><br>
                {f'<span style="color: {theme["muted_text"]}; font-size: 11px;">{esc(meta_text)}</span>' if meta_text else ''}
                {f'<div style="margin-top: 6px; line-height: 1.4;">{esc(truncate_text(summary, 300))}</div>' if summary else ''}
                {open_link}
            </td>
        </tr></table>
    """
    if layout == 'editorial':
        return _shell(layout, theme, label, inner, overline="From the vault")
    return _shell(layout, theme, label, inner)

# ---------------------------------------------------------------- coming soon

def render_sonarr_coming_soon(layout, episodes, msg_root, theme, base_url="", grid_columns=5, hosted_images_enabled=False, hosted_base_url=""):
    if not episodes:
        return _shell(layout, theme, "Coming Soon (TV)", _empty_state_html(theme, "No upcoming episodes found."))
    groups = group_sonarr_episodes(episodes)

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

    if layout == 'classic':
        cards = []
        for i, group in enumerate(groups):
            title, sub, when, series, first = entry(group)
            rel = _relative(when)
            poster = _arr_poster_url(series.get('images')) or _arr_poster_url(first.get('images'))
            src = fetch_and_attach_image(_arr_poster_src(poster, '/proxy-sonarr-art'), msg_root, f"la-tv-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url) if poster else None
            cards.append(_build_card_html(theme, truncate_text(title, 23), truncate_text(sub, 30), f"Airs {rel}" if rel else "", src))
        return _shell(layout, theme, "Coming Soon (TV)", _grid(cards, max(1, int(grid_columns or 5))))

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

def render_radarr_coming_soon(layout, movies, msg_root, theme, base_url="", grid_columns=5, hosted_images_enabled=False, hosted_base_url=""):
    upcoming = filter_radarr_upcoming(movies or [])
    if not upcoming:
        return _shell(layout, theme, "Coming Soon (Movies)", _empty_state_html(theme, "No upcoming movies found."))

    if layout == 'classic':
        cards = []
        for i, movie in enumerate(upcoming):
            rel = _relative(str(upcoming_release_date(movie) or ''))
            poster = _arr_poster_url(movie.get('images'))
            src = fetch_and_attach_image(_arr_poster_src(poster, '/proxy-radarr-art'), msg_root, f"la-mv-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url) if poster else None
            cards.append(_build_card_html(theme, truncate_text(movie.get('title', 'Unknown'), 23), str(movie.get('year') or ''), f"Releases {rel}" if rel else "", src))
        return _shell(layout, theme, "Coming Soon (Movies)", _grid(cards, max(1, int(grid_columns or 5))))

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
    return f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
            <td width="64" valign="top" align="right" style="padding: 7px 14px 7px 0; color: {theme['primary']}; font-weight: 700; font-size: 12px; white-space: nowrap; font-family: {FONT};">{esc(date_label)}</td>
            <td style="padding: 7px 0; font-size: 13px; font-family: {FONT};"><b style="color: #ffffff; font-weight: 600;">{esc(title)}</b> <span style="color: {theme['muted_text']}; font-size: 11.5px;">{esc(sub)}</span></td>
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

    if layout == 'classic':
        def ledger(k, v):
            return f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                    <td style="padding: 8px 16px; font-size: 12.5px; color: {theme['text']}; border-top: 1px solid {theme['border']}; font-family: {FONT};">{esc(k)}</td>
                    <td align="right" style="padding: 8px 16px; font-size: 12.5px; color: {theme['muted_text']}; border-top: 1px solid {theme['border']}; font-family: {FONT};">{v}</td>
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
                board += f'<td align="center" style="padding: 0 12px; font-size: 12px; color: {theme["muted_text"]}; font-family: {FONT};">{esc(k).upper()}<br><b style="color: {theme["text"]};">{esc(str(v))}</b></td>'
        centerpiece = f"""
            <div style="text-align: center; padding: 6px 0 10px 0; font-family: {FONT};">
                <div style="font-size: 22px; font-weight: 800; color: #ffffff;">{esc(top_artist.get('name', ''))}</div>
                <div style="color: {theme['muted_text']}; font-size: 12px;">artist of the moment &middot; {top_artist.get('listen_count', 0)} plays across {listeners} listeners</div>
            </div>
        """ if top_artist else ""
        inner = centerpiece + f'<table align="center" cellpadding="0" cellspacing="0" border="0"><tr>{board}</tr></table>'
        return _shell(layout, theme, "What the server listened to", inner, overline="Liner notes &middot; DroppedNeedle")

    # digest: two mini ledgers side by side
    def mini(rows):
        cells = "".join(_digest_row(theme, esc(k), esc(str(v))) for k, v in rows if v)
        return f'<div style="background-color: {theme["card_bg"]}; border: 1px solid {theme["border"]}; border-radius: 8px; padding: 4px 12px;">{cells}</div>'
    left = mini([("Top artist", top_artist.get('name', '')), ("Top album", truncate_text(top_album.get('name', ''), 18))])
    right = mini([("Top listener", top_listener.get('display_name', '')), ("Server plays", f"~{total}")])
    inner = f'<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td valign="top" width="50%" style="padding-right: 6px;">{left}</td><td valign="top" width="50%" style="padding-left: 6px;">{right}</td></tr></table>'
    return _shell(layout, theme, "Listening &middot; DroppedNeedle", inner)

# ---------------------------------------------------------------- requests

def render_requests(layout, source, data, msg_root, theme, base_url="", grid_columns=5, include_user_info=True, hosted_images_enabled=False, hosted_base_url=""):
    entries = filter_ombi_pending(data) if source == 'ombi' else filter_seerr_pending(data)
    if not entries:
        return _shell(layout, theme, "Recent Requests", _empty_state_html(theme, "No pending or approved requests found."))

    def poster_src(entry, i):
        poster = entry.get('poster')
        if not poster:
            return None
        url = poster if poster.startswith('http') else f"{TMDB_POSTER_BASE}{poster}"
        return fetch_and_attach_image(url, msg_root, f"l-{source}-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

    if layout == 'classic':
        cards = []
        for i, entry in enumerate(entries):
            status = "Approved" if entry['approved'] else "Pending Approval"
            rel = _relative(entry['requested_date'])
            meta = truncate_text(' &middot; '.join(b for b in [status, f'Requested {rel}' if rel else ''] if b), 46)
            extra = truncate_text(f"Requested by {entry['requested_by']}", 46) if include_user_info and entry.get('requested_by') else None
            cards.append(_build_card_html(theme, truncate_text(entry['title'], 23), entry['year'], meta, poster_src(entry, i), extra_line=extra))
        return _shell(layout, theme, "Recent Requests", _grid(cards, max(1, int(grid_columns or 5))))

    rows = ""
    for entry in entries:
        status = "APPROVED" if entry['approved'] else "PENDING"
        rel = _relative(entry['requested_date'])
        by = f"requested by {entry['requested_by']}" if include_user_info and entry.get('requested_by') else "requested"
        if layout == 'editorial':
            rows += f"""
                <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                    <td width="82" valign="top" align="right" style="padding: 7px 14px 7px 0; color: {theme['primary']}; font-weight: 700; font-size: 11px; letter-spacing: .06em; font-family: {FONT};">{status}</td>
                    <td style="padding: 7px 0; font-size: 13px; font-family: {FONT};"><b style="color: #ffffff; font-weight: 600;">{esc(entry['title'])}</b> <span style="color: {theme['muted_text']}; font-size: 11.5px;">{esc(by)}{f', {rel}' if rel else ''}</span></td>
                </tr></table>
            """
        else:
            right = ' &middot; '.join(b for b in [status.lower(), esc(f"by {entry['requested_by']}") if include_user_info and entry.get('requested_by') else ''] if b)
            rows += _digest_row(theme, esc(entry['title']), right)
    if layout == 'editorial':
        return _shell(layout, theme, "Recent Requests", rows, overline="The queue")
    return _shell(layout, theme, "Requests", rows)
