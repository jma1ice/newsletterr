import sqlite3

import pytest

from app import config
from app.clients import plex

@pytest.fixture()
def plex_db(tmp_path, monkeypatch):
    """Fresh-install shape: settings table exists but holds NO row (init_db
    only CREATEs the table, it never seeds id=1)."""
    db = str(tmp_path / "plex.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE settings (id INTEGER PRIMARY KEY, plex_client_id TEXT)")
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "DB_PATH", db)
    return db

def _stored_id(db):
    conn = sqlite3.connect(db)
    try:
        row = conn.execute("SELECT plex_client_id FROM settings WHERE id = 1").fetchone()
    finally:
        conn.close()
    return row[0] if row else None

def test_identifier_is_persisted_on_fresh_install(plex_db):
    # Regression for #159: on a fresh install (no settings row) the identifier
    # must be persisted, not handed out as a throwaway UUID.
    cid = plex.get_plex_client_identifier()
    assert cid
    assert _stored_id(plex_db) == cid

def test_identifier_is_stable_across_calls(plex_db):
    # The OAuth token is scoped to the identifier that minted it; a second call
    # (e.g. the first library fetch) must return the same value or Plex 401s.
    first = plex.get_plex_client_identifier()
    second = plex.get_plex_client_identifier()
    assert first == second

def test_existing_identifier_is_reused(plex_db):
    conn = sqlite3.connect(plex_db)
    conn.execute("INSERT INTO settings (id, plex_client_id) VALUES (1, 'preexisting-id')")
    conn.commit()
    conn.close()
    assert plex.get_plex_client_identifier() == "preexisting-id"

def test_null_identifier_on_existing_row_is_backfilled(plex_db):
    # The token-save path can create the settings row with plex_client_id NULL;
    # the next call must persist a stable id into that same row.
    conn = sqlite3.connect(plex_db)
    conn.execute("INSERT INTO settings (id, plex_client_id) VALUES (1, NULL)")
    conn.commit()
    conn.close()
    cid = plex.get_plex_client_identifier()
    assert cid
    assert _stored_id(plex_db) == cid
    assert plex.get_plex_client_identifier() == cid
