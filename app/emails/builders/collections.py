
from app.cache import get_cached_data, set_cached_data
from app.emails.builders.card_grid import EMPTY_STATE_MARKER
from app.emails import density, headings
from app.settings_store import get_settings
from app.clients.plex import get_collection_items_for_email
from app.security import escape_html_output as esc

import logging

logger = logging.getLogger(__name__)

def _collection_items(collection_key, plex_settings):
    cache_key = f"collection_items:{collection_key}"
    cached = get_cached_data(cache_key, strict=False)
    if cached is not None:
        return cached

    items = get_collection_items_for_email(collection_key, plex_settings)
    set_cached_data(cache_key, items)
    return items

from app.emails.builders.cards import build_collection_card_html, build_individual_item_card_html

def resolve_collection_items(all_collections, expanded_collections=None, group_index=0):
    expanded_collections = expanded_collections or {}
    all_items_to_display = []

    _s = get_settings(decrypt_secrets=False)
    row = (_s.get("plex_url"), _s.get("plex_token")) if "id" in _s else None

    plex_settings = None
    if row and row[0] and row[1]:
        plex_settings = {
            'plex_url': row[0],
            'plex_token': row[1],
            'plex_web_url': _s.get("plex_web_url")
        }

    for collection_index, collection in enumerate(all_collections or []):
        collection_key = collection.get('key')
        collection_id = f"{group_index}-{collection_index}-{collection_key}"

        if collection_id in expanded_collections and plex_settings:
            logger.debug(f"Collection {collection_id} is expanded, fetching individual items...")
            for item in _collection_items(collection_key, plex_settings):
                item['is_individual_item'] = True
                item['original_collection'] = collection.get('title', 'Unknown Collection')
                all_items_to_display.append(item)
        else:
            collection['is_individual_item'] = False
            all_items_to_display.append(collection)

    return all_items_to_display

def build_collections_html_with_cids(all_collections, msg_root, theme_colors, base_url="", custom_title=None, expanded_collections=None, group_index=0, poster_max_height=0, grid_columns=5, hosted_images_enabled=False, hosted_base_url=""):
    if not all_collections:
        return f"""
        <div {EMPTY_STATE_MARKER} style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
            <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">No collections available.</p>
        </div>
        """
    
    all_items_to_display = resolve_collection_items(all_collections, expanded_collections, group_index)
    
    p3 = density.picker3(theme_colors)
    art_on = density.show_art(theme_colors)

    items_html = ""
    if not art_on:
        items_html = _compact_collection_rows_html(all_items_to_display, theme_colors)
    items_per_row = max(1, int(grid_columns) if grid_columns else 5)
    # Cards are fixed width; derive it from the column count so N=5 keeps the
    # historical 120px card and higher counts shrink to avoid row overflow.
    card_width = max(60, min(240, int(600 / items_per_row)))
    cell_width_pct = f"{100 / items_per_row:.4f}%"

    for i in range(0, len(all_items_to_display) if art_on else 0, items_per_row):
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
                    card_html = build_individual_item_card_html(item, theme_colors, msg_root, base_url, poster_max_height=poster_max_height, card_width=card_width, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)
                else:
                    card_html = build_collection_card_html(item, theme_colors, msg_root, base_url, poster_max_height=poster_max_height, card_width=card_width, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

                row_html += f'<td style="vertical-align: top; padding-right: {cell_spacing};">{card_html}</td>'

            row_html += '</tr></table></td></tr>'
            items_html += row_html
        else:
            row_html = "<tr style='text-align: center;'>"

            for j, item in enumerate(row_items):
                cell_style = f"""
                    width: {cell_width_pct};
                    padding: 8px;
                    vertical-align: top;
                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                """

                if item.get('is_individual_item'):
                    card_html = build_individual_item_card_html(item, theme_colors, msg_root, base_url, poster_max_height=poster_max_height, card_width=card_width, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)
                else:
                    card_html = build_collection_card_html(item, theme_colors, msg_root, base_url, poster_max_height=poster_max_height, card_width=card_width, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)
                
                row_html += f'<td style="{cell_style}">{card_html}</td>'
            
            row_html += "</tr>"
            items_html += row_html
    
    container_style = f"""
        background-color: {theme_colors['card_bg']};
        border-radius: 8px;
        margin: {p3('10px 0', '20px 0', '28px 0')};{' padding: 4px 14px 10px 14px;' if not art_on else ''}
        border: 1px solid {theme_colors['border']};
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    title_style = f"""
        text-align: center;
        color: {theme_colors['text']};
        margin: {p3('0 0 6px 0', '0 0 20px 0', '0 0 26px 0')};{' padding-top: 10px;' if not art_on else ''}
        font-size: {p3('17px', '24px', '30px')};
        font-weight: bold;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    table_style = """
        width: 100%;
        border-collapse: collapse;
        margin: 0;
        padding: 0;
    """

    display_title = headings.resolve(theme_colors, custom_title if custom_title else "Collections")
    title_html = f'<h2 style="{title_style}">{esc(display_title)}</h2>' if display_title else ''

    return f"""
        <div style="{container_style}">
            {title_html}
            <table cellpadding="0" cellspacing="0" border="0" style="{table_style}">
                {items_html}
            </table>
        </div>
    """

def _compact_collection_rows_html(items, theme_colors):
    _FONT = "'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif"
    rows = ""
    for i, item in enumerate(items):
        title = item.get('title', 'Unknown')
        if item.get('is_individual_item'):
            meta_bits = [str(item.get('year') or ''), item.get('original_collection') or '']
        else:
            count = item.get('childCount', 0)
            meta_bits = [f"{count} item" + ("s" if str(count) != "1" else "")]
        meta = ' &middot; '.join(esc(str(b)) for b in meta_bits if b)
        border = "" if i == len(items) - 1 else f" border-bottom: 1px solid {theme_colors['border']};"
        rows += f"""
            <tr>
                <td style="padding: 6px 0;{border} font-size: 13px; font-weight: bold; color: {theme_colors['text']}; font-family: {_FONT};">{esc(title)}</td>
                <td align="right" style="padding: 6px 0;{border} font-size: 11px; color: {theme_colors['muted_text']}; white-space: nowrap; font-family: {_FONT};">{meta}</td>
            </tr>
        """
    return rows
