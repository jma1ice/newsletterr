from urllib.parse import quote_plus

from app.config import DEFAULT_PLEX_WEB_URL
from app.clients.plex import build_plex_web_link
from app.emails import density, headings
from app.emails.builders.card_grid import effective_columns
from app.emails.images import fetch_and_attach_image
from app.security import escape_html_output as esc

import logging

logger = logging.getLogger(__name__)

from app.emails.builders.users import get_user_display_name

def build_recommendations_html_with_cids(recs_data, msg_root, theme_colors, user_emails=None, base_url="", display_preference='email', users_full_data=None, recs_grid_columns=5, poster_max_height=0, hosted_images_enabled=False, hosted_base_url="", show_description=True):
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
            poster_max_height=poster_max_height,
            hosted_images_enabled=hosted_images_enabled,
            hosted_base_url=hosted_base_url,
            show_description=show_description
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
            poster_max_height=poster_max_height,
            hosted_images_enabled=hosted_images_enabled,
            hosted_base_url=hosted_base_url,
            show_description=show_description
        )
        
        if movies_html or shows_html:
            p3 = density.picker3(theme_colors)
            container_style = f"""
                margin: {p3('14px 0', '30px 0', '38px 0')};
                padding: {p3('12px', '20px', '26px')};
                background-color: {theme_colors['card_bg']};
                border-radius: 8px;
                border: 1px solid {theme_colors['border']};
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
            """
            
            user_title_style = f"""
                text-align: center;
                color: {theme_colors['text']};
                margin: {p3('0 0 10px 0', '0 0 20px 0', '0 0 26px 0')};
                font-size: {p3('17px', '24px', '30px')};
                font-weight: bold;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
            """
            
            # Only the outer per-user heading takes the override; the inner
            # "Recommended Movies"/"Recommended TV Shows" labels stay put.
            user_heading = headings.resolve(theme_colors, f"Recommendations for {display_name}")
            user_heading_html = f'<h2 style="{user_title_style}">{esc(user_heading)}</h2>' if user_heading else ''

            user_section = f"""
                <div style="{container_style}" data-recs-user="{esc(str(user_id))}">
                    {user_heading_html}
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
        f'<strong>#{i + 1}</strong> {esc(label_fn(item))}'
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

        wrapped_heading = headings.resolve(theme_colors, f"{display_name}'s {payload.get('year', '')} Wrapped")
        wrapped_heading_html = f'<h2 style="{user_title_style}">{esc(wrapped_heading)}</h2>' if wrapped_heading else ''

        html_sections.append(f"""
            <div style="{container_style}" data-wrapped-user="{esc(str(user_id))}">
                {wrapped_heading_html}
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
        f'<p style="color: {theme_colors["text"]};"><strong>Top Artist:</strong> {esc(top_artist.get("name", ""))} '
        f'({top_artist.get("listen_count", 0)} plays)</p>'
    ) if top_artist else ""
    top_album_html = (
        f'<p style="color: {theme_colors["text"]};"><strong>Top Album:</strong> {esc(top_album.get("name", ""))} - '
        f'{esc(top_album.get("artist_name", ""))} ({top_album.get("listen_count", 0)} plays)</p>'
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

    dn_heading = headings.resolve(theme_colors, f"Server Stats - {server_data.get('year', '')}")
    dn_heading_html = f'<h2 style="{title_style}">{esc(dn_heading)}</h2>' if dn_heading else ''

    return f"""
        <div style="{container_style}">
            {dn_heading_html}
            <p style="text-align: center; color: {theme_colors['muted_text']}; margin-bottom: 16px;">
                ~{server_data.get('total_listens_estimated', 0)} plays across {server_data.get('total_users_tracked', 0)} listeners
            </p>
            {top_artist_html}
            {top_album_html}
            {leaderboard_html}
        </div>
    """

def build_recommendations_section_with_cids(available_items, unavailable_items, title, msg_root, section_prefix, theme_colors, base_url="", recs_grid_columns=5, poster_max_height=0, hosted_images_enabled=False, hosted_base_url="", show_description=True):
    if not available_items and not unavailable_items:
        return ""

    # This section renders under every layout, so it needs the three-way
    # picker: the same code is one layout's compact variant and another's
    # expanded one.
    p3 = density.picker3(theme_colors)
    art_on = density.show_art(theme_colors)

    all_items = available_items + unavailable_items
    items_per_row = 1 if not art_on else effective_columns(recs_grid_columns, len(all_items))
    cell_width_pct = f"{100 / items_per_row:.4f}%"

    # Uniform 2:3 poster box regardless of column count (see recently_added.py).
    _base_width = 760
    poster_px = max(60, int(_base_width / items_per_row) - 16)
    if poster_max_height:
        poster_px = min(poster_px, max(40, int(int(poster_max_height) * 2 // 3)))
    poster_target = (poster_px, int(round(poster_px * 1.5)))

    rows_html = ""
    for i in range(0, len(all_items), items_per_row):
        row_items = all_items[i:i + items_per_row]
        row_html = '<tr class="recommendations-row">'
        
        for j, item in enumerate(row_items):
            is_unavailable = (i + j) >= len(available_items)
            
            poster_src_result = None
            if item.get('url') and art_on:
                poster_src_result = fetch_and_attach_image(
                    f"/proxy-img?u={item['url']}",
                    msg_root,
                    f"{section_prefix}-{i}-{j}",
                    base_url,
                    target=poster_target,
                    hosted_images_enabled=hosted_images_enabled,
                    hosted_base_url=hosted_base_url
                )
            
            title_text = item.get('title', 'Unknown')
            year = item.get('year', '')
            vote = item.get('vote', '')
            overview = item.get('overview', '')[:100] + "..." if (item.get('overview') and show_description) else ""
            runtime = item.get('runtime', '')

            if is_unavailable:
                href = item.get('href', '#')
                link_title = "Request on Overseerr"
            else:
                if item.get('plex_url'):
                    href = item['plex_url']
                    link_title = "Open in Plex"
                elif item.get('rating_key') and item.get('machine_id'):
                    href = build_plex_web_link(item['rating_key'], item['machine_id'], item.get('plex_web_url'))
                    link_title = "Open in Plex"
                else:
                    search_query = quote_plus(title_text)
                    search_base = (item.get('plex_web_url') or DEFAULT_PLEX_WEB_URL).rstrip('/')
                    href = f"{search_base}#!/search?query={search_query}"
                    link_title = "Search in Plex"
            
            vote_text = f"★ {vote:.1f}" if isinstance(vote, (int, float)) and vote > 0 else ""
            
            cell_style = f"""
                width: {cell_width_pct};
                padding: 6px;
                vertical-align: top;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                {'opacity: 0.7; filter: grayscale(30%);' if is_unavailable else ''}
            """

            if not art_on:
                # compact: one full-width text row per recommendation
                meta_line = " • ".join(filter(None, [
                    str(year) if year else '', vote_text, runtime,
                    'Unavailable' if is_unavailable else ''
                ]))
                _last = (i + j) == len(all_items) - 1
                card_content = f"""
                    <div style="padding: 6px 0;{'' if _last else f' border-bottom: 1px solid {theme_colors["border"]};'} font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
                        <div style="font-weight: bold; font-size: 13px; color: {theme_colors['text']}; line-height: 1.25;">{esc(title_text)}</div>
                        {f'<div style="font-size: 10.5px; color: {theme_colors["muted_text"]}; padding-top: 2px;">{esc(meta_line)}</div>' if meta_line else ''}
                        {f'<div style="font-size: 11px; color: {theme_colors["text"]}; opacity: 0.8; line-height: 1.4; padding-top: 3px;">{esc(overview[:110])}{"..." if len(overview) > 110 else ""}</div>' if overview else ''}
                    </div>
                """
                card_html = f'<a href="{esc(href)}" style="text-decoration: none; color: inherit; display: block;" target="_blank" title="{link_title}">{card_content}</a>'
            elif poster_src_result:
                poster_src = poster_src_result

                img_attrs = f'width="{poster_px}"'
                img_style = (
                    "width: 100%; height: auto; display: block; "
                    "border-radius: 12px 12px 0 0; background-color: #f8f9fa;"
                )

                meta_line = " • ".join(filter(None, [
                    str(year) if year else '',
                    vote_text,
                    runtime,
                    'Unavailable' if is_unavailable else ''
                ]))

                card_content = f"""
                    <div class="recommendations-card" style="
                        background-color: {theme_colors['card_bg']};
                        border-radius: 12px;
                        overflow: hidden;
                        border: 1px solid {theme_colors['border']};
                        width: 100%;
                        max-width: {poster_px}px;
                        margin: 0 auto;
                        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                    ">
                        <img src="{poster_src}" alt="{esc(title_text)}" {img_attrs} style="{img_style}">
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
                            ">{esc(title_text)}</div>
                            {f'''
                            <div style="
                                font-size: 10px;
                                color: {theme_colors['muted_text']};
                                margin-top: 2px;
                            ">{esc(meta_line)}</div>
                            ''' if meta_line else ''}
                            {f'''
                            <div style="
                                font-size: 10px;
                                line-height: 1.3;
                                margin-top: 4px;
                                padding-top: 4px;
                                border-top: 1px solid {theme_colors['border']};
                            ">{esc(overview[:80])}{'...' if len(overview) > 80 else ''}</div>
                            ''' if overview else ''}
                        </div>
                    </div>
                """

                card_html = f'<a href="{esc(href)}" style="text-decoration: none; color: inherit; display: block;" target="_blank" title="{link_title}">{card_content}</a>'
            else:
                card_html = f"""
                    <div class="recommendations-card" style="
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
                            ">{esc(title_text)}</div>
                            <div style="
                                font-size: 10px;
                                color: {theme_colors['muted_text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{esc(' • '.join(filter(None, [str(year) if year else '', vote_text, runtime, 'Unavailable' if is_unavailable else ''])))}</div>
                            {f'''
                            <div style="
                                font-size: 10px;
                                color: {theme_colors['text']};
                                opacity: 0.8;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                line-height: 1.3;
                            ">{esc(overview[:100])}{'...' if len(overview) > 100 else ''}</div>
                            ''' if overview else ''}
                        </div>
                    </div>
                """
            
            row_html += f'<td class="recommendations-cell" style="{cell_style}">{card_html}</td>'

        while len(row_items) < items_per_row:
            row_html += f'<td class="recommendations-cell" style="width: {cell_width_pct}; padding: 6px;"></td>'
            row_items.append(None)
        
        row_html += "</tr>"
        rows_html += row_html
    
    section_title_style = f"""
        color: {theme_colors['text']};
        margin: {p3('0 0 8px 0', '0 0 15px 0', '0 0 20px 0')};
        font-size: {p3('15px', '20px', '24px')};
        font-weight: bold;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    table_style = """
        width: 100%;
        border-collapse: collapse;
        padding: 0;
        margin: 0;
        table-layout: fixed;
    """

    return f"""
        <div style="margin: {p3('10px 0', '20px 0', '26px 0')};">
            <h3 style="{section_title_style}">{title}</h3>
            <table class="recommendations-table" style="{table_style}">
                {rows_html}
            </table>
        </div>
    """
