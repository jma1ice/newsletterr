import json
import sqlite3

from app import config
from app.config import DEFAULT_PLEX_WEB_URL
from app.db import init_db, migrate_email_templates_for_header_title, migrate_musicseerr_to_droppedneedle, migrate_schema
from app.settings_store import get_settings

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

def test_header_title_migration_survives_quoted_server_name(tmp_path, monkeypatch):
    # a server name containing a quote must not break or inject into the
    # backfill SQL (regression: the UPDATE used to interpolate it directly)
    db = str(tmp_path / "quoted.db")
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE settings (id INTEGER PRIMARY KEY, server_name TEXT DEFAULT '');
        CREATE TABLE email_templates (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, selected_items TEXT NOT NULL);
    """)
    conn.execute("INSERT INTO settings (id, server_name) VALUES (1, ?)", ("Jamie's Plex",))
    conn.execute("INSERT INTO email_templates (name, selected_items) VALUES (?, ?)", ("tpl", "[]"))
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "DB_PATH", db)

    migrate_email_templates_for_header_title()

    conn = sqlite3.connect(db)
    val = conn.execute("SELECT email_header_title FROM email_templates WHERE name = 'tpl'").fetchone()[0]
    assert val == "Jamie's Plex Newsletter"
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

def test_plex_web_url_ddl_default_matches_constant(tmp_path, monkeypatch):
    # The DDL default lives in two SQL string literals (db.init_db and the
    # migrate_schema call in the app factory) that cannot reference the Python
    # constant. A fresh install, a migrated install and get_settings() must all
    # agree, so drift between them is a bug rather than a style nit.
    db = str(tmp_path / "ddl.db")
    monkeypatch.setattr(config, "DB_PATH", db)
    init_db(db)

    conn = sqlite3.connect(db)
    ddl_default = next(
        r[4] for r in conn.execute("PRAGMA table_info(settings)") if r[1] == "plex_web_url"
    )
    conn.close()
    assert ddl_default.strip("'") == DEFAULT_PLEX_WEB_URL

    # an old install gaining the column by ALTER TABLE lands on the same value
    old = str(tmp_path / "old_install.db")
    conn = sqlite3.connect(old)
    conn.execute("CREATE TABLE settings (id INTEGER PRIMARY KEY, plex_url TEXT)")
    conn.execute("INSERT INTO settings (id, plex_url) VALUES (1, 'http://pms:32400')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(config, "DB_PATH", old)
    migrate_schema("plex_web_url TEXT DEFAULT 'https://app.plex.tv/desktop'")

    conn = sqlite3.connect(old)
    assert conn.execute("SELECT plex_web_url FROM settings WHERE id = 1").fetchone()[0] == DEFAULT_PLEX_WEB_URL
    conn.close()
    assert get_settings()["plex_web_url"] == DEFAULT_PLEX_WEB_URL
