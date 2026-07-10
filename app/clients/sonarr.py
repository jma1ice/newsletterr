import requests

from app.security import safe_get

def fetch_sonarr_calendar(base_url, api_key, start_date, end_date):
    """Returns (episodes, error). episodes is a list of Sonarr calendar entries
    with an embedded 'series' object, or [] on any failure."""
    if not base_url or not api_key:
        return [], "Sonarr Error: URL and API key are required"
    try:
        response = safe_get(
            f"{base_url.rstrip('/')}/api/v3/calendar",
            params={
                'start': start_date,
                'end': end_date,
                'includeSeries': 'true',
                'includeEpisodeImages': 'true',
            },
            headers={'X-Api-Key': api_key},
        )
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.RequestException as e:
        return [], f"Sonarr Error: {e}"
