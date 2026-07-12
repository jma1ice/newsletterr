import json
import os
import secrets
import time

import requests
from flask import Blueprint, Response, jsonify, render_template, session

from app.log import LOG_PATH
from app.security import redact_log_content, require_csrf_for_json, requires_auth, json_body
from app.settings_store import get_settings

import logging

logger = logging.getLogger(__name__)

bp = Blueprint('logs', __name__)

def _read_redacted_log():
    if not os.path.exists(LOG_PATH):
        return ""
    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
        return redact_log_content(f.read())

@bp.route('/logs', methods=['GET'])
@requires_auth
def logs_page():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    settings = get_settings(decrypt_secrets=False)
    return render_template('logs.html', has_discord_webhook=bool(settings.get('discord_webhook_url')), csrf_token=session["csrf_token"])

@bp.route('/logs/export', methods=['GET'])
@requires_auth
def export_logs():
    content = _read_redacted_log()
    filename = f"newsletterr-log-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    return Response(
        content,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@bp.route('/logs/send-discord', methods=['POST'])
@requires_auth
def send_discord():
    require_csrf_for_json()
    data, err = json_body()
    if err:
        return err

    thread_id = (data.get('thread_id') or '').strip()

    settings = get_settings(decrypt_secrets=True)
    webhook_url = settings.get('discord_webhook_url')
    if not webhook_url:
        return jsonify({'status': 'error', 'message': 'No Discord webhook URL configured in Settings > Security'}), 400

    content = _read_redacted_log()
    if not content:
        return jsonify({'status': 'error', 'message': 'No log content to send'}), 400

    filename = f"newsletterr-log-{time.strftime('%Y%m%d-%H%M%S')}.txt"
    params = {'wait': 'true'}
    if thread_id:
        params['thread_id'] = thread_id

    try:
        r = requests.post(
            webhook_url,
            params=params,
            data={'payload_json': json.dumps({'content': 'newsletterr log export'})},
            files={'files[0]': (filename, content.encode('utf-8'), 'text/plain')},
            timeout=15,
        )
        if r.status_code in (200, 204):
            return jsonify({'status': 'ok', 'message': 'Log sent to Discord'})
        try:
            detail = r.json().get('message', r.text)
        except ValueError:
            detail = r.text
        return jsonify({'status': 'error', 'message': f'Discord rejected the request ({r.status_code}): {detail}'}), 502
    except requests.exceptions.RequestException as e:
        logger.warning(f"Discord webhook send failed: {e}")
        return jsonify({'status': 'error', 'message': 'Could not reach Discord'}), 502
