# Most Watched snap-in (NEWS-17): fetcher and builder-selection tests with
# Tautulli stubbed out.

from email.mime.multipart import MIMEMultipart

import pytest

from app.emails import fetchers
from app.emails.fetchers import _aggregate_history_rows
from app.emails.builders.most_watched import metric_text, most_watched_items, most_watched_heading, play_count_text

MEDIA_INFO_ROWS = [
    {"title": "Big Hit", "rating_key": 7, "year": 2020, "thumb": "/library/metadata/7/thumb", "play_count": 57, "media_type": "movie", "last_played": 1750000000},
    {"title": "Second Best", "rating_key": 8, "year": 2019, "thumb": "/library/metadata/8/thumb", "play_count": 31, "media_type": "movie", "last_played": 1750000001},
    {"title": "Never Played", "rating_key": 9, "year": 2021, "thumb": "", "play_count": None, "media_type": "movie", "last_played": None},
]

def _fake_run(base, key, command, section_id, error, *a, **k):
    if command == 'get_library_names':
        return [
            {'section_id': 1, 'section_name': 'Movies', 'section_type': 'movie'},
            {'section_id': 2, 'section_name': 'Empty Lib', 'section_type': 'show'},
        ], None
    if command == 'get_library_media_info':
        if section_id == 1:
            return {'data': MEDIA_INFO_ROWS}, None
        return {'data': []}, None
    raise AssertionError(f"unexpected command {command}")

def test_fetch_most_watched_data_normalizes_and_filters(monkeypatch):
    monkeypatch.setattr(fetchers, 'run_tautulli_command', _fake_run)
    monkeypatch.setattr(fetchers, 'get_settings', lambda **kw: {'plex_url': 'http://plex.local', 'plex_token': 'tok', 'plex_web_url': None})
    monkeypatch.setattr(fetchers, 'get_plex_machine_id', lambda: 'm1')

    data = fetchers.fetch_most_watched_data('http://tt.local', 'enc-key')
    # empty library dropped, never-played row filtered out
    assert len(data) == 1
    items = data[0]['most_watched']
    assert [i['title'] for i in items] == ['Big Hit', 'Second Best']
    assert items[0]['play_count'] == 57
    assert items[0]['library_name'] == 'Movies'
    assert 'm1' in items[0]['plex_url']
    assert '/library/metadata/7' in items[0]['plex_url']

def test_fetch_most_watched_data_without_plex_leaves_links_empty(monkeypatch):
    monkeypatch.setattr(fetchers, 'run_tautulli_command', _fake_run)
    monkeypatch.setattr(fetchers, 'get_settings', lambda **kw: {'plex_url': '', 'plex_token': ''})

    data = fetchers.fetch_most_watched_data('http://tt.local', 'enc-key')
    assert data[0]['most_watched'][0]['plex_url'] == ''

def _sample_data():
    return [
        {'most_watched': [
            {'title': 'Big Hit', 'play_count': 57, 'library_name': 'Movies'},
            {'title': 'Second Best', 'play_count': 31, 'library_name': 'Movies'},
        ]},
        {'most_watched': [
            {'title': 'Top Show', 'play_count': 90, 'library_name': 'TV Shows'},
        ]},
    ]

def test_most_watched_items_filters_by_library():
    items = most_watched_items(_sample_data(), 'TV Shows')
    assert [i['title'] for i in items] == ['Top Show']

def test_most_watched_items_caps_at_default_ten():
    data = [{'most_watched': [{'title': f'T{i}', 'play_count': 100 - i, 'library_name': 'Movies'} for i in range(15)]}]
    assert len(most_watched_items(data, 'Movies')) == 10
    assert len(most_watched_items(data, 'Movies', item_cap=3)) == 3

HISTORY_ROWS = [
    # three plays of the same show (two episodes), one movie play, two track plays of one album
    {"media_type": "episode", "rating_key": 101, "grandparent_rating_key": 100, "grandparent_title": "Binge Show", "title": "Ep 1", "year": 2024, "date": 1750000000},
    {"media_type": "episode", "rating_key": 102, "grandparent_rating_key": 100, "grandparent_title": "Binge Show", "title": "Ep 2", "year": 2024, "date": 1750000100},
    {"media_type": "episode", "rating_key": 101, "grandparent_rating_key": 100, "grandparent_title": "Binge Show", "title": "Ep 1", "year": 2024, "date": 1750000200},
    {"media_type": "movie", "rating_key": 200, "title": "One Off", "year": 2020, "thumb": "/library/metadata/200/thumb", "date": 1750000300},
    {"media_type": "track", "rating_key": 301, "parent_rating_key": 300, "parent_title": "Album X", "grandparent_title": "Artist Y", "title": "Song A", "year": 2021, "date": 1750000400},
    {"media_type": "track", "rating_key": 302, "parent_rating_key": 300, "parent_title": "Album X", "grandparent_title": "Artist Y", "title": "Song B", "year": 2021, "date": 1750000500},
]

def test_aggregate_history_rolls_up_episodes_tracks_and_counts():
    aggregates = {a['title']: a for a in _aggregate_history_rows(HISTORY_ROWS)}
    assert aggregates['Binge Show']['play_count'] == 3
    assert aggregates['Binge Show']['rating_key'] == '100'
    assert aggregates['Binge Show']['media_type'] == 'show'
    # show poster comes from the show's own rating key, never an episode still
    assert aggregates['Binge Show']['thumb'] == '/library/metadata/100/thumb'
    assert aggregates['One Off']['play_count'] == 1
    assert aggregates['One Off']['thumb'] == '/library/metadata/200/thumb'
    assert aggregates['Album X']['play_count'] == 2
    assert aggregates['Album X']['media_type'] == 'album'

def test_fetch_most_watched_data_recent_scope_uses_history(monkeypatch):
    calls = []

    def _fake_run_windowed(base, key, command, section_id, error, *a, **k):
        calls.append((command, section_id, a[0] if a else None))
        if command == 'get_library_names':
            return [{'section_id': 1, 'section_name': 'TV Shows', 'section_type': 'show'}], None
        if command == 'get_history':
            return {'data': HISTORY_ROWS[:3]}, None
        raise AssertionError(f"unexpected command {command}")

    monkeypatch.setattr(fetchers, 'run_tautulli_command', _fake_run_windowed)
    monkeypatch.setattr(fetchers, 'get_settings', lambda **kw: {'plex_url': 'http://plex.local', 'plex_token': 'tok', 'plex_web_url': None})
    monkeypatch.setattr(fetchers, 'get_plex_machine_id', lambda: 'm1')

    data = fetchers.fetch_most_watched_data('http://tt.local', 'enc-key', days=30)
    history_calls = [c for c in calls if c[0] == 'get_history']
    assert len(history_calls) == 1
    # the after date is a YYYY-MM-DD string, not a row count
    assert '-' in str(history_calls[0][2])

    items = data[0]['most_watched']
    assert len(items) == 1
    assert items[0]['title'] == 'Binge Show'
    assert items[0]['play_count'] == 3
    assert items[0]['library_name'] == 'TV Shows'
    assert 'm1' in items[0]['plex_url']

def test_heading_and_play_count_text():
    assert most_watched_heading('Movies') == 'Most Watched - Movies'
    assert most_watched_heading() == 'Most Watched'
    assert play_count_text({'play_count': 1}) == '1 play'
    assert play_count_text({'play_count': 57}) == '57 plays'

DURATION_HISTORY_ROWS = [
    {"media_type": "movie", "rating_key": 400, "title": "Long Haul", "year": 2022, "date": 1750000000, "duration": 7200},
    {"media_type": "movie", "rating_key": 401, "title": "Quick Watch", "year": 2022, "date": 1750000100, "duration": 600},
    {"media_type": "movie", "rating_key": 401, "title": "Quick Watch", "year": 2022, "date": 1750000200, "duration": 600},
    {"media_type": "movie", "rating_key": 401, "title": "Quick Watch", "year": 2022, "date": 1750000300, "duration": 600},
]

def _run_with_history(calls, rows):
    def _fake_run(base, key, command, section_id, error, *a, **k):
        calls.append((command, section_id, a[0] if a else None))
        if command == 'get_library_names':
            return [{'section_id': 1, 'section_name': 'Movies', 'section_type': 'movie'}], None
        if command == 'get_history':
            return {'data': rows}, None
        raise AssertionError(f"unexpected command {command}")
    return _fake_run

def test_aggregate_history_sums_watch_seconds():
    aggregates = {a['title']: a for a in _aggregate_history_rows(DURATION_HISTORY_ROWS)}
    assert aggregates['Long Haul']['total_duration'] == 7200
    assert aggregates['Quick Watch']['total_duration'] == 1800
    # a source without duration fields still aggregates, just with no time
    assert _aggregate_history_rows(HISTORY_ROWS)[0]['total_duration'] == 0

def test_duration_metric_ranks_all_time_by_watch_time(monkeypatch):
    calls = []
    monkeypatch.setattr(fetchers, 'run_tautulli_command', _run_with_history(calls, DURATION_HISTORY_ROWS))
    monkeypatch.setattr(fetchers, 'get_settings', lambda **kw: {'plex_url': '', 'plex_token': ''})

    data = fetchers.fetch_most_watched_data('http://tt.local', 'enc-key', metric='duration')
    # all-time duration comes from history (media info has no watch time), and
    # the history call carries no after date
    assert [c[0] for c in calls if c[0] != 'get_library_names'] == ['get_history']
    assert calls[-1][2] == ''

    items = data[0]['most_watched']
    # fewer plays, more time watched: duration wins the top slot
    assert [i['title'] for i in items] == ['Long Haul', 'Quick Watch']
    assert items[0]['play_count'] == 1

def test_plays_metric_still_ranks_all_time_by_play_count(monkeypatch):
    monkeypatch.setattr(fetchers, 'run_tautulli_command', _fake_run)
    monkeypatch.setattr(fetchers, 'get_settings', lambda **kw: {'plex_url': '', 'plex_token': ''})

    items = fetchers.fetch_most_watched_data('http://tt.local', 'enc-key')[0]['most_watched']
    assert [i['title'] for i in items] == ['Big Hit', 'Second Best']
    assert items[0]['total_duration'] == 0

def test_duration_metric_ranks_windowed_scope_by_watch_time(monkeypatch):
    calls = []
    monkeypatch.setattr(fetchers, 'run_tautulli_command', _run_with_history(calls, DURATION_HISTORY_ROWS))
    monkeypatch.setattr(fetchers, 'get_settings', lambda **kw: {'plex_url': '', 'plex_token': ''})

    data = fetchers.fetch_most_watched_data('http://tt.local', 'enc-key', days=30, metric='duration')
    # still windowed: the after date survives the metric switch
    assert '-' in str(calls[-1][2])
    assert [i['title'] for i in data[0]['most_watched']] == ['Long Haul', 'Quick Watch']

def test_metric_text_labels_plays_or_watch_time():
    item = {'play_count': 3, 'total_duration': 7380}
    assert metric_text(item) == '3 plays'
    assert metric_text(item, 'plays') == '3 plays'
    assert metric_text(item, 'duration') == '2h 3m'
    assert metric_text({'play_count': 1, 'total_duration': 3600}, 'duration') == '1h'
    assert metric_text({'play_count': 2, 'total_duration': 900}, 'duration') == '15m'
    # a source that reports no watch time keeps the play-count label
    assert metric_text({'play_count': 9, 'total_duration': 0}, 'duration') == '9 plays'

# --- rendering: the metric labels the cards under every layout

RENDER_THEME = {
    'background': '#333333', 'text': '#62a1a4', 'primary': '#8acbd4',
    'secondary': '#222222', 'accent': '#62a1a4', 'card_bg': '#2d2d2d',
    'border': '#404040', 'muted_text': '#cccccc', 'email_theme': 'newsletterr_blue',
}
RENDER_DATA = [{'most_watched': [
    {'title': 'Long Haul', 'year': '2022', 'play_count': 3, 'total_duration': 7380,
     'thumb': '', 'library_name': 'Movies', 'plex_url': ''},
]}]

@pytest.fixture
def _no_image_fetches(monkeypatch):
    from app.emails.builders import layouts as layouts_mod
    from app.emails.builders import most_watched as mw_mod
    monkeypatch.setattr(layouts_mod, "fetch_and_attach_image", lambda *a, **k: "cid:img")
    monkeypatch.setattr(mw_mod, "fetch_and_attach_image", lambda *a, **k: "cid:img")

@pytest.mark.parametrize("layout", ["classic", "editorial", "digest"])
def test_layouts_label_cards_with_the_metric(layout, _no_image_fetches):
    from app.emails.builders import layouts as layouts_mod
    theme = layouts_mod.apply_theme(layout, RENDER_THEME)

    plays_html = layouts_mod.render_most_watched(layout, RENDER_DATA, MIMEMultipart(), theme, 'Movies', base_url="http://b")
    assert '3 plays' in plays_html and '2h 3m' not in plays_html

    duration_html = layouts_mod.render_most_watched(layout, RENDER_DATA, MIMEMultipart(), theme, 'Movies', base_url="http://b", metric='duration')
    assert '2h 3m' in duration_html and '3 plays' not in duration_html

def test_spotlight_swaps_its_value_and_unit_for_the_duration_metric(_no_image_fetches):
    # spotlight renders the value and its unit as separate lines
    from app.emails.builders import layouts as layouts_mod
    theme = layouts_mod.apply_theme('spotlight', RENDER_THEME)

    plays_html = layouts_mod.render_most_watched('spotlight', RENDER_DATA, MIMEMultipart(), theme, 'Movies', base_url="http://b")
    assert '>3<' in plays_html and '>plays<' in plays_html

    duration_html = layouts_mod.render_most_watched('spotlight', RENDER_DATA, MIMEMultipart(), theme, 'Movies', base_url="http://b", metric='duration')
    assert '>2h 3m<' in duration_html and '>watched<' in duration_html and '>plays<' not in duration_html

def test_legacy_builder_labels_cards_with_the_metric(_no_image_fetches):
    from app.emails.builders.most_watched import build_most_watched_html_with_cids

    plays_html = build_most_watched_html_with_cids(RENDER_DATA, MIMEMultipart(), RENDER_THEME, 'Movies', base_url="http://b")
    assert '3 plays' in plays_html

    duration_html = build_most_watched_html_with_cids(RENDER_DATA, MIMEMultipart(), RENDER_THEME, 'Movies', base_url="http://b", metric='duration')
    assert '2h 3m' in duration_html and '3 plays' not in duration_html
