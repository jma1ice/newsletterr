import os

from flask import Blueprint, Response, render_template, request, send_file

from app.settings_store import get_settings
from app.store import add_suppressed, get_hosted_image, get_most_recent_hosted_newsletter
from app.tokens import verify_unsubscribe_token

import logging

logger = logging.getLogger(__name__)

bp = Blueprint('public', __name__)

@bp.route('/u/<token>', methods=['GET', 'POST'])
def unsubscribe(token):
    email = verify_unsubscribe_token(token)
    if not email:
        return render_template('public_unsubscribe.html', state='invalid'), 404

    if request.method == 'POST':
        add_suppressed(email)
        logger.info(f"Unsubscribed via public link: {email}")
        return render_template('public_unsubscribe.html', state='done', email=email)

    return render_template('public_unsubscribe.html', state='confirm', email=email)

@bp.route('/newsletter', methods=['GET'])
def hosted_newsletter():
    if get_settings(decrypt_secrets=False).get("hosted_enabled") != "enabled":
        return render_template('public_newsletter.html', state='disabled'), 404

    row = get_most_recent_hosted_newsletter()
    if not row:
        return render_template('public_newsletter.html', state='empty')

    return Response(row[1], mimetype='text/html')

@bp.route('/i/<token>', methods=['GET'])
def hosted_image(token):
    result = get_hosted_image(token)
    if not result:
        return Response(status=404)
    path, content_type = result
    return send_file(os.path.abspath(path), mimetype=content_type, max_age=31536000, conditional=True)
