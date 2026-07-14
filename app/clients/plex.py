import threading
import uuid

from datetime import datetime, timedelta
from urllib.parse import quote_plus

from app import config
from app.db import db_connect
from app.settings_store import get_settings
from app.crypto import decrypt
from app.security import safe_get
from app.clients.tautulli import run_tautulli_command

import logging

logger = logging.getLogger(__name__)

# Per-thread health flag: a Plex SDK call raised while Plex was configured, so
# the pipeline silently degraded to Tautulli/cached data. Thread-local keeps
# the request thread's pull separate from the scheduler thread's sends.
_plex_health = threading.local()

def reset_plex_health():
    _plex_health.failed = False

def mark_plex_failed():
    _plex_health.failed = True

def plex_call_failed():
    return getattr(_plex_health, 'failed', False)

def get_plex_client_identifier():
    try:
        _s = get_settings(decrypt_secrets=False)
        row = (_s.get("plex_client_id"),) if "id" in _s else None
        if row and row[0]:
            return row[0]
        client_id = str(uuid.uuid4())
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET plex_client_id = ? WHERE id = 1", (client_id,))
        conn.commit()
        conn.close()
        return client_id
    except Exception:
        logger.debug("suppressed exception; using fallback", exc_info=True)
        return str(uuid.uuid4())

def get_plex_headers(extra=None):
    headers = {
        'Accept': 'application/json',
        'X-Plex-Client-Identifier': get_plex_client_identifier(),
        'X-Plex-Product': 'Newsletterr',
        'X-Plex-Device-Name': 'Newsletterr',
        'X-Plex-Version': config.VERSION,
    }
    if extra:
        headers.update(extra)
    return headers

def get_plex_machine_id():
    try:
        _s = get_settings(decrypt_secrets=False)
        plex_settings = (_s.get("plex_url"), _s.get("plex_token")) if "id" in _s else None
        
        if not plex_settings or not plex_settings[0] or not plex_settings[1]:
            return None
        
        plex_url = plex_settings[0].rstrip('/')
        plex_token = decrypt(plex_settings[1])

        headers = get_plex_headers({'X-Plex-Token': plex_token})
        response = safe_get(f"{plex_url}/identity", headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get('MediaContainer', {}).get('machineIdentifier')
    except Exception as e:
        logger.error(f"Error getting Plex machine ID: {e}")
        mark_plex_failed()
        return None

def build_plex_web_link(rating_key, machine_id):
    if not machine_id or not rating_key:
        return ""
    
    return f"https://app.plex.tv/web/app#!/server/{machine_id}/details?key=/library/metadata/{rating_key}"

def search_plex_for_rating_key(title, year, media_type, plex_url, plex_token, tmdb_id=None):
    try:
        decrypted_token = decrypt(plex_token)
        
        if tmdb_id:
            search_query = quote_plus(title)
            api_url = f"{plex_url}/search?query={search_query}&X-Plex-Token={decrypted_token}"
            
            headers = get_plex_headers()
            
            response = safe_get(api_url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            for provider in data.get('MediaContainer', {}).get('Metadata', []):
                item_type = provider.get('type', '')
                
                if (media_type == 'movie' and item_type == 'movie') or \
                   (media_type == 'show' and item_type == 'show'):
                    
                    guids = provider.get('Guid', [])
                    if isinstance(guids, list):
                        for guid_obj in guids:
                            if isinstance(guid_obj, dict):
                                guid_id = guid_obj.get('id', '')
                                if f"tmdb://{tmdb_id}" in guid_id or f"themoviedb://{tmdb_id}" in guid_id:
                                    logger.debug(f"Found exact TMDB match for {title} (tmdb:{tmdb_id})")
                                    return provider.get('ratingKey')
                    
                    single_guid = provider.get('guid', '')
                    if f"tmdb://{tmdb_id}" in single_guid or f"themoviedb://{tmdb_id}" in single_guid:
                        logger.debug(f"Found exact TMDB match for {title} (tmdb:{tmdb_id})")
                        return provider.get('ratingKey')
        
        search_query = quote_plus(title)
        api_url = f"{plex_url}/search?query={search_query}&X-Plex-Token={decrypted_token}"
        
        headers = get_plex_headers()
        
        response = safe_get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        best_match = None
        for provider in data.get('MediaContainer', {}).get('Metadata', []):
            item_title = provider.get('title', '').lower()
            item_year = str(provider.get('year', ''))
            item_type = provider.get('type', '')
            
            if not ((media_type == 'movie' and item_type == 'movie') or \
                    (media_type == 'show' and item_type == 'show')):
                continue
            
            if tmdb_id:
                guids = provider.get('Guid', [])
                guid_match = False
                
                if isinstance(guids, list):
                    for guid_obj in guids:
                        if isinstance(guid_obj, dict):
                            guid_id = guid_obj.get('id', '')
                            if f"tmdb://{tmdb_id}" in guid_id or f"themoviedb://{tmdb_id}" in guid_id:
                                guid_match = True
                                break
                
                single_guid = provider.get('guid', '')
                if f"tmdb://{tmdb_id}" in single_guid or f"themoviedb://{tmdb_id}" in single_guid:
                    guid_match = True
                
                if guid_match:
                    logger.debug(f"Found TMDB match for {title} via fallback search (tmdb:{tmdb_id})")
                    return provider.get('ratingKey')
            
            title_match = title.lower() in item_title or item_title in title.lower()
            year_match = not year or str(year) == item_year
            
            if title_match and year_match:
                if item_title == title.lower():
                    logger.debug(f"Found exact title match for {title}")
                    return provider.get('ratingKey')
                elif not best_match:
                    best_match = provider.get('ratingKey')
        
        if best_match:
            logger.debug(f"Found approximate match for {title}")
            return best_match
        
        logger.debug(f"No match found in Plex for {title} ({year})" + (f" [tmdb:{tmdb_id}]" if tmdb_id else ""))
        return None
        
    except Exception as e:
        logger.exception(f"Error searching Plex for {title}: {e}")
        return None

def fetch_tv_shows_from_plex_sdk(section_id, limit=10, machine_id=None, days=None):
    try:
        _s = get_settings(decrypt_secrets=False)
        plex_settings = (_s.get("plex_url"), _s.get("plex_token")) if "id" in _s else None

        if not plex_settings or not plex_settings[0] or not plex_settings[1]:
            logger.debug("Plex not configured")
            return []

        plex_url = plex_settings[0].rstrip('/')
        plex_token = decrypt(plex_settings[1])

        if days:
            api_url = (
                f"{plex_url}/library/sections/{section_id}/all"
                f"?type=2"
                f"&sort=addedAt:desc"
                f"&addedAt%3E%3E=-{days}d"
                f"&X-Plex-Container-Start=0"
                f"&X-Plex-Container-Size=500"
                f"&X-Plex-Token={plex_token}"
            )
        else:
            api_url = (
                f"{plex_url}/library/sections/{section_id}/all"
                f"?type=2"
                f"&sort=episode.addedAt:desc"
                f"&X-Plex-Container-Start=0"
                f"&X-Plex-Container-Size={limit}"
                f"&X-Plex-Token={plex_token}"
            )
        
        headers = get_plex_headers()
        
        response = safe_get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        shows = []
        media_container = data.get('MediaContainer', {})
        library_name = media_container.get('librarySectionTitle', '')
        
        for directory in media_container.get('Metadata', []):
            rating_key = str(directory.get('ratingKey', ''))

            duration = int(directory.get('duration', 0) or 0)
            if duration == 0:
                logger.debug(f"Skipping show '{directory.get('title')}' - zero duration")
                continue

            show = {
                'title': directory.get('title', 'Unknown'),
                'rating_key': rating_key,
                'year': str(directory.get('year', '')),
                'thumb': directory.get('thumb', ''),
                'art': directory.get('art', ''),
                'summary': directory.get('summary', ''),
                'added_at': str(directory.get('addedAt', '')),
                'updated_at': str(directory.get('updatedAt', '')),
                'content_rating': directory.get('contentRating', ''),
                'duration': str(directory.get('duration', '')),
                'guid': directory.get('guid', ''),
                'key': directory.get('key', ''),
                'media_type': 'show',
                'type': 'show',
                'library_name': library_name,
                'plex_url': build_plex_web_link(rating_key, machine_id) if rating_key else '',
                'rating': str(directory.get('rating', ''))
            }
            shows.append(show)
        
        logger.debug(f"Fetched {len(shows)} TV shows from Plex API ({'by date filter' if days else 'sorted by recent episode'})")
        return shows
            
    except Exception as e:
        logger.exception(f"Error fetching TV shows from Plex API: {e}")
        mark_plex_failed()
        return []

def fetch_movies_from_plex_sdk(section_id, limit=10, machine_id=None, days=None):
    try:
        _s = get_settings(decrypt_secrets=False)
        plex_settings = (_s.get("plex_url"), _s.get("plex_token")) if "id" in _s else None

        if not plex_settings or not plex_settings[0] or not plex_settings[1]:
            logger.debug("Plex not configured")
            return []

        plex_url = plex_settings[0].rstrip('/')
        plex_token = decrypt(plex_settings[1])

        if days:
            api_url = (
                f"{plex_url}/library/sections/{section_id}/all"
                f"?type=1"
                f"&sort=addedAt:desc"
                f"&addedAt%3E%3E=-{days}d"
                f"&X-Plex-Container-Start=0"
                f"&X-Plex-Container-Size=500"
                f"&X-Plex-Token={plex_token}"
            )
        else:
            api_url = (
                f"{plex_url}/library/sections/{section_id}/all"
                f"?type=1"
                f"&sort=addedAt:desc"
                f"&X-Plex-Container-Start=0"
                f"&X-Plex-Container-Size={limit}"
                f"&X-Plex-Token={plex_token}"
            )
        
        headers = get_plex_headers()
        
        response = safe_get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        movies = []
        media_container = data.get('MediaContainer', {})
        library_name = media_container.get('librarySectionTitle', '')
        
        for video in media_container.get('Metadata', []):
            rating_key = str(video.get('ratingKey', ''))

            duration = int(video.get('duration', 0) or 0)
            if duration == 0:
                logger.debug(f"Skipping movie '{video.get('title')}' - zero duration")
                continue
            
            movie = {
                'title': video.get('title', 'Unknown'),
                'rating_key': rating_key,
                'year': str(video.get('year', '')),
                'thumb': video.get('thumb', ''),
                'art': video.get('art', ''),
                'summary': video.get('summary', ''),
                'added_at': str(video.get('addedAt', '')),
                'updated_at': str(video.get('updatedAt', '')),
                'content_rating': video.get('contentRating', ''),
                'duration': str(video.get('duration', '')),
                'guid': video.get('guid', ''),
                'key': video.get('key', ''),
                'media_type': 'movie',
                'type': 'movie',
                'library_name': library_name,
                'plex_url': build_plex_web_link(rating_key, machine_id) if rating_key else '',
                'rating': str(video.get('rating', ''))
            }
            movies.append(movie)
        
        logger.debug(f"Fetched {len(movies)} movies from Plex API ({'by date filter' if days else 'sorted by addedAt'})")
        return movies
            
    except Exception as e:
        logger.exception(f"Error fetching movies from Plex API: {e}")
        mark_plex_failed()
        return []

def fetch_albums_from_plex_sdk(section_id, limit=10, machine_id=None, days=None):
    try:
        _s = get_settings(decrypt_secrets=False)
        plex_settings = (_s.get("plex_url"), _s.get("plex_token")) if "id" in _s else None

        if not plex_settings or not plex_settings[0] or not plex_settings[1]:
            logger.debug("Plex not configured")
            return []

        plex_url = plex_settings[0].rstrip('/')
        plex_token = decrypt(plex_settings[1])

        if days:
            api_url = (
                f"{plex_url}/library/sections/{section_id}/all"
                f"?type=9"
                f"&sort=addedAt:desc"
                f"&addedAt%3E%3E=-{days}d"
                f"&X-Plex-Container-Start=0"
                f"&X-Plex-Container-Size=500"
                f"&X-Plex-Token={plex_token}"
            )
        else:
            api_url = (
                f"{plex_url}/library/sections/{section_id}/all"
                f"?type=9"
                f"&sort=addedAt:desc"
                f"&X-Plex-Container-Start=0"
                f"&X-Plex-Container-Size={limit}"
                f"&X-Plex-Token={plex_token}"
            )
        
        headers = get_plex_headers()
        
        response = safe_get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        albums = []
        media_container = data.get('MediaContainer', {})
        library_name = media_container.get('librarySectionTitle', '')
        
        for album in media_container.get('Metadata', []):
            rating_key = str(album.get('ratingKey', ''))

            album_data = {
                'title': album.get('title', 'Unknown'),
                'rating_key': rating_key,
                'year': str(album.get('year', '')),
                'thumb': album.get('thumb', ''),
                'art': album.get('art', ''),
                'summary': album.get('summary', ''),
                'added_at': str(album.get('addedAt', '')),
                'updated_at': str(album.get('updatedAt', '')),
                'duration': str(album.get('Genre', '')[0]['tag']) if album.get('Genre', '') else '',
                'guid': album.get('guid', ''),
                'key': album.get('key', ''),
                'parent_title': album.get('parentTitle', ''),
                'parent_thumb': album.get('parentThumb', ''),
                'leaf_count': album.get('leafCount', 0),
                'media_type': 'album',
                'type': 'album',
                'library_name': library_name,
                'plex_url': build_plex_web_link(rating_key, machine_id) if rating_key else '',
                'rating': str(album.get('rating', ''))
            }
            albums.append(album_data)
        
        logger.debug(f"Fetched {len(albums)} albums from Plex API")
        return albums
            
    except Exception as e:
        logger.exception(f"Error fetching albums from Plex API: {e}")
        mark_plex_failed()
        return []

def fetch_recently_added_using_plex_sdk(tautulli_base_url, tautulli_api_key, items_count=10, recently_added_mode="items", recently_added_sort="date"):
    recent_data = []
    days_mode = recently_added_mode == "days"

    machine_id = get_plex_machine_id()
    if machine_id:
        logger.debug(f"Plex machine ID: {machine_id}")
    else:
        logger.warning("Warning: Could not get Plex machine ID, links may not work")

    libraries, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_library_names', None, None, "10")

    if not libraries:
        logger.debug("No libraries found")
        return recent_data

    for library in libraries:
        section_id = library['section_id']
        section_type = library['section_type']
        library_name = library['section_name']

        logger.debug(f"\nFetching recently added for library: {library_name} (type: {section_type}, mode: {recently_added_mode})")

        items = []
        days_val = int(items_count) if days_mode else None

        if section_type == 'show':
            items = fetch_tv_shows_from_plex_sdk(section_id, items_count * 5, machine_id, days=days_val)
        elif section_type == 'movie':
            items = fetch_movies_from_plex_sdk(section_id, items_count * 5, machine_id, days=days_val)
        elif section_type == 'artist':
            items = fetch_albums_from_plex_sdk(section_id, items_count, machine_id, days=days_val)
        else:
            logger.debug(f"Using Tautulli fallback for library type: {section_type}")
            fetch_count = str(items_count * 5) if not days_mode else "500"
            rd, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_recently_added', section_id, None, fetch_count, 0)
            if rd and rd.get('recently_added'):
                items = [item for item in rd['recently_added'] if int(item.get('duration', 0) or 0) > 0]
                if days_mode:
                    cutoff = int((datetime.now() - timedelta(days=int(items_count))).timestamp())
                    items = [item for item in items if int(item.get('added_at', 0) or 0) >= cutoff]
                for item in items:
                    item['library_name'] = library_name
                    if 'rating_key' in item and machine_id:
                        item['plex_url'] = build_plex_web_link(item['rating_key'], machine_id)

        if recently_added_sort == "rating":
            items.sort(key=lambda x: float(x.get('rating', '') or 0), reverse=True)

        if not days_mode:
            items = items[:items_count]

        if items:
            recent_data.append({
                'recently_added': items
            })

    return recent_data

def get_collection_items_for_email(collection_key, settings):
    try:
        plex_url = settings.get('plex_url', '').rstrip('/')
        plex_token = settings.get('plex_token', '')
        
        if not plex_url or not plex_token:
            logger.error(f"ERROR: Plex connection not configured for collection {collection_key}")
            return []
        
        collection_items_url = f"{plex_url}/library/collections/{collection_key}/children"
        headers = get_plex_headers({'X-Plex-Token': decrypt(plex_token)})
        machine_id = get_plex_machine_id()

        logger.debug(f"Fetching collection items from: {collection_items_url}")
        response = safe_get(collection_items_url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"ERROR: Failed to fetch collection items. Status: {response.status_code}")
            return []
        
        plex_data = response.json()
        items = []
        
        if 'MediaContainer' in plex_data and 'Metadata' in plex_data['MediaContainer']:
            for item in plex_data['MediaContainer']['Metadata']:
                thumb = item.get('thumb', '')
                if thumb and not thumb.startswith('http'):
                    thumb = f"{plex_url}{thumb}?X-Plex-Token={decrypt(plex_token)}"
                
                art = item.get('art', '')
                if art and not art.startswith('http'):
                    art = f"{plex_url}{art}?X-Plex-Token={decrypt(plex_token)}"
                
                item_info = {
                    'key': item.get('ratingKey'),
                    'title': item.get('title', 'Unknown Title'),
                    'type': item.get('type'),
                    'year': item.get('year'),
                    'tagline': item.get('tagline'),
                    'summary': item.get('summary'),
                    'rating': item.get('rating'),
                    'duration': item.get('duration'),
                    'addedAt': item.get('addedAt'),
                    'thumb': thumb,
                    'art': art,
                    'childCount': item.get('childCount', 0),
                    'leafCount': item.get('leafCount', 0),
                    'parentTitle': item.get('parentTitle'),
                    'grandparentTitle': item.get('grandparentTitle'),
                    'subtype': item.get('type'),
                    'plex_url': build_plex_web_link(item.get('ratingKey'), machine_id)
                }
                items.append(item_info)
        
        logger.debug(f"Successfully fetched {len(items)} items from collection {collection_key}")
        return items
        
    except Exception as e:
        logger.exception(f"ERROR: Exception fetching collection items for {collection_key}: {e}")
        return []
