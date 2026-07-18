# Reuses the card/grid HTML pattern from coming_soon.py (Radarr/Sonarr).
# Entries arrive pre-enriched by app/clients/seerr.py (title/year/poster
# resolved at fetch time), so this builder only filters and renders.
from datetime import datetime, timezone

from app.emails.builders.card_grid import empty_state_html as _empty_state_html, build_calendar_grid_html as _build_calendar_grid_html, build_card_html as _build_card_html, format_relative_date as _format_relative_date
from app.emails.images import fetch_and_attach_image, truncate_text

import logging

logger = logging.getLogger(__name__)

# Seerr's posterPath is a TMDB-relative fragment (e.g. "/xyz.jpg"); the
# poster itself is a public TMDB CDN asset, so it can be fetched directly
# with no seerr auth, same as the Ombi builder.
TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w300"

def _poster_src(poster_path):
    if not poster_path:
        return None
    if poster_path.startswith('http'):
        return poster_path
    return f"{TMDB_POSTER_BASE}{poster_path}"

def _parse_seerr_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
    except Exception:
        logger.debug("suppressed exception; using fallback", exc_info=True)
        return None

def filter_seerr_pending(data):
    """data is {'requests': [...]} as returned by get_seerr_requests_cached.
    Keeps pending (status 1) and approved (status 2) requests whose media is
    not yet fully available (mediaStatus < 5; partially available TV still
    counts as pending) and returns them sorted by requestedDate, most recent
    first. The client already drops these before caching; re-filtering here
    keeps stale caches and the JS preview mirrors consistent."""
    data = data or {}
    entries = []
    for req in data.get('requests') or []:
        if req.get('status') not in (1, 2):
            continue
        if (req.get('mediaStatus') or 0) >= 5:
            continue
        entries.append({
            'title': req.get('title') or 'Unknown',
            'year': (req.get('releaseDate') or '')[:4],
            'poster': req.get('posterPath'),
            'approved': req.get('status') == 2,
            'requested_date': req.get('requestedDate'),
        })

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    entries.sort(key=lambda e: _parse_seerr_date(e['requested_date']) or epoch, reverse=True)
    return entries

def build_seerr_requests_html_with_cids(data, msg_root, theme_colors, base_url="", grid_columns=5, hosted_images_enabled=False, hosted_base_url=""):
    entries = filter_seerr_pending(data)
    if not entries:
        return _empty_state_html(theme_colors, "No pending or approved requests found.")

    cards = []
    for i, entry in enumerate(entries):
        status = "Approved" if entry['approved'] else "Pending Approval"
        relative = _format_relative_date(entry['requested_date'])
        meta_text = truncate_text(' • '.join(filter(None, [status, f'Requested {relative}' if relative else ''])), 46)

        poster_src = None
        poster_url = _poster_src(entry['poster'])
        if poster_url:
            poster_src = fetch_and_attach_image(poster_url, msg_root, f"seerr-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

        cards.append(_build_card_html(theme_colors, truncate_text(entry['title'], 23), entry['year'], meta_text, poster_src))

    return _build_calendar_grid_html(cards, msg_root, theme_colors, "Recent Requests", base_url, grid_columns)
