
from app.emails.images import fetch_and_attach_image

import logging

logger = logging.getLogger(__name__)

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
        meta_line = f"{type_icon} {subtitle}" if subtitle else type_icon
        return f"""
        <table cellpadding="0" cellspacing="0" border="0" style="
            background-color: {theme_colors['card_bg']};
            border-radius: 12px;
            width: 120px;
            margin: 0;
        ">
            <tr>
                <td style="padding: 0; line-height: 0; font-size: 0;">
                    <img src="cid:{poster_cid}" alt="{display_title}" width="120" height="180" style="
                        display: block;
                        width: 120px;
                        height: 180px;
                        object-fit: cover;
                        border-radius: 12px 12px 0 0;
                        background-color: #f8f9fa;
                    ">
                </td>
            </tr>
            <tr>
                <td style="padding: 6px;">
                    <div style="
                        font-weight: bold;
                        font-size: 11px;
                        color: {theme_colors['text']};
                        line-height: 1.2;
                        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                    ">{display_title}</div>
                    <div style="
                        font-size: 9px;
                        color: {theme_colors['muted_text']};
                        line-height: 1.2;
                        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                        margin-top: 2px;
                    ">{meta_line}</div>
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
        poster_src = f"cid:{poster_cid}"
        logger.debug(f"Final poster src for {collection_title}: {poster_src}")

        return f"""
            <table cellpadding="0" cellspacing="0" border="0" style="
                background-color: {theme_colors['card_bg']};
                border-radius: 12px;
                width: 120px;
                margin: 0;
            ">
                <tr>
                    <td style="padding: 0; line-height: 0; font-size: 0;">
                        <img src="{poster_src}" alt="{collection_title}" width="120" height="180" style="
                            display: block;
                            width: 120px;
                            height: 180px;
                            object-fit: cover;
                            border-radius: 12px 12px 0 0;
                            background-color: #f8f9fa;
                        ">
                    </td>
                </tr>
                <tr>
                    <td style="padding: 6px;">
                        <div style="
                            font-weight: bold;
                            font-size: 12px;
                            color: {theme_colors['text']};
                            line-height: 1.2;
                            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                        ">{collection_title}</div>
                        <div style="
                            font-size: 10px;
                            color: {theme_colors['muted_text']};
                            line-height: 1.2;
                            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            margin-top: 2px;
                        ">{type_icon} {count} items</div>
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
