import secrets
import threading
import time

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app.config import DEFAULT_RADARR_URL, DEFAULT_SONARR_URL, DEFAULT_OMBI_URL, DEFAULT_SEERR_URL
from app.crypto import encrypt
from app.db import db_connect
from app.settings_store import get_settings
from app.security import requires_auth, check_credentials, admin_configured, set_admin_credentials

import logging

logger = logging.getLogger(__name__)

bp = Blueprint('auth', __name__)

def _required_setup_complete():
    """Admin account + email server: the two mandatory setup steps. The
    remaining integrations (Plex/Tautulli/Conjurr/DroppedNeedle) are optional
    and can be finished later from Settings, so they don't gate this."""
    if not admin_configured():
        return False
    s = get_settings(decrypt_secrets=False)
    return bool(s.get('from_email'))

# In-memory login throttle: per-IP failure counter with a lockout window.
_MAX_FAILS = 5
_WINDOW = 300          # count failures within this many seconds
_LOCKOUT = 3600        # lock out for this long once the limit is hit
_attempts = {}         # ip -> [failure_timestamps]
_attempts_lock = threading.Lock()

def _client_ip():
    return (request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
            or request.remote_addr or 'unknown')

def _rate_limited(ip):
    now = time.time()
    with _attempts_lock:
        fails = [t for t in _attempts.get(ip, []) if now - t < _LOCKOUT]
        _attempts[ip] = fails
        return len(fails) >= _MAX_FAILS

def _record_failure(ip):
    now = time.time()
    with _attempts_lock:
        fails = [t for t in _attempts.get(ip, []) if now - t < _WINDOW]
        fails.append(now)
        _attempts[ip] = fails

def _clear_failures(ip):
    with _attempts_lock:
        _attempts.pop(ip, None)

SETUP_STEPS = ['admin', 'email', 'plex', 'tautulli', 'conjurr', 'droppedneedle', 'sonarr', 'radarr', 'ombi', 'seerr']

@bp.route('/setup', methods=['GET', 'POST'])
def setup():
    if admin_configured():
        if _required_setup_complete():
            return redirect(url_for('auth.login'))
        return redirect(url_for('auth.setup_email'))

    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        if not username or not password:
            return render_template('setup.html', step='admin', steps=SETUP_STEPS, error='Username and password are required', csrf_token=session["csrf_token"])
        if len(password) < 8:
            return render_template('setup.html', step='admin', steps=SETUP_STEPS, error='Password must be at least 8 characters', csrf_token=session["csrf_token"])
        if password != confirm:
            return render_template('setup.html', step='admin', steps=SETUP_STEPS, error='Passwords do not match', csrf_token=session["csrf_token"])

        set_admin_credentials(username, password)
        session['authenticated'] = True
        session['username'] = username
        logger.info("Admin account created via first-run setup")
        return redirect(url_for('auth.setup_email'))

    return render_template('setup.html', step='admin', steps=SETUP_STEPS, csrf_token=session["csrf_token"])

@bp.route('/setup/email', methods=['GET', 'POST'])
@requires_auth
def setup_email():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    s = get_settings(decrypt_secrets=False)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        from_email = request.form.get('from_email', '').strip()
        from_name = request.form.get('from_name', '').strip()
        smtp_server = request.form.get('smtp_server', '').strip()
        smtp_port = request.form.get('smtp_port', '587').strip()
        smtp_protocol = request.form.get('smtp_protocol', 'TLS')
        smtp_username = request.form.get('smtp_username', '').strip()
        password = request.form.get('password', '').strip()
        server_name = request.form.get('server_name', '').strip()

        if not from_email or not smtp_server or not password:
            return render_template('setup.html', step='email', steps=SETUP_STEPS, settings=s,
                                    error='From email, SMTP server, and password are required',
                                    csrf_token=session["csrf_token"])
        try:
            smtp_port = int(smtp_port)
        except ValueError:
            smtp_port = 587

        conn = db_connect()
        conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
        conn.execute(
            """UPDATE settings SET from_email = ?, from_name = ?, smtp_server = ?, smtp_port = ?,
               smtp_protocol = ?, smtp_username = ?, password = ?, server_name = ? WHERE id = 1""",
            (from_email, from_name, smtp_server, smtp_port, smtp_protocol, smtp_username, encrypt(password), server_name),
        )
        conn.commit()
        conn.close()
        logger.info("Email server configured via first-run setup")
        return redirect(url_for('auth.setup_plex'))

    return render_template('setup.html', step='email', steps=SETUP_STEPS, settings=s, csrf_token=session["csrf_token"])

@bp.route('/setup/plex', methods=['GET', 'POST'])
@requires_auth
def setup_plex():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    s = get_settings(decrypt_secrets=False)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        plex_url = request.form.get('plex_url', '').strip()
        if plex_url:
            conn = db_connect()
            conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
            conn.execute("UPDATE settings SET plex_url = ? WHERE id = 1", (plex_url,))
            conn.commit()
            conn.close()
        return redirect(url_for('auth.setup_tautulli'))

    return render_template('setup.html', step='plex', steps=SETUP_STEPS, settings=s, csrf_token=session["csrf_token"])

@bp.route('/setup/tautulli', methods=['GET', 'POST'])
@requires_auth
def setup_tautulli():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    s = get_settings(decrypt_secrets=False)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        tautulli_url = request.form.get('tautulli_url', '').strip()
        tautulli_api = request.form.get('tautulli_api', '').strip()
        if tautulli_url and tautulli_api:
            conn = db_connect()
            conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
            conn.execute("UPDATE settings SET tautulli_url = ?, tautulli_api = ? WHERE id = 1", (tautulli_url, encrypt(tautulli_api)))
            conn.commit()
            conn.close()
        return redirect(url_for('auth.setup_conjurr'))

    return render_template('setup.html', step='tautulli', steps=SETUP_STEPS, settings=s, csrf_token=session["csrf_token"])

@bp.route('/setup/conjurr', methods=['GET', 'POST'])
@requires_auth
def setup_conjurr():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    s = get_settings(decrypt_secrets=False)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        conjurr_url = request.form.get('conjurr_url', '').strip()
        if conjurr_url:
            conn = db_connect()
            conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
            conn.execute("UPDATE settings SET conjurr_url = ? WHERE id = 1", (conjurr_url,))
            conn.commit()
            conn.close()
        return redirect(url_for('auth.setup_droppedneedle'))

    return render_template('setup.html', step='conjurr', steps=SETUP_STEPS, settings=s, csrf_token=session["csrf_token"])

@bp.route('/setup/droppedneedle', methods=['GET', 'POST'])
@requires_auth
def setup_droppedneedle():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    s = get_settings(decrypt_secrets=False)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        droppedneedle_url = request.form.get('droppedneedle_url', '').strip()
        droppedneedle_api_key = request.form.get('droppedneedle_api_key', '').strip()
        if droppedneedle_url and droppedneedle_api_key:
            conn = db_connect()
            conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
            conn.execute("UPDATE settings SET droppedneedle_url = ?, droppedneedle_api_key = ? WHERE id = 1", (droppedneedle_url, encrypt(droppedneedle_api_key)))
            conn.commit()
            conn.close()
        return redirect(url_for('auth.setup_sonarr'))

    return render_template('setup.html', step='droppedneedle', steps=SETUP_STEPS, settings=s, csrf_token=session["csrf_token"])

@bp.route('/setup/sonarr', methods=['GET', 'POST'])
@requires_auth
def setup_sonarr():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    s = get_settings(decrypt_secrets=False)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        sonarr_url = request.form.get('sonarr_url', '').strip() or DEFAULT_SONARR_URL
        sonarr_api_key = request.form.get('sonarr_api_key', '').strip()
        if sonarr_api_key:
            conn = db_connect()
            conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
            conn.execute("UPDATE settings SET sonarr_url = ?, sonarr_api_key = ? WHERE id = 1", (sonarr_url, encrypt(sonarr_api_key)))
            conn.commit()
            conn.close()
        return redirect(url_for('auth.setup_radarr'))

    return render_template('setup.html', step='sonarr', steps=SETUP_STEPS, settings=s, csrf_token=session["csrf_token"])

@bp.route('/setup/radarr', methods=['GET', 'POST'])
@requires_auth
def setup_radarr():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    s = get_settings(decrypt_secrets=False)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        radarr_url = request.form.get('radarr_url', '').strip() or DEFAULT_RADARR_URL
        radarr_api_key = request.form.get('radarr_api_key', '').strip()
        if radarr_api_key:
            conn = db_connect()
            conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
            conn.execute("UPDATE settings SET radarr_url = ?, radarr_api_key = ? WHERE id = 1", (radarr_url, encrypt(radarr_api_key)))
            conn.commit()
            conn.close()
        return redirect(url_for('auth.setup_ombi'))

    return render_template('setup.html', step='radarr', steps=SETUP_STEPS, settings=s, csrf_token=session["csrf_token"])

@bp.route('/setup/ombi', methods=['GET', 'POST'])
@requires_auth
def setup_ombi():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    s = get_settings(decrypt_secrets=False)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        ombi_url = request.form.get('ombi_url', '').strip() or DEFAULT_OMBI_URL
        ombi_api_key = request.form.get('ombi_api_key', '').strip()
        if ombi_api_key:
            conn = db_connect()
            conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
            conn.execute("UPDATE settings SET ombi_url = ?, ombi_api_key = ? WHERE id = 1", (ombi_url, encrypt(ombi_api_key)))
            conn.commit()
            conn.close()
        return redirect(url_for('auth.setup_seerr'))

    return render_template('setup.html', step='ombi', steps=SETUP_STEPS, settings=s, csrf_token=session["csrf_token"])

@bp.route('/setup/seerr', methods=['GET', 'POST'])
@requires_auth
def setup_seerr():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    s = get_settings(decrypt_secrets=False)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        seerr_url = request.form.get('seerr_url', '').strip() or DEFAULT_SEERR_URL
        seerr_api_key = request.form.get('seerr_api_key', '').strip()
        if seerr_api_key:
            conn = db_connect()
            conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
            conn.execute("UPDATE settings SET seerr_url = ?, seerr_api_key = ? WHERE id = 1", (seerr_url, encrypt(seerr_api_key)))
            conn.commit()
            conn.close()
        logger.info("First-run setup wizard completed")
        return redirect(url_for('main.index'))

    return render_template('setup.html', step='seerr', steps=SETUP_STEPS, settings=s, csrf_token=session["csrf_token"])

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if not admin_configured():
        return redirect(url_for('auth.setup'))

    alert = request.args.get('alert')

    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        ip = _client_ip()
        if _rate_limited(ip):
            logger.warning(f"Login rate limit hit for {ip}")
            return render_template('login.html', error='Invalid request', csrf_token=session["csrf_token"]), 429

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if check_credentials(username, password):
            _clear_failures(ip)
            session['authenticated'] = True
            session['username'] = username
            return redirect(url_for('main.index'))
        else:
            _record_failure(ip)
            return render_template('login.html', error='Invalid credentials', csrf_token=session["csrf_token"])

    return render_template('login.html', alert=alert, csrf_token=session["csrf_token"])

@bp.route('/logout')
@requires_auth
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
