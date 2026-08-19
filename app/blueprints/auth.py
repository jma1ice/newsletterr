import secrets
import threading
import time

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app import config
from app.config import DEFAULT_RADARR_URL, DEFAULT_SONARR_URL, DEFAULT_OMBI_URL, DEFAULT_SEERR_URL, DEFAULT_TAUTULLI_URL, DEFAULT_DROPPEDNEEDLE_URL, DEFAULT_JELLYFIN_URL, LANDING_ENDPOINTS, DEFAULT_LANDING_PAGE
from app.crypto import encrypt
from app.db import db_connect
from app.settings_store import get_settings
from app.security import requires_auth, check_credentials, admin_configured, set_admin_credentials
from app.store import add_contacts, save_email_list
from app.contacts_import import parse_contacts

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

SETUP_STEPS = ['admin', 'mode', 'email', 'plex', 'jellyfin', 'tautulli', 'conjurr', 'droppedneedle', 'sonarr', 'radarr', 'ombi', 'seerr']

# standalone mode collapses the wizard to the steps that still mean
# something with no media server attached. The step-dot indicator in setup.html
# iterates whatever list it is handed, so it adapts on its own.
STANDALONE_SETUP_STEPS = ['admin', 'mode', 'email', 'contacts']

def _setup_steps():
    """The wizard's step list for the mode chosen so far. Read per request
    rather than captured at import, since the mode step is what sets it."""
    try:
        s = get_settings(decrypt_secrets=False)
    except Exception:
        logger.debug("suppressed exception; showing the full wizard", exc_info=True)
        return SETUP_STEPS
    return STANDALONE_SETUP_STEPS if (s.get('media_server_type') == 'none') else SETUP_STEPS

def _is_standalone_setup():
    return _setup_steps() is STANDALONE_SETUP_STEPS

def _landing_url():
    try:
        page = get_settings(decrypt_secrets=False).get('default_landing_page')
    except Exception:
        logger.debug("suppressed exception; landing on the default page", exc_info=True)
        page = None
    endpoint = LANDING_ENDPOINTS.get(page or DEFAULT_LANDING_PAGE, LANDING_ENDPOINTS[DEFAULT_LANDING_PAGE])
    return url_for(endpoint)

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
            return render_template('setup.html', step='admin', steps=_setup_steps(), error='Username and password are required', csrf_token=session["csrf_token"])
        if len(password) < 8:
            return render_template('setup.html', step='admin', steps=_setup_steps(), error='Password must be at least 8 characters', csrf_token=session["csrf_token"])
        if password != confirm:
            return render_template('setup.html', step='admin', steps=_setup_steps(), error='Passwords do not match', csrf_token=session["csrf_token"])

        set_admin_credentials(username, password)
        session['authenticated'] = True
        session['username'] = username
        logger.info("Admin account created via first-run setup")
        return redirect(url_for('auth.setup_mode'))

    return render_template('setup.html', step='admin', steps=_setup_steps(), csrf_token=session["csrf_token"])

@bp.route('/setup/mode', methods=['GET', 'POST'])
@requires_auth
def setup_mode():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    s = get_settings(decrypt_secrets=False)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        standalone = request.form.get('setup_mode') == 'standalone'
        conn = db_connect()
        conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
        conn.execute(
            "UPDATE settings SET media_server_type = ? WHERE id = 1",
            ('none' if standalone else 'plex',),
        )
        conn.commit()
        conn.close()
        logger.info(f"First-run setup mode: {'standalone' if standalone else 'media server'}")
        return redirect(url_for('auth.setup_email'))

    return render_template('setup.html', step='mode', steps=_setup_steps(), settings=s, csrf_token=session["csrf_token"])

@bp.route('/setup/contacts', methods=['GET', 'POST'])
@requires_auth
def setup_contacts():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    s = get_settings(decrypt_secrets=False)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        list_name = (request.form.get('list_name') or 'Subscribers').strip() or 'Subscribers'
        pasted = request.form.get('contacts_text') or ''
        upload = request.files.get('contacts_file')
        if upload is not None and upload.filename:
            pasted = upload.read(2 * 1024 * 1024).decode('utf-8', errors='replace')

        if pasted.strip():
            result = parse_contacts(pasted)
            if result['contacts']:
                save_email_list(list_name, ', '.join(e for e, _ in result['contacts']))
                conn = db_connect()
                row = conn.execute("SELECT id FROM email_lists WHERE name = ?", (list_name,)).fetchone()
                conn.close()
                if row:
                    add_contacts(row[0], result['contacts'])
                logger.info(f"First-run setup imported {len(result['contacts'])} contacts into '{list_name}'")

        logger.info("First-run setup wizard completed (standalone)")
        return redirect(url_for('main.index'))

    return render_template('setup.html', step='contacts', steps=_setup_steps(), settings=s, csrf_token=session["csrf_token"])

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
            return render_template('setup.html', step='email', steps=_setup_steps(), settings=s,
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
        if _is_standalone_setup():
            return redirect(url_for('auth.setup_contacts'))
        return redirect(url_for('auth.setup_plex'))

    return render_template('setup.html', step='email', steps=_setup_steps(), settings=s, csrf_token=session["csrf_token"])

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
        return redirect(url_for('auth.setup_jellyfin'))

    return render_template('setup.html', step='plex', steps=_setup_steps(), settings=s, csrf_token=session["csrf_token"])

@bp.route('/setup/jellyfin', methods=['GET', 'POST'])
@requires_auth
def setup_jellyfin():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    s = get_settings(decrypt_secrets=False)

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        jellyfin_url = request.form.get('jellyfin_url', '').strip() or DEFAULT_JELLYFIN_URL
        jellyfin_api_key = request.form.get('jellyfin_api_key', '').strip()
        server_choice = 'emby' if request.form.get('jellyfin_flavor') == 'emby' else 'jellyfin'
        jellywatch_url = request.form.get('jellywatch_url', '').strip()
        jellywatch_api_key = request.form.get('jellywatch_api_key', '').strip()
        if jellyfin_api_key:
            conn = db_connect()
            conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
            # Filling in Jellyfin during setup means Jellyfin is the media
            # server; the choice can be flipped any time in Settings.
            conn.execute(
                "UPDATE settings SET media_server_type = ?, jellyfin_url = ?, jellyfin_api_key = ? WHERE id = 1",
                (server_choice, jellyfin_url, encrypt(jellyfin_api_key)),
            )
            if jellywatch_url and jellywatch_api_key:
                conn.execute(
                    "UPDATE settings SET jellywatch_url = ?, jellywatch_api_key = ? WHERE id = 1",
                    (jellywatch_url, encrypt(jellywatch_api_key)),
                )
            conn.commit()
            conn.close()
        return redirect(url_for('auth.setup_tautulli'))

    return render_template('setup.html', step='jellyfin', steps=_setup_steps(), settings=s, csrf_token=session["csrf_token"])

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

        tautulli_url = request.form.get('tautulli_url', '').strip() or DEFAULT_TAUTULLI_URL
        tautulli_api = request.form.get('tautulli_api', '').strip()
        if tautulli_api:
            conn = db_connect()
            conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
            conn.execute("UPDATE settings SET tautulli_url = ?, tautulli_api = ? WHERE id = 1", (tautulli_url, encrypt(tautulli_api)))
            conn.commit()
            conn.close()
        return redirect(url_for('auth.setup_conjurr'))

    return render_template('setup.html', step='tautulli', steps=_setup_steps(), settings=s, csrf_token=session["csrf_token"])

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

    return render_template('setup.html', step='conjurr', steps=_setup_steps(), settings=s, csrf_token=session["csrf_token"])

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

        droppedneedle_url = request.form.get('droppedneedle_url', '').strip() or DEFAULT_DROPPEDNEEDLE_URL
        droppedneedle_api_key = request.form.get('droppedneedle_api_key', '').strip()
        if droppedneedle_api_key:
            conn = db_connect()
            conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
            conn.execute("UPDATE settings SET droppedneedle_url = ?, droppedneedle_api_key = ? WHERE id = 1", (droppedneedle_url, encrypt(droppedneedle_api_key)))
            conn.commit()
            conn.close()
        return redirect(url_for('auth.setup_sonarr'))

    return render_template('setup.html', step='droppedneedle', steps=_setup_steps(), settings=s, csrf_token=session["csrf_token"])

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

    return render_template('setup.html', step='sonarr', steps=_setup_steps(), settings=s, csrf_token=session["csrf_token"])

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

    return render_template('setup.html', step='radarr', steps=_setup_steps(), settings=s, csrf_token=session["csrf_token"])

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

    return render_template('setup.html', step='ombi', steps=_setup_steps(), settings=s, csrf_token=session["csrf_token"])

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

    return render_template('setup.html', step='seerr', steps=_setup_steps(), settings=s, csrf_token=session["csrf_token"])

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
            return redirect(_landing_url())
        else:
            _record_failure(ip)
            return render_template('login.html', error='Invalid credentials', csrf_token=session["csrf_token"])

    return render_template('login.html', alert=alert, csrf_token=session["csrf_token"])

@bp.route('/logout')
@requires_auth
def logout():
    # Demo mode has no account to leave: clearing the session there would send
    # the visitor to first-run setup. The before_request guard in app/demo.py
    # already redirects this endpoint, and this keeps the route honest on its
    # own. The nav hides the button in demo (templates/base.html).
    if config.DEMO_MODE:
        return redirect(url_for('main.index'))
    session.clear()
    return redirect(url_for('auth.login'))
