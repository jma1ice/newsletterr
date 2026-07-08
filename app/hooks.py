import secrets

from flask import Response, g

from app import config, state
from app.settings_store import get_settings
from app.clients.github import _ensure_recent_check

import logging

logger = logging.getLogger(__name__)

def mint_csp_nonce():
    g.csp_nonce = secrets.token_urlsafe(16)

def inject_csp_nonce():
    # every template gets the same per-request nonce the CSP header carries
    return {"nonce": g.csp_nonce}

def inject_update_info():
    _ensure_recent_check()
    return {
        "update_info": {
            "current": config.VERSION,
            "latest": state._update_cache["latest"],
            "is_newer": state._update_cache["is_newer"],
            "release_url": state._update_cache["release_url"],
            "notes": state._update_cache["notes"],
        }
    }

def refresh_hsts_setting():
    try:
        state._hsts_enabled = get_settings(decrypt_secrets=False)["hsts_enabled"] == 'enabled'
    except Exception:
        logger.debug("suppressed exception; using fallback", exc_info=True)
        state._hsts_enabled = False

def set_security_headers(resp: Response):
    try:
        resp.headers.setdefault('X-Frame-Options', 'DENY')
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('Referrer-Policy', 'no-referrer')
        # Report-Only while the policy soaks; flip to enforcing once
        # /csp-report stays quiet through normal use.
        csp = (
            "default-src 'self'; "
            f"script-src 'self' 'nonce-{g.csp_nonce}'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob: https:; "
            "frame-src 'self'; "
            "connect-src 'self'; "
            "report-uri /csp-report"
        )
        resp.headers.setdefault('Content-Security-Policy-Report-Only', csp)
        if state._hsts_enabled:
            resp.headers.setdefault('Strict-Transport-Security', 'max-age=63072000; includeSubDomains; preload')
        return resp
    except Exception:
        logger.debug("suppressed exception; using fallback", exc_info=True)
        return resp

def register(app):
    app.before_request(mint_csp_nonce)
    app.context_processor(inject_csp_nonce)
    app.context_processor(inject_update_info)
    app.after_request(set_security_headers)
