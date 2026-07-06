import os, secrets

from app import config, state, crypto

def create_app():
    from app import legacy
    app = legacy.app

    app.config["GITHUB_OWNER"] = config.GITHUB_OWNER
    app.config["GITHUB_REPO"] = config.GITHUB_REPO
    app.config["UPDATE_CHECK_INTERVAL_SEC"] = config.UPDATE_CHECK_INTERVAL_SEC

    if not app.secret_key:
        app.secret_key = secrets.token_hex(16) + crypto.DATA_KEY[:16]

    app.jinja_env.globals["version"] = config.VERSION
    app.jinja_env.globals["publish_date"] = config.PUBLISH_DATE
    app.jinja_env.globals["get_cache_status"] = legacy.get_global_cache_status

    os.makedirs("database", exist_ok=True)

    legacy.migrate_data_from_separate_dbs()
    legacy.migrate_musicseerr_to_droppedneedle()
    legacy.init_db(config.DB_PATH)
    legacy.refresh_hsts_setting()
    legacy.migrate_schema("logo_filename TEXT")
    legacy.migrate_schema("logo_width INTEGER")
    legacy.migrate_schema("recipient_display_name TEXT DEFAULT 'email'")
    legacy.migrate_schema("plex_client_id TEXT")
    legacy.migrate_ra_recs_to_recently_added_recommendations()
    legacy.migrate_email_templates_for_expanded_collections()
    legacy.migrate_email_templates_for_header_title()
    legacy.migrate_email_templates_for_custom_html()

    state.plex_headers = legacy.get_plex_headers()

    # Same worker gate as the old __main__ block: skip only in the werkzeug
    # reloader parent (WERKZEUG_RUN_MAIN unset while FLASK_DEBUG=1).
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or os.environ.get("FLASK_DEBUG", "0") != "1":
        legacy.start_background_workers()

    return app
