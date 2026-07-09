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
    assert resp.status_code == 302 and "/settings" not in resp.headers["Location"]  # -> index
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

def test_setup_unreachable_once_admin_exists(anon_client, seeded_settings):
    resp = anon_client.get("/setup")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]

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
