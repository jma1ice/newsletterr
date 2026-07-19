# Seerr (the merged Overseerr/Jellyseerr project) and its predecessors all
# expose the same /api/v1 surface. Unlike Ombi, the request list endpoint carries only TMDB ids (no
# title/year/poster), so each kept request is enriched here via the seerr
# movie/tv detail endpoints before caching.
import requests

from app.security import safe_get

import logging

logger = logging.getLogger(__name__)

# Request list page size; also bounds the number of detail lookups per pull.
REQUEST_TAKE = 40

# MediaRequestStatus: 1 pending approval, 2 approved, 3 declined, 4 failed.
# MediaStatus (media.status): 1 unknown, 2 pending, 3 processing,
# 4 partially available, 5 available.
def _fetch_details(base_url, api_key, media_type, tmdb_id):
    """Returns {'title', 'releaseDate', 'posterPath'} or None on failure."""
    endpoint = 'movie' if media_type == 'movie' else 'tv'
    try:
        response = safe_get(
            f"{base_url}/api/v1/{endpoint}/{tmdb_id}",
            headers={'X-Api-Key': api_key},
        )
        response.raise_for_status()
        details = response.json()
    except (requests.exceptions.RequestException, ValueError) as e:
        logger.warning(f"Seerr detail lookup failed for {endpoint}/{tmdb_id}: {e}")
        return None
    if media_type == 'movie':
        return {
            'title': details.get('title'),
            'releaseDate': details.get('releaseDate'),
            'posterPath': details.get('posterPath'),
        }
    return {
        'title': details.get('name'),
        'releaseDate': details.get('firstAirDate'),
        'posterPath': details.get('posterPath'),
    }

def fetch_seerr_requests(base_url, api_key, progress_cb=None):
    """Returns (entries, error). entries is a list of normalized seerr request
    dicts (title/year/poster already resolved via detail lookups), or [] on
    any failure. Declined/failed/fully-available requests are skipped before
    enrichment so they never cost a detail lookup. progress_cb, when given,
    is called with (processed, total) as the result list is walked; the
    caller owns any progress state (clients stay agnostic)."""
    if not base_url or not api_key:
        return [], "Seerr Error: URL and API key are required"
    base_url = base_url.rstrip('/')
    try:
        response = safe_get(
            f"{base_url}/api/v1/request",
            params={'take': REQUEST_TAKE, 'skip': 0, 'sort': 'added', 'filter': 'all'},
            headers={'X-Api-Key': api_key},
        )
        response.raise_for_status()
        results = response.json().get('results') or []
    except (requests.exceptions.RequestException, ValueError) as e:
        return [], f"Seerr Error: {e}"

    entries = []
    details_cache = {}
    if progress_cb and results:
        try:
            progress_cb(0, len(results))
        except Exception:
            logger.debug("suppressed progress callback error", exc_info=True)
    for req_index, req in enumerate(results, 1):
        if progress_cb:
            try:
                progress_cb(req_index, len(results))
            except Exception:
                logger.debug("suppressed progress callback error", exc_info=True)
        media = req.get('media') or {}
        media_type = media.get('mediaType')
        tmdb_id = media.get('tmdbId')
        if media_type not in ('movie', 'tv') or not tmdb_id:
            continue
        # Same drop rules as filter_seerr_pending; skipping here just avoids
        # detail lookups for entries the builder would discard anyway.
        if req.get('status') not in (1, 2) or (media.get('status') or 0) >= 5:
            continue
        key = (media_type, tmdb_id)
        if key not in details_cache:
            details_cache[key] = _fetch_details(base_url, api_key, media_type, tmdb_id)
        details = details_cache[key] or {}
        requester = req.get('requestedBy') or {}
        entries.append({
            'mediaType': media_type,
            'title': details.get('title') or 'Unknown',
            'releaseDate': details.get('releaseDate') or '',
            'posterPath': details.get('posterPath'),
            'status': req.get('status'),
            'mediaStatus': media.get('status'),
            'requestedDate': req.get('createdAt'),
            'requestedBy': requester.get('displayName') or requester.get('plexUsername') or requester.get('username') or '',
        })
    return entries, None
