# Demo mode (NEWS-15 enabling work). Auth bypass, seeded caches,
# and a read-only write guard, all gated on config.DEMO_MODE.

import pytest

from app import config, demo


@pytest.fixture()
def demo_client(monkeypatch, tmp_path_factory):
    """A fully-built app with DEMO_MODE on, so the before_request guard and the
    auth bypass are actually wired. Uses its own CWD sandbox so its DB/cache
    stay isolated from the default session app."""
    import os
    monkeypatch.setattr(config, "DEMO_MODE", True)
    os.chdir(tmp_path_factory.mktemp("demohome"))
    from app import create_app
    app = create_app()
    return app.test_client()


def test_is_demo_reflects_config(monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", False)
    assert demo.is_demo() is False
    monkeypatch.setattr(config, "DEMO_MODE", True)
    assert demo.is_demo() is True


def test_seed_demo_cache_populates(app):
    from app.cache import get_cached_data, clear_cache
    demo.seed_demo_cache()
    stats = get_cached_data('stats', strict=False)
    recent = get_cached_data('recent_data', strict=False)
    assert any(s['stat_title'] == 'Most Watched Movies' for s in stats)
    assert recent and recent[0]['recently_added'][0]['title']
    clear_cache()


def test_index_served_without_login(demo_client):
    # auth bypassed and caches seeded: the build page renders as a demo user
    resp = demo_client.get('/')
    assert resp.status_code == 200
    assert b"Demo mode" in resp.data


def test_settings_write_blocked(demo_client):
    # a settings POST must not persist; it bounces (302) instead of 200
    resp = demo_client.post('/settings', data={'csrf_token': 'x'})
    assert resp.status_code == 302


def test_json_write_returns_demo_notice(demo_client):
    resp = demo_client.post('/pull_stats', json={'time_range': 30})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["demo"] is True
    assert "Demo mode" in body["message"]


def test_appearance_toggle_allowed(demo_client):
    # the harmless theme flip is on the allowlist, so it runs its real path
    # (rather than the demo guard's bounce); supply the CSRF token the route
    # requires so we exercise the success path
    with demo_client.session_transaction() as sess:
        sess['csrf_token'] = 'demo-token'
    resp = demo_client.post('/api/appearance', json={'theme': 'light'},
                            headers={'X-CSRF-Token': 'demo-token'})
    assert resp.status_code == 200
    assert resp.get_json().get('status') == 'ok'


def test_off_by_default_no_banner(client, seeded_settings):
    # DEMO_MODE defaults off: normal auth applies and no demo banner appears
    assert config.DEMO_MODE is False
    resp = client.get('/settings')
    assert b"Demo mode: changes are disabled" not in resp.data
