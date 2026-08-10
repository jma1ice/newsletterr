"""Featured Pick snap-in."""
from email.mime.multipart import MIMEMultipart

import pytest

from app.emails.builders import layouts as layouts_mod
from app.emails.builders.random_pick import build_random_pick_html

LAYOUTS = ("classic", "editorial", "digest", "spotlight")

THEME = {
    'background': '#333333', 'text': '#62a1a4', 'primary': '#8acbd4',
    'secondary': '#222222', 'accent': '#62a1a4', 'card_bg': '#2d2d2d',
    'border': '#404040', 'muted_text': '#cccccc', 'email_theme': 'newsletterr_blue',
}
PICK = {
    'title': 'The Grand Voyage', 'rating_key': '42', 'year': '2024',
    'thumb': '/library/metadata/42/thumb', 'art': '', 'summary': 'A crew sails on.',
    'tagline': '', 'duration': '6900000', 'content_rating': 'PG-13',
    'genres': ['Adventure'], 'media_type': 'movie', 'type': 'movie',
    'plex_url': 'https://app.plex.tv/42', 'rating': '8.4',
}

PLEX_METADATA = {
    'MediaContainer': {
        'librarySectionTitle': 'Movies',
        'Metadata': [{
            'ratingKey': 42, 'title': 'The Grand Voyage', 'year': 2024, 'type': 'movie',
            'thumb': '/library/metadata/42/thumb', 'art': '/library/metadata/42/art',
            'summary': 'A crew sails on.', 'contentRating': 'PG-13', 'duration': 6900000,
            'Genre': [{'tag': 'Adventure'}],
        }],
    }
}
PLEX_SEARCH = {
    'MediaContainer': {
        'librarySectionTitle': 'Movies',
        'Metadata': [
            {'ratingKey': 42, 'title': 'The Grand Voyage', 'year': 2024, 'type': 'movie', 'thumb': '/t/42'},
            {'ratingKey': 43, 'title': 'The Grand Voyage II', 'year': 2025, 'type': 'movie', 'thumb': '/t/43'},
            {'ratingKey': 44, 'title': 'Some Track', 'type': 'track', 'thumb': ''},
        ],
    }
}


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture()
def plex_stub(monkeypatch):
    """A configured Plex whose responses are ours, with the calls recorded."""
    import app.clients.plex as plex
    calls = []

    monkeypatch.setattr(plex, "_plex_connection", lambda: ("http://plex.local", "tok", "https://app.plex.tv/desktop"))
    monkeypatch.setattr(plex, "get_plex_machine_id", lambda: "machine-1")

    def fake_get(url, **kwargs):
        calls.append(url)
        return _Resp(PLEX_SEARCH if '/search' in url or 'title=' in url else PLEX_METADATA)

    monkeypatch.setattr(plex, "safe_get", fake_get)
    return calls


# --- fetching by rating key

def test_item_resolves_by_rating_key(plex_stub):
    from app.clients.plex import fetch_library_item_by_rating_key
    item = fetch_library_item_by_rating_key('42')
    assert item['title'] == 'The Grand Voyage'
    assert item['rating_key'] == '42'
    assert item['library_name'] == 'Movies'
    assert item['plex_url']  # deep link built from the machine id
    assert '42' in plex_stub[0]


def test_a_deleted_item_returns_none_rather_than_raising(monkeypatch):
    import app.clients.plex as plex
    monkeypatch.setattr(plex, "_plex_connection", lambda: ("http://plex.local", "tok", ""))
    monkeypatch.setattr(plex, "get_plex_machine_id", lambda: "m")
    monkeypatch.setattr(plex, "safe_get", lambda url, **k: _Resp({'MediaContainer': {'Metadata': []}}))
    assert plex.fetch_library_item_by_rating_key('999') is None


def test_blank_or_missing_key_never_calls_plex(monkeypatch):
    import app.clients.plex as plex
    called = []
    monkeypatch.setattr(plex, "safe_get", lambda *a, **k: called.append(1))
    assert plex.fetch_library_item_by_rating_key('') is None
    assert plex.fetch_library_item_by_rating_key(None) is None
    assert not called


def test_unreachable_plex_returns_none(monkeypatch):
    import app.clients.plex as plex
    monkeypatch.setattr(plex, "_plex_connection", lambda: ("http://plex.local", "tok", ""))
    monkeypatch.setattr(plex, "get_plex_machine_id", lambda: "m")

    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr(plex, "safe_get", boom)
    assert plex.fetch_library_item_by_rating_key('42') is None


def test_unconfigured_plex_returns_none(monkeypatch):
    import app.clients.plex as plex
    monkeypatch.setattr(plex, "_plex_connection", lambda: None)
    assert plex.fetch_library_item_by_rating_key('42') is None
    assert plex.search_library_items('anything') == []


# --- search

def test_search_returns_light_rows_and_drops_unfeaturable_types(plex_stub):
    from app.clients.plex import search_library_items
    results = search_library_items('voyage', section_id='1')
    assert [r['rating_key'] for r in results] == ['42', '43']  # the track is dropped
    assert results[0]['title'] == 'The Grand Voyage'
    # light rows only: no summary/artwork payload to store in a template
    assert set(results[0]) == {'rating_key', 'title', 'year', 'type', 'thumb', 'library_name'}


def test_search_scopes_to_a_section_when_given(plex_stub):
    from app.clients.plex import search_library_items
    search_library_items('voyage', section_id='7')
    assert '/library/sections/7/all' in plex_stub[-1]


def test_search_without_a_section_goes_server_wide(plex_stub):
    from app.clients.plex import search_library_items
    search_library_items('voyage')
    assert '/search?query=' in plex_stub[-1]


def test_search_respects_the_limit(plex_stub):
    from app.clients.plex import search_library_items
    assert len(search_library_items('voyage', limit=1)) == 1


@pytest.mark.parametrize("query", ["", "   ", None])
def test_empty_search_never_calls_plex(monkeypatch, query):
    import app.clients.plex as plex
    called = []
    monkeypatch.setattr(plex, "safe_get", lambda *a, **k: called.append(1))
    assert plex.search_library_items(query) == []
    assert not called


# --- rendering

@pytest.mark.parametrize("layout", LAYOUTS)
def test_card_renders_under_the_featured_pick_heading(layout, monkeypatch):
    monkeypatch.setattr(layouts_mod, "attach_random_pick_poster", lambda *a, **k: "cid:poster")
    theme = layouts_mod.apply_theme(layout, THEME)
    html = layouts_mod.render_random_pick(layout, PICK, MIMEMultipart(), theme, "http://b", heading="Featured Pick")
    assert "Featured Pick" in html and "The Grand Voyage" in html
    assert "Random Pick" not in html


def test_legacy_card_takes_the_heading_too(monkeypatch):
    import app.emails.builders.random_pick as rp
    monkeypatch.setattr(rp, "fetch_and_attach_image", lambda *a, **k: "cid:poster")
    html = build_random_pick_html(PICK, MIMEMultipart(), THEME, "http://b", heading="Featured Pick")
    assert "Featured Pick" in html and "Random Pick" not in html


def test_heading_defaults_to_random_pick_when_not_given():
    """The override must not disturb the existing snap-in."""
    html = build_random_pick_html(PICK, MIMEMultipart(), THEME, "http://b", library_label="Movies")
    assert "Random Pick - Movies" in html


@pytest.mark.parametrize("layout", LAYOUTS)
def test_a_missing_item_renders_the_empty_state(layout):
    theme = layouts_mod.apply_theme(layout, THEME)
    html = layouts_mod.render_random_pick(layout, None, MIMEMultipart(), theme, "http://b", heading="Featured Pick")
    assert "Featured Pick" in html
    assert "The Grand Voyage" not in html


# --- token + endpoint

def test_token_carries_the_title():
    from app.emails.snapin_tokens import synthesize_snapin_item
    item = synthesize_snapin_item('featured_pick', ['The Grand Voyage'], [])
    assert item == {'id': 'featured-pick-The Grand Voyage', 'type': 'featured_pick',
                    'title': 'The Grand Voyage'}
    assert synthesize_snapin_item('featured_pick', [], []) is None


def test_search_endpoint_returns_results(client, seeded_settings, monkeypatch):
    import app.blueprints.stats as stats_bp
    monkeypatch.setattr(stats_bp, "search_library_items",
                        lambda q, section_id=None, limit=20: [{'rating_key': '42', 'title': q}])
    body = client.get("/featured_pick_search?q=voyage&section_id=1").get_json()
    assert body["status"] == "success"
    assert body["results"][0]["rating_key"] == "42"


def test_search_endpoint_short_circuits_an_empty_query(client, seeded_settings, monkeypatch):
    import app.blueprints.stats as stats_bp
    called = []
    monkeypatch.setattr(stats_bp, "search_library_items", lambda *a, **k: called.append(1) or [])
    assert client.get("/featured_pick_search?q=").get_json()["results"] == []
    assert not called


def test_search_endpoint_requires_auth(anon_client):
    assert anon_client.get("/featured_pick_search?q=x").status_code in (302, 401, 403)
