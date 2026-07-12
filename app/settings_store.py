import sqlite3

from app.db import db_connect
from app.crypto import decrypt

# Columns stored encrypted; get_settings() returns them decrypted unless
# decrypt_secrets=False. decrypt() passes legacy plaintext values through.
# nl_password is deliberately NOT here: it is a one-way password hash
# (werkzeug), handled by app.security, never Fernet-decrypted.
SECRET_COLUMNS = frozenset({
    "password",
    "plex_token",
    "tautulli_api",
    "droppedneedle_api_key",
    "discord_webhook_url",
    "sonarr_api_key",
    "radarr_api_key",
})

# Empty/NULL columns are normalized with `or`-semantics, matching the
# normalizations previously scattered across theme.py, main.py and
# emails/scheduled.py.
DEFAULTS = {
    "primary_color": "#8acbd4",
    "secondary_color": "#222222",
    "accent_color": "#62a1a4",
    "background_color": "#333333",
    "text_color": "#62a1a4",
    "email_theme": "newsletterr_blue",
    "recipient_display_name": "email",
    "scheduled_subject_prefix": "enabled",
    "logo_position": "center",
    "default_intro_text": "",
    "default_outro_text": "",
    "hide_stat_play_counts": "disabled",
    "hide_graph_play_counts": "disabled",
    "stats_type": "plays",
    "recently_added_mode": "items",
    "recently_added_sort": "date",
    "stat_cover_art": "disabled",
    "send_mode": "bcc",
    "hsts_enabled": "disabled",
    "coming_soon_days_ahead": "14",
    "hosted_enabled": "disabled",
    "hosted_base_url": "",
    "hosted_images_enabled": "disabled",
}

INT_COLUMNS = {
    "ra_grid_columns": 5,
    "recs_grid_columns": 5,
    "poster_max_height": 0,
    "coming_soon_grid_columns": 5,
}

def get_settings(decrypt_secrets=True):
    """Return the singleton settings row as a dict, or {} plus defaults when
    the row doesn't exist yet (fresh install before first save).

    Safe to call from background threads: no Flask context involved."""
    conn = db_connect(row_factory=sqlite3.Row)
    try:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    finally:
        conn.close()

    s = dict(row) if row else {}
    if decrypt_secrets:
        for col in SECRET_COLUMNS:
            if s.get(col):
                s[col] = decrypt(s[col])
    for col, default in DEFAULTS.items():
        s[col] = s.get(col) or default
    for col, default in INT_COLUMNS.items():
        # a bad stored value must not take down every get_settings() caller
        # (request threads and the scheduler all depend on this)
        try:
            s[col] = int(s.get(col) or default)
        except (TypeError, ValueError):
            s[col] = default
    return s

def get_service_flags(s):
    """Booleans only (no URLs/keys leak to the client): which pull-data
    services are configured, so the frontend can grey out buttons that
    would just fail. `s` is a settings dict as returned by get_settings()."""
    return {
        "tautulli": bool(s.get("tautulli_url") and s.get("tautulli_api")),
        "conjurr": bool(s.get("conjurr_url")),
        "droppedneedle": bool(s.get("droppedneedle_url") and s.get("droppedneedle_api_key")),
        "calendar": bool(
            (s.get("sonarr_url") and s.get("sonarr_api_key"))
            or (s.get("radarr_url") and s.get("radarr_api_key"))
        ),
    }
