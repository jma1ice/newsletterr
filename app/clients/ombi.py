import requests

from app.security import safe_get

def fetch_ombi_movie_requests(base_url, api_key):
    """Returns (requests, error). requests is a list of Ombi movie request
    entries, or [] on any failure."""
    if not base_url or not api_key:
        return [], "Ombi Error: URL and API key are required"
    try:
        response = safe_get(
            f"{base_url.rstrip('/')}/api/v1/Request/movie",
            headers={'ApiKey': api_key},
        )
        response.raise_for_status()
        return response.json(), None
    except (requests.exceptions.RequestException, ValueError) as e:
        return [], f"Ombi Error: {e}"

def fetch_ombi_tv_requests(base_url, api_key):
    """Returns (requests, error). requests is a list of Ombi TV request
    entries, each with an embedded 'childRequests' array (one per season),
    or [] on any failure."""
    if not base_url or not api_key:
        return [], "Ombi Error: URL and API key are required"
    try:
        response = safe_get(
            f"{base_url.rstrip('/')}/api/v1/Request/tv",
            headers={'ApiKey': api_key},
        )
        response.raise_for_status()
        return response.json(), None
    except (requests.exceptions.RequestException, ValueError) as e:
        return [], f"Ombi Error: {e}"
