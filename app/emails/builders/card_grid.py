# Shared card/grid HTML helpers for the Coming Soon (Sonarr/Radarr) and
# Ombi Recent Requests snap-ins, which all render the same poster-card layout.
import re
from datetime import datetime, timezone

from app.emails import density, headings
from app.security import escape_html_output as esc

import logging

logger = logging.getLogger(__name__)

def format_relative_date(date_str):
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

EMPTY_STATE_MARKER = 'data-nl-empty="1"'

def empty_state_html(theme_colors, message):
    return f"""
    <div {EMPTY_STATE_MARKER} style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
        <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">{message}</p>
    </div>
    """

MIN_AUTO_COLUMNS = 3

POSTER_BASE_WIDTH = 760

_POSTER_PCT_RE = re.compile(r'(<img class="card-poster-img"[^>]*?)width="100%"')


def poster_px_for(items_per_row):
    return max(60, int(POSTER_BASE_WIDTH / max(1, items_per_row)) - 16)


def with_poster_width(card_html, items_per_row):
    return _POSTER_PCT_RE.sub(
        lambda m: f'{m.group(1)}width="{poster_px_for(items_per_row)}"', card_html)

def effective_columns(grid_columns, item_count):
    """Columns to actually lay a snap-in out with."""
    cols = max(1, int(grid_columns) if grid_columns else 5)
    if not item_count:
        return cols
    return max(1, min(cols, max(item_count, MIN_AUTO_COLUMNS)))

def build_calendar_grid_html(cards, msg_root, theme_colors, title, base_url, grid_columns):
    p3 = density.picker3(theme_colors)
    art_on = density.show_art(theme_colors)
    items_per_row = 1 if not art_on else effective_columns(grid_columns, len(cards))
    cell_width_pct = f"{100 / items_per_row:.4f}%"

    rows_html = ""
    for i in range(0, len(cards), items_per_row):
        row_cards = cards[i:i + items_per_row]
        row_html = '<tr class="coming-soon-row nl-grid-row">'
        for card_html in row_cards:
            card_html = with_poster_width(card_html, items_per_row)
            row_html += f'<td class="coming-soon-cell" style="width: {cell_width_pct}; padding: {p3("3px 0", "8px", "10px")}; vertical-align: top; font-family: \'IBM Plex Sans\', \'Segoe UI\', Helvetica, Arial, sans-serif;">{card_html}</td>'
        for _ in range(items_per_row - len(row_cards)):
            row_html += f'<td class="coming-soon-cell" style="width: {cell_width_pct}; padding: {p3("3px 0", "8px", "10px")};"></td>'
        row_html += "</tr>"
        rows_html += row_html

    container_style = f"""
        background-color: {theme_colors['card_bg']};
        padding-bottom: {p3('10px', '10px', '14px')};{' padding-left: 14px; padding-right: 14px;' if not art_on else ''}
        border-radius: 8px;
        margin: {p3('10px 0', '20px 0', '28px 0')};
        border: 1px solid {theme_colors['border']};
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
        overflow: hidden;
        max-width: 100%;
    """
    title_style = f"""
        text-align: center;
        color: {theme_colors['text']};
        margin: {p3('6px 0', '0 0 10px 0', '0 0 14px 0')};
        font-size: {p3('17px', '24px', '30px')};
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

    title = headings.resolve(theme_colors, title)
    title_html = f'<h2 style="{title_style}">{esc(title)}</h2>' if title else ''

    return f"""
        <div style="{container_style}">
            {title_html}
            <table class="coming-soon-table nl-grid" style="{table_style}">
                {rows_html}
            </table>
        </div>
    """

def build_card_html(theme_colors, title, subtitle, meta_text, poster_src, extra_line=None, compact=False):
    title, subtitle, meta_text = esc(title), esc(subtitle), esc(meta_text)
    extra_line = esc(extra_line) if extra_line else None
    if poster_src:
        poster_html = f'<img class="card-poster-img" src="{poster_src}" alt="{title}" width="100%" style="width: 100%; height: auto; display: block; object-fit: cover; border-radius: 10px 10px 0 0; background-color: #f8f9fa;">'
    else:
        poster_html = ""

    return f"""
        <div class="coming-soon-card nl-grid-card" style="
            background-color: {theme_colors['card_bg']};
            border-radius: {'8px' if compact else '12px'};
            overflow: hidden;
            border: 1px solid {theme_colors['border']};
            width: 100%;
            margin: 0 auto;
            box-shadow: {'none' if compact else '0 6px 18px rgba(0, 0, 0, 0.6)'};
        ">
            {poster_html}
            <div class="card-content" style="
                padding: {'5px 9px' if compact else '6px'};
                background-color: {theme_colors['card_bg']};
                color: {theme_colors['text']};
                min-height: {'0' if compact else '60px'};
            ">
                <div style="
                    font-weight: bold;
                    font-size: {'13px' if compact else '14px'};
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
                {f'''
                <div style="
                    font-size: 10px;
                    color: {theme_colors['muted_text']};
                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                ">{extra_line}</div>
                ''' if extra_line else ''}
            </div>
        </div>
    """
