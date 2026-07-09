import os
import sqlite3
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Hermetic environment: must be set BEFORE the first `import app.*`:
# a preset DATA_ENC_KEY stops crypto.ensure_data_key() writing env/.env,
# and FLASK_DEBUG=1 without WERKZEUG_RUN_MAIN keeps the factory's
# background-worker gate closed (no scheduler/update-checker threads).
os.environ.setdefault("DATA_ENC_KEY", Fernet.generate_key().decode())
os.environ.setdefault("NEWSLETTERR_SECRET_KEY", "test-secret-key-not-for-production")
os.environ["FLASK_DEBUG"] = "1"
os.environ.pop("WERKZEUG_RUN_MAIN", None)

@pytest.fixture(scope="session")
def app(tmp_path_factory):
    # config.DB_PATH is CWD-relative by design; chdir into a sandbox so
    # create_app()'s makedirs/init_db/migrations land in a throwaway DB.
    os.chdir(tmp_path_factory.mktemp("apphome"))
    from app import create_app
    return create_app()

def _db():
    from app import config
    return sqlite3.connect(config.DB_PATH)

@pytest.fixture(autouse=True)
def _reset_login_throttle():
    # the login rate limiter is module-level state; clear it between tests so
    # one test's failed logins do not lock out another
    yield
    try:
        from app.blueprints import auth
        with auth._attempts_lock:
            auth._attempts.clear()
    except Exception:
        pass

@pytest.fixture()
def seeded_settings(app):
    """Ensure the singleton settings row exists with an admin account."""
    from werkzeug.security import generate_password_hash
    conn = _db()
    conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
    conn.execute(
        "UPDATE settings SET login_toggle = 'enabled', nl_username = 'admin', nl_password = ? WHERE id = 1",
        (generate_password_hash("secret123"),),
    )
    conn.commit()
    conn.close()

@pytest.fixture()
def client(app, seeded_settings):
    """Authenticated test client."""
    c = app.test_client()
    with c.session_transaction() as sess:
        sess["authenticated"] = True
        sess["username"] = "admin"
    return c

@pytest.fixture()
def anon_client(app):
    """Unauthenticated client, for testing the auth gate and setup flow."""
    return app.test_client()

@pytest.fixture()
def csrf_client(client):
    """Authenticated client with a session CSRF token; returns (client, token)."""
    token = "test-csrf-token"
    with client.session_transaction() as sess:
        sess["csrf_token"] = token
    return client, token

@pytest.fixture()
def login_enabled(anon_client, seeded_settings):
    """Credentials for the seeded admin, with an unauthenticated client."""
    return {"username": "admin", "password": "secret123"}
