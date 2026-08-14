from datetime import datetime

from app.cache import get_cache_info
from app.emails import density, headings
from app.emails.images import fetch_and_attach_blurred_image, fetch_and_attach_small_thumbnail, email_icon_img
from app.security import escape_html_output as esc

import logging

logger = logging.getLogger(__name__)

def get_stat_headers(title, hide_play_counts=False):
    if title == "Most Watched Movies" or title == "Most Watched TV Shows":
        headers = ["Title", "Year", "Plays", "Hours Played", "Cert.", "Score"]
    elif title == "Most Popular Movies" or title == "Most Popular TV Shows":
        headers = ["Title", "Year", "Plays", "Users", "Cert.", "Score"]
    elif title == "Most Played Artists":
        headers = ["Author", "Year", "Plays", "Hours Played"]
    elif title == "Most Popular Artists":
        headers = ["Author", "Year", "Plays", "Users"]
    elif title == "Recently Watched":
        headers = ["Title", "Year", "Cert.", "Score"]
    elif title == "Most Active Libraries":
        headers = ["Library", "Plays", "Hours Played"]
    elif title == "Library Item Counts":
        headers = ["Library", "Item Count"]
    elif title == "Most Active Users":
        headers = ["Username", "Plays", "Hours Played"]
    elif title == "Most Active Platforms":
        headers = ["Platform", "Plays", "Hours Played"]
    elif title == "Most Concurrent Streams":
        headers = ["Category", "Count"]
    else:
        headers = ["Title", "Value"]
    if hide_play_counts:
        headers = [h for h in headers if h != "Plays"]
    return headers

def get_stat_cells(title, row, hide_play_counts=False):
    cells = []

    if title == "Most Active Libraries" or title == "Library Item Counts":
        cells.append(esc(row.get('section_name', '')))
    elif title == "Most Active Users":
        cells.append(esc(row.get('user', '')))
    elif title == "Most Active Platforms":
        cells.append(esc(row.get('platform', '')))
    else:
        title_cell = esc(row.get('title', ''))
        if row.get('plex_url'):
            title_cell = f'<a href="{esc(row["plex_url"])}" style="color: inherit; text-decoration: underline;" target="_blank" title="Open in Plex">{title_cell}</a>'
        cells.append(title_cell)

    skip_year_stats = ["Most Active Libraries", "Library Item Counts", "Most Active Users", "Most Active Platforms", "Most Concurrent Streams"]
    if title not in skip_year_stats:
        cells.append(esc(str(row.get('year', ''))))

    skip_plays_stats = ["Library Item Counts"]
    if "Recently" not in title and "Concurrent" not in title and title not in skip_plays_stats and not hide_play_counts:
        cells.append(row.get('total_plays', 0))

    hours_stats = ["Most Watched Movies", "Most Watched TV Shows", "Most Played Artists", "Most Active Libraries", "Most Active Users", "Most Active Platforms"]
    users_stats = ["Most Popular Movies", "Most Popular TV Shows", "Most Popular Artists"]

    if title in hours_stats:
        hours = round(row.get('total_duration', 0) / 3600) if row.get('total_duration') else 0
        cells.append(int(hours))
    elif title in users_stats:
        cells.append(row.get('users_watched', ''))

    skip_rating_stats = ["Most Active Libraries", "Library Item Counts", "Most Played Artists", "Most Popular Artists", "Most Active Users", "Most Active Platforms", "Most Concurrent Streams"]
    if title not in skip_rating_stats:
        cells.append(esc(str(row.get('content_rating', ''))))
        rating = row.get('rating')
        cells.append(esc(f"{rating}") if rating else 'NA')

    if title == "Most Concurrent Streams":
        cells.append(row.get('count', 0))
    elif title == "Library Item Counts":
        cells.append(row.get('count', 0))

    return cells

def build_stats_html_with_cid_background(stat_data, msg_root, theme_colors, base_url="", date_range="", hide_play_counts=False, show_cover_art=False, include_user_info=True, hosted_images_enabled=False, hosted_base_url=""):
    if not stat_data or not stat_data.get('rows'):
        return ""

    title = stat_data.get('stat_title', 'Statistics')
    rows = stat_data['rows']

    # user-info toggle: the Most Active Users stat names other users; drop it
    # server-side regardless of what a template selected
    if title == "Most Active Users" and not include_user_info:
        return ""

    p = density.picker(theme_colors)
    art_on = density.show_art(theme_colors)

    background_src = None
    if art_on and rows and (rows[0].get('art') or rows[0].get('grandparent_thumb')):
        artwork_path = rows[0].get('art') or rows[0].get('grandparent_thumb')
        if artwork_path:
            image_url = f"/proxy-art{artwork_path}" if not artwork_path.startswith('/proxy-art') else artwork_path
            background_src = fetch_and_attach_blurred_image(
                image_url,
                msg_root,
                f"stat-bg-{len(msg_root.get_payload())}",
                base_url,
                hosted_images_enabled=hosted_images_enabled,
                hosted_base_url=hosted_base_url
            )
    
    headers = get_stat_headers(title, hide_play_counts=hide_play_counts)
    header_cells = "".join([
        f'<th style="padding: {p("7px 9px", "12px")}; background-color: rgba(52, 58, 64, 0.9); color: white; font-weight: bold; border: none; font-family: \'IBM Plex Sans\', \'Segoe UI\', Helvetica, Arial, sans-serif; font-size: 14px; text-align: left;">{h}</th>'
        for h in headers
    ])

    _COVER_ART_TYPES = {
        "Most Watched Movies", "Most Watched TV Shows",
        "Most Popular Movies", "Most Popular TV Shows",
        "Most Played Artists", "Most Popular Artists",
        "Recently Watched"
    }
    apply_cover_art = show_cover_art and art_on and title in _COVER_ART_TYPES

    rows_html = ""
    for row in rows:
        cells = get_stat_cells(title, row, hide_play_counts=hide_play_counts)
        if title == "Most Active Users" and include_user_info:
            thumb_url = (row.get('user_thumb') or '') if art_on else ''
            if thumb_url:
                avatar_src = fetch_and_attach_small_thumbnail(thumb_url, msg_root, f"user-avatar-{len(msg_root.get_payload())}", base_url, height=38, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)
                if avatar_src:
                    cells[0] = f'<img src="{avatar_src}" width="32" height="32" style="width:32px;max-width:32px;height:32px;border-radius:50%;object-fit:cover;margin-right:7px;vertical-align:middle;">{cells[0]}'
        if apply_cover_art:
            thumb_path = row.get('thumb', '') or row.get('grandparent_thumb', '')
            if thumb_path:
                proxy_path = f"/proxy-art{thumb_path}" if not thumb_path.startswith('/proxy-art') else thumb_path
                thumb_src = fetch_and_attach_small_thumbnail(proxy_path, msg_root, f"stat-thumb-{len(msg_root.get_payload())}", base_url, height=38, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)
                if thumb_src:
                    # Sized by width, not height: the head CSS carries
                    # img { height: auto !important }, so the old inline pixel
                    # height was ignored and the preview (which points at the
                    # full-size source rather than the resized attachment)
                    # rendered these posters at their natural size.
                    cells[0] = f'<img src="{thumb_src}" width="25" style="width:25px;max-width:25px;height:auto;border-radius:3px;margin-right:7px;vertical-align:middle;">{cells[0]}'
        cells_html = "".join([
            f'<td style="padding: {p("7px 9px", "12px")}; background-color: rgba(255, 255, 255, 0.5); color: #333; border-bottom: 1px solid rgba(222, 226, 230, 0.8); font-family: \'IBM Plex Sans\', \'Segoe UI\', Helvetica, Arial, sans-serif; font-size: 14px;">{cell}</td>'
            for cell in cells
        ])
        rows_html += f'<tr>{cells_html}</tr>'
    
    container_style = f"""
        margin: {p('10px 0', '20px 0')};
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        border: 1px solid {theme_colors['border']};
        position: relative;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    if background_src:
        container_style += f"""
            background-image: url('{background_src}');
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
        """
    else:
        container_style += f"background-color: {theme_colors['card_bg']};"

    overlay = ""
    if background_src:
        overlay = f"""
            <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; 
                        background-color: rgba(0, 0, 0, 0.3); z-index: 0;"></div>
        """
    
    header_style = f"""
        background-color: {theme_colors['primary']};
        color: white;
        padding: {p('9px 12px', '15px')};
        text-align: center;
        font-weight: bold;
        font-size: {p('14px', '18px')};
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
        margin: 0;
        position: relative;
        z-index: 2;
    """
    
    table_style = """
        width: 100%;
        border-collapse: collapse;
        position: relative;
        z-index: 2;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """

    if date_range == "":
        date_range = get_cache_info('stats')['params']['time_range']

    date_suffix = "" if title == "Library Item Counts" else f" - Last {date_range} days"

    # A per-item override replaces the whole header, date suffix included:
    # someone naming the section themselves does not want " - Last 7 days"
    # appended to it. date_suffix is generated text with nothing to escape, so
    # escaping the joined string matches the previous bytes exactly.
    header_text = headings.resolve(theme_colors, f"{title}{date_suffix}")
    header_html = f'<div style="{header_style}">{esc(header_text)}</div>' if header_text else ''

    return f"""
        <div style="{container_style}">
            {overlay}
            <div style="position: relative; z-index: 1;">
                {header_html}
                <table style="{table_style}">
                    <thead>
                        <tr>{header_cells}</tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </div>
    """

def build_yearly_wrapped_html_with_cids(stats_data, msg_root, theme_colors, year=None, base_url="", include_user_info=True, hosted_images_enabled=False, hosted_base_url=""):
    if not stats_data:
        return ""

    def _first_row(title):
        for stat in stats_data:
            if stat.get('stat_title') == title and stat.get('rows'):
                return stat['rows'][0]
        return None

    top_movie = _first_row('Most Watched Movies')
    top_show = _first_row('Most Watched TV Shows')
    top_artist = _first_row('Most Played Artists')
    top_user = _first_row('Most Active Users')

    total_plays = 0
    for stat in stats_data:
        if stat.get('stat_title') in ('Most Watched Movies', 'Most Watched TV Shows', 'Most Played Artists'):
            for row in stat.get('rows', []):
                total_plays += int(row.get('total_plays', 0) or 0)

    p = density.picker(theme_colors)
    art_on = density.show_art(theme_colors)

    def _thumb_src(row, cid_name):
        thumb_path = row.get('thumb') or row.get('grandparent_thumb')
        if not thumb_path or not art_on:
            return None
        proxy_path = f"/proxy-art{thumb_path}" if not thumb_path.startswith('/proxy-art') else thumb_path
        return fetch_and_attach_small_thumbnail(proxy_path, msg_root, cid_name, base_url, height=60, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

    # White icon tint: the wrapped card sits on the primary->accent gradient
    def _hl_icon(name):
        return email_icon_img(name, msg_root, base_url, tint='white', size=12, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

    highlights = []
    if top_movie:
        highlights.append((f"{_hl_icon('film')} Top Movie", top_movie.get('title', ''), _thumb_src(top_movie, 'wrapped-movie'), False))
    if top_show:
        highlights.append((f"{_hl_icon('tv')} Top Show", top_show.get('title', ''), _thumb_src(top_show, 'wrapped-show'), False))
    if top_artist:
        highlights.append((f"{_hl_icon('music')} Top Artist", top_artist.get('title', ''), _thumb_src(top_artist, 'wrapped-artist'), False))
    if top_user and include_user_info:
        # user_thumb is an absolute plex.tv avatar URL; small-thumbnail fetch
        # handles http URLs directly (round style variant)
        user_thumb = (top_user.get('user_thumb') or '') if art_on else ''
        user_avatar = fetch_and_attach_small_thumbnail(user_thumb, msg_root, 'wrapped-user', base_url, height=60, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url) if user_thumb else None
        highlights.append((f"{_hl_icon('users')} Most Active", top_user.get('user', ''), user_avatar, True))

    if not highlights and not total_plays:
        return ""

    def _wrapped_thumb_html(thumb_src, value, is_round):
        if not thumb_src:
            return ''
        if is_round:
            return (f'<img src="{thumb_src}" alt="{esc(value)}" width="60" height="60" '
                    f'style="height:60px;width:60px;border-radius:50%;object-fit:cover;'
                    f'display:block;margin:0 auto 6px;">')
        return (f'<img src="{thumb_src}" alt="{esc(value)}" width="40" '
                f'style="width:40px;max-width:40px;height:auto;border-radius:4px;'
                f'display:block;margin:0 auto 6px;">')

    # The img is placed immediately before the value div so a missing thumbnail
    # leaves no stray whitespace (keeps the thumb-less golden byte-for-byte stable).
    highlight_cells = "".join([
        f"""
        <td style="text-align: center; padding: {p('7px', '12px')}; vertical-align: top; width: {100 // max(len(highlights), 1)}%;">
            <div style="font-size: {p('11px', '12px')}; color: {theme_colors['muted_text']}; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: {p('2px', '4px')};">{label}</div>
            {_wrapped_thumb_html(thumb_src, value, is_round)}<div style="font-size: 15px; font-weight: bold; color: white; line-height: 1.3;">{esc(value)}</div>
        </td>
        """
        for label, value, thumb_src, is_round in highlights
    ])

    display_year = year or datetime.now().year

    container_style = f"""
        margin: {p('10px 0', '20px 0')};
        border-radius: 12px;
        overflow: hidden;
        background: linear-gradient(135deg, {theme_colors['primary']} 0%, {theme_colors['accent']} 100%);
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    """

    return f"""
        <div style="{container_style}">
            <div style="padding: {p('12px 14px 3px 14px', '20px 20px 4px 20px')}; text-align: center;">
                <div style="font-size: {p('11.5px', '13px')}; color: rgba(255,255,255,0.85); text-transform: uppercase; letter-spacing: 0.1em;">Year in Plex</div>
                <div style="font-size: {p('20px', '26px')}; font-weight: bold; color: white; margin: {p('2px 0', '4px 0 4px 0')};">{display_year} Wrapped</div>
                {f'<div style="font-size: 14px; color: rgba(255,255,255,0.9); margin-bottom: 8px;">~{total_plays} plays this year</div>' if total_plays else ''}
            </div>
            <table cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>{highlight_cells}</tr>
            </table>
        </div>
    """
