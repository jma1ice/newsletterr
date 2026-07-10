import time

import requests
from flask import Blueprint, jsonify, render_template, request, session

from app.settings_store import get_settings
from app.cache import set_cached_data, get_cache_info
from app.crypto import decrypt
from app.security import require_csrf_for_json, requires_auth, safe_get, json_body
from app.theme import get_theme_settings
from app.clients.plex import get_plex_headers, get_plex_machine_id, build_plex_web_link
from app.clients.tautulli import run_tautulli_command, days_since_year_start
from app.clients.conjurr import run_conjurr_command
from app.clients.droppedneedle import run_droppedneedle_command, fetch_droppedneedle_server_stats
from app.clients.sonarr import fetch_sonarr_calendar
from app.clients.radarr import fetch_radarr_calendar
from app.emails.fetchers import fetch_recent_data_for_index

from datetime import datetime, timedelta

import logging

logger = logging.getLogger(__name__)

bp = Blueprint('stats', __name__)

@bp.route('/pull_stats', methods=['POST'])
@requires_auth
def pull_stats():
    require_csrf_for_json()
    data, err = json_body()
    if err:
        return err
    time_range = str(data.get('time_range', 30))
    count = str(data.get('count', 10))

    _s = get_settings(decrypt_secrets=False)
    row = (_s.get("tautulli_url"), _s.get("tautulli_api"), _s.get("server_name"), _s.get("stats_type"), _s.get("recently_added_mode"), _s.get("recently_added_sort")) if "id" in _s else None

    if not row or not row[0]:
        return jsonify({"error": "Please enter tautulli info on settings page"}), 400

    tautulli_base_url = row[0].rstrip('/')
    tautulli_api_key = decrypt(row[1])
    stats_type = row[3] or 'plays'
    recently_added_mode = row[4] or 'items'
    recently_added_sort = row[5] or 'date'

    cache_params = {
        'time_range': time_range,
        'count': count,
        'url': tautulli_base_url,
        'timestamp': time.time()
    }

    stats, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', None, time_range, stats_type=stats_type)
    stats = stats or []

    libraries_with_counts, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_libraries', None, None)
    if libraries_with_counts:
        stats.append({
            'stat_id': 'library_item_counts',
            'stat_title': 'Library Item Counts',
            'rows': [
                {'section_name': lib.get('section_name', ''), 'count': lib.get('count', 0)}
                for lib in libraries_with_counts
            ]
        })

    set_cached_data('stats', stats, cache_params)

    yearly_wrapped_data, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', None, days_since_year_start(), stats_type=stats_type)
    if yearly_wrapped_data:
        set_cached_data('yearly_wrapped_json', yearly_wrapped_data, cache_params)

    users, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_users', 'Users', error)
    set_cached_data('users', users, cache_params)

    graph_data = []
    graph_commands = [
        {'command': 'get_concurrent_streams_by_stream_type', 'name': 'Stream Type'},
        {'command': 'get_plays_by_date', 'name': 'Plays by Date'},
        {'command': 'get_plays_by_dayofweek', 'name': 'Plays by Day'},
        {'command': 'get_plays_by_hourofday', 'name': 'Plays by Hour'},
        {'command': 'get_plays_by_source_resolution', 'name': 'Plays by Source Res'},
        {'command': 'get_plays_by_stream_resolution', 'name': 'Plays by Stream Res'},
        {'command': 'get_plays_by_stream_type', 'name': 'Plays by Stream Type'},
        {'command': 'get_plays_by_top_10_platforms', 'name': 'Plays by Top Platforms'},
        {'command': 'get_plays_by_top_10_users', 'name': 'Plays by Top Users'},
        {'command': 'get_plays_per_month', 'name': 'Plays per Month'},
        {'command': 'get_stream_type_by_top_10_platforms', 'name': 'Stream Type by Top Platforms'},
        {'command': 'get_stream_type_by_top_10_users', 'name': 'Stream Type by Top Users'}
    ]
    for command in graph_commands:
        try:
            gd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], error, time_range, y_axis=stats_type)
            graph_data.append(gd if gd is not None else {})
        except Exception as e:
            graph_data.append({})
            if error is None:
                error = f"Graph Error: {str(e)}"
            else:
                error += f", Graph Error: {str(e)}"
    set_cached_data('graph_data', graph_data, cache_params)

    libraries, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_library_names', None, None, "10")
    library_section_ids = {}
    for library in (libraries or []):
        if isinstance(library, dict) and 'section_id' in library:
            library_section_ids[f"{library['section_id']}"] = library.get("section_name")

    recent_data = fetch_recent_data_for_index(tautulli_base_url, tautulli_api_key, count, recently_added_mode=recently_added_mode, recently_added_sort=recently_added_sort)
    set_cached_data('recent_data', recent_data, cache_params)

    user_dict = {}
    users_full_data = None
    if users:
        users_full_data = users
        for user in users:
            if user['email'] != None and user['is_active']:
                user_dict[user['user_id']] = user['email']

    return jsonify({
        "success": True,
        "alert": f"Fresh data loaded! Stats/graphs for {time_range} days, and recently added {'within last ' + count + ' days' if recently_added_mode == 'days' else count + ' items'}.",
        "stats": stats or [],
        "yearly_wrapped_json": yearly_wrapped_data or [],
        "graph_data": graph_data,
        "graph_commands": graph_commands,
        "recent_data": recent_data,
        "user_dict": user_dict,
        "users_full_data": users_full_data,
        "cache_info": {
            "stats": get_cache_info('stats'),
            "users": get_cache_info('users'),
            "graph_data": get_cache_info('graph_data'),
            "recent_data": get_cache_info('recent_data'),
            "recommendations_json": get_cache_info('recommendations_json'),
            "filtered_users": get_cache_info('filtered_users'),
        },
        "time_range": time_range,
        "count": count,
        "error": error
    })

@bp.route('/pull_recommendations', methods=['POST'])
@requires_auth
def pull_recommendations():
    require_csrf_for_json()
    recommendations_json = {}
    error = None
    alert = None
    
    data, err = json_body(["to_emails"])
    if err:
        return err
    stats = data.get('stats')
    user_dict = data.get('user_dict', {})
    graph_data = data.get('graph_data')
    graph_commands = data.get('graph_commands')
    recent_data = data.get('recent_data')
    libs = data.get('libs')
    settings = data.get('settings', {})
    to_emails = data['to_emails']

    _s = get_settings(decrypt_secrets=False)
    row = (_s.get("conjurr_url"),) if "id" in _s else None

    if row:
        conjurr_settings = {
            "conjurr_url": row[0]
        }
    else:
        conjurr_settings = {
            "conjurr_url": ""
        }

    selected_emails = {e.strip().lower() for e in to_emails.split(',') if e.strip()}
    filtered_users = {
    k: v for k, v in user_dict.items()
    if v and str(v).strip().lower() in selected_emails
    }

    if request.method == 'POST':
        if conjurr_settings['conjurr_url'] == "":
            return render_template('index.html', error='Please enter conjurr info on settings page',
                                    stats=stats, user_dict=user_dict, graph_data=graph_data,
                                    graph_commands=graph_commands, recent_data=recent_data,
                                    libs=libs, settings=settings, theme_settings=get_theme_settings(),
                                    csrf_token=session.get("csrf_token", ""))
        else:
            conjurr_base_url = conjurr_settings['conjurr_url']
            recommendations_json, error = run_conjurr_command(conjurr_base_url, filtered_users, error)
            if error:
                alert = None
            else:
                alert = "User recommendations pulled from conjurr!"

            cache_params = {'timestamp': time.time()}

            set_cached_data('filtered_users', filtered_users, cache_params)
            set_cached_data('recommendations_json', recommendations_json, cache_params)

    cache_info = {
        'stats': get_cache_info('stats'),
        'users': get_cache_info('users'), 
        'graph_data': get_cache_info('graph_data'),
        'recent_data': get_cache_info('recent_data'),
        'recommendations_json': get_cache_info('recommendations_json'),
        'filtered_users': get_cache_info('filtered_users')
    }
    
    theme_settings = get_theme_settings()

    return render_template('index.html', stats=stats, user_dict=user_dict, graph_data=graph_data, cache_info=cache_info,
                            graph_commands=graph_commands, recent_data=recent_data, libs=libs, settings=settings,
                            recommendations_json=recommendations_json, filtered_users=filtered_users, alert=alert,
                            error=error, theme_settings=theme_settings, csrf_token=session.get("csrf_token", ""))

@bp.route('/pull_droppedneedle_stats', methods=['POST'])
@requires_auth
def pull_droppedneedle_stats():
    require_csrf_for_json()
    droppedneedle_wrapped_json = {}
    droppedneedle_server_json = None
    error = None
    alert = None

    data, err = json_body(["to_emails"])
    if err:
        return err
    stats = data.get('stats')
    user_dict = data.get('user_dict', {})
    graph_data = data.get('graph_data')
    graph_commands = data.get('graph_commands')
    recent_data = data.get('recent_data')
    libs = data.get('libs')
    settings = data.get('settings', {})
    to_emails = data['to_emails']

    _s = get_settings(decrypt_secrets=False)
    row = (_s.get("droppedneedle_url"), _s.get("droppedneedle_api_key")) if "id" in _s else None

    droppedneedle_url = (row[0] or "").strip() if row else ""
    droppedneedle_api_key = decrypt(row[1]) if row and row[1] else ""

    filtered_users = {k: v for k, v in user_dict.items() if v in to_emails}

    if droppedneedle_url == "" or droppedneedle_api_key == "":
        return render_template('index.html', error='Please enter DroppedNeedle URL and API key on settings page',
                                stats=stats, user_dict=user_dict, graph_data=graph_data,
                                graph_commands=graph_commands, recent_data=recent_data,
                                libs=libs, settings=settings, theme_settings=get_theme_settings(),
                                csrf_token=session.get("csrf_token", ""))

    droppedneedle_wrapped_json, error = run_droppedneedle_command(droppedneedle_url, droppedneedle_api_key, filtered_users, error)
    droppedneedle_server_json, server_error = fetch_droppedneedle_server_stats(droppedneedle_url, droppedneedle_api_key)
    if server_error:
        error = (error + ", " if error else "") + server_error

    if error:
        alert = None
    else:
        alert = "DroppedNeedle stats pulled!"

    cache_params = {'timestamp': time.time()}
    set_cached_data('droppedneedle_filtered_users', filtered_users, cache_params)
    set_cached_data('droppedneedle_wrapped_json', droppedneedle_wrapped_json, cache_params)
    set_cached_data('droppedneedle_server_json', droppedneedle_server_json, cache_params)

    cache_info = {
        'stats': get_cache_info('stats'),
        'users': get_cache_info('users'),
        'graph_data': get_cache_info('graph_data'),
        'recent_data': get_cache_info('recent_data'),
        'recommendations_json': get_cache_info('recommendations_json'),
        'filtered_users': get_cache_info('filtered_users')
    }

    theme_settings = get_theme_settings()

    return render_template('index.html', stats=stats, user_dict=user_dict, graph_data=graph_data, cache_info=cache_info,
                            graph_commands=graph_commands, recent_data=recent_data, libs=libs, settings=settings,
                            droppedneedle_wrapped_json=droppedneedle_wrapped_json, droppedneedle_server_json=droppedneedle_server_json,
                            alert=alert, error=error, theme_settings=theme_settings,
                            csrf_token=session.get("csrf_token", ""))

@bp.route('/pull_coming_soon', methods=['POST'])
@requires_auth
def pull_coming_soon():
    require_csrf_for_json()
    sonarr_coming_soon_json = None
    radarr_coming_soon_json = None
    error = None
    alert = None

    data, err = json_body()
    if err:
        return err
    stats = data.get('stats')
    user_dict = data.get('user_dict', {})
    graph_data = data.get('graph_data')
    graph_commands = data.get('graph_commands')
    recent_data = data.get('recent_data')
    libs = data.get('libs')
    settings = data.get('settings', {})

    _s = get_settings(decrypt_secrets=False)
    row = (
        _s.get("sonarr_url"), _s.get("sonarr_api_key"),
        _s.get("radarr_url"), _s.get("radarr_api_key"),
        _s.get("coming_soon_days_ahead"),
    ) if "id" in _s else None

    sonarr_url = (row[0] or "").strip() if row else ""
    sonarr_api_key = decrypt(row[1]) if row and row[1] else ""
    radarr_url = (row[2] or "").strip() if row else ""
    radarr_api_key = decrypt(row[3]) if row and row[3] else ""
    days_ahead = int(row[4] or 14) if row else 14

    if not sonarr_url and not radarr_url:
        return render_template('index.html', error='Please enter a Sonarr and/or Radarr URL and API key on settings page',
                                stats=stats, user_dict=user_dict, graph_data=graph_data,
                                graph_commands=graph_commands, recent_data=recent_data,
                                libs=libs, settings=settings, theme_settings=get_theme_settings(),
                                csrf_token=session.get("csrf_token", ""))

    start_date = datetime.now().strftime('%Y-%m-%d')
    end_date = (datetime.now() + timedelta(days=days_ahead)).strftime('%Y-%m-%d')

    if sonarr_url and sonarr_api_key:
        sonarr_coming_soon_json, sonarr_error = fetch_sonarr_calendar(sonarr_url, sonarr_api_key, start_date, end_date)
        if sonarr_error:
            error = (error + ", " if error else "") + sonarr_error

    if radarr_url and radarr_api_key:
        radarr_coming_soon_json, radarr_error = fetch_radarr_calendar(radarr_url, radarr_api_key, start_date, end_date)
        if radarr_error:
            error = (error + ", " if error else "") + radarr_error

    if error:
        alert = None
    else:
        alert = "Coming soon calendar pulled!"

    cache_params = {'timestamp': time.time()}
    set_cached_data('sonarr_coming_soon_json', sonarr_coming_soon_json, cache_params)
    set_cached_data('radarr_coming_soon_json', radarr_coming_soon_json, cache_params)

    cache_info = {
        'stats': get_cache_info('stats'),
        'users': get_cache_info('users'),
        'graph_data': get_cache_info('graph_data'),
        'recent_data': get_cache_info('recent_data'),
        'recommendations_json': get_cache_info('recommendations_json'),
        'filtered_users': get_cache_info('filtered_users')
    }

    if not cache_info['graph_data'] or 'params' not in cache_info['graph_data']:
        if not cache_info['graph_data']:
            cache_info['graph_data'] = {}
        cache_info['graph_data']['params'] = {
            'time_range': 30
        }

    theme_settings = get_theme_settings()

    return render_template('index.html', stats=stats, user_dict=user_dict, graph_data=graph_data, cache_info=cache_info,
                            graph_commands=graph_commands, recent_data=recent_data, libs=libs, settings=settings,
                            sonarr_coming_soon_json=sonarr_coming_soon_json, radarr_coming_soon_json=radarr_coming_soon_json,
                            alert=alert, error=error, theme_settings=theme_settings,
                            csrf_token=session.get("csrf_token", ""))

@bp.route('/fetch_collections/<collection_type>', methods=['GET'])
@requires_auth
def fetch_collections(collection_type):
    try:
        _s = get_settings(decrypt_secrets=False)
        row = (_s.get("plex_url"), _s.get("plex_token")) if "id" in _s else None

        if not row or not row[0] or not row[1]:
            return jsonify({"status": "error", "message": "Plex connection not configured"})

        plex_url = row[0].rstrip('/')
        plex_token = row[1]
        machine_id = get_plex_machine_id()

        sections_url = f"{plex_url}/library/sections"
        
        sections_response = safe_get(
            sections_url,
            headers = get_plex_headers({'X-Plex-Token': decrypt(plex_token)}),
            timeout = 10
        )
        if sections_response.status_code != 200:
            return jsonify({"status": "error", "message": "Failed to fetch library sections"})

        sections_data = sections_response.json()
        collections = []

        target_type = collection_type
        
        for section in sections_data.get("MediaContainer", {}).get("Directory", []):
            if section.get("type") == target_type:
                section_id = section.get("key")
                section_title = section.get("title", "Unknown Library")
                
                collections_url = f"{plex_url}/library/sections/{section_id}/collections"
                collections_response = safe_get(collections_url, headers=get_plex_headers({'X-Plex-Token': decrypt(plex_token)}), timeout=10)
                
                if collections_response.status_code == 200:
                    collections_data = collections_response.json()
                    
                    for collection in collections_data.get("MediaContainer", {}).get("Metadata", []):
                        thumb = collection.get("thumb", "")
                        if thumb and not thumb.startswith("http"):
                            thumb = f"{plex_url}{thumb}?X-Plex-Token={decrypt(plex_token)}"
                        
                        art = collection.get("art", "")
                        if art and not art.startswith("http"):
                            art = f"{plex_url}{art}?X-Plex-Token={decrypt(plex_token)}"
                        
                        collections.append({
                            "key": collection.get("ratingKey"),
                            "title": collection.get("title", "Unknown Collection"),
                            "summary": collection.get("summary", ""),
                            "thumb": thumb,
                            "art": art,
                            "childCount": collection.get("childCount", 0),
                            "subtype": collection.get("subtype", target_type),
                            "sectionTitle": section_title,
                            "sectionId": section_id,
                            "plex_url": build_plex_web_link(collection.get("ratingKey"), machine_id)
                        })

        return jsonify({
            "status": "success", 
            "collections": collections,
            "type": collection_type
        })

    except Exception as e:
        logger.error(f"Error fetching collections: {e}")
        return jsonify({"status": "error", "message": str(e)})

@bp.route('/get_collection_items', methods=['POST'])
@requires_auth
def get_collection_items():
    require_csrf_for_json()
    try:
        data = request.get_json()
        collection_key = data.get('collection_key')
        collection_type = data.get('collection_type')
        
        if not collection_key:
            return jsonify({
                'status': 'error',
                'message': 'Collection key is required'
            }), 400
        
        _s = get_settings(decrypt_secrets=False)
        row = (_s.get("plex_url"), _s.get("plex_token")) if "id" in _s else None

        if not row or not row[0] or not row[1]:
            return jsonify({"status": "error", "message": "Plex connection not configured"})

        plex_url = row[0].rstrip('/')
        plex_token = row[1]
        
        collection_items_url = f"{plex_url}/library/collections/{collection_key}/children"
        
        headers = get_plex_headers({'X-Plex-Token': decrypt(plex_token)})
        
        response = safe_get(collection_items_url, headers=headers, timeout=30)
        
        if response.status_code == 404:
            return jsonify({
                'status': 'error',
                'message': 'Collection not found'
            }), 404
        elif response.status_code != 200:
            return jsonify({
                'status': 'error',
                'message': f'Plex API error: {response.status_code}'
            }), 500
        
        plex_data = response.json()
        
        items = []
        if 'MediaContainer' in plex_data and 'Metadata' in plex_data['MediaContainer']:
            for item in plex_data['MediaContainer']['Metadata']:
                item_info = {
                    'title': item.get('title', 'Unknown Title'),
                    'key': item.get('key'),
                    'type': item.get('type'),
                    'year': item.get('year'),
                    'tagline': item.get('tagline'),
                    'summary': item.get('summary'),
                    'rating': item.get('rating'),
                    'duration': item.get('duration'),
                    'addedAt': item.get('addedAt'),
                    'thumb': item.get('thumb')
                }
                
                if item.get('type') == 'movie':
                    item_info['name'] = item_info['title']
                elif item.get('type') == 'show':
                    item_info['name'] = item_info['title']
                    if 'leafCount' in item:
                        item_info['episode_count'] = item['leafCount']
                    if 'childCount' in item:
                        item_info['season_count'] = item['childCount']
                elif item.get('type') == 'album':
                    item_info['name'] = item_info['title']
                    if 'parentTitle' in item:
                        item_info['artist'] = item['parentTitle']
                elif item.get('type') == 'track':
                    item_info['name'] = item_info['title']
                    if 'grandparentTitle' in item:
                        item_info['artist'] = item['grandparentTitle']
                    if 'parentTitle' in item:
                        item_info['album'] = item['parentTitle']
                
                items.append(item_info)
        
        items.sort(key=lambda x: x.get('title', '').lower())
        
        return jsonify({
            'status': 'success',
            'items': items,
            'total_count': len(items),
            'collection_key': collection_key,
            'collection_type': collection_type
        })
        
    except requests.RequestException as e:
        logger.error(f"Error fetching collection items from Plex: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to connect to Plex: {str(e)}'
        }), 500
    except Exception as e:
        logger.exception(f"Error in get_collection_items: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500
