# Most Watched snap-in (NEWS-17): fetcher and builder-selection tests with
# Tautulli stubbed out.

from app.emails import fetchers
from app.emails.builders.most_watched import most_watched_items, most_watched_heading, play_count_text

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

def test_heading_and_play_count_text():
    assert most_watched_heading('Movies') == 'Most Watched - Movies'
    assert most_watched_heading() == 'Most Watched'
    assert play_count_text({'play_count': 1}) == '1 play'
    assert play_count_text({'play_count': 57}) == '57 plays'
