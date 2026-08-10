"""Top Viewer snap-in."""
import re
from email.mime.multipart import MIMEMultipart

import pytest

from app.emails.builders import layouts as layouts_mod
from app.emails.builders.top_viewer import (
    build_top_viewer_html,
    find_top_viewer,
    top_viewer_heading,
    top_viewer_metrics,
    watch_time_text,
)

LAYOUTS = ("classic", "editorial", "digest", "spotlight")
NAME = "alice"

THEME = {
    'background': '#333333', 'text': '#62a1a4', 'primary': '#8acbd4',
    'secondary': '#222222', 'accent': '#62a1a4', 'card_bg': '#2d2d2d',
    'border': '#404040', 'muted_text': '#cccccc', 'email_theme': 'newsletterr_blue',
}
STATS = [
    {'stat_title': 'Most Watched Movies', 'rows': [{'title': 'Dune', 'total_plays': 42}]},
    {'stat_title': 'Most Active Users', 'rows': [
        {'user': NAME, 'total_plays': 42, 'total_duration': 65520, 'user_thumb': 'http://plex.tv/a.png'},
        {'user': 'bob', 'total_plays': 10, 'total_duration': 3600, 'user_thumb': ''},
    ]},
]
CHAMP = STATS[1]['rows'][0]


@pytest.fixture(autouse=True)
def _stub_image_fetches(monkeypatch):
    import app.emails.builders.top_viewer as tv
    monkeypatch.setattr(tv, "fetch_and_attach_small_thumbnail", lambda *a, **k: "cid:avatar")


def render(layout, row=CHAMP, include_user_info=True, range_text="Last 30 days"):
    theme = layouts_mod.apply_theme(layout, THEME)
    return layouts_mod.render_top_viewer(layout, row, MIMEMultipart(), theme, "http://b",
                                         range_text=range_text, include_user_info=include_user_info)


# --- picking the champ

def test_finds_the_leader_in_the_cached_stats():
    assert find_top_viewer(STATS) is CHAMP


def test_leader_is_by_watch_time_not_list_order():
    """Tautulli pre-sorts, but a provider that does not must not mislead us."""
    stats = [{'stat_title': 'Most Active Users', 'rows': [
        {'user': 'quiet', 'total_plays': 99, 'total_duration': 60},
        {'user': 'real', 'total_plays': 2, 'total_duration': 90000},
    ]}]
    assert find_top_viewer(stats)['user'] == 'real'


@pytest.mark.parametrize("stats", [None, [], [{'stat_title': 'Most Watched Movies', 'rows': [{}]}],
                                   [{'stat_title': 'Most Active Users', 'rows': []}]])
def test_missing_user_stat_yields_nothing(stats):
    assert find_top_viewer(stats) is None


# --- formatting

def test_watch_time_reads_as_hours_and_minutes():
    assert watch_time_text({'total_duration': 65520}) == "18h 12m"
    assert watch_time_text({'total_duration': 7200}) == "2h"
    assert watch_time_text({'total_duration': 900}) == "15m"
    assert watch_time_text({'total_duration': 0}) == ""
    assert watch_time_text({}) == ""


def test_metrics_never_include_the_identity():
    assert NAME not in " ".join(top_viewer_metrics(CHAMP))


def test_singular_play_wording():
    assert "1 play" in top_viewer_metrics({'total_plays': 1, 'total_duration': 60})


def test_heading_carries_the_pull_range():
    assert top_viewer_heading("Last 30 days") == "Top Viewer - Last 30 days"
    assert top_viewer_heading() == "Top Viewer"


# --- rendering, every layout

@pytest.mark.parametrize("layout", LAYOUTS)
def test_names_the_viewer_when_user_info_is_on(layout):
    html = render(layout)
    assert NAME in html and "18h 12m" in html and "42 plays" in html


@pytest.mark.parametrize("layout", LAYOUTS)
def test_user_info_off_keeps_the_numbers_and_drops_the_identity(layout):
    """The point of the snap-in survives anonymization (NEWS-49)."""
    html = render(layout, include_user_info=False)
    assert NAME not in html
    assert "cid:avatar" not in html
    assert "18h 12m" in html and "42 plays" in html


@pytest.mark.parametrize("layout", LAYOUTS)
def test_avatar_rides_along_when_the_user_has_one(layout):
    assert "cid:avatar" in render(layout)


@pytest.mark.parametrize("layout", LAYOUTS)
def test_no_avatar_markup_without_a_thumb(layout):
    html = render(layout, row={'user': 'bob', 'total_plays': 10, 'total_duration': 3600})
    assert "bob" in html and "<img" not in html


@pytest.mark.parametrize("layout", LAYOUTS)
def test_a_row_with_no_metrics_renders_nothing(layout):
    assert render(layout, row={'user': 'ghost'}) == ""
    assert render(layout, row=None) == ""


@pytest.mark.parametrize("layout", LAYOUTS)
def test_range_text_is_shown(layout):
    assert "Last 30 days" in render(layout)


@pytest.mark.parametrize("layout", LAYOUTS)
def test_markup_stays_email_safe(layout):
    html = render(layout)
    assert "display: flex" not in html and "display: grid" not in html
    assert not re.search(r"position:\s*absolute", html)


def test_legacy_builder_matches_the_same_rules():
    shown = build_top_viewer_html(CHAMP, MIMEMultipart(), THEME, "http://b", range_text="Last 30 days")
    assert NAME in shown and "18h 12m" in shown and "Top Viewer - Last 30 days" in shown

    hidden = build_top_viewer_html(CHAMP, MIMEMultipart(), THEME, "http://b",
                                   range_text="Last 30 days", include_user_info=False)
    assert NAME not in hidden and "18h 12m" in hidden
    assert build_top_viewer_html(None, MIMEMultipart(), THEME) == ""


def test_a_hostile_username_is_escaped():
    row = {'user': '<script>alert(1)</script>', 'total_plays': 3, 'total_duration': 3600}
    for layout in LAYOUTS:
        assert "<script>" not in render(layout, row=row)
    assert "<script>" not in build_top_viewer_html(row, MIMEMultipart(), THEME)


def test_token_resolves_without_arguments():
    from app.emails.snapin_tokens import synthesize_snapin_item
    assert synthesize_snapin_item('top_viewer', [], STATS) == {'id': 'top-viewer', 'type': 'top_viewer'}
