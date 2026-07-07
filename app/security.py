import html, time

import bleach, requests
from flask import abort, redirect, request, session, url_for
from functools import wraps

from app import config
from app.settings_store import get_settings

def require_csrf_for_json():
    token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    if not token or token.strip() != session.get('csrf_token'):
        abort(400)

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

def requires_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if get_settings(decrypt_secrets=False).get('login_toggle') != 'enabled':
            return f(*args, **kwargs)

        if request.headers.get('X-Internal-Token') == config.INTERNAL_TOKEN:
            return f(*args, **kwargs)

        if not session.get('authenticated'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def check_credentials(username, password):
    s = get_settings()
    expected_username = s.get('nl_username')
    expected_password = s.get('nl_password')

    if not expected_password:
        return False

    return username == expected_username and password == expected_password

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
