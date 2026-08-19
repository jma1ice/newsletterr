"""recommendations, collections and graphs under the variant layouts."""
from email.mime.multipart import MIMEMultipart

import pytest

from app.emails.builders import layouts

LAYOUTS = ('classic', 'editorial', 'digest', 'spotlight')

THEME = {
    'background': '#0f0f0f', 'card_bg': '#181818', 'border': '#2b2b2b',
    'muted_text': '#8e8e8e', 'text': '#c9c9c9', 'accent': '#62a1a4',
    'primary': '#8acbd4', 'secondary': '#222222',
}

RECS = {
    '42': {
        'movie_posters': [
            {'title': 'AvailableMovie', 'year': 2026, 'url': '', 'overview': 'A film.', 'vote': 8.1},
        ],
        'movie_posters_unavailable': [
            {'title': 'MissingMovie', 'year': 2025, 'url': '', 'overview': 'Not here.', 'vote': 7.0},
        ],
        'show_posters': [
            {'title': 'AvailableShow', 'year': 2026, 'url': '', 'overview': 'A show.', 'vote': 9.0},
        ],
    }
}

COLLECTIONS = [
    {'title': 'Staff Picks', 'key': '/library/collections/1', 'thumb': '', 'childCount': 4},
    {'title': 'Cult Classics', 'key': '/library/collections/2', 'thumb': '', 'childCount': 7},
]


def _theme_for(layout):
    from app.emails import density
    return density.stamp(layouts.apply_theme(layout, dict(THEME)), layout, '')


# --- recommendations

@pytest.mark.parametrize("layout", LAYOUTS)
def test_recommendations_render_under_every_layout(layout):
    html = layouts.render_recommendations(
        layout, RECS, MIMEMultipart('related'), _theme_for(layout), {'42': 'ada@example.com'})
    assert html
    assert 'AvailableMovie' in html
    assert 'AvailableShow' in html


def test_recommendation_layouts_differ_from_each_other():
    rendered = {
        layout: layouts.render_recommendations(
            layout, RECS, MIMEMultipart('related'), _theme_for(layout), {'42': 'ada@example.com'})
        for layout in LAYOUTS
    }
    assert len(set(rendered.values())) == len(rendered)


def test_unavailable_titles_keep_their_meaning_in_every_layout():
    """The legacy render greys the poster out. The row layouts have no poster to
    grey, so the distinction has to survive some other way rather than being
    quietly dropped."""
    for layout in LAYOUTS:
        html = layouts.render_recommendations(
            layout, RECS, MIMEMultipart('related'), _theme_for(layout), {'42': 'ada@example.com'})
        assert 'MissingMovie' in html
        assert 'not on the server' in html


def test_recommendations_respect_the_user_filter():
    html = layouts.render_recommendations(
        'classic', RECS, MIMEMultipart('related'), _theme_for('classic'), {'99': 'other@example.com'})
    assert html == ""


def test_empty_recommendations_render_nothing():
    for layout in LAYOUTS:
        assert layouts.render_recommendations(layout, {}, MIMEMultipart('related'), _theme_for(layout)) == ""
        assert layouts.render_recommendations(
            layout, {'42': {}}, MIMEMultipart('related'), _theme_for(layout)) == ""


# --- collections

@pytest.mark.parametrize("layout", LAYOUTS)
def test_collections_render_under_every_layout(layout):
    html = layouts.render_collections(
        layout, COLLECTIONS, MIMEMultipart('related'), _theme_for(layout))
    assert 'Staff Picks' in html and 'Cult Classics' in html


def test_collection_layouts_differ_from_each_other():
    rendered = {
        layout: layouts.render_collections(
            layout, COLLECTIONS, MIMEMultipart('related'), _theme_for(layout))
        for layout in LAYOUTS
    }
    assert len(set(rendered.values())) == len(rendered)


def test_collections_use_the_custom_title():
    html = layouts.render_collections(
        'classic', COLLECTIONS, MIMEMultipart('related'), _theme_for('classic'),
        custom_title="Our Shelves")
    assert 'Our Shelves' in html


def test_empty_collections_render_the_marked_empty_state():
    """It has to stay an empty state, not vanish, or NEWS-65 would count a
    missing section as content by omission."""
    from app.emails.builders.card_grid import EMPTY_STATE_MARKER

    html = layouts.render_collections('classic', [], MIMEMultipart('related'), _theme_for('classic'))
    assert EMPTY_STATE_MARKER in html


def test_the_expansion_resolver_is_shared_with_the_legacy_builder():
    """Both paths must agree about what a group contains, or the item count
    would depend on the email layout."""
    from app.emails.builders.collections import resolve_collection_items

    items = resolve_collection_items(COLLECTIONS, {}, 0)
    assert [i['title'] for i in items] == ['Staff Picks', 'Cult Classics']
    assert all(i['is_individual_item'] is False for i in items)


# --- graphs

GRAPH_ITEM = {
    'type': 'graph', 'name': 'Plays by Day',
    # a 1x1 png, enough to exercise the attach path
    'chartImage': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
}


@pytest.mark.parametrize("layout", LAYOUTS)
def test_graphs_render_under_every_layout(layout):
    html = layouts.render_graph(layout, GRAPH_ITEM, MIMEMultipart('related'), _theme_for(layout))
    assert html
    assert 'Plays by Day' in html


def test_graph_layouts_differ_from_each_other():
    rendered = {
        layout: layouts.render_graph(layout, GRAPH_ITEM, MIMEMultipart('related'), _theme_for(layout))
        for layout in LAYOUTS
    }
    assert len(set(rendered.values())) == len(rendered)


def test_an_uncaptured_graph_still_shows_its_placeholder():
    """The legacy path renders a dashed "chart unavailable" box rather than
    nothing, so a failed capture is visible instead of silently missing. The
    layout wrapping must not turn that into a vanishing section."""
    for layout in LAYOUTS:
        html = layouts.render_graph(
            layout, {'type': 'graph', 'name': 'Uncaptured', 'chartImage': ''},
            MIMEMultipart('related'), _theme_for(layout))
        assert html
        assert 'Uncaptured' in html


# --- nothing is left falling through

def test_every_data_section_is_layout_aware():
    """The point of the issue: no data-backed item type still renders legacy
    inside a variant layout. The author-content primitives are excluded on
    purpose, since they have no section chrome to restyle."""
    import re
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    source = (repo_root / 'app' / 'emails' / 'assemble.py').read_text().split('\n')
    starts = [(i, l) for i, l in enumerate(source) if re.search(r"item_type (==|in) ", l)]
    chrome = {'textblock', 'titleblock', 'headerblock', 'separator', 'image', 'gif', 'emoji'}

    for idx, (i, line) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(source)
        body = '\n'.join(source[i:end])
        names = set(re.findall(r"'([a-z_ ]+)'", line))
        if names & chrome:
            continue
        assert 'use_layout' in body, f"{names} still renders legacy inside a variant layout"
