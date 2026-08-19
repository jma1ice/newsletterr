"""most watched and the inactivity filter on Jellyfin."""
import sqlite3
from unittest.mock import patch

import pytest

from app import config


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


# --- most watched

@pytest.fixture()
def jellywatch_configured(app):
    from app.crypto import encrypt
    conn = sqlite3.connect(config.DB_PATH)
    prev = conn.execute("SELECT jellywatch_url, jellywatch_api_key FROM settings WHERE id = 1").fetchone()
    conn.execute("UPDATE settings SET jellywatch_url = ?, jellywatch_api_key = ? WHERE id = 1",
                 ("http://localhost:8volt", encrypt("k")))
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET jellywatch_url = ?, jellywatch_api_key = ? WHERE id = 1",
                 (prev[0] if prev else '', prev[1] if prev else ''))
    conn.commit()
    conn.close()


def test_most_watched_is_empty_when_jellywatch_is_not_configured(app):
    from app.clients.jellywatch import fetch_jellywatch_most_watched
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET jellywatch_url = '', jellywatch_api_key = '' WHERE id = 1")
    conn.commit()
    conn.close()
    assert fetch_jellywatch_most_watched() == []


def test_most_watched_groups_by_media_type(jellywatch_configured):
    """Jellywatch takes a media type, not a library, so the grouping differs
    from Plex by necessity. The group label doubles as library_name so the
    snap-in's existing filter still has something to match."""
    from app.clients.jellywatch import fetch_jellywatch_most_watched

    by_type = {
        'movie': [{'Name': 'A Film', 'ProductionYear': 2026, 'PlayCount': 12, 'ItemId': 'm1'}],
        'show': [{'Name': 'A Series', 'ProductionYear': 2025, 'PlayCount': 30, 'ItemId': 's1'}],
        'music': [],
    }

    def fake_get(url, params=None, **kwargs):
        return FakeResponse(by_type.get((params or {}).get('type'), []))

    with patch("app.clients.jellywatch.safe_get", side_effect=fake_get):
        groups = fetch_jellywatch_most_watched()

    # music came back empty, so it contributes no group rather than an empty one
    assert len(groups) == 2
    labels = [g['most_watched'][0]['library_name'] for g in groups]
    assert labels == ['Movies', 'TV Shows']


def test_most_watched_items_match_the_shape_the_snapin_reads(jellywatch_configured):
    from app.clients.jellywatch import fetch_jellywatch_most_watched

    def fake_get(url, params=None, **kwargs):
        if (params or {}).get('type') != 'movie':
            return FakeResponse([])
        return FakeResponse([{'Name': 'A Film', 'ProductionYear': 2026, 'PlayCount': 12, 'ItemId': 'm1'}])

    with patch("app.clients.jellywatch.safe_get", side_effect=fake_get):
        item = fetch_jellywatch_most_watched()[0]['most_watched'][0]

    assert item['title'] == 'A Film'
    assert item['year'] == '2026'
    assert item['play_count'] == 12
    assert item['thumb'].startswith('/proxy-art/Items/m1')
    # no deep link: building one needs the server id, and a wrong link is worse
    # than none
    assert item['plex_url'] == ''


def test_most_watched_survives_a_failing_endpoint(jellywatch_configured):
    from app.clients.jellywatch import fetch_jellywatch_most_watched

    with patch("app.clients.jellywatch.safe_get", side_effect=RuntimeError("down")):
        assert fetch_jellywatch_most_watched() == []


def test_the_builder_reads_the_grouped_shape(jellywatch_configured):
    from app.clients.jellywatch import fetch_jellywatch_most_watched
    from app.emails.builders.most_watched import most_watched_items

    def fake_get(url, params=None, **kwargs):
        if (params or {}).get('type') != 'movie':
            return FakeResponse([])
        return FakeResponse([{'Name': 'A Film', 'ProductionYear': 2026, 'PlayCount': 12, 'ItemId': 'm1'}])

    with patch("app.clients.jellywatch.safe_get", side_effect=fake_get):
        groups = fetch_jellywatch_most_watched()

    assert [i['title'] for i in most_watched_items(groups)] == ['A Film']
    # the group label is what the per-library filter can match on
    assert [i['title'] for i in most_watched_items(groups, library_filter='Movies')] == ['A Film']
    assert most_watched_items(groups, library_filter='Films') == []


# --- last activity on users

def test_jellyfin_users_carry_last_activity(app):
    from app.crypto import encrypt

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET jellyfin_url = ?, jellyfin_api_key = ? WHERE id = 1",
                 ("http://localhost:8096", encrypt("k")))
    conn.commit()
    conn.close()

    payload = [
        {"Id": "u1", "Name": "Ann", "Policy": {"IsDisabled": False},
         "LastActivityDate": "2026-08-15T12:00:00.0000000Z"},
        {"Id": "u2", "Name": "Bob", "Policy": {"IsDisabled": False}},
    ]
    with patch("app.clients.jellyfin.safe_get", return_value=FakeResponse(payload)):
        from app.clients.jellyfin import fetch_jellyfin_users
        users = {u['user_id']: u['last_seen'] for u in fetch_jellyfin_users()}

    # a string epoch, the same shape Tautulli's last_seen arrives in
    assert users['u1'] == '1786795200'
    assert users['u2'] == ''


# --- the inactivity filter

def _settings(server_type, days=30):
    return {'media_server_type': server_type, 'exclude_inactive_days': days}


def test_filter_is_off_when_the_setting_is_zero():
    from app.emails.send import filter_inactive
    emails = ['a@b.co']
    assert filter_inactive(emails, _settings('jellyfin', 0)) == (emails, [])


def test_standalone_filters_nobody():
    """No media server means no watch history to judge anyone by."""
    from app.emails.send import filter_inactive
    emails = ['a@b.co']
    assert filter_inactive(emails, _settings('none')) == (emails, [])


def test_jellyfin_excludes_only_the_genuinely_stale():
    import time
    from app.emails import send as send_mod

    recent = str(int(time.time() - 3 * 86400))
    stale = str(int(time.time() - 400 * 86400))
    users = [
        {'user_id': 'u1', 'email': 'recent@example.com', 'last_seen': recent},
        {'user_id': 'u2', 'email': 'stale@example.com', 'last_seen': stale},
        {'user_id': 'u3', 'email': 'never@example.com', 'last_seen': ''},
    ]
    with patch.object(send_mod, 'get_media_server_type', return_value='jellyfin'), \
         patch('app.clients.jellyfin.fetch_jellyfin_users', return_value=users):
        kept, excluded = send_mod.filter_inactive(
            ['recent@example.com', 'stale@example.com', 'never@example.com', 'unknown@example.com'],
            _settings('jellyfin'))

    assert 'recent@example.com' in kept
    # an unmapped or unknown address cannot be judged, so it is kept
    assert 'unknown@example.com' in kept
    assert set(excluded) == {'stale@example.com', 'never@example.com'}


def test_jellyfin_filter_fails_open_when_the_lookup_breaks():
    """Dropping people from a send on bad data is worse than not filtering."""
    from app.emails import send as send_mod

    emails = ['a@b.co', 'c@d.co']
    with patch.object(send_mod, 'get_media_server_type', return_value='jellyfin'):
        with patch('app.clients.jellyfin.fetch_jellyfin_users', side_effect=RuntimeError("down")):
            assert send_mod.filter_inactive(emails, _settings('jellyfin')) == (emails, [])
        with patch('app.clients.jellyfin.fetch_jellyfin_users', return_value=[]):
            assert send_mod.filter_inactive(emails, _settings('jellyfin')) == (emails, [])


def test_plex_still_goes_through_tautulli():
    from app.emails import send as send_mod

    emails = ['a@b.co']
    with patch.object(send_mod, 'get_media_server_type', return_value='plex'), \
         patch.object(send_mod, 'run_tautulli_command', return_value=([], None)) as tautulli:
        send_mod.filter_inactive(emails, {**_settings('plex'), 'tautulli_url': 'http://t', 'tautulli_api': 'k'})
    assert tautulli.called
