# Shared card/grid HTML helpers for the Coming Soon (Sonarr/Radarr) and
# Ombi Recent Requests snap-ins, which all render the same poster-card layout.
from datetime import datetime, timezone

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

def empty_state_html(theme_colors, message):
    return f"""
    <div style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
        <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">{message}</p>
    </div>
    """

def build_calendar_grid_html(cards, msg_root, theme_colors, title, base_url, grid_columns):
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

def build_card_html(theme_colors, title, subtitle, meta_text, poster_src):
    title, subtitle, meta_text = esc(title), esc(subtitle), esc(meta_text)
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
