"""The live preview re-renders on every edit, so anything it does per render
is done once per keystroke-debounce."""
import pytest


@pytest.fixture(autouse=True)
def _clear_cache():
    from app import state
    with state._CACHE_LOCK:
        state.cache_storage.clear()
    yield
    with state._CACHE_LOCK:
        state.cache_storage.clear()


THEME = {
    'card_bg': '#181818', 'border': '#2b2b2b', 'text': '#c9c9c9',
    'muted_text': '#8e8e8e', 'accent': '#62a1a4', 'primary': '#8acbd4',
}


def _preview_root():
    """What the preview passes: a message marked preview_mode, so the image
    helpers hand back URLs instead of fetching and attaching."""
    from email.mime.multipart import MIMEMultipart
    root = MIMEMultipart('related')
    root.preview_mode = True
    return root


def test_expanded_collection_items_are_fetched_once_across_renders(monkeypatch):
    """Three renders of the same expanded collection must hit Plex once.

    Before the cache this was one HTTP round trip per expanded collection per
    render, so a newsletter with several expanded collections made several
    sequential calls every time the author typed.
    """
    from app.emails.builders import collections as collections_mod

    calls = []

    def _fake_fetch(collection_key, plex_settings):
        calls.append(collection_key)
        return [{'title': 'An Item', 'key': '1', 'type': 'movie', 'year': 2026}]

    monkeypatch.setattr(collections_mod, "get_collection_items_for_email", _fake_fetch)
    monkeypatch.setattr(collections_mod, "get_settings",
                        lambda **kw: {'id': 1, 'plex_url': 'http://plex', 'plex_token': 'tok'})

    group = [{'key': '99', 'title': 'Faves', 'type': 'movie', 'childCount': 4}]
    expanded = {'0-0-99': {'x': {'title': 'An Item'}}}

    for _ in range(3):
        collections_mod.build_collections_html_with_cids(
            group, _preview_root(), THEME, "", "Faves", expanded, 0)

    assert calls == ['99'], f"fetched {len(calls)} times, expected 1"


def test_a_collection_that_fails_is_not_retried_every_render(monkeypatch):
    """An unresolvable collection would otherwise cost a timeout per render."""
    from app.emails.builders import collections as collections_mod

    calls = []

    def _fake_fetch(collection_key, plex_settings):
        calls.append(collection_key)
        return []

    monkeypatch.setattr(collections_mod, "get_collection_items_for_email", _fake_fetch)
    monkeypatch.setattr(collections_mod, "get_settings",
                        lambda **kw: {'id': 1, 'plex_url': 'http://plex', 'plex_token': 'tok'})

    group = [{'key': '99', 'title': 'Faves', 'type': 'movie', 'childCount': 0}]
    expanded = {'0-0-99': {}}

    for _ in range(3):
        collections_mod.build_collections_html_with_cids(
            group, _preview_root(), THEME, "", "Faves", expanded, 0)

    assert len(calls) == 1


def test_distinct_collections_are_cached_separately(monkeypatch):
    from app.emails.builders import collections as collections_mod

    calls = []
    monkeypatch.setattr(collections_mod, "get_collection_items_for_email",
                        lambda key, s: (calls.append(key), [])[1])
    monkeypatch.setattr(collections_mod, "get_settings",
                        lambda **kw: {'id': 1, 'plex_url': 'http://plex', 'plex_token': 'tok'})

    group = [{'key': 'a', 'title': 'A', 'type': 'movie', 'childCount': 1},
             {'key': 'b', 'title': 'B', 'type': 'movie', 'childCount': 1}]
    expanded = {'0-0-a': {}, '0-1-b': {}}

    collections_mod.build_collections_html_with_cids(group, _preview_root(), THEME, "", "G", expanded, 0)
    collections_mod.build_collections_html_with_cids(group, _preview_root(), THEME, "", "G", expanded, 0)

    assert sorted(calls) == ['a', 'b'], calls


def test_featured_pick_is_resolved_once_across_renders(monkeypatch):
    from app.emails import assemble as assemble_mod

    calls = []

    def _fake_by_key(key):
        calls.append(key)
        return {'title': 'Pinned Film', 'rating_key': key, 'year': 2026}

    monkeypatch.setattr(assemble_mod, "fetch_library_item_by_rating_key", _fake_by_key)

    for _ in range(3):
        pick = assemble_mod._featured_pick_cached("12345", "")
        assert pick['title'] == 'Pinned Film'

    assert calls == ['12345']


def test_unresolvable_featured_pick_is_not_retried(monkeypatch):
    from app.emails import assemble as assemble_mod

    calls = []
    monkeypatch.setattr(assemble_mod, "fetch_library_item_by_rating_key",
                        lambda key: calls.append(key))
    monkeypatch.setattr(assemble_mod, "search_library_items", lambda t, limit=1: [])

    for _ in range(3):
        assert assemble_mod._featured_pick_cached("nope", "") is None

    assert len(calls) == 1


def test_featured_pick_with_nothing_to_resolve_does_no_work(monkeypatch):
    from app.emails import assemble as assemble_mod

    def _boom(*a, **k):
        raise AssertionError("should not have called Plex")

    monkeypatch.setattr(assemble_mod, "fetch_library_item_by_rating_key", _boom)
    monkeypatch.setattr(assemble_mod, "search_library_items", _boom)
    assert assemble_mod._featured_pick_cached("", "") is None


def test_random_pick_is_deliberately_not_cached():
    """It draws a fresh item per render on purpose - the builder says so - and
    that is a live call each time. Documented here so the next person reading
    the preview timings knows it is a choice, not an oversight."""
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "app/emails/assemble.py").read_text(encoding="utf-8")
    block = source.split("item_type == 'random_pick'")[1].split("elif item_type ==")[0]
    assert "fetch_random_library_item(" in block
    assert "_cached" not in block
