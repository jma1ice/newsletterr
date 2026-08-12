from datetime import datetime, timezone, timedelta

from app.emails.builders.card_grid import effective_columns
from app.emails.images import fetch_and_attach_image, truncate_text
from app.security import escape_html_output as esc

import logging

logger = logging.getLogger(__name__)

def _relative_added(raw):
    timestamp = int(raw) if isinstance(raw, str) and raw.isdigit() else raw
    if isinstance(timestamp, (int, float)):
        dt = datetime.fromtimestamp(timestamp)
    else:
        dt = datetime.fromisoformat(str(timestamp))

    now = datetime.now()
    if dt.tzinfo:
        now = datetime.now(timezone.utc)
        dt = dt.replace(tzinfo=timezone.utc)

    diff_days = (now - dt).days
    if diff_days < 0:
        return f"in {abs(diff_days)} days"
    if diff_days == 0:
        return "today"
    if diff_days == 1:
        return "yesterday"
    return f"{diff_days} days ago"

def _added_text(item):
    if not item.get('updated_at'):
        return ""
    try:
        return _relative_added(item['updated_at'])
    except Exception:
        logger.debug("suppressed exception; using fallback", exc_info=True)
    if item.get('originally_available_at'):
        try:
            return _relative_added(item['originally_available_at'])
        except Exception:
            logger.debug("suppressed exception; using fallback", exc_info=True)
    return ""

def _duration_text(item):
    """Runtime, or the days-mode episode rollup count when the pull carries
    one (a per-episode runtime no longer applies to that card)."""
    duration = ""
    if (item.get('media_type') or item.get('type') or '').lower() == 'album':
        duration = item.get('duration') or item.get('grandparent_title') or item.get('parent_title') or 'Audio'
    elif item.get('duration'):
        try:
            s = int(item['duration']) // 1000
            h, m = s // 3600, (s % 3600) // 60
            duration = f"{h}h {m}m" if h else f"{m}m"
        except Exception:
            logger.debug("suppressed exception; using fallback", exc_info=True)

    new_ep_count = item.get('new_episode_count')
    if new_ep_count:
        try:
            n = int(new_ep_count)
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            duration = f"{n} new episode" + ("s" if n != 1 else "")
    return duration

def recently_added_title(library_filter, recently_added_mode, max_items):
    """Section heading. Days mode spells out the window it covers."""
    if recently_added_mode == "days" and max_items:
        try:
            since_date = (datetime.now() - timedelta(days=int(max_items))).strftime("%-m/%-d/%y")
            end_date = datetime.now().strftime("%-m/%-d/%y")
            date_range = f"{since_date} - {end_date}"
        except Exception:
            logger.debug("suppressed exception; using fallback", exc_info=True)
            date_range = ""
        return (f"Added to {library_filter}" if library_filter else "Recently Added") + (f" {date_range}" if date_range else "")
    return f"Recently Added{f' - {library_filter}' if library_filter else ''}"

def build_recently_added_html_with_cids(recent_data, msg_root, theme_colors, library_filter=None, base_url="", max_items=None, recently_added_mode="items", ra_grid_columns=5, poster_max_height=0, hosted_images_enabled=False, hosted_base_url="", show_description=True, library_item_cap=0, orientation=""):
    if not recent_data:
        return f"""
        <div style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
            <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">No recently added items available.</p>
        </div>
        """
    
    items = []
    if isinstance(recent_data, list):
        for item in recent_data:
            if isinstance(item, dict) and 'recently_added' in item:
                items.extend(item['recently_added'])
            elif isinstance(item, dict) and 'title' in item:
                items.append(item)
    
    if library_filter:
        items = [item for item in items if library_filter.lower() == item.get('library_name', '').lower()]

    # library_item_cap is this item's per-library override; unlike max_items
    # it also caps days mode, where max_items carries the day window instead
    if library_item_cap and len(items) > library_item_cap:
        items = items[:library_item_cap]
    elif recently_added_mode != "days" and max_items and len(items) > max_items:
        items = items[:max_items]

    if not items:
        return f"""
        <div style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
            <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">No recently added items found{f' for {esc(library_filter)}' if library_filter else ''}.</p>
        </div>
        """
    
    items_html = ""
    # orientation is the builder item's per-snap-in override: 'list' stacks the
    # items one per row, anything else keeps the poster grid.
    items_per_row = 1 if orientation == 'list' else effective_columns(ra_grid_columns, len(items))
    cell_width_pct = f"{100 / items_per_row:.4f}%"

    if orientation == 'list':
        return _build_recently_added_list_html(
            items, msg_root, theme_colors, base_url,
            recently_added_title(library_filter, recently_added_mode, max_items),
            poster_max_height, hosted_images_enabled, hosted_base_url, show_description)

    # Email-safe uniform poster box: the delivered bytes are cropped to a 2:3
    # box (see poster_target below), so `width:100%; height:auto` renders a
    # consistent aspect ratio at any column count without object-fit. The card
    # is capped to poster_px so it centers in a wider cell instead of stretching.
    _base_width = 760
    poster_px = max(60, int(_base_width / items_per_row) - 16)
    if poster_max_height:
        poster_px = min(poster_px, max(40, int(int(poster_max_height) * 2 // 3)))
    poster_target = (poster_px, int(round(poster_px * 1.5)))
    summary_len = max(40, int(420 / items_per_row))

    for i in range(0, len(items), items_per_row):
        row_items = items[i:i + items_per_row]
        row_html = '<tr class="recently-added-row">'
        
        for j, item in enumerate(row_items):
            full_title = item.get('title', 'Unknown')
            title = truncate_text(full_title, 23)
            year = item.get('year', '')
            if not year and (item.get('media_type') or item.get('type', '')).lower() == 'album':
                year = item.get('grandparent_title') or item.get('parent_title') or ''
            content_rating = item.get('content_rating', '')
            library = item.get('library_name', '')
            added_date = _added_text(item)
            duration = _duration_text(item)

            item_type = (item.get('media_type') or item.get('type') or '').lower()
            if item_type in ['episode', 'season']:
                summary = (
                    item.get('grandparent_tagline') or 
                    item.get('grandparent_summary') or 
                    item.get('parent_summary') or 
                    item.get('tagline') or 
                    item.get('summary', '')
                )
            else:
                summary = item.get('tagline') or item.get('summary', '')
            
            poster_src_result = None
            if item_type in ['episode', 'season']:
                poster_candidates = [
                    item.get('grandparent_thumb'),
                    item.get('parent_thumb'), 
                    item.get('thumb'),
                    item.get('art')
                ]
            else:
                poster_candidates = [
                    item.get('thumb'),
                    item.get('art'),
                    item.get('parent_thumb'),
                    item.get('grandparent_thumb')
                ]

            for candidate in poster_candidates:
                if candidate:
                    poster_url = f"/proxy-art{candidate}" if not candidate.startswith('/proxy-art') else candidate
                    poster_src_result = fetch_and_attach_image(
                        poster_url,
                        msg_root,
                        f"recent-{i}-{j}",
                        base_url,
                        target=poster_target,
                        hosted_images_enabled=hosted_images_enabled,
                        hosted_base_url=hosted_base_url
                    )
                    if poster_src_result:
                        break
                        
            cell_style = f"""
                width: {cell_width_pct};
                padding: 8px;
                vertical-align: top;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
            """

            plex_url = item.get('plex_url', '')

            if poster_src_result:
                poster_src = poster_src_result

                img_attrs = f'width="{poster_px}"'
                img_style = (
                    "width: 100%; height: auto; display: block; "
                    "border-radius: 10px 10px 0 0; background-color: #f8f9fa;"
                )

                meta_text = truncate_text(' • '.join(filter(None, [
                    str(year) if year else '',
                    duration,
                    content_rating,
                    f'Added {added_date}' if added_date else ''
                ])), 46)

                card_html = f"""
                    <div class="recently-added-card" style="
                        background-color: {theme_colors['card_bg']};
                        border-radius: 12px;
                        overflow: hidden;
                        border: 1px solid {theme_colors['border']};
                        width: 100%;
                        max-width: {poster_px}px;
                        margin: 0 auto;
                        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.6);
                    ">
                        <img class="card-poster-img" src="{poster_src}" alt="{esc(title)}" {img_attrs} style="{img_style}">

                        <div class="card-content" style="
                            padding: 6px;
                            background-color: {theme_colors['card_bg']};
                            color: {theme_colors['text']};
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
                            ">{esc(title)}</div>

                            <div style="
                                font-size: 10px;
                                color: {theme_colors['muted_text']};
                                margin-bottom: 2px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{esc(meta_text)}</div>

                            {f'''
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['text']};
                                opacity: 0.8;
                                line-height: 1.3;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                word-wrap: break-word;
                                overflow-wrap: break-word;
                            ">{esc(summary[:summary_len])}{'...' if len(summary) > summary_len else ''}</div>
                            ''' if (summary and show_description) else ''}
                        </div>
                    </div>
                """

                if plex_url:
                    card_html = f'''
                        <a href="{esc(plex_url)}"
                        style="text-decoration: none; color: inherit; display: block;" 
                        target="_blank"
                        title="Open in Plex">
                            {card_html}
                        </a>
                    '''
                else:
                    card_html = card_html
            else:
                card_html = f"""
                    <div style="
                        background-color: {theme_colors['card_bg']};
                        border-radius: 12px;
                        border: 1px solid {theme_colors['border']};
                        padding: 12px;
                        text-align: center;
                        max-width: {poster_px}px;
                        margin: 0 auto;
                        min-height: {poster_target[1]}px;
                    ">
                        <div style="display: table-cell; vertical-align: middle;">
                            <div style="
                                font-weight: bold;
                                font-size: 14px;
                                color: {theme_colors['text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{esc(title)}</div>
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['muted_text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{esc(' • '.join(filter(None, [str(year) if year else '', duration, library, f'Added {added_date}' if added_date else '', content_rating])))}</div>
                            {f'''
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['text']};
                                opacity: 0.8;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{esc(summary[:100])}{'...' if len(summary) > 100 else ''}</div>
                            ''' if (summary and show_description) else ''}
                        </div>
                    </div>
                """

                if plex_url:
                    card_html = f'''
                        <a href="{esc(plex_url)}"
                        style="text-decoration: none; color: inherit; display: block;" 
                        target="_blank"
                        title="Open in Plex">
                            {card_html}
                        </a>
                    '''
                else:
                    card_html = card_html
            
            row_html += f'<td class="recently-added-cell" style="{cell_style}">{card_html}</td>'
        
        while len(row_items) < items_per_row:
            row_html += f'<td class="recently-added-cell" style="width: {cell_width_pct}; padding: 8px;"></td>'
            row_items.append(None)
        
        row_html += "</tr>"
        items_html += row_html
    
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
    
    ra_title = recently_added_title(library_filter, recently_added_mode, max_items)

    return f"""
        <div style="{container_style}">
            <h2 style="{title_style}">{esc(ra_title)}</h2>
            <table class="recently-added-table" style="{table_style}">
                {items_html}
            </table>
        </div>
    """

def _build_recently_added_list_html(items, msg_root, theme_colors, base_url, ra_title, poster_max_height, hosted_images_enabled, hosted_base_url, show_description):
    """Vertical orientation: one item per row, poster left, details right."""
    poster_px = 80
    if poster_max_height:
        poster_px = min(poster_px, max(40, int(int(poster_max_height) * 2 // 3)))
    poster_target = (poster_px, int(round(poster_px * 1.5)))

    rows_html = ""
    for i, item in enumerate(items):
        title = item.get('title', 'Unknown')
        year = item.get('year', '')
        item_type = (item.get('media_type') or item.get('type') or '').lower()
        if not year and item_type == 'album':
            year = item.get('grandparent_title') or item.get('parent_title') or ''
        if item_type in ['episode', 'season']:
            summary = (item.get('grandparent_tagline') or item.get('grandparent_summary')
                       or item.get('parent_summary') or item.get('tagline') or item.get('summary', ''))
            poster_candidates = [item.get('grandparent_thumb'), item.get('parent_thumb'), item.get('thumb'), item.get('art')]
        else:
            summary = item.get('tagline') or item.get('summary', '')
            poster_candidates = [item.get('thumb'), item.get('art'), item.get('parent_thumb'), item.get('grandparent_thumb')]

        poster_src = None
        for candidate in poster_candidates:
            if candidate:
                poster_url = f"/proxy-art{candidate}" if not candidate.startswith('/proxy-art') else candidate
                poster_src = fetch_and_attach_image(poster_url, msg_root, f"recent-{i}", base_url, target=poster_target,
                                                    hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)
                if poster_src:
                    break

        meta_text = ' • '.join(filter(None, [
            str(year) if year else '',
            _duration_text(item),
            item.get('content_rating', ''),
            item.get('library_name', ''),
            f"Added {_added_text(item)}" if _added_text(item) else '',
        ]))

        poster_html = (f'<img class="card-poster-img" src="{poster_src}" alt="{esc(title)}" width="{poster_px}" '
                       f'style="width: {poster_px}px; height: auto; display: block; border-radius: 8px; background-color: #f8f9fa;">'
                       if poster_src else '')
        title_html = esc(truncate_text(title, 60))
        plex_url = item.get('plex_url', '')
        if plex_url:
            title_html = f'<a href="{esc(plex_url)}" target="_blank" style="color: inherit; text-decoration: none;" title="Open in Plex">{title_html}</a>'

        border = "" if i == len(items) - 1 else f" border-bottom: 1px solid {theme_colors['border']};"
        rows_html += f"""
            <tr class="recently-added-row">
                {f'<td class="recently-added-cell" width="{poster_px}" valign="top" style="padding: 10px 14px 10px 0;{border}">{poster_html}</td>' if poster_html else ''}
                <td class="recently-added-cell" valign="top" style="padding: 10px 0;{border} font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
                    <div style="font-weight: bold; font-size: 15px; color: {theme_colors['text']}; line-height: 1.25;">{title_html}</div>
                    {f'<div style="font-size: 11px; color: {theme_colors["muted_text"]}; padding-top: 3px;">{esc(meta_text)}</div>' if meta_text else ''}
                    {f'<div style="font-size: 12px; color: {theme_colors["text"]}; opacity: 0.8; line-height: 1.4; padding-top: 6px;">{esc(truncate_text(summary, 220))}</div>' if (summary and show_description) else ''}
                </td>
            </tr>
        """

    container_style = f"""
        background-color: {theme_colors['card_bg']};
        padding: 0 15px 10px 15px;
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
        padding-top: 10px;
        font-size: 24px;
        font-weight: bold;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    return f"""
        <div style="{container_style}">
            <h2 style="{title_style}">{esc(ra_title)}</h2>
            <table class="recently-added-table" width="100%" cellpadding="0" cellspacing="0" border="0" style="width: 100%; border-collapse: collapse;">
                {rows_html}
            </table>
        </div>
    """
