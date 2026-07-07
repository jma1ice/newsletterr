import base64, os, time

from app import config, state

def get_global_cache_status():
    try:
        cache_keys = ['stats', 'users', 'graph_data', 'recent_data']
        present = []
        missing = []
        oldest_age = 0.0
        date_range_display = '-'
        max_range = 0

        for key in cache_keys:
            info = get_cache_info(key)
            if info.get('exists'):
                present.append(key)
                oldest_age = max(oldest_age, info.get('age_hours', 0))
                if info.get('params'):
                    param_days = info['params'].get('time_range') or info['params'].get('days')
                    try:
                        param_days = int(param_days)
                        if param_days > max_range:
                            max_range = param_days
                    except (TypeError, ValueError):
                        pass
            else:
                missing.append(key)

        if max_range > 0:
            date_range_display = f"{max_range} day" + ("s" if max_range != 1 else "")

        if not present:
            return {
                'has_data': False,
                'status': 'No cached data',
                'age_display': 'no data',
                'class': 'cache-badge-muted',
                'missing': missing,
                'present': present
            }

        if missing:
            freshness_class = 'cache-badge-missing'
            freshness_text = f"Missing: {', '.join(missing)}"
        elif oldest_age < 1:
            freshness_class = 'cache-badge-fresh'
            freshness_text = 'Fresh'
        elif oldest_age < 24:
            freshness_class = 'cache-badge-warn'
            freshness_text = f"~{int(oldest_age)}h old"
        elif oldest_age < 168:
            freshness_class = 'cache-badge-old'
            freshness_text = f"{int(oldest_age/24)}d old"
        else:
            freshness_class = 'cache-badge-stale'
            freshness_text = 'Very old'

        return {
            'has_data': True,
            'status': f"{freshness_text} • Range {date_range_display}",
            'age_display': date_range_display,
            'class': freshness_class,
            'missing': missing,
            'present': present
        }
    except:
        return {'has_data': False, 'status': 'Cache error', 'age_display': 'error', 'class': 'cache-badge-muted'}

def can_use_cached_data_for_preview(required_days):
    try:
        stats_info = get_cache_info('stats')
        graph_info = get_cache_info('graph_data')
        
        if not (stats_info.get('exists') and graph_info.get('exists')):
            return False, "Cache data missing"
        
        if not (stats_info.get('is_usable') and graph_info.get('is_usable')):
            return False, "Cache data too old"
        
        stats_params = stats_info.get('params', {})
        if 'time_range' in stats_params:
            try:
                cached_days = int(stats_params.get('time_range', 0))
            except (TypeError, ValueError):
                cached_days = 0
            if cached_days == required_days:
                return True, f"Using cached data ({cached_days} days exact match)"
            else:
                return False, f"Cached range ({cached_days} days) != requested ({required_days} days)"
        return False, f"No cached range metadata (need {required_days} days)"
    except Exception as e:
        return False, f"Error checking cache: {str(e)}"

def is_cache_valid(cache_key, strict=True):
    cache_entry = state.cache_storage.get(cache_key)
    if cache_entry and cache_entry['data'] is not None:
        age = time.time() - cache_entry['timestamp']
        duration = config.CACHE_DURATION if strict else config.CACHE_EXTENDED_DURATION
        return age < duration
    return False

def get_cached_data(cache_key, strict=True):
    if is_cache_valid(cache_key, strict):
        return state.cache_storage[cache_key]['data']
    return None

def set_cached_data(cache_key, data, params=None):
    state.cache_storage[cache_key] = {
        'data': data,
        'timestamp': time.time(),
        'params': params
    }

def get_cache_info(cache_key):
    cache_entry = state.cache_storage.get(cache_key)
    if cache_entry and cache_entry['data'] is not None:
        age = time.time() - cache_entry['timestamp']
        return {
            'exists': True,
            'age_hours': age / 3600,
            'params': cache_entry.get('params'),
            'is_fresh': age < config.CACHE_DURATION,
            'is_usable': age < config.CACHE_EXTENDED_DURATION
        }
    return {'exists': False}

def clear_cache(cache_key=None):
    if cache_key:
        state.cache_storage[cache_key] = {'data': None, 'timestamp': 0, 'params': None}
    else:
        for key in state.cache_storage:
            state.cache_storage[key] = {'data': None, 'timestamp': 0, 'params': None}

def gkak():
    env_override = os.environ.get('KLIPY', '').strip()
    if env_override:
        return env_override
    try:
        return base64.b64decode(config.k1).decode() + bytes.fromhex(config.k2).decode() + "".join(chr(c) for c in config.k3)
    except Exception:
        return ''
