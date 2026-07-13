import sqlite3

import pytest

from app import config
from app.crypto import encrypt
from app.security import check_credentials, admin_configured

@pytest.fixture()
def clean_credentials(app):
    """Snapshot the admin credentials, blank them for the test, then restore
    them afterwards (the app DB is session-scoped and shared)."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
    row = conn.execute("SELECT nl_username, nl_password FROM settings WHERE id = 1").fetchone()
    conn.execute("UPDATE settings SET nl_username = '', nl_password = '' WHERE id = 1")
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET nl_username = ?, nl_password = ? WHERE id = 1", (row[0], row[1]))
    conn.commit()
    conn.close()

def test_guarded_route_redirects_to_setup_when_no_admin(anon_client, clean_credentials):
    resp = anon_client.get("/settings")
    assert resp.status_code == 302 and "/setup" in resp.headers["Location"]

def test_setup_creates_admin_and_authenticates(anon_client, clean_credentials):
    client = anon_client
    with client.session_transaction() as sess:
        sess["csrf_token"] = "setup-token"

    resp = client.post("/setup", data={
        "csrf_token": "setup-token", "username": "newadmin",
        "password": "strongpass1", "confirm": "strongpass1",
    })
    assert resp.status_code == 302 and "/setup/email" in resp.headers["Location"]  # -> next wizard step
    assert admin_configured()
    # created account authenticates
    assert check_credentials("newadmin", "strongpass1")
    # session is logged in immediately after setup
    assert client.get("/settings").status_code == 200

def test_setup_rejects_short_or_mismatched_password(anon_client, clean_credentials):
    client = anon_client
    with client.session_transaction() as sess:
        sess["csrf_token"] = "t"
    short = client.post("/setup", data={"csrf_token": "t", "username": "a", "password": "short", "confirm": "short"})
    assert b"at least 8" in short.data
    mismatch = client.post("/setup", data={"csrf_token": "t", "username": "a", "password": "longenough1", "confirm": "different1"})
    assert b"do not match" in mismatch.data

def test_setup_continues_to_email_step_when_admin_exists_but_email_unset(anon_client, seeded_settings):
    # seeded_settings only creates the admin account; the required email step
    # is still outstanding, so /setup should resume the wizard, not bounce to login
    resp = anon_client.get("/setup")
    assert resp.status_code == 302 and "/setup/email" in resp.headers["Location"]

def test_setup_unreachable_once_required_steps_complete(anon_client, seeded_settings):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET from_email = 'admin@example.com' WHERE id = 1")
    conn.commit()
    conn.close()
    try:
        resp = anon_client.get("/setup")
        assert resp.status_code == 302 and "/login" in resp.headers["Location"]
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("UPDATE settings SET from_email = '' WHERE id = 1")
        conn.commit()
        conn.close()

def test_setup_email_step_saves_and_advances_to_plex(anon_client, seeded_settings):
    client = anon_client
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["username"] = "admin"
        sess["csrf_token"] = "wizard-token"
    try:
        resp = client.post("/setup/email", data={
            "csrf_token": "wizard-token",
            "from_email": "wizard@example.com",
            "smtp_server": "smtp.example.com",
            "smtp_port": "587",
            "smtp_protocol": "TLS",
            "password": "app-password-1",
        })
        assert resp.status_code == 302 and "/setup/plex" in resp.headers["Location"]

        conn = sqlite3.connect(config.DB_PATH)
        from_email, smtp_server = conn.execute(
            "SELECT from_email, smtp_server FROM settings WHERE id = 1"
        ).fetchone()
        conn.close()
        assert from_email == "wizard@example.com"
        assert smtp_server == "smtp.example.com"
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("UPDATE settings SET from_email = '', smtp_server = '' WHERE id = 1")
        conn.commit()
        conn.close()

def test_setup_sonarr_blank_url_falls_back_to_default(anon_client, seeded_settings):
    client = anon_client
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["username"] = "admin"
        sess["csrf_token"] = "wizard-token"
    try:
        resp = client.post("/setup/sonarr", data={
            "csrf_token": "wizard-token",
            "sonarr_url": "",
            "sonarr_api_key": "sonarr-key-1",
        })
        assert resp.status_code == 302 and "/setup/radarr" in resp.headers["Location"]

        conn = sqlite3.connect(config.DB_PATH)
        sonarr_url = conn.execute("SELECT sonarr_url FROM settings WHERE id = 1").fetchone()[0]
        conn.close()
        assert sonarr_url == config.DEFAULT_SONARR_URL
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("UPDATE settings SET sonarr_url = '', sonarr_api_key = '' WHERE id = 1")
        conn.commit()
        conn.close()

def test_setup_radarr_blank_url_falls_back_to_default(anon_client, seeded_settings):
    client = anon_client
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["username"] = "admin"
        sess["csrf_token"] = "wizard-token"
    try:
        resp = client.post("/setup/radarr", data={
            "csrf_token": "wizard-token",
            "radarr_url": "",
            "radarr_api_key": "radarr-key-1",
        })
        assert resp.status_code == 302

        conn = sqlite3.connect(config.DB_PATH)
        radarr_url = conn.execute("SELECT radarr_url FROM settings WHERE id = 1").fetchone()[0]
        conn.close()
        assert radarr_url == config.DEFAULT_RADARR_URL
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("UPDATE settings SET radarr_url = '', radarr_api_key = '' WHERE id = 1")
        conn.commit()
        conn.close()

def test_setup_sonarr_no_key_does_not_persist(anon_client, seeded_settings):
    client = anon_client
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["username"] = "admin"
        sess["csrf_token"] = "wizard-token"
    resp = client.post("/setup/sonarr", data={
        "csrf_token": "wizard-token",
        "sonarr_url": "",
        "sonarr_api_key": "",
    })
    assert resp.status_code == 302

    conn = sqlite3.connect(config.DB_PATH)
    sonarr_url = conn.execute("SELECT sonarr_url FROM settings WHERE id = 1").fetchone()[0]
    conn.close()
    assert not sonarr_url

def test_setup_optional_step_skip_does_not_require_data(anon_client, seeded_settings):
    client = anon_client
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["username"] = "admin"
    # Skip links are plain GETs to the next step, no form data required
    resp = client.get("/setup/tautulli")
    assert resp.status_code == 200
    assert b"Skip" in resp.data

def test_password_stored_as_hash_not_plaintext(anon_client, clean_credentials):
    client = anon_client
    with client.session_transaction() as sess:
        sess["csrf_token"] = "t"
    client.post("/setup", data={"csrf_token": "t", "username": "u", "password": "supersecret1", "confirm": "supersecret1"})
    conn = sqlite3.connect(config.DB_PATH)
    stored = conn.execute("SELECT nl_password FROM settings WHERE id = 1").fetchone()[0]
    conn.close()
    assert "supersecret1" not in stored           # not plaintext
    assert stored.startswith(("scrypt:", "pbkdf2:"))  # a werkzeug hash

def test_legacy_encrypted_password_migrates_to_hash_on_login(clean_credentials):
    # simulate a pre-upgrade install: nl_password is Fernet-encrypted plaintext
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET nl_username = 'legacy', nl_password = ? WHERE id = 1",
                 (encrypt("oldpass12"),))
    conn.commit()
    conn.close()

    assert check_credentials("legacy", "oldpass12")  # legacy path validates

    conn = sqlite3.connect(config.DB_PATH)
    stored = conn.execute("SELECT nl_password FROM settings WHERE id = 1").fetchone()[0]
    conn.close()
    assert stored.startswith(("scrypt:", "pbkdf2:"))   # upgraded to a hash
    assert check_credentials("legacy", "oldpass12")    # still works post-migration

def test_login_rate_limited_after_repeated_failures(anon_client, seeded_settings):
    client = anon_client
    with client.session_transaction() as sess:
        sess["csrf_token"] = "t"
    last = None
    for _ in range(7):
        last = client.post("/login", data={"csrf_token": "t", "username": "admin", "password": "wrong"})
    assert last.status_code == 429
