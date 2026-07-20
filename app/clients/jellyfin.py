# Jellyfin media server client. Auth is header-based (X-Emby-Token), never a
# query parameter, so tokens cannot leak into email HTML or logs. Every fetch
# normalizes to the shapes the Plex path already produces (the recently-added
# item dict, the Tautulli library list shape) so builders, layouts, previews,
# and goldens from earlier cycles work untouched.
import threading

from datetime import datetime, timedelta, timezone

from app.settings_store import get_settings
from app.crypto import decrypt
from app.security import safe_get

import logging

logger = logging.getLogger(__name__)

# Per-thread health flag mirroring app.clients.plex: a Jellyfin call raised
# while Jellyfin was configured, so the pipeline degraded to cached data.
_jellyfin_health = threading.local()

def reset_jellyfin_health():
    _jellyfin_health.failed = False

def mark_jellyfin_failed():
    _jellyfin_health.failed = True

def jellyfin_call_failed():
    return getattr(_jellyfin_health, 'failed', False)

def get_jellyfin_headers(api_key, extra=None):
    headers = {
        'Accept': 'application/json',
        'X-Emby-Token': api_key,
    }
    if extra:
        headers.update(extra)
    return headers

def _jellyfin_connection():
    """(base_url, decrypted_api_key) from settings, or (None, None) when
    Jellyfin is not configured."""
    s = get_settings(decrypt_secrets=False)
    url = (s.get('jellyfin_url') or '').rstrip('/')
    key = s.get('jellyfin_api_key') or ''
    if not url or not key:
        return None, None
    return url, decrypt(key)

def get_jellyfin_system_info(url, api_key):
    """Raw /System/Info dict (Id, ServerName, Version). Raises on failure so
    the connection test can report the real error."""
    response = safe_get(f"{url.rstrip('/')}/System/Info", headers=get_jellyfin_headers(api_key), timeout=10)
    response.raise_for_status()
    return response.json()

def get_jellyfin_server_id():
    """The Jellyfin server Id, the deep-link equivalent of the Plex machine
    identifier. None when Jellyfin is unconfigured or unreachable."""
    url, api_key = _jellyfin_connection()
    if not url:
        return None
    try:
        return get_jellyfin_system_info(url, api_key).get('Id')
    except Exception as e:
        logger.error(f"Error getting Jellyfin server id: {e}")
        mark_jellyfin_failed()
        return None

def build_jellyfin_web_link(item_id, server_id, jellyfin_web_url=None, jellyfin_url=None):
    """Jellyfin web deep link. Single fallback chokepoint mirroring
    build_plex_web_link: jellyfin_web_url when set, else the server URL
    itself (the bundled web client lives under /web on every install)."""
    if not item_id:
        return ""
    base = (jellyfin_web_url or jellyfin_url or '').rstrip('/')
    if not base:
        return ""
    link = f"{base}/web/index.html#!/details?id={item_id}"
    if server_id:
        link += f"&serverId={server_id}"
    return link

# Jellyfin CollectionType -> the Tautulli section_type vocabulary the rest of
# the app dispatches on. Unlisted types (books, photos, mixed) pass through
# as-is and hit the callers' existing unknown-type fallbacks.
_COLLECTION_TYPE_MAP = {
    'movies': 'movie',
    'tvshows': 'show',
    'music': 'artist',
}

def fetch_jellyfin_libraries():
    """Library list normalized to the Tautulli get_library_names shape:
    [{'section_id', 'section_name', 'section_type'}]. [] on failure."""
    url, api_key = _jellyfin_connection()
    if not url:
        logger.debug("Jellyfin not configured")
        return []
    try:
        response = safe_get(f"{url}/Library/MediaFolders", headers=get_jellyfin_headers(api_key), timeout=10)
        response.raise_for_status()
        items = response.json().get('Items') or []
    except Exception as e:
        logger.exception(f"Error fetching Jellyfin libraries: {e}")
        mark_jellyfin_failed()
        return []

    libraries = []
    for item in items:
        collection_type = (item.get('CollectionType') or '').lower()
        libraries.append({
            'section_id': str(item.get('Id', '')),
            'section_name': item.get('Name', 'Unknown Library'),
            'section_type': _COLLECTION_TYPE_MAP.get(collection_type, collection_type),
        })
    return libraries

def _iso_to_epoch(iso_string):
    """Jellyfin DateCreated ('2026-07-01T12:00:00.1234567Z') to epoch seconds
    as a string, matching the Plex addedAt convention. '' when unparseable."""
    if not iso_string:
        return ''
    try:
        trimmed = iso_string.replace('Z', '+00:00')
        # fromisoformat only accepts up to microseconds; Jellyfin emits ticks
        if '.' in trimmed:
            head, tail = trimmed.split('.', 1)
            frac = ''.join(ch for ch in tail if ch.isdigit())[:6]
            offset = tail[len(''.join(ch for ch in tail if ch.isdigit())):]
            trimmed = f"{head}.{frac}{offset}"
        dt = datetime.fromisoformat(trimmed)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return str(int(dt.timestamp()))
    except (ValueError, TypeError):
        return ''

# Jellyfin item Type -> the media_type vocabulary builders dispatch on.
_ITEM_TYPE_MAP = {
    'Movie': 'movie',
    'Series': 'show',
    'MusicAlbum': 'album',
}

def get_jellyfin_admin_user_id():
    """A user id to scope /Items/Latest calls to (Jellyfin requires one).
    Prefers an administrator; falls back to the first user."""
    url, api_key = _jellyfin_connection()
    if not url:
        return None
    try:
        response = safe_get(f"{url}/Users", headers=get_jellyfin_headers(api_key), timeout=10)
        response.raise_for_status()
        users = response.json() or []
    except Exception as e:
        logger.error(f"Error fetching Jellyfin users: {e}")
        mark_jellyfin_failed()
        return None
    for user in users:
        if (user.get('Policy') or {}).get('IsAdministrator'):
            return user.get('Id')
    return users[0].get('Id') if users else None

def fetch_jellyfin_users():
    """Jellyfin users normalized to the Tautulli get_users subset the app
    consumes: [{user_id, friendly_name, email, is_active}]. Honest limitation:
    Jellyfin does not store user emails, so 'email' is always None and
    recipient lists are managed manually (the email-lists feature covers
    this). [] on failure or when unconfigured."""
    url, api_key = _jellyfin_connection()
    if not url:
        return []
    try:
        response = safe_get(f"{url}/Users", headers=get_jellyfin_headers(api_key), timeout=10)
        response.raise_for_status()
        users = response.json() or []
    except Exception as e:
        logger.exception(f"Error fetching Jellyfin users: {e}")
        mark_jellyfin_failed()
        return []
    normalized = []
    for user in users:
        normalized.append({
            'user_id': str(user.get('Id', '')),
            'friendly_name': user.get('Name', ''),
            'email': None,  # Jellyfin has no user email field
            'is_active': not (user.get('Policy') or {}).get('IsDisabled', False),
        })
    return normalized

def _normalize_jellyfin_item(item, library_name, server_id, jellyfin_web_url, jellyfin_url):
    item_id = str(item.get('Id', ''))
    media_type = _ITEM_TYPE_MAP.get(item.get('Type', ''), (item.get('Type') or '').lower())
    duration_ms = int(item.get('RunTimeTicks') or 0) // 10000
    normalized = {
        'title': item.get('Name', 'Unknown'),
        'rating_key': item_id,
        'year': str(item.get('ProductionYear', '') or ''),
        'thumb': f"/Items/{item_id}/Images/Primary" if (item.get('ImageTags') or {}).get('Primary') else '',
        'art': f"/Items/{item_id}/Images/Backdrop" if item.get('BackdropImageTags') else '',
        'summary': item.get('Overview', '') or '',
        'added_at': _iso_to_epoch(item.get('DateCreated', '')),
        'updated_at': '',
        'content_rating': item.get('OfficialRating', '') or '',
        'duration': str(duration_ms) if duration_ms else '',
        'guid': '',
        'key': '',
        'media_type': media_type,
        'type': media_type,
        'library_name': library_name,
        # key name kept for builder compatibility: every layout reads
        # item['plex_url'] for the deep link regardless of server type
        'plex_url': build_jellyfin_web_link(item_id, server_id, jellyfin_web_url, jellyfin_url),
        'rating': str(item.get('CommunityRating', '') or ''),
    }
    if media_type == 'album':
        normalized['parent_title'] = item.get('AlbumArtist', '') or ''
        normalized['parent_thumb'] = ''
        normalized['leaf_count'] = item.get('ChildCount', 0)
    return normalized

def fetch_jellyfin_latest_for_library(section_id, limit=10, days=None, server_id=None, user_id=None):
    """Latest items in one library, normalized. days mode fetches deep and
    filters by DateCreated; items mode takes the newest `limit`. server_id
    and user_id can be passed by per-library loops so the identity lookups
    happen once per pull."""
    url, api_key = _jellyfin_connection()
    if not url:
        return []
    s = get_settings(decrypt_secrets=False)
    if server_id is None:
        server_id = get_jellyfin_server_id()
    if user_id is None:
        user_id = get_jellyfin_admin_user_id()
    if not user_id:
        return []
    try:
        params = {
            'ParentId': section_id,
            'Limit': 500 if days else limit,
            'Fields': 'Overview,DateCreated,ProductionYear,RunTimeTicks,OfficialRating,CommunityRating,ChildCount',
            'GroupItems': 'true',
        }
        response = safe_get(
            f"{url}/Users/{user_id}/Items/Latest",
            params=params,
            headers=get_jellyfin_headers(api_key),
            timeout=15,
        )
        response.raise_for_status()
        items = response.json() or []
    except Exception as e:
        logger.exception(f"Error fetching Jellyfin latest items for library {section_id}: {e}")
        mark_jellyfin_failed()
        return []

    normalized = [
        _normalize_jellyfin_item(item, '', server_id, s.get('jellyfin_web_url'), s.get('jellyfin_url'))
        for item in items
    ]
    if days:
        cutoff = int((datetime.now() - timedelta(days=int(days))).timestamp())
        normalized = [item for item in normalized if int(item.get('added_at') or 0) >= cutoff]
    return normalized

def fetch_recently_added_using_jellyfin(items_count=10, recently_added_mode="items", recently_added_sort="date"):
    """Jellyfin recently added in the exact recent_data shape the Plex path
    produces: [{'recently_added': [items]}] per library, so the RA snap-in,
    per-library counts, and days/items modes behave identically."""
    recent_data = []
    days_mode = recently_added_mode == "days"
    items_count = int(items_count)

    server_id = get_jellyfin_server_id()
    user_id = get_jellyfin_admin_user_id()
    if not user_id:
        logger.warning("Could not resolve a Jellyfin user for /Items/Latest; recently added unavailable")
        return recent_data

    for library in fetch_jellyfin_libraries():
        if library['section_type'] not in ('movie', 'show', 'artist'):
            continue
        days_val = items_count if days_mode else None
        items = fetch_jellyfin_latest_for_library(library['section_id'], limit=items_count, days=days_val, server_id=server_id, user_id=user_id)
        for item in items:
            item['library_name'] = library['section_name']

        if recently_added_sort == "rating":
            items.sort(key=lambda x: float(x.get('rating', '') or 0), reverse=True)
        if not days_mode:
            items = items[:items_count]
        if items:
            recent_data.append({'recently_added': items})

    return recent_data

def fetch_jellyfin_library_counts():
    """Per-library item counts in the Tautulli get_libraries subset the
    Library Item Counts stat consumes: [{'section_name', 'count'}]."""
    url, api_key = _jellyfin_connection()
    if not url:
        return []
    counts = []
    for library in fetch_jellyfin_libraries():
        try:
            response = safe_get(
                f"{url}/Items",
                params={'ParentId': library['section_id'], 'Recursive': 'true', 'Limit': 0},
                headers=get_jellyfin_headers(api_key),
                timeout=10,
            )
            response.raise_for_status()
            total = response.json().get('TotalRecordCount', 0)
        except Exception as e:
            logger.error(f"Error counting Jellyfin library {library['section_name']}: {e}")
            mark_jellyfin_failed()
            continue
        counts.append({'section_name': library['section_name'], 'count': total})
    return counts
