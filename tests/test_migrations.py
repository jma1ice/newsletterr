import json
import sqlite3

from app import config
from app.db import migrate_musicseerr_to_droppedneedle

def _make_pre_rebrand_db(path):
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE settings (id INTEGER PRIMARY KEY, musicseerr_url TEXT DEFAULT '', musicseerr_api_key TEXT DEFAULT '');
        INSERT INTO settings (id, musicseerr_url, musicseerr_api_key) VALUES (1, 'http://dn.local:5000', 'enc-secret-123');
        CREATE TABLE email_templates (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, selected_items TEXT NOT NULL);
    """)
    conn.execute(
        "INSERT INTO email_templates (name, selected_items) VALUES (?, ?)",
        ("wrapped tpl", json.dumps([
            {"type": "musicseerr_wrapped", "userKey": "u1"},
            {"type": "stats"},
            {"type": "musicseerr_server_stats"},
        ])),
    )
    conn.execute(
        "INSERT INTO email_templates (name, selected_items) VALUES (?, ?)",
        ("plain tpl", json.dumps([{"type": "recently added"}])),
    )
    conn.commit()
    conn.close()

def test_musicseerr_rename_migration(tmp_path, monkeypatch):
    db = str(tmp_path / "old.db")
    _make_pre_rebrand_db(db)
    monkeypatch.setattr(config, "DB_PATH", db)

    migrate_musicseerr_to_droppedneedle()
    migrate_musicseerr_to_droppedneedle()  # idempotent

    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(settings)")]
    assert "droppedneedle_url" in cols and "droppedneedle_api_key" in cols
    assert "musicseerr_url" not in cols

    url, key = conn.execute("SELECT droppedneedle_url, droppedneedle_api_key FROM settings WHERE id = 1").fetchone()
    assert (url, key) == ("http://dn.local:5000", "enc-secret-123")  # data survived the rename

    wrapped = json.loads(conn.execute("SELECT selected_items FROM email_templates WHERE name = 'wrapped tpl'").fetchone()[0])
    assert [i["type"] for i in wrapped] == ["droppedneedle_wrapped", "stats", "droppedneedle_server_stats"]

    plain = json.loads(conn.execute("SELECT selected_items FROM email_templates WHERE name = 'plain tpl'").fetchone()[0])
    assert plain == [{"type": "recently added"}]
    conn.close()

def test_migration_noop_on_fresh_schema(tmp_path, monkeypatch):
    # a DB that never had musicseerr columns must pass through untouched
    db = str(tmp_path / "fresh.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE settings (id INTEGER PRIMARY KEY, droppedneedle_url TEXT DEFAULT '')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "DB_PATH", db)

    migrate_musicseerr_to_droppedneedle()

    conn = sqlite3.connect(db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(settings)")]
    assert cols == ["id", "droppedneedle_url"]
    conn.close()
