
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

from app.settings_store import get_settings
from app.cache import get_cache_info
from app.clients.plex import build_plex_web_link, get_collection_items_for_email
from app.emails.images import fetch_and_attach_image, fetch_and_attach_blurred_image, fetch_and_attach_small_thumbnail, truncate_text

import logging

logger = logging.getLogger(__name__)

def get_user_display_name(user_id, users_data, display_preference='email'):
    if not users_data:
        return str(user_id)
    
    user = next((u for u in users_data if str(u.get('user_id')) == str(user_id)), None)
    
    if not user:
        return str(user_id)
    
    if display_preference == 'username':
        return user.get('username') or user.get('email') or str(user_id)
    elif display_preference == 'friendly_name':
        return user.get('friendly_name') or user.get('username') or user.get('email') or str(user_id)
    else:
        return user.get('email') or user.get('username') or str(user_id)

def build_enhanced_user_dict(users_data):
    user_dict = {}
    if users_data:
        for user in users_data:
            if user.get('is_active'):
                user_dict[str(user['user_id'])] = {
                    'email': user.get('email', ''),
                    'username': user.get('username', ''),
                    'friendly_name': user.get('friendly_name', ''),
                    'user_id': user.get('user_id')
                }
    return user_dict

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

    if title == "Most Active Libraries":
        cells.append(row.get('section_name', ''))
    elif title == "Most Active Users":
        cells.append(row.get('user', ''))
    elif title == "Most Active Platforms":
        cells.append(row.get('platform', ''))
    else:
        cells.append(row.get('title', ''))

    skip_year_stats = ["Most Active Libraries", "Most Active Users", "Most Active Platforms", "Most Concurrent Streams"]
    if title not in skip_year_stats:
        cells.append(row.get('year', ''))

    if "Recently" not in title and "Concurrent" not in title and not hide_play_counts:
        cells.append(row.get('total_plays', 0))

    hours_stats = ["Most Watched Movies", "Most Watched TV Shows", "Most Played Artists", "Most Active Libraries", "Most Active Users", "Most Active Platforms"]
    users_stats = ["Most Popular Movies", "Most Popular TV Shows", "Most Popular Artists"]

    if title in hours_stats:
        hours = round(row.get('total_duration', 0) / 3600) if row.get('total_duration') else 0
        cells.append(int(hours))
    elif title in users_stats:
        cells.append(row.get('users_watched', ''))

    skip_rating_stats = ["Most Active Libraries", "Most Played Artists", "Most Popular Artists", "Most Active Users", "Most Active Platforms", "Most Concurrent Streams"]
    if title not in skip_rating_stats:
        cells.append(row.get('content_rating', ''))
        rating = row.get('rating')
        cells.append(f"{rating}" if rating else 'NA')

    if title == "Most Concurrent Streams":
        cells.append(row.get('count', 0))

    return cells

def build_stats_html_with_cid_background(stat_data, msg_root, theme_colors, base_url="", date_range="", hide_play_counts=False, show_cover_art=False):
    if not stat_data or not stat_data.get('rows'):
        return ""
    
    title = stat_data.get('stat_title', 'Statistics')
    rows = stat_data['rows']
    
    background_cid = None
    if rows and (rows[0].get('art') or rows[0].get('grandparent_thumb')):
        artwork_path = rows[0].get('art') or rows[0].get('grandparent_thumb')
        if artwork_path:
            image_url = f"/proxy-art{artwork_path}" if not artwork_path.startswith('/proxy-art') else artwork_path
            background_cid = fetch_and_attach_blurred_image(
                image_url, 
                msg_root, 
                f"stat-bg-{len(msg_root.get_payload())}", 
                base_url
            )
    
    headers = get_stat_headers(title, hide_play_counts=hide_play_counts)
    header_cells = "".join([
        f'<th style="padding: 12px; background-color: rgba(52, 58, 64, 0.9); color: white; font-weight: bold; border: none; font-family: \'IBM Plex Sans\', \'Segoe UI\', Helvetica, Arial, sans-serif; font-size: 14px; text-align: left;">{h}</th>'
        for h in headers
    ])

    _COVER_ART_TYPES = {
        "Most Watched Movies", "Most Watched TV Shows",
        "Most Popular Movies", "Most Popular TV Shows",
        "Most Played Artists", "Most Popular Artists",
        "Recently Watched"
    }
    apply_cover_art = show_cover_art and title in _COVER_ART_TYPES

    rows_html = ""
    for row in rows:
        cells = get_stat_cells(title, row, hide_play_counts=hide_play_counts)
        if apply_cover_art:
            thumb_path = row.get('thumb', '') or row.get('grandparent_thumb', '')
            if thumb_path:
                proxy_path = f"/proxy-art{thumb_path}" if not thumb_path.startswith('/proxy-art') else thumb_path
                thumb_cid = fetch_and_attach_small_thumbnail(proxy_path, msg_root, f"stat-thumb-{len(msg_root.get_payload())}", base_url)
                if thumb_cid:
                    cells[0] = f'<img src="cid:{thumb_cid}" style="height:38px;width:auto;border-radius:3px;margin-right:7px;vertical-align:middle;">{cells[0]}'
        cells_html = "".join([
            f'<td style="padding: 12px; background-color: rgba(255, 255, 255, 0.5); color: #333; border-bottom: 1px solid rgba(222, 226, 230, 0.8); font-family: \'IBM Plex Sans\', \'Segoe UI\', Helvetica, Arial, sans-serif; font-size: 14px;">{cell}</td>'
            for cell in cells
        ])
        rows_html += f'<tr>{cells_html}</tr>'
    
    container_style = f"""
        margin: 20px 0;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        border: 1px solid {theme_colors['border']};
        position: relative;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    if background_cid:
        container_style += f"""
            background-image: url('cid:{background_cid}');
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
        """
    else:
        container_style += f"background-color: {theme_colors['card_bg']};"
    
    overlay = ""
    if background_cid:
        overlay = f"""
            <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; 
                        background-color: rgba(0, 0, 0, 0.3); z-index: 0;"></div>
        """
    
    header_style = f"""
        background-color: {theme_colors['primary']};
        color: white;
        padding: 15px;
        text-align: center;
        font-weight: bold;
        font-size: 18px;
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
    
    return f"""
        <div style="{container_style}">
            {overlay}
            <div style="position: relative; z-index: 1;">
                <div style="{header_style}">{title} - Last {date_range} days</div>
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
                poster_bg_url = f"cid:{poster_cid}"
                
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
                        <div class="card-poster-wrapper" style="position: relative; display: block; text-align: right;">
                            <div class="card-poster" style="
                                background-image: url('{poster_bg_url}');
                            ">
                                {f'''
                                <div class="card-poster-badge"
                                    style="position: absolute; display: inline-block; bottom: 1px; right: 1px; max-width: fit-content; text-align: right; margin-left: auto;">
                                    {added_date}
                                </div>
                                ''' if added_date else ''}
                            </div>
                        </div>
                        
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
                            ">{truncate_text(' • '.join(filter(None, [str(year) if year else '', duration, content_rating])), 36)}</div>
                            
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

def build_recommendations_html_with_cids(recs_data, msg_root, theme_colors, user_emails=None, base_url="", display_preference='email', users_full_data=None, recs_grid_columns=5, poster_max_height=0):
    if not recs_data:
        return ""
    
    html_sections = []
    
    for user_id, user_recs in recs_data.items():
        if user_emails and str(user_id) not in [str(k) for k in user_emails.keys()]:
            continue

        if users_full_data:
            display_name = get_user_display_name(user_id, users_full_data, display_preference)
        elif user_emails:
            user_email_value = user_emails.get(str(user_id), str(user_id))
            display_name = user_email_value
        else:
            display_name = str(user_id)
        
        movies_html = build_recommendations_section_with_cids(
            user_recs.get('movie_posters', []),
            user_recs.get('movie_posters_unavailable', []),
            "Recommended Movies",
            msg_root,
            f"recs-movies-{user_id}",
            theme_colors,
            base_url,
            recs_grid_columns=recs_grid_columns,
            poster_max_height=poster_max_height
        )

        shows_html = build_recommendations_section_with_cids(
            user_recs.get('show_posters', []),
            user_recs.get('show_posters_unavailable', []),
            "Recommended TV Shows",
            msg_root,
            f"recs-shows-{user_id}",
            theme_colors,
            base_url,
            recs_grid_columns=recs_grid_columns,
            poster_max_height=poster_max_height
        )
        
        if movies_html or shows_html:
            container_style = f"""
                margin: 30px 0;
                padding: 20px;
                background-color: {theme_colors['card_bg']};
                border-radius: 8px;
                border: 1px solid {theme_colors['border']};
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
            """
            
            user_title_style = f"""
                text-align: center;
                color: {theme_colors['text']};
                margin: 0 0 20px 0;
                font-size: 24px;
                font-weight: bold;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
            """
            
            user_section = f"""
                <div style="{container_style}" data-recs-user="{user_id}">
                    <h2 style="{user_title_style}">Recommendations for {display_name}</h2>
                    {movies_html}
                    {shows_html}
                </div>
            """
            html_sections.append(user_section)
    
    return '\n'.join(html_sections)

def _wrapped_ranked_list_html(title, items, label_fn, theme_colors):
    if not items:
        return ""
    rows = "".join(
        f'<li style="margin: 4px 0; color: {theme_colors["text"]};">'
        f'<strong>#{i + 1}</strong> {label_fn(item)}'
        f'<span style="color: {theme_colors["muted_text"]}; font-size: 0.85em;"> — {item.get("listen_count", 0)} plays</span>'
        f'</li>'
        for i, item in enumerate(items)
    )
    return (
        f'<div style="margin-bottom: 16px;">'
        f'<h3 style="margin-bottom: 6px; color: {theme_colors["text"]};">{title}</h3>'
        f'<ol style="padding-left: 20px; margin: 0;">{rows}</ol>'
        f'</div>'
    )

def build_droppedneedle_wrapped_html_with_cids(wrapped_data, msg_root, theme_colors, user_emails=None, display_preference='email', users_full_data=None):
    if not wrapped_data:
        return ""

    html_sections = []

    for user_id, payload in wrapped_data.items():
        if user_emails and str(user_id) not in [str(k) for k in user_emails.keys()]:
            continue
        if not payload or not payload.get('has_data'):
            continue

        if users_full_data:
            display_name = get_user_display_name(user_id, users_full_data, display_preference)
        elif user_emails:
            display_name = user_emails.get(str(user_id), str(user_id))
        else:
            display_name = str(user_id)

        sections = "".join([
            _wrapped_ranked_list_html('Top Artists', payload.get('top_artists', []), lambda a: a.get('name', ''), theme_colors),
            _wrapped_ranked_list_html('Top Tracks', payload.get('top_tracks', []), lambda t: f"{t.get('name', '')} — {t.get('artist_name', '')}", theme_colors),
            _wrapped_ranked_list_html('Top Albums', payload.get('top_albums', []), lambda al: f"{al.get('name', '')} — {al.get('artist_name', '')}", theme_colors),
            _wrapped_ranked_list_html('Top Genres', payload.get('top_genres', []), lambda g: g.get('genre', ''), theme_colors),
        ])

        container_style = f"""
            margin: 30px 0;
            padding: 20px;
            background-color: {theme_colors['card_bg']};
            border-radius: 8px;
            border: 1px solid {theme_colors['border']};
            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
        """
        user_title_style = f"""
            text-align: center;
            color: {theme_colors['text']};
            margin: 0 0 10px 0;
            font-size: 24px;
            font-weight: bold;
            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
        """

        html_sections.append(f"""
            <div style="{container_style}" data-wrapped-user="{user_id}">
                <h2 style="{user_title_style}">{display_name}'s {payload.get('year', '')} Wrapped</h2>
                <p style="text-align: center; color: {theme_colors['muted_text']}; margin-bottom: 16px;">
                    ~{payload.get('total_listens_estimated', 0)} plays tracked &bull; {payload.get('loved_tracks_count', 0)} loved tracks
                </p>
                {sections}
            </div>
        """)

    return '\n'.join(html_sections)

def build_droppedneedle_server_stats_html_with_cids(server_data, msg_root, theme_colors):
    if not server_data:
        return ""

    leaderboard_html = _wrapped_ranked_list_html(
        'Top Listeners', server_data.get('leaderboard', []), lambda entry: entry.get('display_name', ''), theme_colors
    )
    top_artist = server_data.get('top_artist_sitewide')
    top_album = server_data.get('top_album_sitewide')
    top_artist_html = (
        f'<p style="color: {theme_colors["text"]};"><strong>Top Artist:</strong> {top_artist.get("name", "")} '
        f'({top_artist.get("listen_count", 0)} plays)</p>'
    ) if top_artist else ""
    top_album_html = (
        f'<p style="color: {theme_colors["text"]};"><strong>Top Album:</strong> {top_album.get("name", "")} — '
        f'{top_album.get("artist_name", "")} ({top_album.get("listen_count", 0)} plays)</p>'
    ) if top_album else ""

    container_style = f"""
        margin: 30px 0;
        padding: 20px;
        background-color: {theme_colors['card_bg']};
        border-radius: 8px;
        border: 1px solid {theme_colors['border']};
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    title_style = f"""
        text-align: center;
        color: {theme_colors['text']};
        margin: 0 0 10px 0;
        font-size: 24px;
        font-weight: bold;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """

    return f"""
        <div style="{container_style}">
            <h2 style="{title_style}">Server Stats — {server_data.get('year', '')}</h2>
            <p style="text-align: center; color: {theme_colors['muted_text']}; margin-bottom: 16px;">
                ~{server_data.get('total_listens_estimated', 0)} plays across {server_data.get('total_users_tracked', 0)} listeners
            </p>
            {top_artist_html}
            {top_album_html}
            {leaderboard_html}
        </div>
    """

def build_recommendations_section_with_cids(available_items, unavailable_items, title, msg_root, section_prefix, theme_colors, base_url="", recs_grid_columns=5, poster_max_height=0):
    if not available_items and not unavailable_items:
        return ""

    all_items = available_items + unavailable_items
    items_per_row = max(1, int(recs_grid_columns) if recs_grid_columns else 5)
    cell_width_pct = f"{100 / items_per_row:.4f}%"
    
    rows_html = ""
    for i in range(0, len(all_items), items_per_row):
        row_items = all_items[i:i + items_per_row]
        row_html = "<tr>"
        
        for j, item in enumerate(row_items):
            is_unavailable = (i + j) >= len(available_items)
            
            poster_cid = None
            if item.get('url'):
                poster_cid = fetch_and_attach_image(
                    f"/proxy-img?u={item['url']}",
                    msg_root,
                    f"{section_prefix}-{i}-{j}",
                    base_url,
                    max_height=poster_max_height if poster_max_height else None
                )
            
            title_text = item.get('title', 'Unknown')
            year = item.get('year', '')
            vote = item.get('vote', '')
            overview = item.get('overview', '')[:100] + "..." if item.get('overview') else ""
            runtime = item.get('runtime', '')

            if is_unavailable:
                href = item.get('href', '#')
                link_title = "Request on Overseerr"
            else:
                if item.get('plex_url'):
                    href = item['plex_url']
                    link_title = "Open in Plex"
                elif item.get('rating_key') and item.get('machine_id'):
                    href = build_plex_web_link(item['rating_key'], item['machine_id'])
                    link_title = "Open in Plex"
                else:
                    search_query = quote_plus(title_text)
                    href = f"https://app.plex.tv/desktop#!/search?query={search_query}"
                    link_title = "Search in Plex"
            
            vote_text = f"★ {vote:.1f}" if isinstance(vote, (int, float)) and vote > 0 else ""
            
            cell_style = f"""
                width: {cell_width_pct};
                padding: 6px;
                vertical-align: top;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                {'opacity: 0.7; filter: grayscale(30%);' if is_unavailable else ''}
            """

            if poster_cid:
                poster_bg_url = f"cid:{poster_cid}"
                
                card_content = f"""
                    <div style="
                        background-color: {theme_colors['card_bg']};
                        border-radius: 12px;
                        overflow: hidden;
                        border: 1px solid {theme_colors['border']};
                        width: 100%;
                        margin: 0 auto;
                        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                    ">
                        <div style="
                            background-image: url('{poster_bg_url}');
                            background-size: cover;
                            background-position: center;
                            background-repeat: no-repeat;
                            padding-top: 148%;
                            height: 0;
                            position: relative;
                            background-color: #f8f9fa;
                        ">
                            {f'''
                            <div style="
                                position: absolute;
                                top: 4px;
                                left: 4px;
                                background-color: rgba(0, 0, 0, 0.7);
                                color: white;
                                padding: 2px 6px;
                                border-radius: 4px;
                                font-size: 9px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                line-height: 1;
                            ">{year} {vote_text}</div>
                            ''' if year or vote_text else ''}

                            {'''
                            <div style="
                                position: absolute;
                                top: 4px;
                                right: 4px;
                                background-color: rgba(255, 0, 0, 0.8);
                                color: white;
                                padding: 2px 6px;
                                border-radius: 4px;
                                font-size: 9px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                line-height: 1;
                            ">Unavailable</div>
                            ''' if is_unavailable else ''}

                            <div style="
                                position: absolute;
                                bottom: 0;
                                left: 0;
                                right: 0;
                                padding: 8px;
                                background: linear-gradient(transparent, rgba(0, 0, 0, 0.7));
                            ">
                                <div style="
                                    font-weight: bold;
                                    font-size: 12px;
                                    color: white;
                                    line-height: 1.2;
                                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                    word-wrap: break-word;
                                ">{title_text}</div>
                                {f'''
                                <div style="
                                    font-size: 10px;
                                    color: rgba(255, 255, 255, 0.8);
                                    margin-top: 2px;
                                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                ">{runtime}</div>
                                ''' if runtime else ''}
                            </div>
                        </div>
                        
                        {f'''
                        <div style="
                            padding: 8px;
                            background-color: {theme_colors['card_bg']};
                            color: {theme_colors['text']};
                            font-size: 10px;
                            line-height: 1.3;
                            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            border-top: 1px solid {theme_colors['border']};
                        ">
                            {overview[:80]}{'...' if len(overview) > 80 else ''}
                        </div>
                        ''' if overview else ''}
                    </div>
                """
                
                card_html = f'<a href="{href}" style="text-decoration: none; color: inherit; display: block;" target="_blank" title="{link_title}">{card_content}</a>'
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
                        height: 300px;
                        display: table;
                    ">
                        <div style="display: table-cell; vertical-align: middle;">
                            <div style="
                                font-weight: bold;
                                font-size: 12px;
                                color: {theme_colors['text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{title_text}</div>
                            <div style="
                                font-size: 10px;
                                color: {theme_colors['muted_text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{' • '.join(filter(None, [str(year) if year else '', vote_text, runtime, 'Unavailable' if is_unavailable else '']))}</div>
                            {f'''
                            <div style="
                                font-size: 10px;
                                color: {theme_colors['text']};
                                opacity: 0.8;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                line-height: 1.3;
                            ">{overview[:100]}{'...' if len(overview) > 100 else ''}</div>
                            ''' if overview else ''}
                        </div>
                    </div>
                """
            
            row_html += f'<td style="{cell_style}">{card_html}</td>'
        
        while len(row_items) < items_per_row:
            row_html += f'<td style="width: 20%; padding: 6px;"></td>'
            row_items.append(None)
        
        row_html += "</tr>"
        rows_html += row_html
    
    section_title_style = f"""
        color: {theme_colors['text']};
        margin: 0 0 15px 0;
        font-size: 20px;
        font-weight: bold;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    table_style = """
        width: 100%;
        border-collapse: collapse;
        padding: 0;
        margin: 0;
    """
    
    return f"""
        <div style="margin: 20px 0;">
            <h3 style="{section_title_style}">{title}</h3>
            <table style="{table_style}">
                {rows_html}
            </table>
        </div>
    """

def build_individual_item_card_html(item, theme_colors, msg_root, base_url="", poster_max_height=0):
    item_title = item.get('title', 'Unknown Title')
    year = item.get('year')
    item_type = item.get('type', 'unknown')
    
    display_title = item_title
    if year:
        display_title += f" ({year})"
    
    type_icons = {
        'movie': '🎬',
        'show': '📺', 
        'album': '💿',
        'track': '🎵',
        'artist': '🎤'
    }
    type_icon = type_icons.get(item_type, '📄')
    
    subtitle = ""
    if item.get('parentTitle') and item_type in ['album', 'track']:
        subtitle = item['parentTitle']
    elif item.get('grandparentTitle') and item_type == 'track':
        subtitle = item['grandparentTitle']
    elif item_type == 'show':
        season_count = item.get('childCount', 0)
        episode_count = item.get('leafCount', 0)
        if season_count > 0:
            subtitle = f"{season_count} season{'s' if season_count != 1 else ''}"
        elif episode_count > 0:
            subtitle = f"{episode_count} episode{'s' if episode_count != 1 else ''}"
    
    _pmh = poster_max_height if poster_max_height else None
    poster_cid = None
    poster_url = item.get('thumb', '')
    if poster_url:
        logger.debug(f"Attempting to fetch thumb image: {poster_url}")
        if poster_url.startswith('http'):
            poster_cid = fetch_and_attach_image(poster_url, msg_root, f"collection_{item.get('key', 'unknown')}_thumb", base_url, max_height=_pmh)
        else:
            full_poster_url = f"/proxy-art{poster_url if poster_url.startswith('/') else '/' + poster_url}"
            poster_cid = fetch_and_attach_image(full_poster_url, msg_root, f"collection_{item.get('key', 'unknown')}_thumb", base_url, max_height=_pmh)
        logger.debug(f"Thumb CID result: {poster_cid}")

    if not poster_cid:
        logger.debug("No thumb CID, trying art URL...")
        art_url = item.get('art', '')
        if art_url:
            logger.debug(f"Attempting to fetch art image: {art_url}")
            if art_url.startswith('http'):
                poster_cid = fetch_and_attach_image(art_url, msg_root, f"collection_{item.get('key', 'unknown')}_art", base_url, max_height=_pmh)
            else:
                full_art_url = f"/proxy-art{art_url if art_url.startswith('/') else '/' + art_url}"
                poster_cid = fetch_and_attach_image(full_art_url, msg_root, f"collection_{item.get('key', 'unknown')}_art", base_url, max_height=_pmh)
            logger.debug(f"Art CID result: {poster_cid}")

    if poster_cid:
        return f"""
        <table cellpadding="0" cellspacing="0" border="0" style="
            background-color: {theme_colors['card_bg']};
            border-radius: 12px;
            width: 120px;
            margin: 0;
        ">
            <tr>
                <td style="
                    background-image: url('cid:{poster_cid}');
                    background-size: cover;
                    background-position: center;
                    background-repeat: no-repeat;
                    height: 180px;
                    background-color: #f8f9fa;
                    border-radius: 12px;
                    position: relative;
                    vertical-align: top;
                ">
                    <table cellpadding="0" cellspacing="0" border="0" width="100%">
                        <tr>
                            <td style="text-align: right;">
                                <div style="
                                    background-color: rgba(0, 0, 0, 0.8);
                                    color: white;
                                    padding: 4px 6px;
                                    border-radius: 4px;
                                    font-size: 10px;
                                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                    line-height: 1;
                                    display: inline-block;
                                    margin: 6px;
                                ">
                                    {type_icon}
                                </div>
                            </td>
                        </tr>
                        <tr>
                            <td style="height: 148px; vertical-align: bottom;">
                                <div style="
                                    background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent);
                                    border-radius: 0 0 11px 11px;
                                    padding: 6px;
                                ">
                                    <div style="
                                        font-weight: bold;
                                        font-size: 11px;
                                        color: white;
                                        line-height: 1.2;
                                        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                    ">{display_title}</div>
                                    {f'''<div style="
                                        font-size: 9px;
                                        color: #ccc;
                                        line-height: 1.2;
                                        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                        margin-top: 2px;
                                    ">{subtitle}</div>''' if subtitle else ''}
                                </div>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
        """
    else:
        return f"""
        <table cellpadding="0" cellspacing="0" border="0" style="
            background-color: {theme_colors['card_bg']};
            border-radius: 12px;
            border: 1px solid {theme_colors['border']};
            width: 120px;
            height: 180px;
            margin: 0;
        ">
            <tr>
                <td style="
                    text-align: center;
                    vertical-align: middle;
                    padding: 12px;
                    color: {theme_colors['text']};
                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                ">
                    <div style="
                        font-size: 11px;
                        margin-bottom: 8px;
                    ">{type_icon}</div>
                    <div style="
                        font-weight: bold;
                        font-size: 14px;
                        line-height: 1.2;
                        margin-bottom: 8px;
                        padding: 2px;
                    ">{display_title}</div>
                    {f'''<div style="
                        font-size: 9px;
                        color: {theme_colors['muted_text']};
                        line-height: 1.2;
                    ">{subtitle}</div>''' if subtitle else ''}
                </td>
            </tr>
        </table>
        """

def build_collection_card_html(collection, theme_colors, msg_root, base_url="", poster_max_height=0):
    _pmh = poster_max_height if poster_max_height else None
    poster_cid = None
    poster_url = collection.get('thumb', '')
    if poster_url:
        logger.debug(f"Attempting to fetch thumb image: {poster_url}")
        if poster_url.startswith('http'):
            poster_cid = fetch_and_attach_image(poster_url, msg_root, f"collection_{collection.get('key', 'unknown')}_thumb", base_url, max_height=_pmh)
        else:
            full_poster_url = f"/proxy-art{poster_url if poster_url.startswith('/') else '/' + poster_url}"
            poster_cid = fetch_and_attach_image(full_poster_url, msg_root, f"collection_{collection.get('key', 'unknown')}_thumb", base_url, max_height=_pmh)
        logger.debug(f"Thumb CID result: {poster_cid}")

    if not poster_cid:
        logger.debug("No thumb CID, trying art URL...")
        art_url = collection.get('art', '')
        if art_url:
            logger.debug(f"Attempting to fetch art image: {art_url}")
            if art_url.startswith('http'):
                poster_cid = fetch_and_attach_image(art_url, msg_root, f"collection_{collection.get('key', 'unknown')}_art", base_url, max_height=_pmh)
            else:
                full_art_url = f"/proxy-art{art_url if art_url.startswith('/') else '/' + art_url}"
                poster_cid = fetch_and_attach_image(full_art_url, msg_root, f"collection_{collection.get('key', 'unknown')}_art", base_url, max_height=_pmh)
            logger.debug(f"Art CID result: {poster_cid}")
    
    collection_title = collection.get('title', 'Unknown Collection')
    count = collection.get('childCount', 0)
    subtype = collection.get('subtype', 'unknown')
    summary = collection.get('summary', '')
    type_icon = '📽️' if subtype == 'movie' else '📺' if subtype == 'show' else '🎧'
    
    if poster_cid:
        poster_bg_url = f"cid:{poster_cid}"
        logger.debug(f"Final poster src for {collection_title}: {poster_bg_url}")
        
        return f"""
            <table cellpadding="0" cellspacing="0" border="0" style="
                background-color: {theme_colors['card_bg']};
                border-radius: 12px;
                width: 120px;
                margin: 0;
            ">
                <tr>
                    <td style="
                        background-image: url('{poster_bg_url}');
                        background-size: cover;
                        background-position: center;
                        background-repeat: no-repeat;
                        height: 180px;
                        background-color: #f8f9fa;
                        border-radius: 12px;
                        position: relative;
                        vertical-align: top;
                    ">
                        <table cellpadding="0" cellspacing="0" border="0" width="100%">
                            <tr>
                                <td style="text-align: right;">
                                    <div style="
                                        background-color: rgba(0, 0, 0, 0.8);
                                        color: white;
                                        padding: 4px 6px;
                                        border-radius: 4px;
                                        font-size: 10px;
                                        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                        line-height: 1;
                                        display: inline-block;
                                        margin: 6px;
                                    ">
                                        {type_icon} {count}
                                    </div>
                                </td>
                            </tr>
                            <tr>
                                <td style="height: 148px; vertical-align: bottom;">
                                    <div style="
                                        background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent);
                                        border-radius: 0 0 11px 11px;
                                        padding: 6px;
                                    ">
                                        <div style="
                                            font-weight: bold;
                                            font-size: 12px;
                                            color: white;
                                            line-height: 1.2;
                                            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                        ">{collection_title}</div>
                                    </div>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        """
    else:
        logger.debug(f"No valid image data for {collection_title}, using placeholder")
        return f"""
            <table cellpadding="0" cellspacing="0" border="0" style="
                background-color: {theme_colors['card_bg']};
                border-radius: 12px;
                border: 1px solid {theme_colors['border']};
                width: 120px;
                height: 180px;
                margin: 0;
            ">
                <tr>
                    <td style="
                        text-align: center;
                        vertical-align: middle;
                        padding: 12px;
                    ">
                        <div style="
                            font-weight: bold;
                            font-size: 14px;
                            color: {theme_colors['text']};
                            margin-bottom: 8px;
                            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            padding: 2px;
                        ">{collection_title}</div>
                        <div style="
                            font-size: 11px;
                            color: {theme_colors['muted_text']};
                            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                        ">{type_icon} {count} items</div>
                    </td>
                </tr>
            </table>
        """

def build_collections_html_with_cids(all_collections, msg_root, theme_colors, base_url="", custom_title=None, expanded_collections=None, group_index=0, poster_max_height=0):
    if not all_collections:
        return f"""
        <div style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
            <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">No collections available.</p>
        </div>
        """
    
    expanded_collections = expanded_collections or {}
    all_items_to_display = []
    
    _s = get_settings(decrypt_secrets=False)
    row = (_s.get("plex_url"), _s.get("plex_token")) if "id" in _s else None
    
    plex_settings = {}
    if row and row[0] and row[1]:
        plex_settings = {
            'plex_url': row[0],
            'plex_token': row[1]
        }
    else:
        plex_settings = None

    for collection_index, collection in enumerate(all_collections):
        collection_key = collection.get('key')
        collection_id = f"{group_index}-{collection_index}-{collection_key}"

        if collection_id in expanded_collections and plex_settings:
            logger.debug(f"Collection {collection_id} is expanded, fetching individual items...")
            individual_items = get_collection_items_for_email(collection_key, plex_settings)
            
            for item in individual_items:
                item['is_individual_item'] = True
                item['original_collection'] = collection.get('title', 'Unknown Collection')
                all_items_to_display.append(item)
        else:
            logger.debug(f"  No match for {collection_id}")
            if not (collection_id in expanded_collections):
                logger.debug(f"     Reason: Collection ID not in expanded_collections")
                if expanded_collections:
                    logger.debug(f"     Available expanded IDs: {list(expanded_collections.keys())}")
            if not plex_settings:
                logger.debug(f"     Reason: No plex_settings available")
            collection['is_individual_item'] = False
            all_items_to_display.append(collection)
    
    items_html = ""
    items_per_row = 5
    
    for i in range(0, len(all_items_to_display), items_per_row):
        row_items = all_items_to_display[i:i + items_per_row]
        is_partial_row = len(row_items) < items_per_row
        
        if is_partial_row:
            items_count = len(row_items)
            
            row_html = f'<tr><td colspan="{items_per_row}" style="text-align: center; padding: 8px;">'
            row_html += '<table cellpadding="0" cellspacing="0" border="0" style="margin: 0 auto; border-collapse: separate;">'
            row_html += '<tr>'
            
            for j, item in enumerate(row_items):
                if items_count == 1:
                    cell_spacing = "0"
                elif items_count == 2:
                    cell_spacing = "60px" if j == 0 else "0"
                elif items_count == 3:
                    cell_spacing = "40px" if j < 2 else "0"
                elif items_count == 4:
                    cell_spacing = "20px" if j < 3 else "0"
                else:
                    cell_spacing = "8px" if j < items_count - 1 else "0"

                if item.get('is_individual_item'):
                    card_html = build_individual_item_card_html(item, theme_colors, msg_root, base_url, poster_max_height=poster_max_height)
                else:
                    card_html = build_collection_card_html(item, theme_colors, msg_root, base_url, poster_max_height=poster_max_height)

                row_html += f'<td style="vertical-align: top; padding-right: {cell_spacing};">{card_html}</td>'

            row_html += '</tr></table></td></tr>'
            items_html += row_html
        else:
            row_html = "<tr style='text-align: center;'>"

            for j, item in enumerate(row_items):
                cell_style = f"""
                    width: 20%;
                    padding: 8px;
                    vertical-align: top;
                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                """

                if item.get('is_individual_item'):
                    card_html = build_individual_item_card_html(item, theme_colors, msg_root, base_url, poster_max_height=poster_max_height)
                else:
                    card_html = build_collection_card_html(item, theme_colors, msg_root, base_url, poster_max_height=poster_max_height)
                
                row_html += f'<td style="{cell_style}">{card_html}</td>'
            
            row_html += "</tr>"
            items_html += row_html
    
    container_style = f"""
        background-color: {theme_colors['card_bg']};
        border-radius: 8px;
        margin: 20px 0;
        border: 1px solid {theme_colors['border']};
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    title_style = f"""
        text-align: center;
        color: {theme_colors['text']};
        margin: 0 0 20px 0;
        font-size: 24px;
        font-weight: bold;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    table_style = """
        width: 100%;
        border-collapse: collapse;
        margin: 0;
        padding: 0;
    """

    display_title = custom_title if custom_title else "Collections"
    
    return f"""
        <div style="{container_style}">
            <h2 style="{title_style}">{display_title}</h2>
            <table cellpadding="0" cellspacing="0" border="0" style="{table_style}">
                {items_html}
            </table>
        </div>
    """
