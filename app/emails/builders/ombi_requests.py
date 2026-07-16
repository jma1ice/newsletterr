# Reuses the card/grid HTML pattern from coming_soon.py (Radarr/Sonarr).
from datetime import datetime, timezone

from app.emails.builders.card_grid import empty_state_html as _empty_state_html, build_calendar_grid_html as _build_calendar_grid_html, build_card_html as _build_card_html, format_relative_date as _format_relative_date
from app.emails.images import fetch_and_attach_image, truncate_text

import logging

logger = logging.getLogger(__name__)

# Ombi's posterPath is a TMDB-relative fragment (e.g. "/xyz.jpg"); the
# poster itself is a public TMDB CDN asset, so it can be fetched directly
# with no Ombi auth, same as the *arr remoteUrl fallback in coming_soon.py.
TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w300"

def _poster_src(poster_path):
    if not poster_path:
        return None
    if poster_path.startswith('http'):
        return poster_path
    return f"{TMDB_POSTER_BASE}{poster_path}"

def _parse_ombi_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
    except Exception:
        logger.debug("suppressed exception; using fallback", exc_info=True)
        return None

def _normalize_movie_request(req):
    return {
        'title': req.get('title', 'Unknown'),
        'year': (req.get('releaseDate') or '')[:4],
        'poster': req.get('posterPath'),
        'approved': bool(req.get('approved')),
        'available': bool(req.get('available')),
        'denied': bool(req.get('denied')),
        'requested_date': req.get('requestedDate'),
    }

def _normalize_tv_request(req):
    """TV requests carry their approved/available/denied state per-season on
    childRequests; a show is treated as pending as long as any season is."""
    children = req.get('childRequests') or []
    if not children:
        return None
    pending_children = [c for c in children if not c.get('available') and not c.get('denied')]
    relevant = pending_children or children
    requested_dates = [c.get('requestedDate') for c in children if c.get('requestedDate')]
    # No pending_children means every season is resolved (available/denied, in
    # any mix) with nothing actionable left, so treat the whole entry as
    # resolved and let 'available' alone drive the drop in filter_ombi_pending.
    resolved = not pending_children
    return {
        'title': req.get('title', 'Unknown'),
        'year': (req.get('releaseDate') or '')[:4],
        'poster': req.get('posterPath'),
        'approved': any(c.get('approved') for c in relevant),
        'available': resolved,
        'denied': False,
        'requested_date': max(requested_dates) if requested_dates else None,
    }

def filter_ombi_pending(data):
    """data is {'movies': [...], 'tv': [...]} as returned by
    get_ombi_requests_cached. Drops fulfilled (available) or denied requests
    and returns a combined list sorted by requestedDate, most recent first."""
    data = data or {}
    entries = []
    for req in data.get('movies') or []:
        entry = _normalize_movie_request(req)
        if entry['available'] or entry['denied']:
            continue
        entries.append(entry)
    for req in data.get('tv') or []:
        entry = _normalize_tv_request(req)
        if entry is None or entry['available'] or entry['denied']:
            continue
        entries.append(entry)

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    entries.sort(key=lambda e: _parse_ombi_date(e['requested_date']) or epoch, reverse=True)
    return entries

def build_ombi_requests_html_with_cids(data, msg_root, theme_colors, base_url="", grid_columns=5, hosted_images_enabled=False, hosted_base_url=""):
    entries = filter_ombi_pending(data)
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
            poster_src = fetch_and_attach_image(poster_url, msg_root, f"ombi-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

        cards.append(_build_card_html(theme_colors, truncate_text(entry['title'], 23), entry['year'], meta_text, poster_src))

    return _build_calendar_grid_html(cards, msg_root, theme_colors, "Recent Requests", base_url, grid_columns)
