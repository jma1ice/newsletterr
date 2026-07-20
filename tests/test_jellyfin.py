# NEWS-24: the media-server abstraction and Jellyfin client primitives.
# Network-touching paths are exercised through mocks; the deep link builder
# and normalization logic are pure.

from unittest.mock import patch

from app.clients.jellyfin import build_jellyfin_web_link, _COLLECTION_TYPE_MAP
from app.clients.mediaserver import get_media_server_type, build_media_web_link, artwork_proxy_prefix

def test_build_jellyfin_web_link_prefers_web_url():
    link = build_jellyfin_web_link("abc123", "srv1", "https://jf.example.com", "http://localhost:8096")
    assert link == "https://jf.example.com/web/index.html#!/details?id=abc123&serverId=srv1"

def test_build_jellyfin_web_link_falls_back_to_server_url():
    link = build_jellyfin_web_link("abc123", "srv1", "", "http://localhost:8096/")
    assert link == "http://localhost:8096/web/index.html#!/details?id=abc123&serverId=srv1"

def test_build_jellyfin_web_link_without_server_id():
    link = build_jellyfin_web_link("abc123", None, None, "http://localhost:8096")
    assert link == "http://localhost:8096/web/index.html#!/details?id=abc123"

def test_build_jellyfin_web_link_empty_inputs():
    assert build_jellyfin_web_link("", "srv1", "x", "y") == ""
    assert build_jellyfin_web_link("abc", None, None, None) == ""

def test_collection_type_map_covers_core_sections():
    assert _COLLECTION_TYPE_MAP["movies"] == "movie"
    assert _COLLECTION_TYPE_MAP["tvshows"] == "show"
    assert _COLLECTION_TYPE_MAP["music"] == "artist"

def test_media_server_type_defaults_to_plex():
    assert get_media_server_type({}) == "plex"
    assert get_media_server_type({"media_server_type": "jellyfin"}) == "jellyfin"
    assert get_media_server_type({"media_server_type": "emby"}) == "plex"

def test_artwork_proxy_prefix_dispatch():
    assert artwork_proxy_prefix({"media_server_type": "plex"}) == "/proxy-art"
    assert artwork_proxy_prefix({"media_server_type": "jellyfin"}) == "/proxy-jf-art"

def test_build_media_web_link_dispatches_jellyfin():
    s = {
        "media_server_type": "jellyfin",
        "jellyfin_url": "http://localhost:8096",
        "jellyfin_web_url": "",
    }
    link = build_media_web_link("item9", "srv9", s)
    assert link == "http://localhost:8096/web/index.html#!/details?id=item9&serverId=srv9"

def test_build_media_web_link_dispatches_plex():
    s = {
        "media_server_type": "plex",
        "plex_web_url": "https://app.plex.tv/desktop",
    }
    link = build_media_web_link("42", "machine1", s)
    assert link == "https://app.plex.tv/desktop#!/server/machine1/details?key=/library/metadata/42"

def test_service_flags_include_jellyfin(app, seeded_settings):
    from app.settings_store import get_service_flags
    flags = get_service_flags({
        "jellyfin_url": "http://localhost:8096",
        "jellyfin_api_key": "enc",
        "jellywatch_url": "",
        "jellywatch_api_key": "",
    })
    assert flags["jellyfin"] is True
    assert flags["jellywatch"] is False

def test_jellyfin_libraries_normalized(app, seeded_settings):
    import sqlite3
    from app import config
    from app.crypto import encrypt
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "UPDATE settings SET jellyfin_url = ?, jellyfin_api_key = ? WHERE id = 1",
        ("http://localhost:8096", encrypt("k")),
    )
    conn.commit()
    conn.close()

    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"Items": [
                {"Id": "lib1", "Name": "Movies", "CollectionType": "movies"},
                {"Id": "lib2", "Name": "Shows", "CollectionType": "tvshows"},
                {"Id": "lib3", "Name": "Tunes", "CollectionType": "music"},
            ]}

    with patch("app.clients.jellyfin.safe_get", return_value=FakeResponse()) as mock_get:
        from app.clients.jellyfin import fetch_jellyfin_libraries
        libs = fetch_jellyfin_libraries()

    assert libs == [
        {"section_id": "lib1", "section_name": "Movies", "section_type": "movie"},
        {"section_id": "lib2", "section_name": "Shows", "section_type": "show"},
        {"section_id": "lib3", "section_name": "Tunes", "section_type": "artist"},
    ]
    # auth must ride in the header, never the URL
    args, kwargs = mock_get.call_args
    assert "X-Emby-Token" in kwargs["headers"]
    assert "api_key" not in args[0]

def test_iso_to_epoch():
    from app.clients.jellyfin import _iso_to_epoch
    assert _iso_to_epoch("1970-01-01T00:00:10Z") == "10"
    assert _iso_to_epoch("1970-01-01T00:00:10.1234567Z") == "10"
    assert _iso_to_epoch("") == ""
    assert _iso_to_epoch("not-a-date") == ""

def test_normalize_jellyfin_item_matches_plex_shape():
    from app.clients.jellyfin import _normalize_jellyfin_item
    item = {
        'Id': 'abc',
        'Name': 'The Movie',
        'Type': 'Movie',
        'ProductionYear': 2024,
        'Overview': 'A film.',
        'OfficialRating': 'PG-13',
        'CommunityRating': 7.8,
        'RunTimeTicks': 60_000_000_000,  # 100 minutes in 100ns ticks
        'DateCreated': '1970-01-01T01:00:00Z',
        'ImageTags': {'Primary': 'tag1'},
        'BackdropImageTags': ['tag2'],
    }
    n = _normalize_jellyfin_item(item, 'Movies', 'srv1', '', 'http://localhost:8096')
    # exact keys the plex fetchers produce, so builders never branch
    assert n['title'] == 'The Movie'
    assert n['rating_key'] == 'abc'
    assert n['year'] == '2024'
    assert n['thumb'] == '/Items/abc/Images/Primary'
    assert n['media_type'] == 'movie'
    assert n['type'] == 'movie'
    assert n['duration'] == '6000000'  # milliseconds, plex convention
    assert n['added_at'] == '3600'
    assert n['library_name'] == 'Movies'
    assert n['plex_url'] == 'http://localhost:8096/web/index.html#!/details?id=abc&serverId=srv1'
    assert n['rating'] == '7.8'

def test_normalize_jellyfin_item_without_images():
    from app.clients.jellyfin import _normalize_jellyfin_item
    n = _normalize_jellyfin_item({'Id': 'x', 'Name': 'N', 'Type': 'Series'}, 'Shows', None, '', '')
    assert n['thumb'] == ''
    assert n['art'] == ''
    assert n['media_type'] == 'show'
    assert n['plex_url'] == ''

def test_pull_stats_jellyfin_branch(csrf_client):
    import sqlite3
    from app import config
    from app.crypto import encrypt
    client, token = csrf_client
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "UPDATE settings SET media_server_type = 'jellyfin', jellyfin_url = ?, jellyfin_api_key = ? WHERE id = 1",
        ("http://localhost:8096", encrypt("k")),
    )
    conn.commit()
    conn.close()
    try:
        fake_recent = [{'recently_added': [{'title': 'X', 'rating_key': '1', 'thumb': '', 'library_name': 'Movies'}]}]
        with patch("app.blueprints.stats.fetch_jellyfin_library_counts", return_value=[{'section_name': 'Movies', 'count': 5}]), \
             patch("app.blueprints.stats.fetch_recently_added_using_jellyfin", return_value=fake_recent), \
             patch("app.blueprints.stats.fetch_jellywatch_home_stats", return_value=[]), \
             patch("app.blueprints.stats.get_jellyfin_server_id", return_value="srv1"):
            resp = client.post("/pull_stats", json={"time_range": 30, "count": 10},
                               headers={"X-CSRF-Token": token})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["recent_data"] == fake_recent
        assert data["stats"][0]["stat_id"] == "library_item_counts"
        assert data["graph_commands"] == []
        assert data["plex_unavailable"] is False
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("UPDATE settings SET media_server_type = 'plex', jellyfin_url = '', jellyfin_api_key = '' WHERE id = 1")
        conn.commit()
        conn.close()

def test_fetch_jellyfin_users_normalized(app, seeded_settings):
    import sqlite3
    from app import config
    from app.crypto import encrypt
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "UPDATE settings SET jellyfin_url = ?, jellyfin_api_key = ? WHERE id = 1",
        ("http://localhost:8096", encrypt("k")),
    )
    conn.commit()
    conn.close()

    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return [
                {"Id": "u1", "Name": "Ann", "Policy": {"IsDisabled": False}},
                {"Id": "u2", "Name": "Bob", "Policy": {"IsDisabled": True}},
            ]

    with patch("app.clients.jellyfin.safe_get", return_value=FakeResponse()):
        from app.clients.jellyfin import fetch_jellyfin_users
        users = fetch_jellyfin_users()

    assert users == [
        {"user_id": "u1", "friendly_name": "Ann", "email": None, "is_active": True},
        {"user_id": "u2", "friendly_name": "Bob", "email": None, "is_active": False},
    ]

def test_proxy_jf_art_unconfigured_400(client):
    import sqlite3
    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET jellyfin_url = '', jellyfin_api_key = '' WHERE id = 1")
    conn.commit()
    conn.close()
    resp = client.get("/proxy-jf-art/Items/abc/Images/Primary")
    assert resp.status_code == 400
