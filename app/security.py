import hmac, html, time

import bleach, requests
from flask import abort, jsonify, redirect, request, session, url_for
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

from app import config
from app.crypto import decrypt
from app.db import db_connect
from app.settings_store import get_settings

import logging

logger = logging.getLogger(__name__)

def require_csrf_for_json():
    token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    expected = session.get('csrf_token') or ""
    if not token or not hmac.compare_digest(token.strip(), expected):
        abort(400)

def json_body(required=()):
    """Parse a JSON object body and validate required fields.

    Returns (data, None) on success or (None, (response, 400)) on a malformed
    body or missing field, so routes stay 400-not-500 on junk input:
        data, err = json_body(["to_emails", "subject"])
        if err:
            return err
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({"error": "Request body must be a JSON object"}), 400)
    missing = [f for f in required if data.get(f) in (None, "")]
    if missing:
        return None, (jsonify({"error": f"Missing required field(s): {', '.join(missing)}"}), 400)
    return data, None

def sanitize_html_input(text):
    if not text:
        return ""

    allowed_tags = [
        'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'blockquote', 'a', 'img', 'div', 'span'
    ]

    allowed_attributes = {
        'a': ['href', 'title'],
        'img': ['src', 'alt', 'title', 'width', 'height'],
        'div': ['class'],
        'span': ['class', 'style']
    }

    allowed_protocols = ['http', 'https', 'mailto']

    return bleach.clean(
        text,
        tags=allowed_tags,
        attributes=allowed_attributes,
        protocols=allowed_protocols,
        strip=True
    )

def escape_html_output(text):
    if not text:
        return ""
    return html.escape(text)

def admin_configured():
    s = get_settings(decrypt_secrets=False)
    return bool(s.get('nl_username')) and bool(s.get('nl_password'))

def requires_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # internal server-to-self calls (image proxy) carry a per-process token
        token = request.headers.get('X-Internal-Token')
        if token and hmac.compare_digest(token, config.INTERNAL_TOKEN):
            return f(*args, **kwargs)

        if not admin_configured():
            return redirect(url_for('auth.setup'))

        if not session.get('authenticated'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def set_admin_credentials(username, password):
    conn = db_connect()
    conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
    conn.execute(
        "UPDATE settings SET login_toggle = 'enabled', nl_username = ?, nl_password = ? WHERE id = 1",
        (username, generate_password_hash(password)),
    )
    conn.commit()
    conn.close()

def check_credentials(username, password):
    s = get_settings(decrypt_secrets=False)
    expected_username = s.get('nl_username')
    stored = s.get('nl_password')

    if not stored or username != expected_username:
        return False

    # current scheme: a werkzeug password hash
    try:
        if check_password_hash(stored, password):
            return True
    except Exception:
        logger.debug("password hash check failed to parse stored value", exc_info=True)

    # legacy scheme: Fernet-encrypted plaintext. If it matches, transparently
    # upgrade the stored value to a hash so the legacy form disappears.
    legacy = decrypt(stored)
    if legacy and hmac.compare_digest(legacy, password):
        set_admin_credentials(username, password)
        return True

    return False

def safe_get(url: str, *, timeout: int = 120, retries: int = 2, **kwargs):
    for attempt in range(retries + 1):
        try:
            return requests.get(url, timeout=timeout, **kwargs)
        except requests.RequestException as e:
            if attempt == retries:
                raise
            time.sleep(1.0 * (attempt + 1))

def sanitize_html(html: str) -> str:
    allowed_tags = [
        'p','br','strong','em','b','i','u','ul','ol','li','a','h1','h2','h3','h4','h5','h6',
        'blockquote','code','pre','span'
    ]
    allowed_attrs = {
        'a': ['href','title','target','rel'],
        'span': ['style'],
        '*': ['style']
    }
    cleaned = bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs, strip=True)
    return cleaned
