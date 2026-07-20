# NEWS-24: Jellywatch stats normalized to the Tautulli home-stats
# shape so the stats builder never branches on the stats backend.

from unittest.mock import patch

from app.clients.jellywatch import (
    _normalize_watched_rows,
    _normalize_user_rows,
    fetch_jellywatch_home_stats,
)

def test_normalize_watched_rows_pascalcase():
    rows = _normalize_watched_rows([
        {'ItemId': 'm1', 'Name': 'Film', 'ProductionYear': 2024, 'PlayCount': 12,
         'TotalDuration': 7200, 'OfficialRating': 'PG', 'CommunityRating': 8.1},
    ])
    assert rows == [{
        'title': 'Film', 'year': '2024', 'total_plays': 12, 'total_duration': 7200,
        'content_rating': 'PG', 'rating': 8.1, 'thumb': '/Items/m1/Images/Primary',
    }]

def test_normalize_watched_rows_camelcase_and_defaults():
    rows = _normalize_watched_rows([{'name': 'X'}])
    assert rows[0]['title'] == 'X'
    assert rows[0]['total_plays'] == 0
    assert rows[0]['total_duration'] == 0
    assert rows[0]['thumb'] == ''

def test_normalize_user_rows_proxy_prefixed_thumb():
    rows = _normalize_user_rows([{'UserId': 'u1', 'UserName': 'Ann', 'PlayCount': 5}])
    assert rows[0]['user'] == 'Ann'
    assert rows[0]['total_plays'] == 5
    assert rows[0]['user_thumb'] == '/proxy-art/Users/u1/Images/Primary'

def test_fetch_home_stats_omits_empty_and_respects_user_toggle(app, seeded_settings):
    import sqlite3
    from app import config
    from app.crypto import encrypt
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "UPDATE settings SET jellywatch_url = ?, jellywatch_api_key = ? WHERE id = 1",
        ("http://jw.local", encrypt("k")),
    )
    conn.commit()
    conn.close()

    def fake_watched(url, api_key, media_type, days):
        if media_type == 'movie':
            return [{'title': 'A', 'total_plays': 1}]
        return []  # no shows -> stat omitted

    def fake_users(url, api_key, days):
        return [{'user': 'Ann', 'total_plays': 2}]

    with patch("app.clients.jellywatch._fetch_watched", side_effect=fake_watched), \
         patch("app.clients.jellywatch._fetch_users", side_effect=fake_users):
        stats = fetch_jellywatch_home_stats(days=30, include_user_info=True)
        titles = [s['stat_title'] for s in stats]
        assert 'Most Watched Movies' in titles
        assert 'Most Watched TV Shows' not in titles  # empty -> omitted
        assert 'Most Active Users' in titles

        stats_no_users = fetch_jellywatch_home_stats(days=30, include_user_info=False)
        assert 'Most Active Users' not in [s['stat_title'] for s in stats_no_users]

def test_fetch_home_stats_unconfigured_returns_empty(app, seeded_settings):
    import sqlite3
    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET jellywatch_url = '', jellywatch_api_key = '' WHERE id = 1")
    conn.commit()
    conn.close()
    assert fetch_jellywatch_home_stats(days=30) == []
