
from app.settings_store import get_settings
from app.clients.plex import get_collection_items_for_email

import logging

logger = logging.getLogger(__name__)

from app.emails.builders.cards import build_collection_card_html, build_individual_item_card_html

def build_collections_html_with_cids(all_collections, msg_root, theme_colors, base_url="", custom_title=None, expanded_collections=None, group_index=0, poster_max_height=0, grid_columns=5, hosted_images_enabled=False, hosted_base_url=""):
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
    items_per_row = max(1, int(grid_columns) if grid_columns else 5)
    # Cards are fixed width; derive it from the column count so N=5 keeps the
    # historical 120px card and higher counts shrink to avoid row overflow.
    card_width = max(60, min(240, int(600 / items_per_row)))
    cell_width_pct = f"{100 / items_per_row:.4f}%"

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
