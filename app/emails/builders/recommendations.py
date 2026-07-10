from urllib.parse import quote_plus

from app.clients.plex import build_plex_web_link
from app.emails.images import fetch_and_attach_image

import logging

logger = logging.getLogger(__name__)

from app.emails.builders.users import get_user_display_name

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
        f'<span style="color: {theme_colors["muted_text"]}; font-size: 0.85em;"> - {item.get("listen_count", 0)} plays</span>'
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
            _wrapped_ranked_list_html('Top Tracks', payload.get('top_tracks', []), lambda t: f"{t.get('name', '')} - {t.get('artist_name', '')}", theme_colors),
            _wrapped_ranked_list_html('Top Albums', payload.get('top_albums', []), lambda al: f"{al.get('name', '')} - {al.get('artist_name', '')}", theme_colors),
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
        f'<p style="color: {theme_colors["text"]};"><strong>Top Album:</strong> {top_album.get("name", "")} - '
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
            <h2 style="{title_style}">Server Stats - {server_data.get('year', '')}</h2>
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
                poster_src = f"cid:{poster_cid}"

                img_attrs = 'width="100%"'
                img_style = (
                    "width: 100%; height: auto; display: block; object-fit: cover; "
                    "border-radius: 12px 12px 0 0; background-color: #f8f9fa;"
                )
                if poster_max_height:
                    img_attrs = f'width="100%" height="{poster_max_height}"'
                    img_style = (
                        f"width: 100%; height: {poster_max_height}px; display: block; object-fit: cover; "
                        "border-radius: 12px 12px 0 0; background-color: #f8f9fa;"
                    )

                meta_line = " • ".join(filter(None, [
                    str(year) if year else '',
                    vote_text,
                    runtime,
                    'Unavailable' if is_unavailable else ''
                ]))

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
                        <img src="{poster_src}" alt="{title_text}" {img_attrs} style="{img_style}">
                        <div style="
                            padding: 8px;
                            background-color: {theme_colors['card_bg']};
                            color: {theme_colors['text']};
                            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                        ">
                            <div style="
                                font-weight: bold;
                                font-size: 12px;
                                color: {theme_colors['text']};
                                line-height: 1.2;
                                word-wrap: break-word;
                            ">{title_text}</div>
                            {f'''
                            <div style="
                                font-size: 10px;
                                color: {theme_colors['muted_text']};
                                margin-top: 2px;
                            ">{meta_line}</div>
                            ''' if meta_line else ''}
                            {f'''
                            <div style="
                                font-size: 10px;
                                line-height: 1.3;
                                margin-top: 4px;
                                padding-top: 4px;
                                border-top: 1px solid {theme_colors['border']};
                            ">{overview[:80]}{'...' if len(overview) > 80 else ''}</div>
                            ''' if overview else ''}
                        </div>
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
