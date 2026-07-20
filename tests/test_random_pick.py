# Random Pick snap-in (NEWS-17): client-level tests for
# fetch_random_library_item, with Plex HTTP stubbed and the RNG pinned.

import pytest

from app.clients import plex

class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload

PROBE_PAYLOAD = {"MediaContainer": {"totalSize": 10}}

ITEM_PAYLOAD = {
    "MediaContainer": {
        "librarySectionTitle": "Movies",
        "Metadata": [
            {
                "ratingKey": "42",
                "title": "Pinned Movie",
                "type": "movie",
                "year": 2001,
                "thumb": "/library/metadata/42/thumb",
                "art": "/library/metadata/42/art",
                "summary": "A fixed random pick.",
                "contentRating": "PG-13",
                "duration": 5400000,
                "Genre": [{"tag": "Drama"}, {"tag": "Crime"}],
            }
        ],
    }
}

@pytest.fixture()
def plex_stub(monkeypatch):
    calls = []

    def _fake_safe_get(url, **kwargs):
        calls.append(url)
        if "X-Plex-Container-Size=0" in url:
            return _FakeResponse(PROBE_PAYLOAD)
        return _FakeResponse(ITEM_PAYLOAD)

    monkeypatch.setattr(plex, "get_settings", lambda **k: {"id": 1, "plex_url": "http://plex.local", "plex_token": "enc-token", "plex_web_url": None})
    monkeypatch.setattr(plex, "decrypt", lambda v: "tok")
    monkeypatch.setattr(plex, "get_plex_machine_id", lambda: "machine1")
    monkeypatch.setattr(plex, "safe_get", _fake_safe_get)
    monkeypatch.setattr(plex.random, "randrange", lambda n: 3)
    return calls

def test_fetch_random_library_item_normalizes_item(plex_stub):
    pick = plex.fetch_random_library_item("5")
    assert pick["title"] == "Pinned Movie"
    assert pick["rating_key"] == "42"
    assert pick["year"] == "2001"
    assert pick["media_type"] == "movie"
    assert pick["genres"] == ["Drama", "Crime"]
    assert pick["library_name"] == "Movies"
    assert "machine1" in pick["plex_url"]
    assert "/library/metadata/42" in pick["plex_url"]

def test_fetch_random_library_item_uses_random_offset(plex_stub):
    plex.fetch_random_library_item("5")
    probe, fetch = plex_stub
    assert "X-Plex-Container-Size=0" in probe
    assert "X-Plex-Container-Start=3" in fetch
    assert "X-Plex-Container-Size=1" in fetch

def test_fetch_random_library_item_passes_genre_filter(plex_stub):
    plex.fetch_random_library_item("5", genre="88")
    probe, fetch = plex_stub
    assert "genre=88" in probe
    assert "genre=88" in fetch

def test_fetch_random_library_item_empty_section_returns_none(monkeypatch):
    monkeypatch.setattr(plex, "get_settings", lambda **k: {"id": 1, "plex_url": "http://plex.local", "plex_token": "enc-token", "plex_web_url": None})
    monkeypatch.setattr(plex, "decrypt", lambda v: "tok")
    monkeypatch.setattr(plex, "get_plex_machine_id", lambda: "machine1")
    monkeypatch.setattr(plex, "safe_get", lambda url, **k: _FakeResponse({"MediaContainer": {"totalSize": 0}}))
    assert plex.fetch_random_library_item("5") is None

def test_fetch_random_library_item_unconfigured_returns_none(monkeypatch):
    monkeypatch.setattr(plex, "get_settings", lambda **k: {"id": 1, "plex_url": "", "plex_token": ""})
    assert plex.fetch_random_library_item("5") is None
