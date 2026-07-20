# Jellywatch client: watch statistics for Jellyfin, filling the role Tautulli
# plays for Plex. Everything returned from here is normalized to the Tautulli
# shapes the app already consumes (home-stats entries as
# {stat_id, stat_title, rows: [...]}) so no builder or layout branches on the
# stats backend. Endpoint paths live in the constants below; if a Jellywatch
# release moves them, this file is the only place to update.
from app.settings_store import get_settings
from app.crypto import decrypt
from app.security import safe_get

import logging

logger = logging.getLogger(__name__)

API_BASE = "/api/v1"
STATUS_PATH = f"{API_BASE}/status"
MOST_WATCHED_PATH = f"{API_BASE}/stats/most-watched"
USERS_PATH = f"{API_BASE}/stats/users"

def get_jellywatch_headers(api_key):
    return {
        'Accept': 'application/json',
        'X-Api-Key': api_key,
    }

def _jellywatch_connection():
    """(base_url, decrypted_api_key) from settings, or (None, None) when
    Jellywatch is not configured."""
    s = get_settings(decrypt_secrets=False)
    url = (s.get('jellywatch_url') or '').rstrip('/')
    key = s.get('jellywatch_api_key') or ''
    if not url or not key:
        return None, None
    return url, decrypt(key)

def ping_jellywatch(url, api_key):
    """Raise-on-failure reachability check used by the connection test."""
    response = safe_get(f"{url.rstrip('/')}{STATUS_PATH}", headers=get_jellywatch_headers(api_key), timeout=10)
    return response

def _first(item, *names, default=None):
    """Jellywatch field names vary by release (PascalCase vs camelCase vs
    snake_case); read the first key that is present so the normalizers do not
    hard-depend on one spelling."""
    for name in names:
        if isinstance(item, dict) and item.get(name) is not None:
            return item.get(name)
    return default

def _normalize_watched_rows(items):
    """Jellywatch most-watched entries -> Tautulli home-stats rows. Only the
    keys the stats builder reads are produced; missing fields degrade to the
    same defaults an empty Tautulli row would carry."""
    rows = []
    for item in items or []:
        item_id = _first(item, 'ItemId', 'itemId', 'id', default='')
        rows.append({
            'title': _first(item, 'Name', 'name', 'title', default='Unknown'),
            'year': str(_first(item, 'ProductionYear', 'year', default='') or ''),
            'total_plays': int(_first(item, 'PlayCount', 'playCount', 'plays', default=0) or 0),
            # Tautulli reports total_duration in seconds; Jellywatch is assumed
            # to report the same. Ticks/ms conversions belong here if a release
            # differs.
            'total_duration': int(_first(item, 'TotalDuration', 'totalDuration', 'seconds', default=0) or 0),
            'content_rating': _first(item, 'OfficialRating', 'contentRating', default='') or '',
            'rating': _first(item, 'CommunityRating', 'rating', default=None),
            'thumb': f"/Items/{item_id}/Images/Primary" if item_id else '',
        })
    return rows

def _normalize_user_rows(items):
    """Jellywatch per-user activity -> Most Active Users rows."""
    rows = []
    for item in items or []:
        user_id = _first(item, 'UserId', 'userId', 'id', default='')
        rows.append({
            'user': _first(item, 'UserName', 'userName', 'name', default='Unknown'),
            'total_plays': int(_first(item, 'PlayCount', 'playCount', 'plays', default=0) or 0),
            'total_duration': int(_first(item, 'TotalDuration', 'totalDuration', 'seconds', default=0) or 0),
            # user_thumb is passed to the avatar helper as-is (unlike movie/show
            # thumbs, which the stats builder proxy-prefixes), so prefix it here
            'user_thumb': f"/proxy-art/Users/{user_id}/Images/Primary" if user_id else '',
        })
    return rows

def _fetch_watched(url, api_key, media_type, days):
    params = {'type': media_type}
    if days:
        params['days'] = days
    try:
        response = safe_get(f"{url}{MOST_WATCHED_PATH}", params=params, headers=get_jellywatch_headers(api_key), timeout=15)
        response.raise_for_status()
        payload = response.json()
    except Exception as e:
        logger.warning(f"Jellywatch most-watched ({media_type}) fetch failed: {e}")
        return []
    # accept either a bare list or {'items': [...]} / {'data': [...]}
    if isinstance(payload, dict):
        payload = payload.get('items') or payload.get('data') or []
    return _normalize_watched_rows(payload)

def _fetch_users(url, api_key, days):
    params = {'days': days} if days else {}
    try:
        response = safe_get(f"{url}{USERS_PATH}", params=params, headers=get_jellywatch_headers(api_key), timeout=15)
        response.raise_for_status()
        payload = response.json()
    except Exception as e:
        logger.warning(f"Jellywatch users fetch failed: {e}")
        return []
    if isinstance(payload, dict):
        payload = payload.get('items') or payload.get('data') or []
    return _normalize_user_rows(payload)

def fetch_jellywatch_home_stats(days=None, include_user_info=True):
    """Home stats in the Tautulli get_home_stats shape:
    [{stat_id, stat_title, rows: [...]}]. Only stats Jellywatch can answer are
    included; a stat with no rows is omitted entirely, so the snap-in list
    naturally offers only what exists (absence is already handled downstream).
    Returns [] when Jellywatch is not configured."""
    url, api_key = _jellywatch_connection()
    if not url:
        return []

    stats = []
    movie_rows = _fetch_watched(url, api_key, 'movie', days)
    if movie_rows:
        stats.append({'stat_id': 'top_movies', 'stat_title': 'Most Watched Movies', 'rows': movie_rows})
    show_rows = _fetch_watched(url, api_key, 'show', days)
    if show_rows:
        stats.append({'stat_id': 'top_tv', 'stat_title': 'Most Watched TV Shows', 'rows': show_rows})
    if include_user_info:
        user_rows = _fetch_users(url, api_key, days)
        if user_rows:
            stats.append({'stat_id': 'top_users', 'stat_title': 'Most Active Users', 'rows': user_rows})
    return stats
