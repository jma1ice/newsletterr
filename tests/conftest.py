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

@pytest.fixture()
def client(app):
    return app.test_client()

def _db():
    from app import config
    return sqlite3.connect(config.DB_PATH)

@pytest.fixture()
def seeded_settings(app):
    """Ensure the singleton settings row exists (login disabled)."""
    conn = _db()
    conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
    conn.execute("UPDATE settings SET login_toggle = 'disabled' WHERE id = 1")
    conn.commit()
    conn.close()

@pytest.fixture()
def csrf_client(client, seeded_settings):
    """Client with a session CSRF token; returns (client, token)."""
    token = "test-csrf-token"
    with client.session_transaction() as sess:
        sess["csrf_token"] = token
    return client, token

@pytest.fixture()
def login_enabled(app, seeded_settings):
    """Enable login with admin/secret123 for the duration of a test."""
    from app.crypto import encrypt
    conn = _db()
    conn.execute(
        "UPDATE settings SET login_toggle = 'enabled', nl_username = ?, nl_password = ? WHERE id = 1",
        ("admin", encrypt("secret123")),
    )
    conn.commit()
    conn.close()
    yield {"username": "admin", "password": "secret123"}
    conn = _db()
    conn.execute("UPDATE settings SET login_toggle = 'disabled' WHERE id = 1")
    conn.commit()
    conn.close()
