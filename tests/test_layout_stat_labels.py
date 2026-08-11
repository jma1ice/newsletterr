"""Aggregate stat rows must be labelled by their key, not by the last-watched item.

Tautulli ships the last-played item on every top_users/top_libraries/top_platforms
row (title, year, rating_key, artwork). The legacy table pins the label column per
stat; the classic/editorial/digest/spotlight layouts have to do the same or a user
gets named after whatever show they watched last.
"""
import re
from email.mime.multipart import MIMEMultipart

import pytest

from app.emails.builders import layouts as layouts_mod

LAYOUTS = ("classic", "editorial", "digest", "spotlight")

THEME = {
    'background': '#333333', 'text': '#62a1a4', 'primary': '#8acbd4',
    'secondary': '#222222', 'accent': '#62a1a4', 'card_bg': '#2d2d2d',
    'border': '#404040', 'muted_text': '#cccccc', 'email_theme': 'newsletterr_blue',
}

# every aggregate row also carries the last-watched item's fields
USER_STAT = {
    'stat_id': 'top_users', 'stat_title': 'Most Active Users',
    'rows': [{
        'user': 'alice', 'friendly_name': 'alice', 'user_thumb': 'http://plex.tv/alice.png',
        'total_plays': 20, 'total_duration': 36000,
        'title': 'Severance', 'year': '2022', 'plex_url': 'https://app.plex.tv/last-watched',
    }],
}
LIBRARY_STAT = {
    'stat_id': 'top_libraries', 'stat_title': 'Most Active Libraries',
    'rows': [{
        'section_name': 'TV Shows', 'total_plays': 12, 'total_duration': 7200,
        'title': 'Severance', 'year': '2022', 'plex_url': 'https://app.plex.tv/last-watched',
    }],
}
PLATFORM_STAT = {
    'stat_id': 'top_platforms', 'stat_title': 'Most Active Platforms',
    'rows': [{
        'platform': 'Roku', 'total_plays': 12, 'total_duration': 7200,
        'title': 'Severance', 'year': '2022', 'plex_url': 'https://app.plex.tv/last-watched',
    }],
}
MOVIE_STAT = {
    'stat_id': 'top_movies', 'stat_title': 'Most Watched Movies',
    'rows': [{'title': 'Dune', 'year': '2021', 'total_plays': 42,
              'plex_url': 'https://app.plex.tv/dune'}],
}

AGGREGATES = [
    pytest.param(USER_STAT, 'alice', id='users'),
    pytest.param(LIBRARY_STAT, 'TV Shows', id='libraries'),
    pytest.param(PLATFORM_STAT, 'Roku', id='platforms'),
]


@pytest.fixture(autouse=True)
def _stub_image_fetches(monkeypatch):
    monkeypatch.setattr(layouts_mod, "fetch_and_attach_small_thumbnail", lambda *a, **k: "cid:thumb")
    monkeypatch.setattr(layouts_mod, "fetch_and_attach_blurred_image", lambda *a, **k: "cid:bg")
    monkeypatch.setattr(layouts_mod, "email_icon_img", lambda *a, **k: '<img src="cid:icon">')


def render(layout, stat):
    return layouts_mod.render_stats(layout, stat, MIMEMultipart(), THEME, "http://base", "30")


def text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("stat,label", AGGREGATES)
def test_aggregate_rows_are_named_by_their_key(layout, stat, label):
    body = text(render(layout, stat))
    assert label in body
    assert 'Severance' not in body


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("stat,label", AGGREGATES)
def test_aggregate_rows_hide_the_last_watched_year(layout, stat, label):
    assert '2022' not in text(render(layout, stat))


@pytest.mark.parametrize("layout", LAYOUTS)
@pytest.mark.parametrize("stat,label", AGGREGATES)
def test_aggregate_rows_do_not_link_to_the_last_watched_item(layout, stat, label):
    assert 'last-watched' not in render(layout, stat)


@pytest.mark.parametrize("layout", LAYOUTS)
def test_item_stats_still_use_the_title_year_and_link(layout):
    html = render(layout, MOVIE_STAT)
    assert 'Dune' in text(html)
    assert 'https://app.plex.tv/dune' in html
    assert '2021' in text(html)
