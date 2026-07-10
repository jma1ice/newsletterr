import math

import requests

from app.crypto import decrypt
from app.security import safe_get

import logging

logger = logging.getLogger(__name__)

def run_tautulli_command(base_url, api_key, command, section_id, error, time_range='30', start='0', y_axis='plays', stats_type='plays'):
    out_data = None
    _NO_Y_AXIS_COMMANDS = {'get_concurrent_streams_by_stream_type'}

    if command == 'get_users' or command == 'get_library_names' or command == 'get_libraries':
        api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}"
    elif command == 'get_recently_added':
        api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}&count={time_range}&section_id={section_id}&start={start}"
        logger.info(f"Tautulli API call: get_recently_added with count={time_range}, start={start}")
    elif command == 'get_home_stats':
        api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}&time_range={time_range}&stats_type={stats_type}"
    else:
        _y = f"&y_axis={y_axis}" if command not in _NO_Y_AXIS_COMMANDS else ""
        if command == 'get_plays_per_month':
            month_range = str(math.ceil(int(time_range) / 30))
            api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}&time_range={month_range}{_y}"
        else:
            api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}&time_range={time_range}{_y}"

    try:
        response = safe_get(api_url)
        response.raise_for_status()
        data = response.json()

        if data.get('response', {}).get('result') == 'success':
            out_data = data['response']['data']
        else:
            logger.error(f"Tautulli API Error: {data.get('response', {}).get('message', 'Unknown error')}")
            if error == None:
                error = f"Tautulli API Error: {data.get('response', {}).get('message', 'Unknown error')}"
            else:
                if "Multiple Tautulli API calls failed" not in error:
                    error = "Multiple Tautulli API calls failed"
    except requests.exceptions.RequestException as e:
        logger.error(f"Tautulli Connection Error: {str(e)}")
        if error == None:
            error = f"Tautulli Connection Error: {str(e)}"
        else:
            if "Multiple Tautulli API calls failed" not in error:
                error = "Multiple Tautulli API calls failed"

    return [out_data, error]
