
import requests

from app import state
from app.settings_store import get_settings
from app.security import safe_get
from app.clients.plex import search_plex_for_rating_key, build_plex_web_link, get_plex_machine_id

import logging

logger = logging.getLogger(__name__)

def run_conjurr_command(base_url, user_dict, error, progress_cb=None):
    # progress_cb, when given, is called with the user id after each user is
    # processed; the caller owns any progress state (clients stay agnostic)
    # A fresh run starts uncancelled; the cancel route sets this event while we
    # loop, and we bail out between users with whatever we have so far. The
    # caller reads state.recommendations_cancel.is_set() afterwards to tell a
    # cancelled run from a completed one.
    state.recommendations_cancel.clear()
    if base_url == None:
        if error == None:
            error = "Conjurr Error: No Base URL provided"
        else:
            error += ", Conjurr Error: No Base URL provided"

    try:
        safe_get(f"{base_url}", timeout=5, retries=0)
    except requests.exceptions.RequestException:
        try:
            safe_get(base_url, timeout=5, retries=0)
        except requests.exceptions.RequestException as e:
            return [{}, f"Conjurr Error: Could not reach conjurr at {base_url}. Is it running?"]

    _s = get_settings(decrypt_secrets=False)
    plex_settings = (_s.get("plex_url"), _s.get("plex_token")) if "id" in _s else None
    
    plex_url = plex_settings[0].rstrip('/') if plex_settings and plex_settings[0] else None
    plex_token = plex_settings[1] if plex_settings and plex_settings[1] else None
    plex_web_url = _s.get("plex_web_url")
    machine_id = get_plex_machine_id() if plex_url and plex_token else None

    # Optional per-section cap (settings recs_item_count, blank = show all).
    # Applied here so the route pull and scheduled sends stay consistent.
    try:
        recs_cap = int(_s.get("recs_item_count") or 0)
    except (TypeError, ValueError):
        recs_cap = 0

    api_base_url = f"{base_url}/recommendations?user_id="
    recommendations_dict = {}

    for user in user_dict.keys():
        if state.recommendations_cancel.is_set():
            logger.info("Recommendations pull cancelled; returning partial results")
            break
        try:
            api_url = f"{api_base_url}{user}&mode=history"
            response = safe_get(api_url)
            response.raise_for_status()
            data = response.json()

            # Cap before Plex enrichment so dropped items never cost a search.
            # Available items fill first; unavailable only pad the remainder.
            if recs_cap > 0:
                for kind in ('movie_posters', 'show_posters'):
                    available = data.get(kind) or []
                    unavailable = data.get(f'{kind}_unavailable') or []
                    data[kind] = available[:recs_cap]
                    data[f'{kind}_unavailable'] = unavailable[:max(0, recs_cap - len(data[kind]))]

            if plex_url and plex_token and machine_id:
                if 'movie_posters' in data:
                    for item in data['movie_posters']:
                        title = item.get('title', '')
                        year = item.get('year', '')
                        tmdb_id = item.get('tmdbId') or item.get('tmdb_id')
                        
                        rating_key = search_plex_for_rating_key(title, year, 'movie', plex_url, plex_token, tmdb_id=tmdb_id)
                        
                        if rating_key:
                            item['rating_key'] = rating_key
                            item['machine_id'] = machine_id
                            item['plex_web_url'] = plex_web_url
                            item['plex_url'] = build_plex_web_link(rating_key, machine_id, plex_web_url)
                            logger.info(f"Linked movie: {title} (tmdb:{tmdb_id}) -> ratingKey:{rating_key}")
                        else:
                            logger.info(f"Could not find movie in Plex: {title} (tmdb:{tmdb_id})")
                
                if 'show_posters' in data:
                    for item in data['show_posters']:
                        title = item.get('title', '')
                        year = item.get('year', '')
                        tmdb_id = item.get('tmdbId') or item.get('tmdb_id')
                        
                        rating_key = search_plex_for_rating_key(title, year, 'show', plex_url, plex_token, tmdb_id=tmdb_id)
                        
                        if rating_key:
                            item['rating_key'] = rating_key
                            item['machine_id'] = machine_id
                            item['plex_web_url'] = plex_web_url
                            item['plex_url'] = build_plex_web_link(rating_key, machine_id, plex_web_url)
                            logger.info(f"Linked show: {title} (tmdb:{tmdb_id}) -> ratingKey:{rating_key}")
                        else:
                            logger.info(f"Could not find show in Plex: {title} (tmdb:{tmdb_id})")

            recommendations_dict[user] = data
        except requests.exceptions.RequestException as e:
            if error == None:
                error = str(f"Conjurr Error: {e}")
            else:
                error += str(f", Conjurr Error: {e}")
        if progress_cb:
            try:
                progress_cb(user)
            except Exception:
                logger.debug("suppressed progress callback error", exc_info=True)

    return [recommendations_dict, error]
