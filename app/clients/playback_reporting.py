"""Playback Reporting plugin client: time-series graphs for Jellyfin and Emby."""
from collections import OrderedDict
from datetime import datetime, timedelta

from app.security import safe_get
from app.settings_store import get_settings
from app.crypto import decrypt

import logging

logger = logging.getLogger(__name__)

API_BASE = "/user_usage_stats"
PLAY_ACTIVITY_PATH = f"{API_BASE}/PlayActivity"
HOURLY_PATH = f"{API_BASE}/HourlyReport"
BREAKDOWN_PATH = f"{API_BASE}/BreakdownReport"

# The graphs this backend can actually produce, in the order they are offered.
# Names match the Plex/Tautulli ones where the meaning matches, so a template
# built on Plex keeps naming the same thing after a switch.
GRAPH_NAMES = (
    'Plays by Date',
    'Plays by Day',
    'Plays by Hour',
    'Plays by Top Users',
    'Plays by Top Platforms',
)

def _connection():
    s = get_settings(decrypt_secrets=False)
    if s.get('playback_reporting_enabled') != 'enabled':
        return None, None
    server_type = (s.get('media_server_type') or 'plex').strip().lower()
    if server_type not in ('jellyfin', 'emby'):
        return None, None
    url = (s.get('jellyfin_url') or '').rstrip('/')
    key = s.get('jellyfin_api_key') or ''
    if not url or not key:
        return None, None
    return url, decrypt(key)

def _headers(api_key):
    return {'Accept': 'application/json', 'X-Emby-Token': api_key}

def _get(url, path, api_key, params=None):
    try:
        response = safe_get(f"{url}{path}", params=params or {}, headers=_headers(api_key), timeout=15)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.info(f"Playback Reporting {path} unavailable: {e}")
        return None

def _pairs(payload):
    out = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, (int, float)):
                out.append((str(key), value))
            elif isinstance(value, dict):
                numbers = [v for v in value.values() if isinstance(v, (int, float))]
                if numbers:
                    out.append((str(key), sum(numbers)))
        return out
    if isinstance(payload, list):
        for entry in payload:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    out.append((str(entry[0]), float(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                label = next((entry[k] for k in ('label', 'name', 'key', 'Name', 'Label')
                              if entry.get(k) is not None), None)
                value = next((entry[k] for k in ('count', 'value', 'plays', 'Count', 'Value')
                              if entry.get(k) is not None), None)
                if label is not None and isinstance(value, (int, float)):
                    out.append((str(label), value))
    return out

def _graph(categories, name, data):
    if not categories or not data:
        return None
    return {'categories': list(categories), 'series': [{'name': name, 'data': list(data)}]}

def _plays_by_date(url, api_key, days):
    payload = _get(url, PLAY_ACTIVITY_PATH, api_key, {'days': days, 'end_date': datetime.now().strftime('%Y-%m-%d')})
    pairs = _pairs(payload)
    if not pairs:
        return None, None
    by_day = {label[:10]: value for label, value in pairs}
    today = datetime.now().date()
    categories, data = [], []
    for offset in range(int(days) - 1, -1, -1):
        day = today - timedelta(days=offset)
        key = day.isoformat()
        categories.append(key)
        data.append(by_day.get(key, 0))
    return categories, data

def _plays_by_weekday(categories, data):
    if not categories or not data:
        return None
    names = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
    totals = OrderedDict((n, 0) for n in names)
    for label, value in zip(categories, data):
        try:
            totals[names[datetime.fromisoformat(label).weekday()]] += value
        except (ValueError, TypeError, IndexError):
            continue
    return _graph(list(totals), 'Plays', list(totals.values()))

def _hourly(url, api_key, days):
    pairs = _pairs(_get(url, HOURLY_PATH, api_key, {'days': days}))
    if not pairs:
        return None
    # the report keys hours as '0'..'23' or 'DayOfWeek-Hour' depending on the
    # release; sum whatever resolves to an hour and drop the rest
    totals = OrderedDict((f"{h:02d}", 0) for h in range(24))
    for label, value in pairs:
        hour = label.split('-')[-1].strip()
        if hour.isdigit() and 0 <= int(hour) <= 23:
            totals[f"{int(hour):02d}"] += value
    if not any(totals.values()):
        return None
    return _graph(list(totals), 'Plays', list(totals.values()))

def _breakdown(url, api_key, days, breakdown_type, series_name, limit=10):
    pairs = _pairs(_get(url, BREAKDOWN_PATH, api_key, {'days': days, 'type': breakdown_type}))
    if not pairs:
        return None
    pairs.sort(key=lambda p: p[1], reverse=True)
    pairs = pairs[:limit]
    return _graph([p[0] for p in pairs], series_name, [p[1] for p in pairs])

def fetch_playback_reporting_graphs(days=30):
    url, api_key = _connection()
    if not url:
        return [], []

    graphs, names = [], []

    categories, data = _plays_by_date(url, api_key, days)
    by_date = _graph(categories, 'Plays', data) if categories else None
    if by_date:
        graphs.append(by_date)
        names.append('Plays by Date')

        by_weekday = _plays_by_weekday(categories, data)
        if by_weekday:
            graphs.append(by_weekday)
            names.append('Plays by Day')

    for graph, name in (
        (_hourly(url, api_key, days), 'Plays by Hour'),
        (_breakdown(url, api_key, days, 'UserId', 'Plays'), 'Plays by Top Users'),
        (_breakdown(url, api_key, days, 'ClientName', 'Plays'), 'Plays by Top Platforms'),
    ):
        if graph:
            graphs.append(graph)
            names.append(name)

    if not graphs:
        logger.info("Playback Reporting produced no graphs; leaving the graph list empty")
    return graphs, [{'command': name, 'name': name} for name in names]

def ping_playback_reporting(url, api_key):
    response = safe_get(f"{url.rstrip('/')}{PLAY_ACTIVITY_PATH}", params={'days': 1},
                        headers=_headers(api_key), timeout=10)
    response.raise_for_status()
    return response
