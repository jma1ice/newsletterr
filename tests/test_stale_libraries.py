"""Libraries Tautulli still lists after they were deleted from Plex."""

import pytest

from app.clients import plex

LIBRARIES = [
    {"section_id": "1", "section_type": "movie", "section_name": "Movies"},
    {"section_id": "2", "section_type": "show", "section_name": "TV Shows"},
    {"section_id": "20", "section_type": "movie", "section_name": "Deleted Movies"},
    {"section_id": "5", "section_type": "artist", "section_name": "Deleted Music"},
]

# Only sections 1 and 2 still exist on the Plex server.
LIVE_SECTIONS = [
    {"section_id": "1", "title": "Movies", "type": "movie", "genres": []},
    {"section_id": "2", "title": "TV Shows", "type": "show", "genres": []},
]

class _Response:
    def __init__(self, status_code):
        self.status_code = status_code

class _HTTPError(Exception):
    def __init__(self, status_code):
        super().__init__(f"{status_code} Client Error")
        self.response = _Response(status_code)

@pytest.fixture()
def wired(monkeypatch):
    """The recently-added pull with Tautulli and Plex both stubbed."""
    plex.reset_plex_health()
    calls = []

    monkeypatch.setattr(plex, "get_settings", lambda **kw: {"id": 1, "plex_web_url": ""})
    monkeypatch.setattr(plex, "get_plex_machine_id", lambda: "machine-id")
    monkeypatch.setattr(plex, "run_tautulli_command", lambda *a, **k: (LIBRARIES, None))
    monkeypatch.setattr(plex, "fetch_library_sections_with_genres", lambda **kw: LIVE_SECTIONS)

    def _record(name):
        def _fetch(section_id, *a, **k):
            calls.append((name, str(section_id)))
            return []
        return _fetch

    monkeypatch.setattr(plex, "fetch_movies_from_plex_sdk", _record("movie"))
    monkeypatch.setattr(plex, "fetch_tv_shows_from_plex_sdk", _record("show"))
    monkeypatch.setattr(plex, "fetch_albums_from_plex_sdk", _record("artist"))
    return calls

def test_stale_libraries_are_never_fetched(wired):
    plex.fetch_recently_added_using_plex_sdk("http://tautulli", "key", 10)
    assert wired == [("movie", "1"), ("show", "2")]

def test_stale_libraries_are_reported_with_their_names(wired):
    plex.fetch_recently_added_using_plex_sdk("http://tautulli", "key", 10)
    missing = plex.plex_missing_libraries()
    assert [(m["section_id"], m["name"]) for m in missing] == [
        ("20", "Deleted Movies"),
        ("5", "Deleted Music"),
    ]

def test_stale_libraries_do_not_mark_plex_unavailable(wired):
    plex.fetch_recently_added_using_plex_sdk("http://tautulli", "key", 10)
    # The banner this drives says previews and images may be missing. A library
    # that no longer exists says nothing about whether Plex is reachable.
    assert plex.plex_call_failed() is False

def test_unknown_section_list_falls_back_to_attempting_everything(wired, monkeypatch):
    # If the /library/sections call fails it returns an empty list. Filtering on
    # that would silently drop every library and ship an empty newsletter, so
    # nothing is filtered and the per-section error handling runs as before.
    monkeypatch.setattr(plex, "fetch_library_sections_with_genres", lambda **kw: [])
    plex.fetch_recently_added_using_plex_sdk("http://tautulli", "key", 10)
    assert wired == [("movie", "1"), ("show", "2"), ("movie", "20"), ("artist", "5")]

def test_non_plex_library_types_are_not_filtered(monkeypatch):
    # Photo libraries and the like never reach Plex here, they go through the
    # Tautulli fallback, so a section list that omits them must not skip them.
    plex.reset_plex_health()
    monkeypatch.setattr(plex, "get_settings", lambda **kw: {"id": 1, "plex_web_url": ""})
    monkeypatch.setattr(plex, "get_plex_machine_id", lambda: "machine-id")
    monkeypatch.setattr(plex, "fetch_library_sections_with_genres", lambda **kw: LIVE_SECTIONS)

    photos = {"section_id": "9", "section_type": "photo", "section_name": "Photos"}
    fallback = []

    def _tautulli(base, key, command, *a, **k):
        if command == "get_library_names":
            return ([photos], None)
        fallback.append(command)
        return ({"recently_added": []}, None)

    monkeypatch.setattr(plex, "run_tautulli_command", _tautulli)
    plex.fetch_recently_added_using_plex_sdk("http://tautulli", "key", 10)

    assert fallback == ["get_recently_added"]
    assert plex.plex_missing_libraries() == []

def test_section_404_during_fetch_is_recorded_not_a_plex_failure(monkeypatch):
    # A library deleted between the sections call and the item fetch: the
    # fetcher returns None so the caller records it, rather than tripping the
    # health flag the way any other exception does.
    plex.reset_plex_health()
    monkeypatch.setattr(plex, "get_settings", lambda **kw: {"id": 1, "plex_web_url": ""})
    monkeypatch.setattr(plex, "get_plex_machine_id", lambda: "machine-id")
    monkeypatch.setattr(plex, "run_tautulli_command", lambda *a, **k: (LIBRARIES[:1], None))
    monkeypatch.setattr(plex, "fetch_library_sections_with_genres", lambda **kw: LIVE_SECTIONS)
    monkeypatch.setattr(plex, "fetch_movies_from_plex_sdk", lambda *a, **k: None)

    plex.fetch_recently_added_using_plex_sdk("http://tautulli", "key", 10)

    assert [m["section_id"] for m in plex.plex_missing_libraries()] == ["1"]
    assert plex.plex_call_failed() is False

def test_section_is_gone_only_matches_404():
    assert plex.section_is_gone(_HTTPError(404)) is True
    assert plex.section_is_gone(_HTTPError(503)) is False
    assert plex.section_is_gone(Exception("connection refused")) is False

def test_reset_clears_reported_libraries():
    plex.note_missing_library("42", "Gone", "movie")
    assert plex.plex_missing_libraries()
    plex.reset_plex_health()
    assert plex.plex_missing_libraries() == []

def test_repeated_reports_are_deduped():
    plex.reset_plex_health()
    plex.note_missing_library("42", "Gone", "movie")
    plex.note_missing_library("42", "Gone", "movie")
    assert len(plex.plex_missing_libraries()) == 1
