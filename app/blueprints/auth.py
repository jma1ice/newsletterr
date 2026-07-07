import secrets

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app.security import requires_auth, check_credentials
from app.settings_store import get_settings

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    alert = request.args.get('alert')
    # missing-row default is 'disabled', so a fresh install redirects instead
    # of crashing on login_toggle[0]
    if get_settings(decrypt_secrets=False)["login_toggle"] != 'enabled':
        return redirect(url_for('main.index', alert=alert))

    if request.method == 'POST':
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if check_credentials(username, password):
            session['authenticated'] = True
            session['username'] = username
            return redirect(url_for('main.index'))
        else:
            return render_template('login.html', error='Invalid credentials')
        
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)

    return render_template('login.html', alert=alert, csrf_token=session["csrf_token"])

@bp.route('/logout')
@requires_auth
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
