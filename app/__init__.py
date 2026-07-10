import os

from flask import Flask

from app import cache, config, crypto, db, hooks, scheduler, state
from app.clients import plex
from app.log import setup_logging

def create_app():
    setup_logging()

    from app.blueprints import api, auth, emails, logs, main, scheduling, settings, stats

    app = Flask(__name__, template_folder = str(config.ASSET_ROOT / 'templates'), static_folder = str(config.ASSET_ROOT / 'static'))

    for module in (api, auth, emails, logs, main, scheduling, settings, stats):
        app.register_blueprint(module.bp)

    app.config["GITHUB_OWNER"] = config.GITHUB_OWNER
    app.config["GITHUB_REPO"] = config.GITHUB_REPO
    app.config["UPDATE_CHECK_INTERVAL_SEC"] = config.UPDATE_CHECK_INTERVAL_SEC

    app.secret_key = crypto.ensure_secret_key()

    app.jinja_env.globals["version"] = config.VERSION
    app.jinja_env.globals["publish_date"] = config.PUBLISH_DATE
    app.jinja_env.globals["get_cache_status"] = cache.get_global_cache_status

    os.makedirs("database", exist_ok=True)

    db.migrate_data_from_separate_dbs()
    db.migrate_musicseerr_to_droppedneedle()
    db.init_db(config.DB_PATH)
    hooks.refresh_hsts_setting()
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # HSTS enabled implies the instance is served over https
    app.config["SESSION_COOKIE_SECURE"] = state._hsts_enabled
    db.migrate_schema("logo_filename TEXT")
    db.migrate_schema("logo_width INTEGER")
    db.migrate_schema("recipient_display_name TEXT DEFAULT 'email'")
    db.migrate_schema("plex_client_id TEXT")
    db.migrate_ra_recs_to_recently_added_recommendations()
    db.migrate_email_templates_for_expanded_collections()
    db.migrate_email_templates_for_header_title()
    db.migrate_email_templates_for_custom_html()

    state.plex_headers = plex.get_plex_headers()

    hooks.register(app)

    # Same worker gate as the old __main__ block: skip only in the werkzeug
    # reloader parent (WERKZEUG_RUN_MAIN unset while FLASK_DEBUG=1).
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or os.environ.get("FLASK_DEBUG", "0") != "1":
        scheduler.start_background_workers()

    return app
