"""the Recently Released snap-in."""
from datetime import date

import pytest

from app.emails.builders import recently_released as rr

TODAY = date(2026, 8, 13)


def _item(title, released, library="Movies", added="1750000000"):
    return {
        "title": title,
        "originally_available_at": released,
        "library_name": library,
        "added_at": added,
        "media_type": "movie",
        "type": "movie",
    }


def _pull(*items):
    return [{"recently_added": list(items)}]


# ------------------------------------------------------------- release dates

@pytest.mark.parametrize("raw,expected", [
    ("2026-08-01", date(2026, 8, 1)),
    ("2026-08-01T00:00:00Z", date(2026, 8, 1)),   # trimmed to the date half
    ("", None),
    (None, None),
    ("not a date", None),
    ("2026-13-45", None),                          # impossible date, not a crash
])
def test_release_date_parsing(raw, expected):
    assert rr.release_date({"originally_available_at": raw}) == expected


def test_release_date_of_an_item_without_the_field():
    assert rr.release_date({"title": "x"}) is None


# -------------------------------------------------------------------- shape

def test_flatten_accepts_per_library_blocks_and_flat_lists():
    blocks = [{"recently_added": [_item("A", "2026-01-01")]},
              {"recently_added": [_item("B", "2026-01-02")]}]
    assert [i["title"] for i in rr.flatten(blocks)] == ["A", "B"]

    flat = [_item("C", "2026-01-03")]
    assert [i["title"] for i in rr.flatten(flat)] == ["C"]


def test_flatten_tolerates_junk():
    assert rr.flatten(None) == []
    assert rr.flatten("nope") == []
    assert rr.flatten([{"unrelated": 1}]) == []


def test_as_recent_data_round_trips_through_flatten():
    items = [_item("A", "2026-01-01")]
    assert rr.flatten(rr.as_recent_data(items)) == items
    assert rr.as_recent_data([]) == []


# ------------------------------------------------------------------- cutoff

def test_setting_wins_over_the_pull_window():
    assert rr.resolve_cutoff(7, 30, today=TODAY) == date(2026, 8, 6)


def test_pull_window_is_used_when_the_setting_is_blank():
    assert rr.resolve_cutoff("", 30, today=TODAY) == date(2026, 7, 14)


def test_no_cutoff_when_neither_is_set():
    """Items mode has no time window, so ordering is the whole behaviour."""
    assert rr.resolve_cutoff("", None, today=TODAY) is None
    assert rr.resolve_cutoff(None, None, today=TODAY) is None


@pytest.mark.parametrize("bogus", ["abc", 0, -5, "  "])
def test_bogus_values_do_not_become_a_cutoff(bogus):
    assert rr.resolve_cutoff(bogus, None, today=TODAY) is None


def test_string_days_from_settings_are_accepted():
    """Settings columns are TEXT, so the value arrives as a string."""
    assert rr.resolve_cutoff("7", None, today=TODAY) == date(2026, 8, 6)


# ----------------------------------------------------------------- selection

def test_items_without_a_release_date_are_dropped():
    """The snap-in is defined by that date; an undated item cannot be said to
    have been released recently."""
    data = _pull(_item("Dated", "2026-08-01"), _item("Undated", ""))
    picked = rr.select(data, today=TODAY)
    assert [i["title"] for i in picked] == ["Dated"]


def test_ordered_by_release_date_newest_first():
    data = _pull(
        _item("Old", "2026-01-05"),
        _item("Newest", "2026-08-10"),
        _item("Middle", "2026-05-01"),
    )
    assert [i["title"] for i in rr.select(data, today=TODAY)] == ["Newest", "Middle", "Old"]


def test_release_date_order_differs_from_added_order():
    """The whole point: an old film added yesterday sorts last here."""
    data = _pull(
        _item("Classic", "1994-09-23", added="1760000000"),   # added most recently
        _item("New Release", "2026-08-01", added="1700000000"),
    )
    assert [i["title"] for i in rr.select(data, today=TODAY)] == ["New Release", "Classic"]


def test_cutoff_excludes_older_releases():
    data = _pull(_item("In Window", "2026-08-10"), _item("Too Old", "2025-01-01"))
    picked = rr.select(data, released_since_days=30, today=TODAY)
    assert [i["title"] for i in picked] == ["In Window"]


def test_release_on_the_cutoff_day_is_included():
    data = _pull(_item("Exactly", "2026-08-06"))
    assert len(rr.select(data, released_since_days=7, today=TODAY)) == 1


def test_future_releases_are_kept():
    """Plex can carry a future air date; that is still 'released' by this
    snap-in's ordering and Coming Soon owns the upcoming view."""
    data = _pull(_item("Future", "2026-09-01"))
    assert len(rr.select(data, released_since_days=30, today=TODAY)) == 1


def test_library_filter():
    data = _pull(
        _item("Movie", "2026-08-01", library="Movies"),
        _item("Show", "2026-08-02", library="TV Shows"),
    )
    picked = rr.select(data, library_filter="tv shows", today=TODAY)
    assert [i["title"] for i in picked] == ["Show"]


def test_item_cap_applies_after_ordering():
    data = _pull(
        _item("Third", "2026-01-01"),
        _item("First", "2026-08-10"),
        _item("Second", "2026-06-01"),
    )
    picked = rr.select(data, item_cap=2, today=TODAY)
    assert [i["title"] for i in picked] == ["First", "Second"]


@pytest.mark.parametrize("cap", [0, None, "", "abc", -3])
def test_blank_cap_keeps_everything(cap):
    data = _pull(*[_item(f"T{i}", "2026-08-01") for i in range(5)])
    assert len(rr.select(data, item_cap=cap, today=TODAY)) == 5


def test_same_day_releases_keep_the_pulls_order():
    data = _pull(
        _item("A", "2026-08-01"), _item("B", "2026-08-01"), _item("C", "2026-08-01"),
    )
    assert [i["title"] for i in rr.select(data, today=TODAY)] == ["A", "B", "C"]


def test_empty_input():
    assert rr.select([], today=TODAY) == []
    assert rr.select(None, today=TODAY) == []


# ---------------------------------------------------------------- rendering

def test_it_renders_through_the_recently_added_builders():
    """Not a second renderer: it reshapes and delegates, so every layout and
    density comes along without a copy that can drift."""
    from app.emails.builders.recently_added import build_recently_added_html_with_cids

    theme = {
        'background': '#0f0f0f', 'card_bg': '#181818', 'border': '#2b2b2b',
        'muted_text': '#8e8e8e', 'text': '#c9c9c9', 'accent': '#62a1a4',
        'primary': '#8acbd4', 'secondary': '#222222',
    }
    items = rr.select(_pull(_item("Fresh Release", "2026-08-10")), today=TODAY)
    html = build_recently_added_html_with_cids(
        rr.as_recent_data(items), None, theme, None, "", None,
        recently_added_mode='items')
    assert "Fresh Release" in html


def test_default_title_is_distinct_from_recently_added():
    assert rr.DEFAULT_TITLE == "Recently Released"


def test_assemble_dispatches_the_item_type():
    """Guards the wiring: the module can be perfect and still never called."""
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent / "app/emails/assemble.py").read_text(encoding="utf-8")
    assert "item_type == 'recently_released'" in source
    assert "recently_released.select(" in source
    # its own default heading, still overridable by a heading typed on the item
    assert "item.get('heading') or recently_released.DEFAULT_TITLE" in source


def test_token_grammar_is_registered():
    from app.emails.snapin_tokens import synthesize_snapin_item
    item = synthesize_snapin_item('recently_released', ['Movies', '5', 'list'], [])
    assert item['type'] == 'recently_released'
    assert item['rrLibrary'] == 'Movies'
    assert item['rrCount'] == '5'
    assert item['rrOrientation'] == 'list'


# ------------------------------------------------------- the client payloads

def test_plex_and_jellyfin_clients_carry_the_release_date():
    """Without this field in the pull the snap-in has nothing to filter on."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    plex = (root / "app/clients/plex.py").read_text(encoding="utf-8")
    jelly = (root / "app/clients/jellyfin.py").read_text(encoding="utf-8")

    # movies, albums and the rolled-up show entry
    assert plex.count("'originally_available_at': ") >= 3
    assert "originallyAvailableAt" in plex
    assert "'originally_available_at': (item.get('PremiereDate') or '')[:10]" in jelly
    # Jellyfin only returns fields it is asked for
    assert "PremiereDate" in jelly.split("'Fields':")[1].split("\n")[0]
