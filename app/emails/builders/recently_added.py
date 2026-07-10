from datetime import datetime, timezone, timedelta

from app.emails.images import fetch_and_attach_image, truncate_text

import logging

logger = logging.getLogger(__name__)

def build_recently_added_html_with_cids(recent_data, msg_root, theme_colors, library_filter=None, base_url="", max_items=None, recently_added_mode="items", ra_grid_columns=5, poster_max_height=0):
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
        items = [item for item in items if library_filter.lower() in item.get('library_name', '').lower()]

    if recently_added_mode != "days" and max_items and len(items) > max_items:
        items = items[:max_items]

    if not items:
        return f"""
        <div style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
            <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">No recently added items found{f' for {library_filter}' if library_filter else ''}.</p>
        </div>
        """
    
    items_html = ""
    items_per_row = max(1, int(ra_grid_columns) if ra_grid_columns else 5)
    cell_width_pct = f"{100 / items_per_row:.4f}%"

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
            added_date = ""
            duration = ""

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
            
            poster_cid = None
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
                    poster_cid = fetch_and_attach_image(
                        poster_url,
                        msg_root,
                        f"recent-{i}-{j}",
                        base_url,
                        max_height=poster_max_height if poster_max_height else None
                    )
                    if poster_cid:
                        break
                        
            if item.get('updated_at'):
                try:
                    timestamp = item['updated_at']
                    if isinstance(timestamp, str) and timestamp.isdigit():
                        timestamp = int(timestamp)
                    
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
                        added_date = f"in {abs(diff_days)} days"
                    elif diff_days == 0:
                        added_date = "today"
                    elif diff_days == 1:
                        added_date = "yesterday"
                    else:
                        added_date = f"{diff_days} days ago"

                except Exception as e:
                    logger.debug("suppressed exception; using fallback", exc_info=True)
                    if item.get('originally_available_at'):
                        try:
                            timestamp = item['originally_available_at']
                            if isinstance(timestamp, str) and timestamp.isdigit():
                                timestamp = int(timestamp)
                            
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
                                added_date = f"in {abs(diff_days)} days"
                            elif diff_days == 0:
                                added_date = "today"
                            elif diff_days == 1:
                                added_date = "yesterday"
                            else:
                                added_date = f"{diff_days} days ago"

                        except Exception as e2:
                            logger.debug("suppressed exception; using fallback", exc_info=True)
                            added_date = ""
            
            if item_type == 'album':
                duration = item.get('duration') or item.get('grandparent_title') or item.get('parent_title') or 'Audio'
            else:
                if item.get('duration'):
                    try:
                        ms = int(item['duration'])
                        s = ms // 1000
                        h = s // 3600
                        m = (s % 3600) // 60
                        duration = f"{h}h {m}m" if h else f"{m}m"
                    except:
                        logger.debug("suppressed exception; using fallback", exc_info=True)
                        pass
            
            cell_style = f"""
                width: {cell_width_pct};
                padding: 8px;
                vertical-align: top;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
            """

            plex_url = item.get('plex_url', '')

            if poster_cid:
                poster_src = f"cid:{poster_cid}"

                img_attrs = 'width="100%"'
                img_style = "width: 100%; height: auto; display: block; object-fit: cover; border-radius: 10px 10px 0 0; background-color: #f8f9fa;"
                if poster_max_height:
                    img_attrs = f'width="100%" height="{poster_max_height}"'
                    img_style = (
                        f"width: 100%; height: {poster_max_height}px; display: block; object-fit: cover; "
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
                        margin: 0 auto;
                        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.6);
                    ">
                        <img class="card-poster-img" src="{poster_src}" alt="{title}" {img_attrs} style="{img_style}">

                        <div class="card-content" style="
                            padding: 6px;
                            background-color: {theme_colors['card_bg']};
                            color: {theme_colors['text']};
                            min-height: 135px;
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

                            <div style="
                                font-size: 10px;
                                color: {theme_colors['muted_text']};
                                margin-bottom: 2px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{meta_text}</div>

                            {f'''
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['text']};
                                opacity: 0.8;
                                line-height: 1.3;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                word-wrap: break-word;
                                overflow-wrap: break-word;
                            ">{summary[:84]}{'...' if len(summary) > 84 else ''}</div>
                            ''' if summary else ''}
                        </div>
                    </div>
                """

                if plex_url:
                    card_html = f'''
                        <a href="{plex_url}" 
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
                        max-width: 200px;
                        margin: 0 auto;
                        height: 320px;
                    ">
                        <div style="display: table-cell; vertical-align: middle;">
                            <div style="
                                font-weight: bold;
                                font-size: 14px;
                                color: {theme_colors['text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{title}</div>
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['muted_text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{' • '.join(filter(None, [str(year) if year else '', duration, library, f'Added {added_date}' if added_date else '', content_rating]))}</div>
                            {f'''
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['text']};
                                opacity: 0.8;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{summary[:100]}{'...' if len(summary) > 100 else ''}</div>
                            ''' if summary else ''}
                        </div>
                    </div>
                """

                if plex_url:
                    card_html = f'''
                        <a href="{plex_url}" 
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
            row_html += f'<td class="recently-added-cell" style="width: 20%; padding: 8px;"></td>'
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
    
    if recently_added_mode == "days" and max_items:
        try:
            since_date = (datetime.now() - timedelta(days=int(max_items))).strftime("%-m/%-d/%y")
        except Exception:
            logger.debug("suppressed exception; using fallback", exc_info=True)
            since_date = ""
        ra_title = (f"Added to {library_filter}" if library_filter else "Recently Added") + (f" since {since_date}" if since_date else "")
    else:
        ra_title = f"Recently Added{f' - {library_filter}' if library_filter else ''}"

    return f"""
        <div style="{container_style}">
            <h2 style="{title_style}">{ra_title}</h2>
            <table class="recently-added-table" style="{table_style}">
                {items_html}
            </table>
        </div>
    """
