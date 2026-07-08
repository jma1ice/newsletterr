import json, re

from app.cache import get_cache_info
from app.emails.images import fetch_and_attach_image
from app.emails.blocks import build_graph_html_with_frontend_image, build_text_block_html, build_separator_html, build_image_html_with_cid, build_emoji_html
from app.emails.builders import build_stats_html_with_cid_background, build_recently_added_html_with_cids, build_recommendations_html_with_cids, build_droppedneedle_wrapped_html_with_cids, build_droppedneedle_server_stats_html_with_cids, build_collections_html_with_cids
from app.theme import get_email_theme_colors, build_email_css_from_theme

def convert_html_to_plain_text(html_content):
    html_content = re.sub(r'<script.*?</script>', '', html_content, flags=re.DOTALL)
    html_content = re.sub(r'<style.*?</style>', '', html_content, flags=re.DOTALL)
    
    html_content = re.sub(r'<br\s*/?>', '\n', html_content)
    html_content = re.sub(r'</p>', '\n\n', html_content)
    html_content = re.sub(r'</div>', '\n', html_content)
    html_content = re.sub(r'<h[1-6][^>]*>', '\n\n', html_content)
    html_content = re.sub(r'</h[1-6]>', '\n', html_content)
    
    html_content = re.sub(r'<[^>]+>', '', html_content)
    
    html_content = re.sub(r'\n\s*\n', '\n\n', html_content)
    html_content = html_content.strip()
    
    return html_content

def attach_logo_image(msg_root, logo_filename, custom_logo_filename, base_url=""):
    if logo_filename == 'custom':
        logo_url = f"/static/uploads/logos/{custom_logo_filename}"
    else:
        logo_url = f"/static/img/{logo_filename}"
    return fetch_and_attach_image(logo_url, msg_root, "logo", base_url)

def build_email_html_with_all_cids(template_data, tautulli_data, msg_root, display_preference, users_data, recommendations_data=None, user_dict=None, base_url="", target_user_key=None, is_scheduled=False, items_count=None, date_range="", expanded_collections=None, email_header_title=None, droppedneedle_wrapped_data=None, droppedneedle_server_data=None):
    custom_html = template_data.get('custom_html', '').strip()
    if custom_html:
        return custom_html
    selected_items = json.loads(template_data.get('selected_items', '[]'))
    email_text = template_data.get('email_text', '')
    subject = template_data.get('subject', '')
    server_name = tautulli_data.get('settings', {}).get('server_name', 'Plex Server')
    logo_filename = tautulli_data.get('settings', {}).get('logo_filename')
    custom_logo_filename = tautulli_data.get('settings', {}).get('custom_logo_filename')
    logo_width = tautulli_data.get('settings', {}).get('logo_width')
    logo_position = tautulli_data.get('settings', {}).get('logo_position', 'center')
    hide_stat_play_counts = tautulli_data.get('settings', {}).get('hide_stat_play_counts', 'disabled') == 'enabled'
    show_cover_art = tautulli_data.get('settings', {}).get('stat_cover_art', 'disabled') == 'enabled'
    recently_added_mode = tautulli_data.get('settings', {}).get('recently_added_mode', 'items')
    ra_grid_columns = int(tautulli_data.get('settings', {}).get('ra_grid_columns', 5) or 5)
    recs_grid_columns = int(tautulli_data.get('settings', {}).get('recs_grid_columns', 5) or 5)
    poster_max_height = int(tautulli_data.get('settings', {}).get('poster_max_height') or 0)
    _default_intro = tautulli_data.get('settings', {}).get('default_intro_text') or ''
    _default_outro = tautulli_data.get('settings', {}).get('default_outro_text') or ''
    _resolved_intro = _default_intro or f"You are receiving this email because you are a member of {server_name}."
    _resolved_outro = _default_outro or 'Thanks for using Plex and for reading this newsletterr email!'
    expanded_collections = expanded_collections or {}
    email_header_title = email_header_title or ''
    
    theme_colors = get_email_theme_colors()

    if logo_filename == '' or logo_filename is None:
        if theme_colors['email_theme'] == 'custom':
            pass
        else:
            logo_filename = 'Asset_94x.png'

    if logo_width == '' or logo_width is None:
        if theme_colors['email_theme'] == 'custom':
            pass
        else:
            logo_width = 80
    
    logo_src = ""
    if logo_filename != '' and logo_filename is not None and logo_width != '' and logo_width is not None:
        logo_cid = attach_logo_image(msg_root, logo_filename, custom_logo_filename, base_url)
        if logo_filename == 'custom' and custom_logo_filename:
            logo_src = f"cid:{logo_cid}" if logo_cid else f"/static/uploads/logos/{custom_logo_filename}"
        else:
            logo_src = f"cid:{logo_cid}" if logo_cid else f"/static/img/{logo_filename}"
    
    content_html = ""
    
    if email_text.strip():
        email_text_resolved = email_text.replace('__DEFAULT_INTRO__', _resolved_intro).replace('__DEFAULT_OUTRO__', _resolved_outro)
        content_html += build_text_block_html(email_text_resolved, 'textblock', theme_colors)

    for group_index, item in enumerate(selected_items):
        item_type = item.get('type', '')

        if item_type in ['textblock', 'titleblock', 'headerblock']:
            content = item.get('content', '').strip()
            if content == '__DEFAULT_INTRO__':
                content = _resolved_intro
            elif content == '__DEFAULT_OUTRO__':
                content = _resolved_outro
            if content:
                content_html += build_text_block_html(content, item_type, theme_colors)

        elif item_type == 'separator':
            content_html += build_separator_html(theme_colors)

        elif item_type in ('image', 'gif'):
            content_html += build_image_html_with_cid(item, msg_root, base_url)

        elif item_type == 'emoji':
            content_html += build_emoji_html(item, theme_colors)
        
        elif item_type == 'stat':
            stat_index = int(item['id'].split('-')[1])
            if stat_index < len(tautulli_data.get('stats', [])):
                stat_data = tautulli_data['stats'][stat_index]
                content_html += build_stats_html_with_cid_background(stat_data, msg_root, theme_colors, base_url, date_range, hide_play_counts=hide_stat_play_counts, show_cover_art=show_cover_art)
        
        elif item_type == 'graph':
            content_html += build_graph_html_with_frontend_image(item, msg_root)
        
        elif item_type == 'recently added':
            library_filter = item.get('raLibrary')
            recent_data = tautulli_data.get('recent_data', [])

            max_items = items_count
            if max_items is None:
                cache_info = get_cache_info('recent_data')
                if cache_info.get('params'):
                    try:
                        max_items = int(cache_info['params'].get('count', 10))
                    except (TypeError, ValueError):
                        max_items = 10

            content_html += build_recently_added_html_with_cids(recent_data, msg_root, theme_colors, library_filter, base_url, max_items, recently_added_mode=recently_added_mode, ra_grid_columns=ra_grid_columns, poster_max_height=poster_max_height)
        
        elif item_type == 'recommendations':
            if recommendations_data:
                if target_user_key:
                    if item.get('userKey') == str(target_user_key):
                        filtered_recommendations = {target_user_key: recommendations_data.get(target_user_key, {})}
                        filtered_user_dict = {target_user_key: user_dict.get(target_user_key, target_user_key)} if user_dict else {target_user_key: target_user_key}
                        content_html += build_recommendations_html_with_cids(filtered_recommendations, msg_root, theme_colors, filtered_user_dict, base_url, display_preference, users_data, recs_grid_columns=recs_grid_columns, poster_max_height=poster_max_height)
                else:
                    content_html += build_recommendations_html_with_cids(recommendations_data, msg_root, theme_colors, user_dict, base_url, display_preference, users_data, recs_grid_columns=recs_grid_columns, poster_max_height=poster_max_height)

        elif item_type == 'droppedneedle_wrapped':
            if droppedneedle_wrapped_data:
                if target_user_key:
                    if item.get('userKey') == str(target_user_key):
                        filtered_wrapped = {target_user_key: droppedneedle_wrapped_data.get(target_user_key, {})}
                        filtered_user_dict = {target_user_key: user_dict.get(target_user_key, target_user_key)} if user_dict else {target_user_key: target_user_key}
                        content_html += build_droppedneedle_wrapped_html_with_cids(filtered_wrapped, msg_root, theme_colors, filtered_user_dict, display_preference, users_data)
                else:
                    content_html += build_droppedneedle_wrapped_html_with_cids(droppedneedle_wrapped_data, msg_root, theme_colors, user_dict, display_preference, users_data)

        elif item_type == 'droppedneedle_server_stats':
            if droppedneedle_server_data:
                content_html += build_droppedneedle_server_stats_html_with_cids(droppedneedle_server_data, msg_root, theme_colors)

        elif item_type == 'collection_group':
            group_title = item.get('title', 'Collections')
            group_collections = item.get('collections', [])
            if group_collections:
                content_html += build_collections_html_with_cids(group_collections, msg_root, theme_colors, base_url, group_title, expanded_collections, group_index, poster_max_height=poster_max_height)

    return build_complete_email_html_with_cid_logo(content_html, server_name, subject, email_header_title, logo_src, logo_width, is_scheduled, logo_position=logo_position)

def build_complete_email_html_with_cid_logo(content_html, server_name, subject, email_header_title, logo_src, logo_width, is_scheduled=False, logo_position='center'):
    theme_colors = get_email_theme_colors()
    
    css = build_email_css_from_theme(theme_colors, logo_width)
    
    body_style = f"""
        margin: 0;
        padding: 0;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
        background-color: {theme_colors['background']};
        line-height: 1.6;
        color: {theme_colors['text']};
        -webkit-text-size-adjust: 100%;
        -ms-text-size-adjust: 100%;
    """
    
    container_style = f"""
        width: 100%;
        max-width: 800px;
        margin: 0 auto;
        background-color: {theme_colors['card_bg']};
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        border: 1px solid {theme_colors['border']};
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    header_style = f"""
        background: linear-gradient(135deg, {theme_colors['accent']} 0%, {theme_colors['primary']} 100%);
        color: white;
        padding: 10px 20px;
        text-align: center;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    _logo_margin_left  = '0'    if logo_position == 'left'  else 'auto'
    _logo_margin_right = '0'    if logo_position == 'right' else 'auto'
    logo_style = f"""
        max-width: {logo_width}px;
        width: auto;
        height: auto;
        margin-bottom: 15px;
        border: 0;
        line-height: 100%;
        outline: none;
        text-decoration: none;
        display: block;
        margin-left: {_logo_margin_left};
        margin-right: {_logo_margin_right};
    """
    
    title_style = """
        font-size: 28px;
        font-weight: bold;
        margin: 0;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
        color: white;
    """
    
    content_style = f"""
        padding: 10px 15px;
        color: {theme_colors['text']};
        background-color: {theme_colors['card_bg']};
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    footer_style = f"""
        background-color: {theme_colors['secondary']};
        padding: 20px;
        text-align: center;
        border-top: 3px solid {theme_colors['primary']};
        color: {theme_colors['muted_text']};
        font-size: 12px;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    footer_link_style = f"""
        color: {theme_colors['accent']};
        text-decoration: none;
    """

    logo_html = ""
    if logo_src != "" and logo_src is not None and logo_width != "" and logo_width is not None:
        logo_html = f'<img src="{logo_src}" alt="{server_name}" class="email-logo" style="{logo_style}">'

    title_html = f'<h1 style="{title_style}">{email_header_title}</h1>'
    
    return f"""<!DOCTYPE html>
        <html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <meta http-equiv="X-UA-Compatible" content="IE=edge">
                <meta name="x-apple-disable-message-reformatting">
                <meta name="format-detection" content="telephone=no">
                <title>{subject}</title>
                <!--[if mso]>
                <noscript>
                    <xml>
                        <o:OfficeDocumentSettings>
                            <o:PixelsPerInch>96</o:PixelsPerInch>
                        </o:OfficeDocumentSettings>
                    </xml>
                </noscript>
                <![endif]-->
                {css}
            </head>
            <body style="{body_style}">
                <div style="width: 100%; background-color: {theme_colors['background']}; padding: 20px 0;">
                    <!--[if mso | IE]>
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" align="center" style="width:8;">
                    <tr>
                    <td>
                    <![endif]-->
                    <div class="email-container" style="{container_style}">
                        <div style="{header_style}">
                            {logo_html}
                            {title_html}
                        </div>
                        
                        <div style="{content_style}">
                            {content_html}
                        </div>
                        
                        <div style="{footer_style}">
                            <div style="margin-bottom: 10px;">
                                Generated for Plex Media Server by 
                                <a href="https://github.com/jma1ice/newsletterr" style="{footer_link_style}">newsletterr</a>
                            </div>
                            <div>
                                newsletterr is not affiliated with or a product of Plex, Inc.
                            </div>
                        </div>
                    </div>
                    <!--[if mso | IE]>
                    </td>
                    </tr>
                    </table>
                    <![endif]-->
                </div>
            </body>
        </html>"""
