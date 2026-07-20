# Most Watched snap-in (NEWS-17): per-library most watched content as a
# poster card grid (not a stats table), reusing the shared card/grid helpers.
# Scope is all-time: that is what Tautulli's get_library_media_info returns,
# so headings intentionally carry no date range.
from app.emails.builders.card_grid import build_card_html, build_calendar_grid_html, empty_state_html
from app.emails.images import fetch_and_attach_image, truncate_text
from app.security import escape_html_output as esc

import logging

logger = logging.getLogger(__name__)

DEFAULT_ITEM_CAP = 10

def most_watched_heading(library_filter=None):
    return f"Most Watched{f' - {library_filter}' if library_filter else ''}"

def most_watched_items(most_watched_data, library_filter=None, item_cap=0):
    items = []
    if isinstance(most_watched_data, list):
        for entry in most_watched_data:
            if isinstance(entry, dict) and 'most_watched' in entry:
                items.extend(entry['most_watched'])
            elif isinstance(entry, dict) and 'title' in entry:
                items.append(entry)
    if library_filter:
        items = [i for i in items if library_filter.lower() == (i.get('library_name') or '').lower()]
    cap = item_cap or DEFAULT_ITEM_CAP
    return items[:cap]

def most_watched_poster(item, msg_root, cid, base_url, hosted_images_enabled=False, hosted_base_url="", target=None):
    thumb = item.get('thumb') or ''
    if not thumb:
        return None
    proxy = thumb if thumb.startswith('/proxy-art') else f"/proxy-art{thumb if thumb.startswith('/') else '/' + thumb}"
    return fetch_and_attach_image(proxy, msg_root, cid, base_url, target=target, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

def play_count_text(item):
    count = item.get('play_count') or 0
    return f"{count} play{'s' if count != 1 else ''}"

def build_most_watched_html_with_cids(most_watched_data, msg_root, theme_colors, library_filter=None, base_url="", grid_columns=5, poster_max_height=0, item_cap=0, range_text="", hosted_images_enabled=False, hosted_base_url=""):
    heading = most_watched_heading(library_filter)
    if range_text:
        heading += f" ({range_text})"
    items = most_watched_items(most_watched_data, library_filter, item_cap)
    if not items:
        return empty_state_html(theme_colors, f"No most watched items found{f' for {esc(library_filter)}' if library_filter else ''}{f' ({range_text})' if range_text else ''}.")

    cols = max(1, int(grid_columns) if grid_columns else 5)
    poster_px = max(60, int(760 / cols) - 16)
    if poster_max_height:
        poster_px = min(poster_px, max(40, int(int(poster_max_height) * 2 // 3)))
    poster_target = (poster_px, int(round(poster_px * 1.5)))

    cards = []
    for i, item in enumerate(items):
        title = truncate_text(item.get('title', 'Unknown'), 23)
        year = str(item.get('year') or '')
        poster_src = most_watched_poster(item, msg_root, f"mw-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url, target=poster_target)
        card_html = build_card_html(theme_colors, title, year, play_count_text(item), poster_src)
        plex_url = item.get('plex_url', '')
        if plex_url:
            card_html = f'<a href="{esc(plex_url)}" style="text-decoration: none; color: inherit; display: block;" target="_blank" title="Open in Plex">{card_html}</a>'
        cards.append(card_html)

    return build_calendar_grid_html(cards, msg_root, theme_colors, esc(heading), base_url, cols)
