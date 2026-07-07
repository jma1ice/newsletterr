import sqlite3

import requests

from app import config
from app.security import safe_get
from app.clients.plex import search_plex_for_rating_key, build_plex_web_link, get_plex_machine_id

def run_conjurr_command(base_url, user_dict, error):
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

    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT plex_url, plex_token FROM settings WHERE id = 1")
    plex_settings = cursor.fetchone()
    conn.close()
    
    plex_url = plex_settings[0].rstrip('/') if plex_settings and plex_settings[0] else None
    plex_token = plex_settings[1] if plex_settings and plex_settings[1] else None
    machine_id = get_plex_machine_id() if plex_url and plex_token else None

    api_base_url = f"{base_url}/recommendations?user_id="
    recommendations_dict = {}

    for user in user_dict.keys():
        try:
            api_url = f"{api_base_url}{user}&mode=history"
            response = safe_get(api_url)
            response.raise_for_status()
            data = response.json()

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
                            item['plex_url'] = build_plex_web_link(rating_key, machine_id)
                            print(f"Linked movie: {title} (tmdb:{tmdb_id}) -> ratingKey:{rating_key}")
                        else:
                            print(f"Could not find movie in Plex: {title} (tmdb:{tmdb_id})")
                
                if 'show_posters' in data:
                    for item in data['show_posters']:
                        title = item.get('title', '')
                        year = item.get('year', '')
                        tmdb_id = item.get('tmdbId') or item.get('tmdb_id')
                        
                        rating_key = search_plex_for_rating_key(title, year, 'show', plex_url, plex_token, tmdb_id=tmdb_id)
                        
                        if rating_key:
                            item['rating_key'] = rating_key
                            item['machine_id'] = machine_id
                            item['plex_url'] = build_plex_web_link(rating_key, machine_id)
                            print(f"Linked show: {title} (tmdb:{tmdb_id}) -> ratingKey:{rating_key}")
                        else:
                            print(f"Could not find show in Plex: {title} (tmdb:{tmdb_id})")

            recommendations_dict[user] = data
        except requests.exceptions.RequestException as e:
            if error == None:
                error = str(f"Conjurr Error: {e}")
            else:
                error += str(f", Conjurr Error: {e}")

    return [recommendations_dict, error]
