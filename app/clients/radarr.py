import requests

from app.security import safe_get

def fetch_radarr_calendar(base_url, api_key, start_date, end_date):
    """Returns (movies, error). movies is a list of Radarr calendar entries,
    or [] on any failure."""
    if not base_url or not api_key:
        return [], "Radarr Error: URL and API key are required"
    try:
        response = safe_get(
            f"{base_url.rstrip('/')}/api/v3/calendar",
            params={
                'start': start_date,
                'end': end_date,
            },
            headers={'X-Api-Key': api_key},
        )
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        return [], f"Radarr Error: {e}"
