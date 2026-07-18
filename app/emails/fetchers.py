import time

from app.settings_store import get_settings
from app.cache import get_cached_data, set_cached_data
from app.crypto import decrypt
from app.clients.tautulli import run_tautulli_command, days_since_year_start
from app.clients.plex import fetch_recently_added_using_plex_sdk
from app.clients.conjurr import run_conjurr_command
from app.clients.droppedneedle import run_droppedneedle_command, fetch_droppedneedle_server_stats
from app.clients.sonarr import fetch_sonarr_calendar
from app.clients.radarr import fetch_radarr_calendar
from app.clients.ombi import fetch_ombi_movie_requests, fetch_ombi_tv_requests

from datetime import datetime, timedelta

import logging

logger = logging.getLogger(__name__)

def fetch_tautulli_data_for_email(tautulli_base_url, tautulli_api_key, date_range, server_name, items_count=10, stats_type='plays', recently_added_mode='items', recently_added_sort='date'):
    data = {
        'settings': {'server_name': server_name},
        'stats': [],
        'graph_data': [],
        'recent_data': [],
        'graph_commands': []
    }
    
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
    
    try:
        stats, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', None, str(date_range), stats_type=stats_type)
        if stats:
            data['stats'] = stats

        libraries, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_libraries', None, None)
        if libraries:
            data['stats'].append({
                'stat_id': 'library_item_counts',
                'stat_title': 'Library Item Counts',
                'rows': [
                    {'section_name': lib.get('section_name', ''), 'count': lib.get('count', 0)}
                    for lib in libraries
                ]
            })

        graph_data = []
        for command in graph_commands:
            try:
                gd, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], None, str(date_range), y_axis=stats_type)
                graph_data.append(gd if gd is not None else {})
            except Exception as e:
                graph_data.append({})
                logger.error(f"Error fetching graph data for {command['name']}: {e}")
        
        data['graph_data'] = graph_data
        data['graph_commands'] = graph_commands

        recent_data = fetch_recently_added_using_plex_sdk(tautulli_base_url, tautulli_api_key, items_count, recently_added_mode=recently_added_mode, recently_added_sort=recently_added_sort)
        data['recent_data'] = recent_data
                
        logger.info(f"Fetched Tautulli data: {len(data['stats'])} stats, {len(data['graph_data'])} graphs, {len(data['recent_data'])} recent sections")
        
    except Exception as e:
        logger.exception(f"Error fetching Tautulli data: {e}")
    
    return data

def fetch_recent_data_for_index(tautulli_base_url, tautulli_api_key, count, recently_added_mode="items", recently_added_sort="date"):
    return fetch_recently_added_using_plex_sdk(tautulli_base_url, tautulli_api_key, int(count), recently_added_mode=recently_added_mode, recently_added_sort=recently_added_sort)

def get_current_tautulli_data_for_email(settings):
    data = {
        'settings': settings,
        'stats': [],
        'graph_data': [],
        'recent_data': [],
        'graph_commands': []
    }
    
    try:
        stats = get_cached_data('stats', strict=False)
        if stats:
            data['stats'] = stats
        
        recent_data = get_cached_data('recent_data', strict=False)
        if recent_data:
            data['recent_data'] = recent_data
            
        graph_data = get_cached_data('graph_data', strict=False)
        if graph_data:
            data['graph_data'] = graph_data
            
        data['graph_commands'] = [
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
        
    except Exception as e:
        logger.error(f"Error getting current Tautulli data: {e}")
    
    return data

def get_recommendations_for_users(user_keys, to_emails, user_dict, use_cache=True):
    try:
        if use_cache:
            cached_recommendations = get_cached_data('recommendations_json', strict=True) or get_cached_data('recommendations_json', strict=False)
            cached_filtered_users = get_cached_data('filtered_users', strict=True) or get_cached_data('filtered_users', strict=False)
            
            if cached_recommendations and cached_filtered_users:
                filtered_users = {k: v for k, v in user_dict.items() if k in user_keys and v in to_emails}
                
                cached_user_keys = set(str(k) for k in cached_filtered_users.keys())
                required_user_keys = set(str(k) for k in filtered_users.keys())
                
                if required_user_keys.issubset(cached_user_keys):
                    logger.info(f"Using cached recommendations for users: {list(required_user_keys)}")
                    return {k: v for k, v in cached_recommendations.items() if str(k) in required_user_keys}
                else:
                    logger.info(f"Cache miss - need users {required_user_keys}, cache has {cached_user_keys}")
            else:
                logger.info("No cached recommendations available")

        _s = get_settings(decrypt_secrets=False)
        row = (_s.get("conjurr_url"),) if "id" in _s else None
        
        if not row or not row[0]:
            return {}
            
        conjurr_url = row[0].strip()
        
        filtered_users = {k: v for k, v in user_dict.items() if k in user_keys and v in to_emails}
        
        if not filtered_users:
            return {}
            
        recommendations_data, _ = run_conjurr_command(conjurr_url, filtered_users, None)

        if use_cache and recommendations_data:
            cache_params = {'timestamp': time.time(), 'manual_fetch': True}
            set_cached_data('recommendations_json', recommendations_data, cache_params)
            set_cached_data('filtered_users', filtered_users, cache_params)
            logger.info("Cached fresh recommendations data")

        return recommendations_data or {}

    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        return {}

def get_droppedneedle_wrapped_for_users(user_keys, to_emails, user_dict, use_cache=True):
    try:
        if use_cache:
            cached_wrapped = get_cached_data('droppedneedle_wrapped_json', strict=True) or get_cached_data('droppedneedle_wrapped_json', strict=False)
            cached_filtered_users = get_cached_data('droppedneedle_filtered_users', strict=True) or get_cached_data('droppedneedle_filtered_users', strict=False)

            if cached_wrapped and cached_filtered_users:
                filtered_users = {k: v for k, v in user_dict.items() if k in user_keys and v in to_emails}

                cached_user_keys = set(str(k) for k in cached_filtered_users.keys())
                required_user_keys = set(str(k) for k in filtered_users.keys())

                if required_user_keys.issubset(cached_user_keys):
                    logger.info(f"Using cached DroppedNeedle wrapped data for users: {list(required_user_keys)}")
                    return {k: v for k, v in cached_wrapped.items() if str(k) in required_user_keys}
                else:
                    logger.info(f"Cache miss - need users {required_user_keys}, cache has {cached_user_keys}")
            else:
                logger.info("No cached DroppedNeedle wrapped data available")

        _s = get_settings(decrypt_secrets=False)
        row = (_s.get("droppedneedle_url"), _s.get("droppedneedle_api_key")) if "id" in _s else None

        if not row or not row[0] or not row[1]:
            return {}

        droppedneedle_url = row[0].strip()
        droppedneedle_api_key = decrypt(row[1])

        filtered_users = {k: v for k, v in user_dict.items() if k in user_keys and v in to_emails}

        if not filtered_users:
            return {}

        wrapped_data, _ = run_droppedneedle_command(droppedneedle_url, droppedneedle_api_key, filtered_users, None)

        if use_cache and wrapped_data:
            cache_params = {'timestamp': time.time(), 'manual_fetch': True}
            set_cached_data('droppedneedle_wrapped_json', wrapped_data, cache_params)
            set_cached_data('droppedneedle_filtered_users', filtered_users, cache_params)
            logger.info("Cached fresh DroppedNeedle wrapped data")

        return wrapped_data or {}

    except Exception as e:
        logger.error(f"Error getting DroppedNeedle wrapped data: {e}")
        return {}

def get_droppedneedle_server_stats_cached(use_cache=True):
    try:
        if use_cache:
            cached = get_cached_data('droppedneedle_server_json', strict=True) or get_cached_data('droppedneedle_server_json', strict=False)
            if cached:
                return cached

        _s = get_settings(decrypt_secrets=False)
        row = (_s.get("droppedneedle_url"), _s.get("droppedneedle_api_key")) if "id" in _s else None

        if not row or not row[0] or not row[1]:
            return None

        droppedneedle_url = row[0].strip()
        droppedneedle_api_key = decrypt(row[1])

        server_data, _ = fetch_droppedneedle_server_stats(droppedneedle_url, droppedneedle_api_key)

        if use_cache and server_data:
            set_cached_data('droppedneedle_server_json', server_data, {'timestamp': time.time(), 'manual_fetch': True})

        return server_data

    except Exception as e:
        logger.error(f"Error getting DroppedNeedle server stats: {e}")
        return None

def get_yearly_wrapped_cached(use_cache=True):
    try:
        if use_cache:
            cached = get_cached_data('yearly_wrapped_json', strict=True) or get_cached_data('yearly_wrapped_json', strict=False)
            if cached:
                return cached

        _s = get_settings(decrypt_secrets=False)
        row = (_s.get("tautulli_url"), _s.get("tautulli_api"), _s.get("stats_type")) if "id" in _s else None

        if not row or not row[0] or not row[1]:
            return None

        tautulli_base_url = row[0].rstrip('/')
        tautulli_api_key = decrypt(row[1])
        stats_type = row[2] or 'plays'

        stats_data, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', None, days_since_year_start(), stats_type=stats_type)

        if use_cache and stats_data:
            set_cached_data('yearly_wrapped_json', stats_data, {'timestamp': time.time(), 'manual_fetch': True})

        return stats_data

    except Exception as e:
        logger.error(f"Error getting yearly wrapped stats: {e}")
        return None

def get_sonarr_coming_soon_cached(use_cache=True, days_ahead=14):
    try:
        if use_cache:
            cached = get_cached_data('sonarr_coming_soon_json', strict=True) or get_cached_data('sonarr_coming_soon_json', strict=False)
            if cached:
                return cached

        _s = get_settings(decrypt_secrets=False)
        row = (_s.get("sonarr_url"), _s.get("sonarr_api_key")) if "id" in _s else None

        if not row or not row[0] or not row[1]:
            return None

        sonarr_url = row[0].rstrip('/')
        sonarr_api_key = decrypt(row[1])

        start_date = datetime.now().strftime('%Y-%m-%d')
        end_date = (datetime.now() + timedelta(days=int(days_ahead))).strftime('%Y-%m-%d')

        episodes, _ = fetch_sonarr_calendar(sonarr_url, sonarr_api_key, start_date, end_date)

        if use_cache and episodes:
            set_cached_data('sonarr_coming_soon_json', episodes, {'timestamp': time.time(), 'manual_fetch': True})

        return episodes

    except Exception as e:
        logger.error(f"Error getting Sonarr coming soon calendar: {e}")
        return None

def get_radarr_coming_soon_cached(use_cache=True, days_ahead=14):
    try:
        if use_cache:
            cached = get_cached_data('radarr_coming_soon_json', strict=True) or get_cached_data('radarr_coming_soon_json', strict=False)
            if cached:
                return cached

        _s = get_settings(decrypt_secrets=False)
        row = (_s.get("radarr_url"), _s.get("radarr_api_key")) if "id" in _s else None

        if not row or not row[0] or not row[1]:
            return None

        radarr_url = row[0].rstrip('/')
        radarr_api_key = decrypt(row[1])

        start_date = datetime.now().strftime('%Y-%m-%d')
        end_date = (datetime.now() + timedelta(days=int(days_ahead))).strftime('%Y-%m-%d')

        movies, _ = fetch_radarr_calendar(radarr_url, radarr_api_key, start_date, end_date)

        if use_cache and movies:
            set_cached_data('radarr_coming_soon_json', movies, {'timestamp': time.time(), 'manual_fetch': True})

        return movies

    except Exception as e:
        logger.error(f"Error getting Radarr coming soon calendar: {e}")
        return None

def get_ombi_requests_cached(use_cache=True):
    try:
        if use_cache:
            cached = get_cached_data('ombi_requests_json', strict=True) or get_cached_data('ombi_requests_json', strict=False)
            if cached:
                return cached

        _s = get_settings(decrypt_secrets=False)
        row = (_s.get("ombi_url"), _s.get("ombi_api_key")) if "id" in _s else None

        if not row or not row[0] or not row[1]:
            return None

        ombi_url = row[0].rstrip('/')
        ombi_api_key = decrypt(row[1])

        movies, _ = fetch_ombi_movie_requests(ombi_url, ombi_api_key)
        tv, _ = fetch_ombi_tv_requests(ombi_url, ombi_api_key)
        data = {'movies': movies or [], 'tv': tv or []}

        if use_cache and (data['movies'] or data['tv']):
            set_cached_data('ombi_requests_json', data, {'timestamp': time.time(), 'manual_fetch': True})

        return data

    except Exception as e:
        logger.error(f"Error getting Ombi requests: {e}")
        return None
