
import requests
from flask import Blueprint, jsonify, request
from urllib.parse import quote_plus, urlparse

from app import state
from app.db import db_connect
from app.settings_store import get_settings
from app.cache import gkak
from app.crypto import encrypt, decrypt
from app.security import requires_auth, safe_get
from app.clients.plex import get_plex_client_identifier, get_plex_headers

import logging

logger = logging.getLogger(__name__)

bp = Blueprint('api', __name__)

@bp.route('/api/test/tautulli', methods=['POST'])
@requires_auth
def test_tautulli():
    data = request.get_json()
    url = (data.get('url') or '').rstrip('/')
    api_key = (data.get('api_key') or '').strip()
    if not url:
        return jsonify({'status': 'error', 'message': 'Tautulli URL is required'})
    if not api_key:
        return jsonify({'status': 'error', 'message': 'Tautulli API key is required'})
    try:
        r = requests.get(f"{url}/api/v2", params={'apikey': api_key, 'cmd': 'arnold'}, timeout=10)
        resp = r.json()
        if resp.get('response', {}).get('result') == 'success':
            return jsonify({'status': 'ok', 'message': 'Connected to Tautulli'})
        msg = resp.get('response', {}).get('message') or 'Unexpected response, check your API key'
        return jsonify({'status': 'error', 'message': msg})
    except requests.exceptions.ConnectionError:
        return jsonify({'status': 'error', 'message': 'Tautulli is unreachable at that URL'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@bp.route('/api/test/conjurr', methods=['POST'])
@requires_auth
def test_conjurr():
    data = request.get_json()
    url = (data.get('url') or '').rstrip('/')
    if not url:
        return jsonify({'status': 'error', 'message': 'Conjurr URL is required'})
    try:
        r = requests.get(f"{url}/", timeout=10, allow_redirects=True)
        if urlparse(r.url).path.rstrip('/') == '/settings':
            return jsonify({'status': 'warning', 'message': 'Conjurr is reachable but not configured, complete setup in Conjurr settings'})
        return jsonify({'status': 'ok', 'message': 'Connected to Conjurr'})
    except requests.exceptions.ConnectionError:
        return jsonify({'status': 'error', 'message': 'Conjurr is unreachable at that URL'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@bp.route('/api/test/droppedneedle', methods=['POST'])
@requires_auth
def test_droppedneedle():
    data = request.get_json()
    url = (data.get('url') or '').rstrip('/')
    api_key = data.get('api_key') or ''
    if not url:
        return jsonify({'status': 'error', 'message': 'DroppedNeedle URL is required'})
    if not api_key:
        return jsonify({'status': 'error', 'message': 'DroppedNeedle Wrapped API key is required'})
    try:
        r = safe_get(f"{url}/api/v1/wrapped/users", timeout=10, headers={'X-Wrapped-Api-Key': api_key})
        if r.status_code == 401:
            return jsonify({'status': 'error', 'message': 'DroppedNeedle rejected the API key'})
        r.raise_for_status()
        return jsonify({'status': 'ok', 'message': 'Connected to DroppedNeedle'})
    except requests.exceptions.ConnectionError:
        return jsonify({'status': 'error', 'message': 'DroppedNeedle is unreachable at that URL'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@bp.route('/api/gif/search', methods=['GET'])
@requires_auth
def gif_search():
    query = request.args.get('q', '').strip()
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(max(8, int(request.args.get('per_page', 24))), 50)
    except (TypeError, ValueError):
        return jsonify({"error": "page and per_page must be integers"}), 400

    if not query:
        return jsonify({"results": []}), 200

    ak = gkak()
    if not ak:
        return jsonify({"error": "GIF search not configured"}), 503
    
    customer_id = get_plex_client_identifier()

    try:
        url = f"https://api.klipy.com/api/v1/{ak}/gifs/search"
        resp = safe_get(
            url,
            params={
                "q": query,
                "page": page,
                "per_page": per_page,
                "customer_id": customer_id,
                "content_filter": "off",
                "locale": "us",
                "format_filter": "gif,webp"
            },
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get('data', {}).get('data', []):
            hd = item.get('file', {}).get('hd', {})
            gif = hd.get('gif', {})
            webp = hd.get('webp', {})
            results.append({
                'id': item.get('id'),
                'title': item.get('title', ''),
                'url': webp.get('url', '') or gif.get('url', ''),
                'width': webp.get('width', '') or gif.get('width', 0),
                'height': webp.get('height', '') or gif.get('height', 0),
            })

        return jsonify({
            "results": results,
            "page": page,
            "per_page": per_page
        })
    except Exception as e:
        logger.error(f"GIF search error: {e}")
        return jsonify({"error": "GIF search failed"}), 500

@bp.post('/api/plex/pin')
@requires_auth
def plex_create_pin():
    response = requests.post("https://plex.tv/api/v2/pins", headers=state.plex_headers, timeout=10)
    response.raise_for_status()
    data = response.json()

    auth_url = (
        "https://plex.tv/link?"
        f"clientID={quote_plus(state.plex_headers['X-Plex-Client-Identifier'])}"
        f"&code={quote_plus(data['code'])}"
    )
    return jsonify({"pin_id": data["id"], "code": data["code"], "auth_url": auth_url, "expires_in": data.get("expiresIn", 900)})

@bp.get('/api/plex/pin/<int:pin_id>')
@requires_auth
def plex_poll_pin(pin_id: int):
    response = requests.get(f"https://plex.tv/api/v2/pins/{pin_id}", headers=state.plex_headers, timeout=10)
    response.raise_for_status()
    data = response.json()

    token = data.get("authToken")
    if token:
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (id, plex_token)
            VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET plex_token = excluded.plex_token
        """, (encrypt(token),))
        conn.commit()
        conn.close()

        return jsonify({"connected": True})
    return jsonify({"connected": False})

@bp.get('/api/plex/info')
@requires_auth
def plex_get_info():
    token = get_settings(decrypt_secrets=False).get("plex_token")
    if not token:
        return jsonify({"connected": False, "error": "Plex is not connected"}), 400

    url = "https://plex.tv/api/v2/resources"
    headers = get_plex_headers({"X-Plex-Token": decrypt(token)})
    params = {
        "includeHttps": "1"
    }

    try:
        response = safe_get(url, headers=headers, params=params)
        data = response.json()
    except Exception:
        logger.debug("plex info fetch/parse failed", exc_info=True)
        return jsonify({"connected": False, "error": "Could not reach Plex.tv"}), 502

    def select_best_connection(connections):
        https_connections = [connection for connection in connections if connection.get('protocol') == 'https']

        if https_connections:
            local_https = [connection for connection in https_connections if connection.get('local')]
            if local_https:
                return local_https[0]['uri']

            return https_connections[0]['uri']

        return connections[0]['uri'] if connections else None

    if not isinstance(data, list) or not data:
        return jsonify({"connected": False, "error": "No Plex servers found on this account"}), 400

    server = data[0]
    best_url = select_best_connection(server.get('connections') or [])

    if not best_url:
        return jsonify({"connected": False, "error": "No suitable connection found"})

    conn = db_connect()
    conn.execute("""
        INSERT INTO settings (id, server_name, plex_url)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET server_name = excluded.server_name, plex_url = excluded.plex_url
    """, (server.get('name'), best_url))
    conn.commit()
    conn.close()

    return jsonify({"connected": True})
