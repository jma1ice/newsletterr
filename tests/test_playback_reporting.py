"""graphs for Jellyfin and Emby via the Playback Reporting plugin."""
import sqlite3
from unittest.mock import patch

import pytest

from app import config
from app.clients import playback_reporting as pr


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture()
def plugin_enabled(app):
    from app.crypto import encrypt
    conn = sqlite3.connect(config.DB_PATH)
    prev = conn.execute(
        "SELECT media_server_type, jellyfin_url, jellyfin_api_key, playback_reporting_enabled "
        "FROM settings WHERE id = 1").fetchone()
    conn.execute(
        "UPDATE settings SET media_server_type = 'jellyfin', jellyfin_url = ?, "
        "jellyfin_api_key = ?, playback_reporting_enabled = 'enabled' WHERE id = 1",
        ("http://localhost:8096", encrypt("k")))
    conn.commit()
    conn.close()
    yield
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "UPDATE settings SET media_server_type = ?, jellyfin_url = ?, jellyfin_api_key = ?, "
        "playback_reporting_enabled = ? WHERE id = 1", prev)
    conn.commit()
    conn.close()


# --- the shape tolerance, which is where the real risk sits

def test_pairs_accepts_the_shapes_the_plugin_is_known_to_use():
    assert pr._pairs({'a': 3, 'b': 1}) == [('a', 3), ('b', 1)]
    assert pr._pairs([['a', 3], ['b', 1]]) == [('a', 3.0), ('b', 1.0)]
    assert pr._pairs([{'label': 'a', 'count': 3}]) == [('a', 3)]
    assert pr._pairs([{'name': 'a', 'value': 3}]) == [('a', 3)]
    assert pr._pairs([{'Name': 'a', 'Count': 3}]) == [('a', 3)]
    # nested per-day dicts sum rather than crash
    assert pr._pairs({'a': {'movie': 2, 'show': 1}}) == [('a', 3)]


def test_pairs_yields_nothing_for_shapes_it_cannot_read():
    for junk in (None, 'a string', 42, [], {}, [{'unexpected': 'keys'}], [['only-one']]):
        assert pr._pairs(junk) == []


def test_a_graph_needs_both_axes():
    assert pr._graph([], 'Plays', [1]) is None
    assert pr._graph(['a'], 'Plays', []) is None
    assert pr._graph(['a'], 'Plays', [1]) == {
        'categories': ['a'], 'series': [{'name': 'Plays', 'data': [1]}]}


# --- degradation

def test_no_graphs_when_the_toggle_is_off(app):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET playback_reporting_enabled = 'disabled' WHERE id = 1")
    conn.commit()
    conn.close()
    assert pr.fetch_playback_reporting_graphs() == ([], [])


def test_no_graphs_on_plex_even_if_the_toggle_is_on(app):
    """The plugin lives on a Jellyfin or Emby server; Plex has Tautulli."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET media_server_type = 'plex', playback_reporting_enabled = 'enabled' WHERE id = 1")
    conn.commit()
    conn.close()
    assert pr.fetch_playback_reporting_graphs() == ([], [])


def test_a_missing_plugin_produces_no_graphs_rather_than_an_error(plugin_enabled):
    with patch.object(pr, 'safe_get', side_effect=RuntimeError("404 plugin not installed")):
        assert pr.fetch_playback_reporting_graphs() == ([], [])


def test_an_unreadable_shape_produces_no_graphs(plugin_enabled):
    with patch.object(pr, 'safe_get', return_value=FakeResponse({'unexpected': {'nested': 'strings'}})):
        graphs, commands = pr.fetch_playback_reporting_graphs()
    assert graphs == [] and commands == []


# --- the graphs themselves

def _activity_payload(days=3):
    from datetime import datetime, timedelta
    today = datetime.now().date()
    return {(today - timedelta(days=i)).isoformat(): (i + 1) for i in range(days)}


def test_plays_by_date_fills_days_with_no_plays(plugin_enabled):
    """A day with no plays is absent from the report, and a line chart that
    skips it misreads as continuous activity."""
    def fake_get(url, params=None, **kwargs):
        if pr.PLAY_ACTIVITY_PATH in url:
            return FakeResponse(_activity_payload(days=2))
        return FakeResponse({})

    with patch.object(pr, 'safe_get', side_effect=fake_get):
        graphs, commands = pr.fetch_playback_reporting_graphs(days=5)

    by_date = graphs[commands.index({'command': 'Plays by Date', 'name': 'Plays by Date'})]
    assert len(by_date['categories']) == 5
    assert len(by_date['series'][0]['data']) == 5
    # the three days with no report entry are zero, not missing
    assert by_date['series'][0]['data'].count(0) == 3


def test_day_of_week_is_derived_from_the_daily_series(plugin_enabled):
    """The plugin has no day-of-week report; the daily series already answers
    it, so this is derived rather than fetched."""
    def fake_get(url, params=None, **kwargs):
        if pr.PLAY_ACTIVITY_PATH in url:
            return FakeResponse(_activity_payload(days=7))
        return FakeResponse({})

    with patch.object(pr, 'safe_get', side_effect=fake_get):
        graphs, commands = pr.fetch_playback_reporting_graphs(days=7)

    names = [c['name'] for c in commands]
    assert 'Plays by Day' in names
    by_day = graphs[names.index('Plays by Day')]
    assert by_day['categories'] == ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
                                    'Friday', 'Saturday', 'Sunday']


def test_hourly_report_buckets_into_24_hours(plugin_enabled):
    def fake_get(url, params=None, **kwargs):
        if pr.HOURLY_PATH in url:
            # the release that keys hours as 'DayOfWeek-Hour'
            return FakeResponse({'1-09': 4, '2-09': 2, '3-23': 1})
        return FakeResponse({})

    with patch.object(pr, 'safe_get', side_effect=fake_get):
        graphs, commands = pr.fetch_playback_reporting_graphs()

    names = [c['name'] for c in commands]
    by_hour = graphs[names.index('Plays by Hour')]
    assert len(by_hour['categories']) == 24
    assert by_hour['series'][0]['data'][9] == 6    # both 09 entries summed
    assert by_hour['series'][0]['data'][23] == 1


def test_breakdowns_are_sorted_and_capped(plugin_enabled):
    def fake_get(url, params=None, **kwargs):
        if pr.BREAKDOWN_PATH in url and (params or {}).get('type') == 'UserId':
            return FakeResponse({f"user{i}": i for i in range(15)})
        return FakeResponse({})

    with patch.object(pr, 'safe_get', side_effect=fake_get):
        graphs, commands = pr.fetch_playback_reporting_graphs()

    names = [c['name'] for c in commands]
    top_users = graphs[names.index('Plays by Top Users')]
    assert len(top_users['categories']) == 10          # capped
    assert top_users['series'][0]['data'][0] == 14     # highest first


def test_graphs_and_commands_stay_index_aligned(plugin_enabled):
    """The frontend names graph N from commands[N], so a mismatch mislabels
    every chart after the gap."""
    def fake_get(url, params=None, **kwargs):
        # only the hourly endpoint answers; everything else is absent
        if pr.HOURLY_PATH in url:
            return FakeResponse({'09': 4})
        return FakeResponse({})

    with patch.object(pr, 'safe_get', side_effect=fake_get):
        graphs, commands = pr.fetch_playback_reporting_graphs()

    assert len(graphs) == len(commands) == 1
    assert commands[0]['name'] == 'Plays by Hour'


def test_every_produced_name_is_one_the_charts_expect():
    """Names match the Plex ones where the meaning matches, so a template built
    on Plex keeps naming the same thing after a switch."""
    assert set(pr.GRAPH_NAMES) <= {
        'Plays by Date', 'Plays by Day', 'Plays by Hour',
        'Plays by Top Users', 'Plays by Top Platforms',
    }
