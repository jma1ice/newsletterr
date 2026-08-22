"""Microsoft OAuth (XOAUTH2) for SMTP."""

import base64
import smtplib
import sqlite3
import time

import pytest

from app import config
from app.clients import msoauth
from app.emails.send import smtp_connect, xoauth2_string

# The worked example from Microsoft's IMAP/POP/SMTP OAuth documentation.
MS_USER = "test@contoso.onmicrosoft.com"
MS_TOKEN = "EwBAAl3BAAUFFpUAo7J3Ve0bjLBWZWCclRC3EoAA"
MS_EXPECTED = (
    "dXNlcj10ZXN0QGNvbnRvc28ub25taWNyb3NvZnQuY29tAWF1dGg9QmVhcmVy"
    "IEV3QkFBbDNCQUFVRkZwVUFvN0ozVmUwYmpMQldaV0NjbFJDM0VvQUEBAQ=="
)

@pytest.fixture()
def oauth_db(tmp_path, monkeypatch):
    """A settings row with a live OAuth connection."""
    db = str(tmp_path / "oauth.db")
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE settings (
            id INTEGER PRIMARY KEY,
            smtp_auth_method TEXT,
            oauth_provider TEXT,
            oauth_client_id TEXT,
            oauth_tenant TEXT,
            oauth_account TEXT,
            oauth_access_token TEXT,
            oauth_refresh_token TEXT,
            oauth_token_expires_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "DB_PATH", db)

    from app.crypto import encrypt
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO settings (id, smtp_auth_method, oauth_provider, oauth_client_id,"
        " oauth_tenant, oauth_account, oauth_access_token, oauth_refresh_token, oauth_token_expires_at)"
        " VALUES (1, 'oauth', 'microsoft', 'client-abc', 'common', 'sender@example.com', ?, ?, ?)",
        (encrypt("live-access-token"), encrypt("refresh-1"), str(int(time.time()) + 3600)),
    )
    conn.commit()
    conn.close()
    return db

def _stored(db, column):
    conn = sqlite3.connect(db)
    try:
        return conn.execute(f"SELECT {column} FROM settings WHERE id = 1").fetchone()[0]
    finally:
        conn.close()

# --- the SASL payload -------------------------------------------------------

def test_xoauth2_matches_microsofts_worked_example():
    raw = xoauth2_string(MS_USER, MS_TOKEN)
    assert base64.b64encode(raw.encode()).decode() == MS_EXPECTED

def test_xoauth2_uses_control_a_separators():
    raw = xoauth2_string("a@b.c", "tok")
    assert raw == "user=a@b.c\x01auth=Bearer tok\x01\x01"

# --- token refresh ----------------------------------------------------------

def test_a_live_token_is_reused_without_calling_microsoft(oauth_db, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("refreshed a token that had not expired")

    monkeypatch.setattr(msoauth, "refresh_tokens", _boom)
    assert msoauth.get_valid_access_token() == "live-access-token"

def test_an_expired_token_is_refreshed(oauth_db, monkeypatch):
    conn = sqlite3.connect(oauth_db)
    conn.execute("UPDATE settings SET oauth_token_expires_at = ? WHERE id = 1", (str(int(time.time()) - 10),))
    conn.commit()
    conn.close()

    monkeypatch.setattr(msoauth, "refresh_tokens", lambda *a, **k: {
        "access_token": "fresh-access-token",
        "refresh_token": "refresh-2",
        "expires_in": 3600,
    })
    assert msoauth.get_valid_access_token() == "fresh-access-token"

def test_a_token_inside_the_expiry_margin_is_refreshed_early(oauth_db, monkeypatch):
    # Still technically valid, but not for long enough to finish a send.
    conn = sqlite3.connect(oauth_db)
    conn.execute(
        "UPDATE settings SET oauth_token_expires_at = ? WHERE id = 1",
        (str(int(time.time()) + msoauth.EXPIRY_MARGIN - 30),),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(msoauth, "refresh_tokens", lambda *a, **k: {
        "access_token": "fresh-access-token", "refresh_token": "refresh-2", "expires_in": 3600,
    })
    assert msoauth.get_valid_access_token() == "fresh-access-token"

def test_the_rotated_refresh_token_is_persisted(oauth_db, monkeypatch):
    # Microsoft retires the refresh token it was just handed. If the successor
    # is not stored, the next unattended send has nothing to refresh with.
    conn = sqlite3.connect(oauth_db)
    conn.execute("UPDATE settings SET oauth_token_expires_at = '0' WHERE id = 1")
    conn.commit()
    conn.close()

    monkeypatch.setattr(msoauth, "refresh_tokens", lambda *a, **k: {
        "access_token": "fresh-access-token", "refresh_token": "refresh-2", "expires_in": 3600,
    })
    msoauth.get_valid_access_token()

    from app.crypto import decrypt
    assert decrypt(_stored(oauth_db, "oauth_refresh_token")) == "refresh-2"

def test_a_refresh_without_a_successor_keeps_the_existing_token(oauth_db, monkeypatch):
    conn = sqlite3.connect(oauth_db)
    conn.execute("UPDATE settings SET oauth_token_expires_at = '0' WHERE id = 1")
    conn.commit()
    conn.close()

    monkeypatch.setattr(msoauth, "refresh_tokens", lambda *a, **k: {
        "access_token": "fresh-access-token", "expires_in": 3600,
    })
    msoauth.get_valid_access_token()

    from app.crypto import decrypt
    assert decrypt(_stored(oauth_db, "oauth_refresh_token")) == "refresh-1"

def test_tokens_are_stored_encrypted(oauth_db):
    assert "live-access-token" not in (_stored(oauth_db, "oauth_access_token") or "")
    assert "refresh-1" not in (_stored(oauth_db, "oauth_refresh_token") or "")

def test_a_dead_refresh_token_says_to_reconnect(oauth_db, monkeypatch):
    conn = sqlite3.connect(oauth_db)
    conn.execute("UPDATE settings SET oauth_token_expires_at = '0', oauth_refresh_token = '' WHERE id = 1")
    conn.commit()
    conn.close()

    with pytest.raises(msoauth.OAuthError, match="reconnect"):
        msoauth.get_valid_access_token()

def test_disconnect_clears_every_token_column(oauth_db):
    msoauth.clear_tokens()
    for column in ("oauth_access_token", "oauth_refresh_token", "oauth_token_expires_at", "oauth_account"):
        assert _stored(oauth_db, column) == ""

# --- the device flow --------------------------------------------------------

class _Resp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

def test_device_code_requests_the_smtp_scope_and_offline_access(monkeypatch):
    seen = {}

    def _post(url, data=None, timeout=None):
        seen.update({"url": url, "data": data})
        return _Resp(200, {"device_code": "dc", "user_code": "ABC123"})

    monkeypatch.setattr(msoauth.requests, "post", _post)
    msoauth.start_device_code("client-abc", "common")

    assert seen["url"].endswith("/common/oauth2/v2.0/devicecode")
    # SMTP.Send alone is rejected; it has to carry the resource URL, and
    # without offline_access there is no refresh token for scheduled sends.
    assert seen["data"]["scope"] == "https://outlook.office.com/SMTP.Send offline_access"

def test_pending_consent_is_not_an_error(monkeypatch):
    monkeypatch.setattr(msoauth.requests, "post",
                        lambda *a, **k: _Resp(400, {"error": "authorization_pending"}))
    status, _ = msoauth.poll_device_code("client-abc", "dc")
    assert status == "pending"

def test_slow_down_is_also_pending(monkeypatch):
    monkeypatch.setattr(msoauth.requests, "post",
                        lambda *a, **k: _Resp(400, {"error": "slow_down"}))
    status, _ = msoauth.poll_device_code("client-abc", "dc")
    assert status == "pending"

def test_a_declined_consent_is_an_error(monkeypatch):
    monkeypatch.setattr(msoauth.requests, "post",
                        lambda *a, **k: _Resp(400, {"error": "authorization_declined"}))
    status, _ = msoauth.poll_device_code("client-abc", "dc")
    assert status == "error"

def test_completed_consent_returns_the_tokens(monkeypatch):
    monkeypatch.setattr(msoauth.requests, "post",
                        lambda *a, **k: _Resp(200, {"access_token": "at", "refresh_token": "rt"}))
    status, payload = msoauth.poll_device_code("client-abc", "dc")
    assert status == "complete"
    assert payload["access_token"] == "at"

def test_account_email_is_read_from_the_id_token():
    claims = base64.urlsafe_b64encode(b'{"preferred_username": "sender@example.com"}').decode().rstrip("=")
    assert msoauth.account_email({"id_token": f"header.{claims}.signature"}) == "sender@example.com"

def test_a_missing_id_token_is_not_fatal():
    assert msoauth.account_email({}) == ""

def test_a_malformed_id_token_is_not_fatal():
    assert msoauth.account_email({"id_token": "not-a-jwt"}) == ""

# --- smtp_connect wiring ----------------------------------------------------

class _RecorderSMTP:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.greeted = False
        self.auth_calls = []
        self.login_calls = []

    def starttls(self):
        self.greeted = False

    def ehlo(self):
        self.greeted = True

    def auth(self, mechanism, authobject, **kwargs):
        # Mirrors smtplib: the authobject is called with no argument for the
        # initial response, and returns the string smtplib will base64 encode.
        self.auth_calls.append((mechanism, authobject(), self.greeted))

    def login(self, username, password):
        self.login_calls.append((username, password))

@pytest.fixture()
def smtp_recorder(monkeypatch):
    created = []

    def _factory(host, port):
        server = _RecorderSMTP(host, port)
        created.append(server)
        return server

    monkeypatch.setattr(smtplib, "SMTP", _factory)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _factory)
    return created

OAUTH_SETTINGS = {"smtp_auth_method": "oauth", "oauth_account": "sender@example.com"}

def test_oauth_settings_authenticate_with_xoauth2(smtp_recorder, monkeypatch):
    monkeypatch.setattr(msoauth, "get_valid_access_token", lambda: "tok")
    server = smtp_connect("smtp.office365.com", 587, "TLS", "", "from@example.com", "", OAUTH_SETTINGS)

    assert server.login_calls == []
    mechanism, payload, _ = server.auth_calls[0]
    assert mechanism == "XOAUTH2"
    assert payload == "user=sender@example.com\x01auth=Bearer tok\x01\x01"

def test_xoauth2_greets_again_after_starttls(smtp_recorder, monkeypatch):
    # STARTTLS discards the capabilities learned before the upgrade, and
    # SMTP.auth, unlike SMTP.login, does not re-greet on its own.
    monkeypatch.setattr(msoauth, "get_valid_access_token", lambda: "tok")
    server = smtp_connect("smtp.office365.com", 587, "TLS", "", "from@example.com", "", OAUTH_SETTINGS)
    assert server.auth_calls[0][2] is True

def test_password_settings_still_use_login(smtp_recorder):
    settings = {"smtp_auth_method": "password"}
    server = smtp_connect("smtp.gmail.com", 587, "TLS", "user", "from@example.com", "pw", settings)
    assert server.auth_calls == []
    assert server.login_calls == [("user", "pw")]

def test_a_caller_passing_no_settings_uses_the_password_path(smtp_recorder):
    server = smtp_connect("smtp.gmail.com", 587, "TLS", "user", "from@example.com", "pw")
    assert server.login_calls == [("user", "pw")]

def test_blank_auth_method_is_the_password_path(smtp_recorder):
    # Every install that predates this feature has no value in the column.
    server = smtp_connect("smtp.gmail.com", 587, "TLS", "user", "from@example.com", "pw", {})
    assert server.login_calls == [("user", "pw")]

def test_the_connected_account_is_preferred_over_the_smtp_username(smtp_recorder, monkeypatch):
    # The token is bound to the account that consented, so that address is the
    # one XOAUTH2 has to name.
    monkeypatch.setattr(msoauth, "get_valid_access_token", lambda: "tok")
    server = smtp_connect("smtp.office365.com", 587, "TLS", "someone-else", "from@example.com", "", OAUTH_SETTINGS)
    assert "user=sender@example.com" in server.auth_calls[0][1]

# --- routes -----------------------------------------------------------------

def _post(client, token, path, payload):
    import json as _json
    return client.post(path, data=_json.dumps(payload), content_type="application/json",
                       headers={"X-CSRF-Token": token})

def test_oauth_routes_require_csrf(client, seeded_settings):
    for path in ("/api/oauth/microsoft/start",
                 "/api/oauth/microsoft/poll",
                 "/api/oauth/microsoft/disconnect"):
        assert client.post(path, json={}).status_code == 400, path

def test_oauth_routes_require_auth(anon_client, login_enabled):
    for path in ("/api/oauth/microsoft/start",
                 "/api/oauth/microsoft/poll",
                 "/api/oauth/microsoft/disconnect"):
        assert anon_client.post(path, json={}).status_code in (302, 400), path

def test_start_without_a_client_id_is_a_400_not_a_500(csrf_client):
    client, token = csrf_client
    resp = _post(client, token, "/api/oauth/microsoft/start", {"client_id": ""})
    assert resp.status_code == 400
    assert "client" in resp.get_json()["message"].lower()

def test_poll_without_a_device_code_is_a_400(csrf_client):
    client, token = csrf_client
    resp = _post(client, token, "/api/oauth/microsoft/poll", {})
    assert resp.status_code == 400

def test_start_reports_an_unreachable_microsoft_as_502(csrf_client, monkeypatch):
    import requests as _requests

    def _boom(*a, **k):
        raise _requests.RequestException("no route to host")

    monkeypatch.setattr(msoauth.requests, "post", _boom)
    client, token = csrf_client
    resp = _post(client, token, "/api/oauth/microsoft/start", {"client_id": "abc"})
    assert resp.status_code == 502

def test_completing_the_flow_stores_tokens_and_switches_the_auth_method(csrf_client, monkeypatch):
    claims = base64.urlsafe_b64encode(b'{"preferred_username": "sender@example.com"}').decode().rstrip("=")
    monkeypatch.setattr(msoauth, "poll_device_code", lambda *a, **k: ("complete", {
        "access_token": "at", "refresh_token": "rt", "expires_in": 3600,
        "id_token": f"header.{claims}.signature",
    }))

    client, token = csrf_client
    resp = _post(client, token, "/api/oauth/microsoft/poll",
                 {"device_code": "dc", "client_id": "client-abc", "tenant": "common"})
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "connected", "account": "sender@example.com"}

    from app.settings_store import get_settings
    s = get_settings()
    assert s["smtp_auth_method"] == "oauth"
    assert s["oauth_client_id"] == "client-abc"
    assert s["oauth_refresh_token"] == "rt"

def test_disconnecting_reverts_to_password_auth(csrf_client):
    client, token = csrf_client
    resp = _post(client, token, "/api/oauth/microsoft/disconnect", {})
    assert resp.status_code == 200

    from app.settings_store import get_settings
    s = get_settings()
    assert s["smtp_auth_method"] == "password"
    assert not s["oauth_refresh_token"]
