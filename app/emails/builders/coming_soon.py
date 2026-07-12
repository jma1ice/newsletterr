# Kept in sync by hand with buildSonarrComingSoonPreviewHTML/
# buildRadarrComingSoonPreviewHTML in static/js/app/04-stats-graphs.js.
from datetime import datetime, timezone

from app.emails.images import fetch_and_attach_image, truncate_text

import logging

logger = logging.getLogger(__name__)

def _poster_url(images):
    for img in images or []:
        if img.get('coverType') == 'poster' and img.get('url'):
            return img['url']
    for img in images or []:
        if img.get('url'):
            return img['url']
    return None

def _format_relative_date(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
        now = datetime.now(timezone.utc) if dt.tzinfo else datetime.now()
        diff_days = (dt.date() - now.date()).days
        if diff_days == 0:
            return "today"
        elif diff_days == 1:
            return "tomorrow"
        elif diff_days > 1:
            return f"in {diff_days} days"
        elif diff_days == -1:
            return "yesterday"
        else:
            return f"{abs(diff_days)} days ago"
    except Exception:
        logger.debug("suppressed exception; using fallback", exc_info=True)
        return ""

def _empty_state_html(theme_colors, message):
    return f"""
    <div style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
        <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">{message}</p>
    </div>
    """

def _build_calendar_grid_html(cards, msg_root, theme_colors, title, base_url, grid_columns):
    items_per_row = max(1, int(grid_columns) if grid_columns else 5)
    cell_width_pct = f"{100 / items_per_row:.4f}%"

    rows_html = ""
    for i in range(0, len(cards), items_per_row):
        row_cards = cards[i:i + items_per_row]
        row_html = '<tr class="coming-soon-row">'
        for card_html in row_cards:
            row_html += f'<td class="coming-soon-cell" style="width: {cell_width_pct}; padding: 8px; vertical-align: top; font-family: \'IBM Plex Sans\', \'Segoe UI\', Helvetica, Arial, sans-serif;">{card_html}</td>'
        for _ in range(items_per_row - len(row_cards)):
            row_html += f'<td class="coming-soon-cell" style="width: {cell_width_pct}; padding: 8px;"></td>'
        row_html += "</tr>"
        rows_html += row_html

    container_style = f"""
        background-color: {theme_colors['card_bg']};
        padding-bottom: 10px;
        border-radius: 8px;
        margin: 20px 0;
        border: 1px solid {theme_colors['border']};
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
        overflow: hidden;
        max-width: 100%;
    """
    title_style = f"""
        text-align: center;
        color: {theme_colors['text']};
        margin: 0 0 10px 0;
        font-size: 24px;
        font-weight: bold;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    table_style = """
        width: 100%;
        border-collapse: collapse;
        margin: 0;
        padding: 0;
        table-layout: fixed;
    """

    return f"""
        <div style="{container_style}">
            <h2 style="{title_style}">{title}</h2>
            <table class="coming-soon-table" style="{table_style}">
                {rows_html}
            </table>
        </div>
    """

def _build_card_html(theme_colors, title, subtitle, meta_text, poster_src):
    if poster_src:
        poster_html = f'<img class="card-poster-img" src="{poster_src}" alt="{title}" width="100%" style="width: 100%; height: auto; display: block; object-fit: cover; border-radius: 10px 10px 0 0; background-color: #f8f9fa;">'
    else:
        poster_html = ""

    return f"""
        <div class="coming-soon-card" style="
            background-color: {theme_colors['card_bg']};
            border-radius: 12px;
            overflow: hidden;
            border: 1px solid {theme_colors['border']};
            width: 100%;
            margin: 0 auto;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.6);
        ">
            {poster_html}
            <div class="card-content" style="
                padding: 6px;
                background-color: {theme_colors['card_bg']};
                color: {theme_colors['text']};
                min-height: 60px;
            ">
                <div style="
                    font-weight: bold;
                    font-size: 14px;
                    color: {theme_colors['text']};
                    margin-bottom: 1px;
                    line-height: 1.2;
                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                    word-wrap: break-word;
                    overflow-wrap: break-word;
                ">{title}</div>
                {f'''
                <div style="
                    font-size: 11px;
                    color: {theme_colors['text']};
                    opacity: 0.85;
                    margin-bottom: 2px;
                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                ">{subtitle}</div>
                ''' if subtitle else ''}
                <div style="
                    font-size: 10px;
                    color: {theme_colors['muted_text']};
                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                ">{meta_text}</div>
            </div>
        </div>
    """

def build_sonarr_coming_soon_html_with_cids(episodes, msg_root, theme_colors, base_url="", grid_columns=5, hosted_images_enabled=False, hosted_base_url=""):
    if not episodes:
        return _empty_state_html(theme_colors, "No upcoming episodes found.")

    cards = []
    for i, ep in enumerate(episodes):
        series = ep.get('series') or {}
        series_title = series.get('title') or ep.get('title', 'Unknown')
        season = ep.get('seasonNumber')
        episode_num = ep.get('episodeNumber')
        se_label = f"S{int(season):02d}E{int(episode_num):02d}" if season is not None and episode_num is not None else ""
        episode_title = ep.get('title', '')
        air_date = ep.get('airDateUtc') or ep.get('airDate')
        relative = _format_relative_date(air_date)

        poster = _poster_url(series.get('images')) or _poster_url(ep.get('images'))
        poster_src = None
        if poster:
            poster_url = f"/proxy-sonarr-art{poster}" if not poster.startswith('/proxy-sonarr-art') else poster
            poster_src = fetch_and_attach_image(poster_url, msg_root, f"sonarr-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

        subtitle = truncate_text(' - '.join(filter(None, [se_label, episode_title])), 40)
        meta_text = truncate_text(' • '.join(filter(None, [f'Airs {relative}' if relative else ''])), 46)

        cards.append(_build_card_html(theme_colors, truncate_text(series_title, 23), subtitle, meta_text, poster_src))

    return _build_calendar_grid_html(cards, msg_root, theme_colors, "Coming Soon (TV)", base_url, grid_columns)

def build_radarr_coming_soon_html_with_cids(movies, msg_root, theme_colors, base_url="", grid_columns=5, hosted_images_enabled=False, hosted_base_url=""):
    if not movies:
        return _empty_state_html(theme_colors, "No upcoming movies found.")

    cards = []
    for i, movie in enumerate(movies):
        title = movie.get('title', 'Unknown')
        year = movie.get('year', '')
        release_date = movie.get('digitalRelease') or movie.get('physicalRelease') or movie.get('inCinemas')
        relative = _format_relative_date(release_date)

        poster = _poster_url(movie.get('images'))
        poster_src = None
        if poster:
            poster_url = f"/proxy-radarr-art{poster}" if not poster.startswith('/proxy-radarr-art') else poster
            poster_src = fetch_and_attach_image(poster_url, msg_root, f"radarr-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

        subtitle = str(year) if year else ""
        meta_text = truncate_text(' • '.join(filter(None, [f'Releases {relative}' if relative else ''])), 46)

        cards.append(_build_card_html(theme_colors, truncate_text(title, 23), subtitle, meta_text, poster_src))

    return _build_calendar_grid_html(cards, msg_root, theme_colors, "Coming Soon (Movies)", base_url, grid_columns)
