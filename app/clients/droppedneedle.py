import requests

from app.security import safe_get

def fetch_droppedneedle_users(base_url, api_key):
    """Returns {email_lower: droppedneedle_user_id} for DroppedNeedle users with ListenBrainz linked."""
    try:
        response = safe_get(f"{base_url}/api/v1/wrapped/users", headers={'X-Wrapped-Api-Key': api_key})
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException:
        return {}
    return {
        (u.get('email') or '').strip().lower(): u['id']
        for u in data.get('users', [])
        if u.get('email') and u.get('has_listenbrainz')
    }

def run_droppedneedle_command(base_url, api_key, user_dict, error):
    if not base_url:
        return [{}, (error + ", " if error else "") + "DroppedNeedle Error: No Base URL provided"]
    if not api_key:
        return [{}, (error + ", " if error else "") + "DroppedNeedle Error: No API key provided"]

    email_to_droppedneedle_id = fetch_droppedneedle_users(base_url, api_key)
    wrapped_dict = {}

    for user, email in user_dict.items():
        droppedneedle_id = email_to_droppedneedle_id.get((email or '').strip().lower())
        if not droppedneedle_id:
            continue
        try:
            response = safe_get(
                f"{base_url}/api/v1/wrapped/user/{droppedneedle_id}",
                headers={'X-Wrapped-Api-Key': api_key},
            )
            response.raise_for_status()
            data = response.json()
            if data.get('has_data'):
                wrapped_dict[user] = data
        except requests.exceptions.RequestException as e:
            error = (error + ", " if error else "") + f"DroppedNeedle Error: {e}"

    return [wrapped_dict, error]

def fetch_droppedneedle_server_stats(base_url, api_key):
    if not base_url or not api_key:
        return None, "DroppedNeedle Error: URL and API key are required"
    try:
        response = safe_get(f"{base_url}/api/v1/wrapped/server", headers={'X-Wrapped-Api-Key': api_key})
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        return None, f"DroppedNeedle Error: {e}"
