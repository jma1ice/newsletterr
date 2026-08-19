"""the DroppedNeedle music card and the yearly wrapped card."""
import json

import pytest

THEME = {
    'background': '#0f0f0f', 'card_bg': '#181818', 'border': '#2b2b2b',
    'muted_text': '#8e8e8e', 'text': '#c9c9c9', 'accent': '#62a1a4',
    'primary': '#8acbd4', 'secondary': '#222222',
}

MBID = "b1a9c0e9-d987-4042-ae91-78d6a3267d69"

PAYLOAD = {
    'has_data': True,
    'year': 2026,
    'display_name': 'Wrapped Name',
    'total_listens_estimated': 420,
    'loved_tracks_count': 7,
    'top_artists': [{'name': f'Artist {i}', 'listen_count': 10 - i, 'artist_mbid': MBID} for i in range(10)],
    'top_tracks': [{'name': f'Track {i}', 'artist_name': 'A', 'listen_count': 10 - i} for i in range(10)],
    'top_albums': [{'name': f'Album {i}', 'artist_name': 'A', 'listen_count': 10 - i, 'mbid': MBID} for i in range(10)],
    'top_genres': [{'genre': f'Genre {i}', 'listen_count': 10 - i} for i in range(10)],
}


# --- Cover Art Archive URLs

def test_cover_url_requires_a_well_formed_mbid():
    from app.clients.coverart import release_group_cover_url

    assert release_group_cover_url(MBID) == (
        f"https://coverartarchive.org/release-group/{MBID}/front-250")
    # anything that is not a UUID cannot reach the URL, which is what keeps a
    # payload value from injecting a path or a host
    for bad in (None, "", "../../etc/passwd", "not-a-mbid", "http://evil/x", MBID + "/x"):
        assert release_group_cover_url(bad) is None


def test_cover_url_size_falls_back_to_a_supported_width():
    from app.clients.coverart import release_group_cover_url
    assert release_group_cover_url(MBID, size=999).endswith("/front-250")
    assert release_group_cover_url(MBID, size=500).endswith("/front-500")


# --- DroppedNeedle display options

def test_dn_options_default_to_the_pre_news44_behavior():
    from app.emails.builders.recommendations import dn_options_from_settings

    options = dn_options_from_settings({})
    assert options['item_count'] == 0        # 0 means no cap, all ten rows
    assert options['cover_art'] is False     # art is opt in
    assert all(options[k] for k in ('show_artists', 'show_tracks', 'show_albums', 'show_genres'))


def test_dn_options_read_the_settings_columns():
    from app.emails.builders.recommendations import dn_options_from_settings

    options = dn_options_from_settings({
        'dn_item_count': '3', 'dn_cover_art': 'enabled', 'dn_show_genres': 'disabled',
    })
    assert options['item_count'] == 3
    assert options['cover_art'] is True
    assert options['show_genres'] is False
    assert options['show_artists'] is True


def test_bad_item_count_does_not_raise():
    from app.emails.builders.recommendations import dn_options_from_settings
    assert dn_options_from_settings({'dn_item_count': 'lots'})['item_count'] == 0
    assert dn_options_from_settings({'dn_item_count': '-4'})['item_count'] == 0


def test_lists_are_capped_and_can_be_hidden():
    from app.emails.builders.recommendations import wrapped_lists

    lists = wrapped_lists(PAYLOAD, {'item_count': 3})
    assert [title for title, _, _, _ in lists] == ['Top Artists', 'Top Tracks', 'Top Albums', 'Top Genres']
    assert all(len(items) == 3 for _, items, _, _ in lists)

    only_albums = wrapped_lists(PAYLOAD, {
        'show_artists': False, 'show_tracks': False, 'show_genres': False, 'show_albums': True})
    assert [title for title, _, _, _ in only_albums] == ['Top Albums']
    assert len(only_albums[0][1]) == 10  # no cap configured, all ten survive


# --- display name resolution

def test_display_name_falls_back_to_the_payload_then_the_id():
    from app.emails.builders.recommendations import wrapped_display_name

    # no Tautulli users and no recipient map: the payload's own name is what
    # makes this readable on Jellyfin and in standalone installs
    assert wrapped_display_name('42', PAYLOAD) == 'Wrapped Name'
    # a payload with no name at all still degrades to something printable
    assert wrapped_display_name('42', {'has_data': True}) == '42'
    # the recipient map wins over the payload
    assert wrapped_display_name('42', PAYLOAD, {'42': 'me@example.com'}) == 'me@example.com'


# --- rendering

def _render_legacy(options=None):
    from app.emails.builders.recommendations import build_droppedneedle_wrapped_html_with_cids
    return build_droppedneedle_wrapped_html_with_cids(
        {'42': PAYLOAD}, None, THEME, None, 'email', None, options=options or {})


def test_legacy_card_renders_every_list_by_default():
    html = _render_legacy()
    for title in ('Top Artists', 'Top Tracks', 'Top Albums', 'Top Genres'):
        assert title in html
    assert 'Album 9' in html          # no cap, so the tenth row is present
    assert 'coverartarchive' not in html   # art stays off until asked for


def test_legacy_card_honors_the_cap_and_the_hidden_lists():
    html = _render_legacy({'item_count': 2, 'show_tracks': False})
    assert 'Top Tracks' not in html
    assert 'Album 1' in html
    assert 'Album 2' not in html


@pytest.mark.parametrize("layout", ['classic', 'editorial', 'digest', 'spotlight'])
def test_layout_card_picks_up_each_chassis(layout):
    """Before NEWS-44 this card bypassed the layout dispatch entirely and looked
    identical everywhere. Each layout must now produce its own markup."""
    from app.emails.builders.layouts import render_dn_wrapped

    html = render_dn_wrapped(layout, {'42': PAYLOAD}, None, THEME, None, 'email', None)
    assert html
    assert 'Wrapped Name' in html


def test_layout_cards_differ_from_each_other():
    from app.emails.builders.layouts import render_dn_wrapped

    rendered = {
        layout: render_dn_wrapped(layout, {'42': PAYLOAD}, None, THEME, None, 'email', None)
        for layout in ('classic', 'editorial', 'digest', 'spotlight')
    }
    assert len(set(rendered.values())) == len(rendered)


def test_users_without_data_are_skipped():
    from app.emails.builders.layouts import render_dn_wrapped

    assert render_dn_wrapped('classic', {'42': {'has_data': False}}, None, THEME) == ""
    assert render_dn_wrapped('classic', {}, None, THEME) == ""


# --- yearly wrapped extras

STATS = [
    {'stat_title': 'Most Watched Movies', 'rows': [
        {'title': 'Movie A', 'total_plays': 5}, {'title': 'Movie B', 'total_plays': 3}]},
    {'stat_title': 'Most Active Platforms', 'rows': [{'platform': 'Chrome', 'total_plays': 9}]},
    {'stat_title': 'Most Concurrent Streams', 'rows': [{'count': 12}]},
]


def test_extras_parse_from_either_storage_shape():
    from app.emails.builders.stats import parse_wrapped_extras

    assert parse_wrapped_extras(json.dumps(['top_platforms', 'bogus'])) == ('top_platforms',)
    assert parse_wrapped_extras('top_platforms,most_concurrent') == ('top_platforms', 'most_concurrent')
    for empty in ('', None, '[]', 'bogus', '{"a": 1}'):
        assert parse_wrapped_extras(empty) == ()


def test_row_label_handles_every_category_shape():
    from app.emails.builders.stats import _row_label

    assert _row_label({'title': 'Movie A'}) == 'Movie A'
    assert _row_label({'user': 'alice'}) == 'alice'
    assert _row_label({'platform': 'Chrome'}) == 'Chrome'
    assert _row_label({'section_name': 'Movies'}) == 'Movies'
    assert _row_label({'count': 12}) == '12'          # most_concurrent has only a count
    assert _row_label({}) == ''


def test_rank_depth_one_returns_the_original_string_untouched():
    """The reason the goldens hold: depth 1 is not a code path change."""
    from app.emails.builders.stats import ranked_value

    assert ranked_value(STATS, 'Most Watched Movies', 'Movie A', 1) == 'Movie A'
    assert ranked_value(STATS, 'Most Watched Movies', 'Movie A', None) == 'Movie A'
    assert ranked_value(STATS, 'Most Watched Movies', 'Movie A', 'junk') == 'Movie A'


def test_deeper_ranks_join_names_as_text_not_markup():
    from app.emails.builders.stats import RANK_SEPARATOR, ranked_value

    value = ranked_value(STATS, 'Most Watched Movies', 'Movie A', 3)
    assert value == f'Movie A{RANK_SEPARATOR}Movie B'
    assert '<' not in value  # stays escapable by every layout


def test_missing_stat_falls_back_rather_than_blanking():
    from app.emails.builders.stats import ranked_value
    assert ranked_value(STATS, 'Most Played Artists', 'Artist A', 3) == 'Artist A'


def test_extra_categories_render_only_when_the_source_answers_them(monkeypatch):
    from app.emails.builders import layouts

    monkeypatch.setattr(layouts, 'email_icon_img', lambda *a, **k: '')

    with_extras = layouts.render_wrapped(
        'classic', STATS, None, THEME,
        extra_stats=json.dumps(['top_platforms', 'top_libraries']), rank_depth=1)
    assert 'Chrome' in with_extras          # platforms are in the data
    assert 'Top Library' not in with_extras  # libraries are not, so no empty cell

    without = layouts.render_wrapped('classic', STATS, None, THEME)
    assert 'Chrome' not in without           # extras are opt in
