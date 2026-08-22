# Demo mode. Auth bypass, the sample install (settings
# overlay plus seeded caches), the per-visitor session overlay that stands in
# for saving, and the read-only write guard, all gated on config.DEMO_MODE.

import json
import sqlite3

import pytest

from app import config, demo


@pytest.fixture()
def demo_client(monkeypatch, tmp_path_factory):
    """A fully-built app with DEMO_MODE on, so the before_request guard and the
    auth bypass are actually wired. Uses its own CWD sandbox so its DB stays
    isolated from the default session app, and hands the CWD and the (global,
    in-process) caches back afterwards so the rest of the session is unaffected
    by the seeded sample data."""
    import os
    from app.cache import clear_cache
    prev_cwd = os.getcwd()
    monkeypatch.setattr(config, "DEMO_MODE", True)
    os.chdir(tmp_path_factory.mktemp("demohome"))
    from app import create_app
    app = create_app()
    try:
        yield app.test_client()
    finally:
        os.chdir(prev_cwd)
        clear_cache()


@pytest.fixture()
def demo_csrf(demo_client):
    """(client, token) with the token installed in the demo session."""
    token = "demo-csrf-token"
    with demo_client.session_transaction() as sess:
        sess["csrf_token"] = token
    return demo_client, token


def test_is_demo_reflects_config(monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", False)
    assert demo.is_demo() is False
    monkeypatch.setattr(config, "DEMO_MODE", True)
    assert demo.is_demo() is True


def test_seed_demo_cache_populates(app):
    from app.cache import get_cached_data, clear_cache
    demo.seed_demo_cache()  # module under test seeds the shared cache; cleared below
    stats = get_cached_data('stats', strict=False)
    recent = get_cached_data('recent_data', strict=False)
    coming_soon = get_cached_data('sonarr_coming_soon_json', strict=False)
    assert any(s['stat_title'] == 'Most Watched Movies' for s in stats)
    assert recent and recent[0]['recently_added'][0]['title']
    assert coming_soon and coming_soon[0]['series']['title']
    clear_cache()


def test_index_served_without_login(demo_client):
    # auth bypassed and caches seeded: the build page renders as a demo user
    resp = demo_client.get('/')
    assert resp.status_code == 200
    assert b"Demo mode" in resp.data
    # the sample install reaches the page, so the builder has something to show
    assert b"The Grand Voyage" in resp.data


def test_logout_returns_to_the_app_not_setup(demo_client):
    # a demo visitor has no account: logging out must not clear the session and
    # drop them into first-run setup
    demo_client.get('/')
    resp = demo_client.get('/logout')
    assert resp.status_code == 302
    assert resp.headers['Location'].rstrip('/').endswith('') and '/setup' not in resp.headers['Location']
    with demo_client.session_transaction() as sess:
        assert sess.get('authenticated') is True
    assert b"logout" not in demo_client.get('/').data


def test_login_and_setup_bounce_to_index(demo_client):
    for path in ('/login', '/setup', '/setup/email'):
        resp = demo_client.get(path)
        assert resp.status_code == 302, path
        assert resp.headers['Location'].endswith('/'), path


def test_preview_renders_sample_email(demo_csrf):
    client, token = demo_csrf
    resp = client.post('/preview_email', json={
        "subject": "Demo",
        "email_header_title": "What landed",
        "selected_items": [
            {"id": "intro-block-1", "name": "Intro", "type": "textblock", "content": "Hello"},
            {"id": "ra-lib-movies", "name": "Recently Added", "type": "recently added", "raLibrary": "Movies"},
            {"id": "stat-0", "name": "Most Watched Movies", "type": "stat"},
        ],
    }, headers={'X-CSRF-Token': token})
    assert resp.status_code == 200
    html = resp.get_json()["html"]
    assert "The Grand Voyage" in html
    assert "/proxy-art/library/demo/" in html


def test_demo_art_is_served_and_unknown_paths_404(demo_client):
    ok = demo_client.get('/proxy-art/library/demo/the-grand-voyage.png')
    assert ok.status_code == 200
    assert ok.headers['Content-Type'].startswith('image/')
    # anything else must not fall through to the real proxy (no media server)
    assert demo_client.get('/proxy-art/library/metadata/1/thumb').status_code == 404


def test_pull_stats_returns_sample_data(demo_csrf):
    client, token = demo_csrf
    resp = client.post('/pull_stats', json={'time_range': 30, 'count': 10},
                       headers={'X-CSRF-Token': token})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True and body["demo"] is True
    assert body["stats"] and body["recent_data"] and len(body["graph_data"]) == 12


def test_send_is_blocked_with_a_notice(demo_client):
    resp = demo_client.post('/send_email', json={'to_emails': 'a@b.c'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["demo"] is True
    assert "Demo mode" in body["message"]


def test_oauth_endpoints_are_blocked(demo_client):
    # The demo must never reach Microsoft. These are POSTs outside the write
    # allowlist, so the demo before_request answers them before the route runs.
    for path in ('/api/oauth/microsoft/start',
                 '/api/oauth/microsoft/poll',
                 '/api/oauth/microsoft/disconnect'):
        resp = demo_client.post(path, json={'client_id': 'x', 'device_code': 'y'})
        assert resp.status_code == 200, path
        assert resp.get_json()["demo"] is True, path


def test_settings_save_applies_to_the_session_only(demo_csrf):
    client, token = demo_csrf
    resp = client.post('/settings', data={
        'csrf_token': token,
        'email_layout': 'digest',
        'email_density': 'compact',
        'email_theme': 'plex_orange',
    })
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        overlay = sess['demo_settings']
    assert overlay['email_layout'] == 'digest'
    assert overlay['email_density'] == 'compact'
    # a preset theme carries its palette, exactly as the real save does
    assert overlay['primary_color'] == '#e5a00d'

    # the database is untouched
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute("SELECT email_layout FROM settings WHERE id = 1").fetchone()
    conn.close()
    assert row is None or row[0] in (None, '', 'classic')

    # and the choice reaches the pages through get_settings()
    assert b'option value="digest" selected' in client.get('/settings').data


def test_settings_save_rejects_a_bad_csrf_token(demo_client):
    assert demo_client.post('/settings', data={'csrf_token': 'nope'}).status_code == 400


def test_settings_save_ignores_credentials_and_endpoints(demo_csrf):
    client, token = demo_csrf
    client.post('/settings', data={
        'csrf_token': token,
        'from_email': 'attacker@example.com',
        'smtp_server': 'smtp.example.com',
        'plex_url': 'http://192.168.0.5:32400',
        'tautulli_api': 'stolen-key',
        'nl_username': 'attacker',
        'media_server_type': 'jellyfin',
        'hosted_enabled': 'enabled',
        'email_layout': 'editorial',
    })
    with client.session_transaction() as sess:
        overlay = sess['demo_settings']
    assert overlay == {'email_layout': 'editorial'} or set(overlay) == {'email_layout'}

    from app.settings_store import get_settings
    with client.application.test_request_context('/'):
        with client.session_transaction() as sess:
            pass
        s = get_settings(decrypt_secrets=False)
    assert s['from_email'] == demo.BASE_SETTINGS['from_email']
    assert s['media_server_type'] == 'plex'


def test_overlay_drops_oversized_text_to_fit_the_cookie(demo_csrf):
    client, token = demo_csrf
    client.post('/settings', data={
        'csrf_token': token,
        'email_layout': 'digest',
        'default_intro_text': 'x' * 4000,
        'default_outro_text': 'y' * 4000,
    })
    with client.session_transaction() as sess:
        overlay = sess['demo_settings']
    assert len(json.dumps(overlay)) <= demo._OVERLAY_BUDGET_BYTES
    assert overlay.get('email_layout') == 'digest'


def test_appearance_toggle_writes_the_session_not_the_db(demo_csrf):
    client, token = demo_csrf
    resp = client.post('/api/appearance', json={'theme': 'light', 'pride': 'trans'},
                       headers={'X-CSRF-Token': token})
    assert resp.status_code == 200
    assert resp.get_json().get('status') == 'ok'
    with client.session_transaction() as sess:
        assert sess['demo_settings']['appearance_theme'] == 'light'
        assert sess['demo_settings']['pride_flag'] == 'trans'

    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute("SELECT appearance_theme FROM settings WHERE id = 1").fetchone()
    conn.close()
    assert row is None or row[0] in (None, '', 'dark')


def test_service_lookups_answer_from_sample_data(demo_client):
    collections = demo_client.get('/fetch_collections/movie').get_json()
    assert collections['status'] == 'success' and collections['collections']
    libraries = demo_client.get('/random_pick_options').get_json()
    assert [lib['title'] for lib in libraries['libraries']] == ['Movies', 'TV Shows', 'Music']
    search = demo_client.get('/featured_pick_search?q=voyage').get_json()
    assert search['results'][0]['title'] == 'The Grand Voyage'


def test_scheduling_and_history_render_sample_rows(demo_client):
    # Both pages read the database rather than a media server, so they are the
    # two that render as empty states unless demo supplies rows of its own.
    scheduling = demo_client.get('/scheduling').get_data(as_text=True)
    assert 'no schedules created' not in scheduling
    assert 'Weekly Roundup' in scheduling and 'Coming Soon Friday' in scheduling
    # An inactive schedule is present too: the page styles the two differently.
    assert 'Paused' in scheduling

    history = demo_client.get('/email_history').get_data(as_text=True)
    assert 'no email history' not in history
    # The table lists subjects and a recipient count; the addresses themselves
    # only arrive through the modal's fetch, covered separately below.
    assert 'Demo Media Server - Weekly Roundup' in history
    # One of each terminal state, so the status filter chips all have a row.
    for status in ('sent', 'skipped', 'failed'):
        assert f'data-status="{status}"' in history


def test_sample_sends_never_reach_the_database(demo_client):
    demo_client.get('/scheduling')
    demo_client.get('/email_history')
    conn = sqlite3.connect(config.DB_PATH)
    try:
        for table in ('email_schedules', 'email_history', 'email_lists', 'email_templates'):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        conn.close()


def test_schedule_next_send_lands_on_its_own_recurrence(demo_client):
    # The cards print next_send while the calendar walks forward from
    # start_date itself. Picked independently they drift apart and the demo
    # looks like the scheduler is miscounting.
    from datetime import datetime
    for row in demo.demo_schedule_rows():
        start, frequency, last, upcoming = row[5], row[4], row[7], row[8]
        if frequency != 'weekly' or not upcoming:
            continue
        start_dt = datetime.fromisoformat(start)
        for stamp in (last, upcoming):
            when = datetime.fromisoformat(stamp)
            assert (when.date() - start_dt.date()).days % 7 == 0
            assert when.weekday() == start_dt.weekday()
        assert datetime.fromisoformat(upcoming) > datetime.now()
        assert datetime.fromisoformat(last) <= datetime.now()


def test_history_row_actions_answer_instead_of_404ing(demo_client):
    recipients = demo_client.get('/email_history/recipients/1').get_json()
    assert recipients['recipients'] and '@' in recipients['recipients'][0]
    # No stored message body exists to export, so the button explains itself.
    pdf = demo_client.get('/email_history/1/pdf')
    assert pdf.status_code == 404 and pdf.get_json().get('demo') is True


def test_off_by_default_no_banner(client, seeded_settings):
    # DEMO_MODE defaults off: normal auth applies and no demo banner appears
    assert config.DEMO_MODE is False
    resp = client.get('/settings')
    assert b"Demo mode: a sandbox" not in resp.data
