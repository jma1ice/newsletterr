"""Both are pure functions over the Sonarr/Radarr calendar payloads, so they are
tested directly rather than through rendered HTML."""
import pytest

from app.emails.builders.coming_soon import (
    episode_kind,
    filter_sonarr_by_kind,
    radarr_upcoming,
    resolve_kind,
    sonarr_groups,
)


def _ep(series_id, season, number, air="2026-08-20", title=None):
    return {
        "seriesId": series_id,
        "seasonNumber": season,
        "episodeNumber": number,
        "airDate": air,
        "airDateUtc": f"{air}T01:00:00Z",
        "title": title or f"S{season}E{number}",
        "series": {"id": series_id, "title": f"Series {series_id}"},
    }


# ------------------------------------------------------------- classification

@pytest.mark.parametrize("season,number,expected", [
    (1, 1, 'new-series'),     # series premiere
    (2, 1, 'premiere'),       # returning season
    (7, 1, 'premiere'),
    (1, 2, 'episode'),
    (3, 12, 'episode'),
    (0, 1, 'episode'),        # specials are not a premiere
    (None, 1, 'episode'),     # unknown season
    (1, None, 'episode'),     # unknown episode number
])
def test_episode_kind(season, number, expected):
    assert episode_kind(_ep(1, season, number)) == expected


@pytest.mark.parametrize("raw,expected", [
    ('', 'all'), (None, 'all'), ('nonsense', 'all'),
    ('all', 'all'), ('premieres', 'premieres'), ('new-series', 'new-series'),
    ('  Premieres  ', 'premieres'),
])
def test_resolve_kind_falls_back_to_all(raw, expected):
    assert resolve_kind(raw) == expected


# -------------------------------------------------------------------- filter

EPISODES = [
    _ep(1, 1, 1),     # new series
    _ep(2, 3, 1),     # returning
    _ep(3, 2, 5),     # mid season
    _ep(4, 0, 1),     # special
]


def test_blank_kind_keeps_everything():
    assert len(filter_sonarr_by_kind(EPISODES, '')) == 4
    assert filter_sonarr_by_kind(EPISODES, '') == EPISODES


def test_premieres_keeps_new_and_returning():
    kept = filter_sonarr_by_kind(EPISODES, 'premieres')
    assert [e['seriesId'] for e in kept] == [1, 2]


def test_new_series_keeps_only_series_premieres():
    kept = filter_sonarr_by_kind(EPISODES, 'new-series')
    assert [e['seriesId'] for e in kept] == [1]


def test_filter_does_not_mutate_the_input():
    original = list(EPISODES)
    filter_sonarr_by_kind(EPISODES, 'premieres')
    assert EPISODES == original


def test_filter_handles_empty_and_none():
    assert filter_sonarr_by_kind([], 'premieres') == []
    assert filter_sonarr_by_kind(None, 'premieres') == []


# ----------------------------------------------------------------- entry cap

def test_cap_counts_grouped_entries_not_raw_episodes():
    """A full-season drop is one entry, so a cap of 1 keeps the whole season.

    Capping raw episodes first would truncate the drop and change the
    "(N episodes)" count the group reports.
    """
    season_drop = [_ep(1, 2, n) for n in range(1, 9)]   # 8 episodes, one drop
    other = [_ep(2, 1, 1)]
    groups = sonarr_groups(season_drop + other, '', 1)
    assert len(groups) == 1
    assert len(groups[0]['episodes']) == 8


def test_cap_trims_to_the_requested_number_of_entries():
    episodes = [_ep(i, 1, 5) for i in range(1, 8)]      # 7 separate series
    assert len(sonarr_groups(episodes, '', 3)) == 3
    assert len(sonarr_groups(episodes, '', 99)) == 7


@pytest.mark.parametrize("limit", ['', None, 0, -4, 'abc'])
def test_blank_or_bogus_cap_keeps_everything(limit):
    episodes = [_ep(i, 1, 5) for i in range(1, 6)]
    assert len(sonarr_groups(episodes, '', limit)) == 5


def test_cap_applies_after_the_kind_filter():
    """Order matters: filtering first means the cap counts what survives."""
    episodes = [
        _ep(1, 2, 4), _ep(2, 3, 9),      # mid-season, dropped by the filter
        _ep(3, 1, 1), _ep(4, 5, 1),      # premieres, kept
    ]
    groups = sonarr_groups(episodes, 'premieres', 2)
    assert [g['series']['id'] for g in groups] == [3, 4]


def test_string_cap_from_the_builder_payload_is_accepted():
    """The builder sends a number, but a template round-trip can stringify."""
    episodes = [_ep(i, 1, 5) for i in range(1, 6)]
    assert len(sonarr_groups(episodes, '', '2')) == 2


# ------------------------------------------------------------------- radarr

def _movie(title, in_cinemas="2026-09-01", has_file=False):
    return {"title": title, "inCinemas": in_cinemas, "hasFile": has_file, "year": 2026}


def test_radarr_cap_applies_after_the_upcoming_filter():
    movies = [
        _movie("Already Have", has_file=True),
        _movie("One"), _movie("Two"), _movie("Three"),
    ]
    kept = radarr_upcoming(movies, 2)
    assert [m['title'] for m in kept] == ["One", "Two"]


def test_radarr_blank_cap_keeps_everything():
    movies = [_movie("One"), _movie("Two"), _movie("Three")]
    assert len(radarr_upcoming(movies, 0)) == 3
    assert len(radarr_upcoming(movies, None)) == 3


def test_radarr_handles_none():
    assert radarr_upcoming(None, 5) == []
