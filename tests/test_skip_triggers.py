"""the widened skip-if-no-new triggers."""
import json
from datetime import date, timedelta

import pytest

from app.emails.scheduled import (
    LEGACY_SKIP_TRIGGERS,
    SKIP_TRIGGER_TYPES,
    count_new_content,
    parse_skip_triggers,
    scheduled_send_has_new_content,
    skip_probe_sources,
)

RA_ITEM = {"type": "recently added", "raLibrary": ""}
RA_DATA = {"recent_data": [{"recently_added": [
    {"title": "A", "library_name": "TV"},
    {"title": "B", "library_name": "TV"},
]}]}


# --- the stored column

@pytest.mark.parametrize("raw", ["", None, "[]", "not json", "{}", '["nonsense"]'])
def test_blank_or_junk_triggers_mean_the_legacy_pair(raw):
    assert parse_skip_triggers(raw) == LEGACY_SKIP_TRIGGERS


def test_known_triggers_survive_and_unknown_ones_are_dropped():
    raw = json.dumps(["ombi_requests", "made_up", "recently added"])
    assert parse_skip_triggers(raw) == ("ombi_requests", "recently added")


def test_every_trigger_type_has_a_probe_source():
    from app.emails.scheduled import SKIP_TRIGGER_SOURCES
    assert set(SKIP_TRIGGER_SOURCES) == set(SKIP_TRIGGER_TYPES)


# --- the probe only fetches what it needs

def test_probe_only_fetches_sources_the_template_actually_uses():
    # watching everything, but the template only has a recently-added section
    assert skip_probe_sources([RA_ITEM], SKIP_TRIGGER_TYPES) == {"tautulli"}


def test_probe_fetches_nothing_when_no_watched_section_is_present():
    items = [{"type": "textblock"}, {"type": "graph"}]
    assert skip_probe_sources(items, SKIP_TRIGGER_TYPES) == set()
    # a section that exists but is not watched also probes nothing
    assert skip_probe_sources([RA_ITEM], ("ombi_requests",)) == set()


def test_probe_fans_out_only_for_the_watched_types_present():
    items = [RA_ITEM, {"type": "sonarr_coming_soon"}, {"type": "seerr_requests"}]
    sources = skip_probe_sources(items, ("recently added", "sonarr_coming_soon"))
    assert sources == {"tautulli", "sonarr"}


# --- counting

def test_count_is_a_total_not_a_boolean():
    assert count_new_content([RA_ITEM], RA_DATA, ("recently added",)) == 2


def test_unwatched_sections_contribute_nothing():
    assert count_new_content([RA_ITEM], RA_DATA, ("ombi_requests",)) == 0


def test_counts_add_up_across_several_watched_sections():
    data = {
        **RA_DATA,
        "most_watched_data": [{"most_watched": [{"title": "M", "library_name": "Movies"}]}],
    }
    items = [RA_ITEM, {"type": "most_watched", "mwLibrary": ""}]
    assert count_new_content(items, data, LEGACY_SKIP_TRIGGERS) == 3


def test_library_filter_still_applies_when_counting():
    items = [{"type": "recently added", "raLibrary": "Movies"}]
    assert count_new_content(items, RA_DATA, ("recently added",)) == 0


def test_missing_probe_data_counts_as_nothing_found():
    """A failed fetch must not be able to claim there is new content."""
    items = [{"type": "sonarr_coming_soon"}, {"type": "ombi_requests"}]
    assert count_new_content(items, {}, SKIP_TRIGGER_TYPES) == 0
    assert count_new_content(items, None, SKIP_TRIGGER_TYPES) == 0


def test_coming_soon_counts_upcoming_movies():
    from app.emails.builders.coming_soon import filter_radarr_upcoming

    soon = (date.today() + timedelta(days=3)).isoformat()
    movies = [
        {"title": "Future", "digitalRelease": soon, "hasFile": False, "monitored": True},
        {"title": "Old", "digitalRelease": "2020-01-01", "hasFile": False, "monitored": True},
    ]
    expected = len(filter_radarr_upcoming(movies))
    data = {"radarr_coming_soon": movies}
    assert count_new_content([{"type": "radarr_coming_soon"}], data, ("radarr_coming_soon",)) == expected


def test_seerr_requests_count_pending_only():
    data = {"seerr_requests": {"requests": [
        {"status": 1, "mediaStatus": 3, "media": {"mediaType": "movie"}},
        {"status": 2, "mediaStatus": 5, "media": {"mediaType": "movie"}},   # available, excluded
        {"status": 3, "mediaStatus": 1, "media": {"mediaType": "movie"}},   # declined, excluded
    ]}}
    assert count_new_content([{"type": "seerr_requests"}], data, ("seerr_requests",)) == 1


# --- the legacy wrapper keeps its exact old shape

def test_legacy_wrapper_is_a_threshold_of_one_over_the_legacy_pair():
    assert scheduled_send_has_new_content([RA_ITEM], RA_DATA) is True
    assert scheduled_send_has_new_content([RA_ITEM], {"recent_data": []}) is False
    # a widened type is invisible to the legacy call even when it has content
    seerr = [{"type": "seerr_requests"}]
    data = {"seerr_requests": {"requests": [{"status": 1, "mediaStatus": 1, "media": {"mediaType": "movie"}}]}}
    assert scheduled_send_has_new_content(seerr, data) is False


def test_threshold_boundary():
    """Two items available: a threshold of 2 sends, a threshold of 3 skips."""
    found = count_new_content([RA_ITEM], RA_DATA, ("recently added",))
    assert found == 2
    assert found >= 2      # sends
    assert not found >= 3  # skips


# --- route normalization

def test_route_normalizes_triggers_and_threshold():
    from app.blueprints.scheduling import _normalize_skip_options

    triggers, threshold = _normalize_skip_options(
        {"skip_triggers": ["ombi_requests", "bogus"], "skip_min_items": 4})
    assert json.loads(triggers) == ["ombi_requests"]
    assert threshold == 4

    # nothing valid stores blank, which the sender reads as the legacy pair
    triggers, threshold = _normalize_skip_options({"skip_triggers": ["bogus"], "skip_min_items": 0})
    assert triggers == ""
    assert threshold == 1

    # a JSON string body is accepted too, and junk never raises
    triggers, _ = _normalize_skip_options({"skip_triggers": '["recently added"]'})
    assert json.loads(triggers) == ["recently added"]
    assert _normalize_skip_options({"skip_triggers": "{{{"})[0] == ""
    assert _normalize_skip_options({"skip_min_items": "many"})[1] == 1


def test_always_present_sections_are_not_offered_as_triggers():
    """Watching a section that always renders would mean never skipping, so
    those types are deliberately absent from the picker."""
    for never in ('collection_group', 'recommendations', 'random_pick', 'top_viewer',
                  'yearly_wrapped', 'featured_pick', 'droppedneedle_wrapped', 'stat'):
        assert never not in SKIP_TRIGGER_TYPES
