import sqlite3
import threading

import pytest

from app import config
from app.crypto import encrypt
from app.settings_store import DEFAULTS, INT_COLUMNS, get_settings

@pytest.fixture()
def settings_db(tmp_path, monkeypatch):
    db = str(tmp_path / "settings.db")
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE settings (
            id INTEGER PRIMARY KEY,
            server_name TEXT, tautulli_url TEXT, tautulli_api TEXT,
            password TEXT, stats_type TEXT, ra_grid_columns TEXT,
            poster_max_height TEXT, recipient_display_name TEXT
        )
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "DB_PATH", db)
    return db

def _seed(db, **cols):
    conn = sqlite3.connect(db)
    keys = ", ".join(cols)
    marks = ", ".join("?" * len(cols))
    conn.execute(f"INSERT INTO settings (id, {keys}) VALUES (1, {marks})", tuple(cols.values()))
    conn.commit()
    conn.close()

def test_missing_row_returns_defaults(settings_db):
    s = get_settings()
    for col, default in DEFAULTS.items():
        assert s[col] == default
    for col, default in INT_COLUMNS.items():
        assert s[col] == default

def test_values_and_defaults(settings_db):
    _seed(settings_db, server_name="MyPlex", stats_type="", ra_grid_columns="3")
    s = get_settings()
    assert s["server_name"] == "MyPlex"
    assert s["stats_type"] == "plays"        # empty string -> default (or-semantics)
    assert s["ra_grid_columns"] == 3          # int cast
    assert s["poster_max_height"] == 0        # NULL int -> default

def test_secrets_decrypted_eagerly(settings_db):
    _seed(settings_db, tautulli_api=encrypt("tt-key"), password=encrypt("smtp-pw"))
    s = get_settings()
    assert s["tautulli_api"] == "tt-key"
    assert s["password"] == "smtp-pw"

def test_legacy_plaintext_secret_passes_through(settings_db):
    _seed(settings_db, tautulli_api="plain-old-key")
    assert get_settings()["tautulli_api"] == "plain-old-key"

def test_decrypt_secrets_false_returns_ciphertext(settings_db):
    token = encrypt("tt-key")
    _seed(settings_db, tautulli_api=token)
    assert get_settings(decrypt_secrets=False)["tautulli_api"] == token

def test_unknown_columns_survive(settings_db):
    # schema grows via migrations; the accessor must expose new columns as-is
    conn = sqlite3.connect(settings_db)
    conn.execute("ALTER TABLE settings ADD COLUMN some_future_column TEXT")
    conn.commit()
    conn.close()
    _seed(settings_db, server_name="x")
    conn = sqlite3.connect(settings_db)
    conn.execute("UPDATE settings SET some_future_column = 'future' WHERE id = 1")
    conn.commit()
    conn.close()
    assert get_settings()["some_future_column"] == "future"

def test_callable_from_bare_thread(settings_db):
    _seed(settings_db, server_name="ThreadPlex")
    result = {}

    def worker():
        result["s"] = get_settings()

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    assert result["s"]["server_name"] == "ThreadPlex"
