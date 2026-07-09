import secrets
import threading
import time

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app.security import requires_auth, check_credentials, admin_configured, set_admin_credentials

import logging

logger = logging.getLogger(__name__)

bp = Blueprint('auth', __name__)

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

@bp.route('/setup', methods=['GET', 'POST'])
def setup():
    if admin_configured():
        return redirect(url_for('auth.login'))

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
            return render_template('setup.html', error='Username and password are required', csrf_token=session["csrf_token"])
        if len(password) < 8:
            return render_template('setup.html', error='Password must be at least 8 characters', csrf_token=session["csrf_token"])
        if password != confirm:
            return render_template('setup.html', error='Passwords do not match', csrf_token=session["csrf_token"])

        set_admin_credentials(username, password)
        session['authenticated'] = True
        session['username'] = username
        logger.info("Admin account created via first-run setup")
        return redirect(url_for('main.index'))

    return render_template('setup.html', csrf_token=session["csrf_token"])

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
