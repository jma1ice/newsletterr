# Structural regression tests: the URL surface and response basics that the
# frontend's hardcoded fetch() paths depend on. If a route move/rename is
# intentional, update EXPECTED_RULES deliberately in the same commit.

import pytest

EXPECTED_RULES = [
    "/",
    "/about",
    "/api/gif/search",
    "/api/plex/info",
    "/api/plex/pin",
    "/api/plex/pin/<int:pin_id>",
    "/api/test/conjurr",
    "/api/test/droppedneedle",
    "/api/test/radarr",
    "/api/test/sonarr",
    "/api/test/tautulli",
    "/cache_status",
    "/clear_cache",
    "/csp-report",
    "/delete-logo",
    "/email_history",
    "/email_history/clear",
    "/email_history/recipients/<int:email_id>",
    "/email_history/<int:email_id>/resend",
    "/email_lists",
    "/email_lists/<int:list_id>",
    "/email_templates",
    "/email_templates/<int:template_id>",
    "/fetch_collections/<collection_type>",
    "/get_collection_items",
    "/i/<token>",
    "/login",
    "/logout",
    "/logs",
    "/logs/export",
    "/logs/send-discord",
    "/newsletter",
    "/proxy-art/<path:art_path>",
    "/proxy-img",
    "/proxy-radarr-art/<path:art_path>",
    "/proxy-sonarr-art/<path:art_path>",
    "/pull_coming_soon",
    "/pull_droppedneedle_stats",
    "/pull_recommendations",
    "/pull_stats",
    "/scheduling",
    "/send_test_email",
    "/setup",
    "/setup/conjurr",
    "/setup/droppedneedle",
    "/setup/email",
    "/setup/plex",
    "/setup/radarr",
    "/setup/sonarr",
    "/setup/tautulli",
    "/scheduling/<int:schedule_id>",
    "/scheduling/<int:schedule_id>/preview",
    "/scheduling/<int:schedule_id>/preview-page",
    "/scheduling/<int:schedule_id>/send-now",
    "/scheduling/<int:schedule_id>/toggle",
    "/scheduling/calendar-data",
    "/scheduling/create",
    "/send_email",
    "/settings",
    "/u/<token>",
    "/upload-logo",
    "/upload/media",
]

def test_url_map_snapshot(app):
    # set(): GET/POST pairs registered as separate decorators share a rule string
    rules = sorted({r.rule for r in app.url_map.iter_rules() if r.endpoint != "static"})
    assert rules == sorted(EXPECTED_RULES)

def test_endpoints_are_blueprint_dotted(app):
    for rule in app.url_map.iter_rules():
        if rule.endpoint != "static":
            assert "." in rule.endpoint, f"{rule.rule} has non-blueprint endpoint {rule.endpoint}"

@pytest.mark.parametrize("path", ["/settings", "/about", "/scheduling", "/email_history"])
def test_pages_render(client, seeded_settings, path):
    resp = client.get(path)
    assert resp.status_code == 200

def test_settings_includes_email_wizard(client, seeded_settings):
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert b"emailWizardModal" in resp.data
    assert b"email-providers.js" in resp.data

def test_index_unconfigured_redirects_to_settings(client, seeded_settings):
    # index redirects to settings until from_email is configured; force that
    # state explicitly so this test is independent of execution order
    import sqlite3
    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET from_email = '' WHERE id = 1")
    conn.commit()
    conn.close()

    resp = client.get("/")
    assert resp.status_code == 302
    assert "/settings" in resp.headers["Location"]

def test_cache_status_json(client, seeded_settings):
    resp = client.get("/cache_status")
    assert resp.status_code == 200
    assert resp.is_json

def test_security_headers(client, seeded_settings):
    resp = client.get("/about")
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"

def test_login_page_renders_when_admin_configured(client, seeded_settings):
    resp = client.get("/login")
    assert resp.status_code == 200
