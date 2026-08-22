# Microsoft OAuth for SMTP AUTH (XOAUTH2).
#
# Exchange Online is retiring basic authentication for client submission, and
# personal Outlook.com mailboxes cannot enable it at all, so a password is no
# longer a way to send through Microsoft. SMTP itself stays: the supported
# path is an OAuth access token presented over SASL XOAUTH2, which is what
# app.emails.send.smtp_connect does with the token this module supplies.
import base64
import json
import threading
import time

import requests

from app.crypto import encrypt
from app.db import db_connect
from app.settings_store import get_settings

import logging

logger = logging.getLogger(__name__)

AUTHORITY = "https://login.microsoftonline.com"

SCOPES = "https://outlook.office.com/SMTP.Send offline_access"

EXPIRY_MARGIN = 300

_REFRESH_LOCK = threading.Lock()

class OAuthError(Exception):
    """Raised when a token cannot be obtained. The message is shown to the
    operator, so it carries Microsoft's own error description where there is
    one."""

def _endpoint(tenant, leaf):
    return f"{AUTHORITY}/{tenant or 'common'}/oauth2/v2.0/{leaf}"

def _describe(payload):
    return payload.get("error_description") or payload.get("error") or "unknown error"

def start_device_code(client_id, tenant="common"):
    if not client_id:
        raise OAuthError("No application (client) ID configured")

    response = requests.post(
        _endpoint(tenant, "devicecode"),
        data={"client_id": client_id, "scope": SCOPES},
        timeout=30,
    )
    payload = response.json()
    if response.status_code != 200:
        raise OAuthError(_describe(payload))
    return payload

def poll_device_code(client_id, device_code, tenant="common"):
    response = requests.post(
        _endpoint(tenant, "token"),
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": device_code,
        },
        timeout=30,
    )
    payload = response.json()
    if response.status_code == 200:
        return "complete", payload

    error = payload.get("error")
    # authorization_pending is the normal answer until the operator finishes
    # in the browser; slow_down additionally asks for a longer interval.
    if error in ("authorization_pending", "slow_down"):
        return "pending", payload
    return "error", payload

def refresh_tokens(client_id, refresh_token, tenant="common"):
    if not refresh_token:
        raise OAuthError("No refresh token stored: reconnect the Microsoft account")

    response = requests.post(
        _endpoint(tenant, "token"),
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
            "scope": SCOPES,
        },
        timeout=30,
    )
    payload = response.json()
    if response.status_code != 200:
        raise OAuthError(_describe(payload))
    return payload

def store_tokens(payload, account=None):
    access_token = payload.get("access_token") or ""
    refresh_token = payload.get("refresh_token") or ""
    expires_at = int(time.time()) + int(payload.get("expires_in") or 0)

    assignments = [
        "oauth_access_token = ?",
        "oauth_token_expires_at = ?",
    ]
    values = [encrypt(access_token), str(expires_at)]

    # A refresh response normally carries a successor, but treat its absence
    # as "keep the existing one" rather than blanking the column.
    if refresh_token:
        assignments.append("oauth_refresh_token = ?")
        values.append(encrypt(refresh_token))
    if account:
        assignments.append("oauth_account = ?")
        values.append(account)

    conn = db_connect()
    try:
        conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
        conn.execute(f"UPDATE settings SET {', '.join(assignments)} WHERE id = 1", values)
        conn.commit()
    finally:
        conn.close()

def clear_tokens():
    conn = db_connect()
    try:
        conn.execute(
            "UPDATE settings SET oauth_access_token = '', oauth_refresh_token = '',"
            " oauth_token_expires_at = '', oauth_account = '' WHERE id = 1"
        )
        conn.commit()
    finally:
        conn.close()

def account_email(payload):
    id_token = payload.get("id_token")
    if not id_token:
        return ""
    try:
        claims_segment = id_token.split(".")[1]
        claims_segment += "=" * (-len(claims_segment) % 4)
        claims = json.loads(base64.urlsafe_b64decode(claims_segment))
    except Exception:
        logger.debug("could not read claims from id_token", exc_info=True)
        return ""
    return claims.get("preferred_username") or claims.get("email") or ""

def get_valid_access_token():
    with _REFRESH_LOCK:
        settings = get_settings()
        client_id = settings.get("oauth_client_id") or ""
        tenant = settings.get("oauth_tenant") or "common"
        access_token = settings.get("oauth_access_token") or ""

        try:
            expires_at = int(settings.get("oauth_token_expires_at") or 0)
        except (TypeError, ValueError):
            expires_at = 0

        if access_token and time.time() < expires_at - EXPIRY_MARGIN:
            return access_token

        logger.info("Refreshing Microsoft OAuth access token for SMTP")
        payload = refresh_tokens(client_id, settings.get("oauth_refresh_token") or "", tenant)
        store_tokens(payload)

        new_token = payload.get("access_token") or ""
        if not new_token:
            raise OAuthError("Token refresh returned no access token")
        return new_token

def uses_oauth(settings):
    return (settings.get("smtp_auth_method") or "password") == "oauth"

def connection_status(settings):
    return {
        "configured": bool(settings.get("oauth_client_id")),
        "connected": bool(settings.get("oauth_refresh_token")),
        "account": settings.get("oauth_account") or "",
        "provider": settings.get("oauth_provider") or "microsoft",
    }
