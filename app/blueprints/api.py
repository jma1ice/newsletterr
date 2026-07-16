
import requests
from flask import Blueprint, jsonify, request
from urllib.parse import quote_plus, urlparse

from app import state
from app.db import db_connect
from app.settings_store import get_settings
from app.cache import gkak
from app.crypto import encrypt, decrypt
from app.security import requires_auth, safe_get, require_csrf_for_json
from app.clients.plex import get_plex_client_identifier, get_plex_headers

import logging

logger = logging.getLogger(__name__)

bp = Blueprint('api', __name__)

def test_tautulli_connection(url, api_key):
    url = (url or '').rstrip('/')
    api_key = (api_key or '').strip()
    if not url:
        return {'status': 'error', 'message': 'Tautulli URL is required'}
    if not api_key:
        return {'status': 'error', 'message': 'Tautulli API key is required'}
    try:
        r = requests.get(f"{url}/api/v2", params={'apikey': api_key, 'cmd': 'arnold'}, timeout=10)
        resp = r.json()
        if resp.get('response', {}).get('result') == 'success':
            return {'status': 'ok', 'message': 'Connected to Tautulli'}
        msg = resp.get('response', {}).get('message') or 'Unexpected response, check your API key'
        return {'status': 'error', 'message': msg}
    except requests.exceptions.ConnectionError:
        return {'status': 'error', 'message': 'Tautulli is unreachable at that URL'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def test_conjurr_connection(url):
    url = (url or '').rstrip('/')
    if not url:
        return {'status': 'error', 'message': 'Conjurr URL is required'}
    try:
        r = requests.get(f"{url}/", timeout=10, allow_redirects=True)
        if urlparse(r.url).path.rstrip('/') == '/settings':
            return {'status': 'warning', 'message': 'Conjurr is reachable but not configured, complete setup in Conjurr settings'}
        return {'status': 'ok', 'message': 'Connected to Conjurr'}
    except requests.exceptions.ConnectionError:
        return {'status': 'error', 'message': 'Conjurr is unreachable at that URL'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def test_droppedneedle_connection(url, api_key):
    url = (url or '').rstrip('/')
    api_key = api_key or ''
    if not url:
        return {'status': 'error', 'message': 'DroppedNeedle URL is required'}
    if not api_key:
        return {'status': 'error', 'message': 'DroppedNeedle Wrapped API key is required'}
    try:
        r = safe_get(f"{url}/api/v1/wrapped/users", timeout=10, headers={'X-Wrapped-Api-Key': api_key})
        if r.status_code == 401:
            return {'status': 'error', 'message': 'DroppedNeedle rejected the API key'}
        r.raise_for_status()
        return {'status': 'ok', 'message': 'Connected to DroppedNeedle'}
    except requests.exceptions.ConnectionError:
        return {'status': 'error', 'message': 'DroppedNeedle is unreachable at that URL'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def test_sonarr_connection(url, api_key):
    url = (url or '').rstrip('/')
    api_key = (api_key or '').strip()
    if not url:
        return {'status': 'error', 'message': 'Sonarr URL is required'}
    if not api_key:
        return {'status': 'error', 'message': 'Sonarr API key is required'}
    try:
        r = safe_get(f"{url}/api/v3/system/status", timeout=10, headers={'X-Api-Key': api_key})
        if r.status_code == 401:
            return {'status': 'error', 'message': 'Sonarr rejected the API key'}
        r.raise_for_status()
        return {'status': 'ok', 'message': 'Connected to Sonarr'}
    except requests.exceptions.ConnectionError:
        return {'status': 'error', 'message': 'Sonarr is unreachable at that URL'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def test_radarr_connection(url, api_key):
    url = (url or '').rstrip('/')
    api_key = (api_key or '').strip()
    if not url:
        return {'status': 'error', 'message': 'Radarr URL is required'}
    if not api_key:
        return {'status': 'error', 'message': 'Radarr API key is required'}
    try:
        r = safe_get(f"{url}/api/v3/system/status", timeout=10, headers={'X-Api-Key': api_key})
        if r.status_code == 401:
            return {'status': 'error', 'message': 'Radarr rejected the API key'}
        r.raise_for_status()
        return {'status': 'ok', 'message': 'Connected to Radarr'}
    except requests.exceptions.ConnectionError:
        return {'status': 'error', 'message': 'Radarr is unreachable at that URL'}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def _fallback(posted, saved):
    posted = (posted or '').strip()
    return posted or (saved or '')

@bp.route('/api/test/tautulli', methods=['POST'])
@requires_auth
def test_tautulli():
    data = request.get_json()
    s = get_settings()
    url = _fallback(data.get('url'), s.get('tautulli_url'))
    api_key = _fallback(data.get('api_key'), s.get('tautulli_api'))
    return jsonify(test_tautulli_connection(url, api_key))

@bp.route('/api/test/conjurr', methods=['POST'])
@requires_auth
def test_conjurr():
    data = request.get_json()
    s = get_settings()
    url = _fallback(data.get('url'), s.get('conjurr_url'))
    return jsonify(test_conjurr_connection(url))

@bp.route('/api/test/droppedneedle', methods=['POST'])
@requires_auth
def test_droppedneedle():
    data = request.get_json()
    s = get_settings()
    url = _fallback(data.get('url'), s.get('droppedneedle_url'))
    api_key = _fallback(data.get('api_key'), s.get('droppedneedle_api_key'))
    return jsonify(test_droppedneedle_connection(url, api_key))

@bp.route('/api/test/sonarr', methods=['POST'])
@requires_auth
def test_sonarr():
    data = request.get_json()
    s = get_settings()
    url = _fallback(data.get('url'), s.get('sonarr_url'))
    api_key = _fallback(data.get('api_key'), s.get('sonarr_api_key'))
    return jsonify(test_sonarr_connection(url, api_key))

@bp.route('/api/test/radarr', methods=['POST'])
@requires_auth
def test_radarr():
    data = request.get_json()
    s = get_settings()
    url = _fallback(data.get('url'), s.get('radarr_url'))
    api_key = _fallback(data.get('api_key'), s.get('radarr_api_key'))
    return jsonify(test_radarr_connection(url, api_key))

PRIDE_FLAGS = frozenset({'off', 'rainbow', 'trans', 'bi', 'pan', 'nonbinary', 'lesbian', 'ace', 'progress'})

@bp.route('/api/appearance', methods=['POST'])
@requires_auth
def set_appearance():
    # Instant appearance changes (the sidebar theme toggle) persist here so they
    # follow the login. Pride and floating also persist through the settings
    # form; this endpoint only touches the three appearance columns.
    require_csrf_for_json()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    updates = {}
    if 'theme' in data:
        theme = str(data.get('theme') or '').strip().lower()
        if theme not in ('light', 'dark'):
            return jsonify({"error": "theme must be light or dark"}), 400
        updates['appearance_theme'] = theme
    if 'pride' in data:
        pride = str(data.get('pride') or 'off').strip().lower()
        if pride not in PRIDE_FLAGS:
            return jsonify({"error": "invalid pride flag"}), 400
        updates['pride_flag'] = pride
    if 'snapins_floating' in data:
        updates['snapins_floating'] = '0' if str(data.get('snapins_floating')).lower() in ('0', 'false') else '1'

    if not updates:
        return jsonify({"error": "no appearance fields provided"}), 400

    # Column names come from the fixed whitelist above, never user input.
    conn = db_connect()
    try:
        assignments = ', '.join(f"{col} = ?" for col in updates)
        conn.execute(f"UPDATE settings SET {assignments} WHERE id = 1", list(updates.values()))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"status": "ok", **updates})

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
    # strong=true yields a full account token via the canonical Plex OAuth flow
    # (app.plex.tv/auth). The old plex.tv/link device flow produced a limited
    # token that plex.tv honored but the Plex Media Server rejected with 401 on
    # library endpoints (issue #159).
    response = requests.post(
        "https://plex.tv/api/v2/pins",
        headers=state.plex_headers,
        params={"strong": "true"},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    client_id = state.plex_headers['X-Plex-Client-Identifier']
    product = state.plex_headers.get('X-Plex-Product', 'Newsletterr')
    device_name = state.plex_headers.get('X-Plex-Device-Name', 'Newsletterr')
    auth_url = (
        "https://app.plex.tv/auth#?"
        f"clientID={quote_plus(client_id)}"
        f"&code={quote_plus(data['code'])}"
        f"&context%5Bdevice%5D%5Bproduct%5D={quote_plus(product)}"
        f"&context%5Bdevice%5D%5BdeviceName%5D={quote_plus(device_name)}"
    )
    logger.info(f"Created Plex OAuth PIN {data["id"]} (strong)")
    return jsonify({"pin_id": data["id"], "code": data["code"], "auth_url": auth_url, "expires_in": data.get("expiresIn", 900)})

@bp.get('/api/plex/pin/<int:pin_id>')
@requires_auth
def plex_poll_pin(pin_id: int):
    response = requests.get(f"https://plex.tv/api/v2/pins/{pin_id}", headers=state.plex_headers, timeout=10)
    response.raise_for_status()
    data = response.json()

    token = data.get("authToken")
    if token:
        logger.info(f"Plex PIN {pin_id} authorized; token length={len(token)}")
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
    settings = get_settings(decrypt_secrets=False)
    token = settings.get("plex_token")
    if not token:
        return jsonify({"connected": False, "error": "Plex is not connected"}), 400

    plain_token = decrypt(token)
    url = "https://plex.tv/api/v2/resources"
    headers = get_plex_headers({"X-Plex-Token": plain_token})
    params = {
        "includeHttps": "1"
    }

    try:
        response = safe_get(url, headers=headers, params=params)
        data = response.json()
    except Exception:
        logger.debug("plex info fetch/parse failed", exc_info=True)
        return jsonify({"connected": False, "error": "Could not reach Plex.tv"}), 502

    def connection_label(connection):
        if connection.get('relay'):
            return 'Relay'
        return 'Local' if connection.get('local') else 'Remote'

    def select_best_connection(connections):
        # Direct connections first (local https), then any direct https, then
        # any non-relay, and only fall back to a relay if nothing else exists.
        for predicate in (
            lambda c: c['protocol'] == 'https' and c['local'] and not c['relay'],
            lambda c: c['protocol'] == 'https' and not c['relay'],
            lambda c: not c['relay'],
        ):
            match = [c for c in connections if predicate(c)]
            if match:
                return match[0]['uri']
        return connections[0]['uri'] if connections else None

    if not isinstance(data, list) or not data:
        return jsonify({"connected": False, "error": "No Plex servers found on this account"}), 400

    # Prefer an owned server; fall back to the first entry.
    server = next((srv for srv in data if srv.get('owned')), data[0])

    # Root cause of #159: /resources returns a per-server accessToken. When the
    # server comes back owned:true it equals the account OAuth token, but when it
    # comes back owned:false (seen intermittently for the same server, Plex Home/
    # session dependent) it is a distinct server-scoped token that the Plex Media
    # Server requires for direct API calls. The account PIN token 401s on library
    # endpoints in that case. Store the per-server accessToken for all PMS calls,
    # falling back to the account token when the server did not provide one.
    server_access_token = server.get('accessToken') or plain_token

    connections = [
        {
            'uri': c.get('uri'),
            'local': bool(c.get('local')),
            'relay': bool(c.get('relay')),
            'protocol': c.get('protocol'),
            'label': connection_label(c),
        }
        for c in (server.get('connections') or [])
        if c.get('uri')
    ]

    recommended_url = select_best_connection(connections)

    if not recommended_url:
        return jsonify({"connected": False, "error": "No suitable connection found"})

    # Respect a user-chosen URL: only auto-fill plex_url on first connect (when
    # it is empty). Force Reconnect must not clobber a manual LAN address; the
    # frontend offers the full connection list as a dropdown for switching.
    existing_url = settings.get('plex_url') or ''
    save_url = existing_url or recommended_url

    logger.info(f"Plex resource {server.get('name')} owned={server.get('owned')} server_token_differs={server_access_token != plain_token}")

    conn = db_connect()
    conn.execute("""
        INSERT INTO settings (id, server_name, plex_url, plex_token)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET server_name = excluded.server_name, plex_url = excluded.plex_url, plex_token = excluded.plex_token
    """, (server.get('name'), save_url, encrypt(server_access_token)))
    conn.commit()
    conn.close()

    # Diagnostic for #159: confirm the server-scoped token we just stored is
    # actually accepted by the Plex Media Server. /identity is unauthenticated
    # and cannot reveal a bad token; /library/sections requires a valid one.
    probe_url = (save_url or recommended_url or '').rstrip('/')
    if probe_url:
        try:
            probe = safe_get(
                f"{probe_url}/library/sections",
                headers=get_plex_headers({"X-Plex-Token": server_access_token}),
                timeout=10,
            )
            logger.info(f"Plex library probe {probe_url} -> HTTP {probe.status_code} (server_token_differs={server_access_token != plain_token})")
            if probe.status_code == 401:
                logger.warning(
                    f"Plex token rejected by the media server at {probe_url} (401) despite "
                    "plex.tv accepting it. This is the #159 symptom.")
        except Exception:
            logger.debug("Plex library probe failed", exc_info=True)

    return jsonify({
        "connected": True,
        "server_name": server.get('name'),
        "connections": connections,
        "recommended_url": recommended_url,
        "plex_url": save_url,
    })
