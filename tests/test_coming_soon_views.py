"""The per-snap-in Coming Soon views: poster grid (the default), month
calendar, and agenda, plus the narrow-screen reflow rules they depend on."""
import re
from datetime import date, timedelta

import pytest

THEME = {
    'background': '#0f0f0f', 'card_bg': '#181818', 'border': '#2b2b2b',
    'muted_text': '#8e8e8e', 'text': '#c9c9c9', 'accent': '#62a1a4',
    'primary': '#8acbd4', 'secondary': '#222222',
}

TODAY = date(2026, 8, 12)  # a Wednesday


def _event(day_offset, title="Show", subtitle="", poster="cid:p"):
    from app.emails.builders.calendar_view import make_event
    return make_event(TODAY + timedelta(days=day_offset), title, subtitle, poster)


# --- span and grouping

def test_week_start_is_the_preceding_sunday():
    from app.emails.builders.calendar_view import _week_start
    # Wednesday 2026-08-12 sits in the week beginning Sunday the 9th
    assert _week_start(TODAY) == date(2026, 8, 9)
    assert _week_start(date(2026, 8, 9)) == date(2026, 8, 9)


def test_events_without_a_date_are_dropped():
    from app.emails.builders.calendar_view import group_events_by_day, make_event
    by_day = group_events_by_day([_event(1), make_event(None, "Undated")])
    assert sum(len(v) for v in by_day.values()) == 1


def test_same_day_events_keep_their_order():
    from app.emails.builders.calendar_view import group_events_by_day
    by_day = group_events_by_day([_event(1, "First"), _event(1, "Second")])
    assert [e['title'] for e in by_day[TODAY + timedelta(days=1)]] == ["First", "Second"]


def test_span_starts_at_the_current_week_even_when_events_are_later():
    from app.emails.builders.calendar_view import calendar_span, group_events_by_day
    start, end, overflow = calendar_span(group_events_by_day([_event(10)]), TODAY)
    assert start == date(2026, 8, 9)
    assert end == TODAY + timedelta(days=10)
    assert overflow == []


def test_span_caps_the_grid_and_reports_the_overflow():
    """A 90-day window would otherwise emit a 13-week table."""
    from app.emails.builders.calendar_view import MAX_CALENDAR_WEEKS, calendar_span, group_events_by_day
    events = [_event(3), _event(80)]
    start, end, overflow = calendar_span(group_events_by_day(events), TODAY)
    assert end <= start + timedelta(days=MAX_CALENDAR_WEEKS * 7 - 1)
    assert overflow == [TODAY + timedelta(days=80)]


# --- month calendar

def _calendar(events, today=TODAY):
    from app.emails.builders.calendar_view import build_month_calendar_html
    return build_month_calendar_html(events, THEME, today)


def test_calendar_renders_a_weekday_header_and_seven_cells_per_week():
    html = _calendar([_event(1)])
    assert 'class="cs-cal-head"' in html
    for label in ('Sun', 'Wed', 'Sat'):
        assert f'>{label}<' in html
    assert html.count('class="cs-cal-row"') == 1
    assert html.count('<td class="cs-cal-cell') == 7


def test_calendar_spans_one_row_per_week():
    html = _calendar([_event(1), _event(9)])
    assert html.count('class="cs-cal-row"') == 2
    assert html.count('<td class="cs-cal-cell') == 14


def test_empty_days_are_marked_so_they_drop_out_on_narrow_screens():
    html = _calendar([_event(1)])
    # one day carries the event, the other six in the week are collapsible
    assert html.count('cs-cal-empty') == 6


def test_calendar_carries_both_date_labels_for_the_breakpoint_swap():
    html = _calendar([_event(1)])
    assert 'class="cs-cal-daynum"' in html
    assert 'class="cs-cal-daylong"' in html
    assert 'Thu, Aug 13' in html


def test_calendar_poster_avoids_the_global_full_width_rule():
    """.card-poster-img is forced to width 100% for the card grid; a calendar
    cell poster must not inherit that."""
    html = _calendar([_event(1)])
    assert 'class="cs-cal-poster"' in html
    assert 'card-poster-img' not in html


def test_calendar_footnotes_events_past_the_cap():
    html = _calendar([_event(3), _event(80), _event(81)])
    assert 'Plus 2 more items after' in html


def test_calendar_returns_none_when_nothing_is_datable():
    from app.emails.builders.calendar_view import make_event
    assert _calendar([]) is None
    assert _calendar([make_event(None, "Undated")]) is None


def test_calendar_escapes_titles():
    html = _calendar([_event(1, '<script>x</script>', '"quoted"')])
    assert '<script>' not in html
    assert '&lt;script&gt;' in html


# --- agenda

def _agenda(events, today=TODAY):
    from app.emails.builders.calendar_view import build_agenda_html
    return build_agenda_html(events, THEME, today)


def test_agenda_emits_one_row_per_populated_day_in_date_order():
    html = _agenda([_event(5, "Later"), _event(1, "Sooner")])
    assert html.count('class="cs-agenda-row"') == 2
    assert html.index("Sooner") < html.index("Later")


def test_agenda_groups_a_days_items_under_one_date():
    html = _agenda([_event(2, "A"), _event(2, "B")])
    assert html.count('class="cs-agenda-row"') == 1
    assert "A" in html and "B" in html


def test_agenda_labels_today_and_tomorrow_by_name():
    html = _agenda([_event(0, "Now"), _event(1, "Next"), _event(4, "Later")])
    assert '>Today<' in html
    assert '>Tomorrow<' in html
    assert 'Sun, Aug 16' in html


def test_agenda_returns_none_when_empty():
    assert _agenda([]) is None


def test_agenda_escapes_titles():
    html = _agenda([_event(1, '<b>bold</b>')])
    assert '<b>bold</b>' not in html
    assert '&lt;b&gt;' in html


# --- view resolution and builder dispatch

@pytest.mark.parametrize("raw,expected", [
    ("", ""), (None, ""), ("nonsense", ""), ("Calendar", "calendar"),
    ("grid", "grid"), (" agenda ", "agenda"),
])
def test_resolve_view_normalizes_and_falls_back_to_the_layout_default(raw, expected):
    from app.emails.builders.coming_soon import resolve_view
    assert resolve_view(raw) == expected


@pytest.fixture()
def stub_images(monkeypatch):
    from app.emails.builders import coming_soon
    monkeypatch.setattr(coming_soon, 'fetch_and_attach_image', lambda *a, **k: 'cid:full')
    monkeypatch.setattr(coming_soon, 'fetch_and_attach_small_thumbnail', lambda *a, **k: 'cid:thumb')


def _episodes():
    soon = (date.today() + timedelta(days=2)).isoformat()
    later = (date.today() + timedelta(days=4)).isoformat()
    return [
        {'seriesId': 1, 'seasonNumber': 1, 'episodeNumber': 3, 'title': 'Pilot',
         'airDate': soon, 'series': {'id': 1, 'title': 'Some Show', 'year': 2024,
                                     'images': [{'coverType': 'poster', 'remoteUrl': 'http://x/p.jpg'}]}},
        {'seriesId': 2, 'seasonNumber': 2, 'episodeNumber': 1, 'title': 'Return',
         'airDate': later, 'series': {'id': 2, 'title': 'Other Show', 'year': 2020, 'images': []}},
    ]


def _movies():
    return [{'title': 'A Movie', 'year': 2026, 'hasFile': False,
             'digitalRelease': (date.today() + timedelta(days=3)).isoformat(),
             'images': [{'coverType': 'poster', 'remoteUrl': 'http://x/m.jpg'}]}]


@pytest.mark.parametrize("view,marker", [
    ("", 'class="coming-soon-table nl-grid"'),
    ("grid", 'class="coming-soon-table nl-grid"'),
    ("calendar", 'class="cs-cal-table"'),
    ("agenda", 'class="cs-agenda-table"'),
])
def test_legacy_sonarr_builder_dispatches_on_view(stub_images, view, marker):
    from app.emails.builders.coming_soon import build_sonarr_coming_soon_html_with_cids
    html = build_sonarr_coming_soon_html_with_cids(_episodes(), None, THEME, view=view)
    assert marker in html
    assert 'Some Show' in html


@pytest.mark.parametrize("view,marker", [
    ("", 'class="coming-soon-table nl-grid"'),
    ("calendar", 'class="cs-cal-table"'),
    ("agenda", 'class="cs-agenda-table"'),
])
def test_legacy_radarr_builder_dispatches_on_view(stub_images, view, marker):
    from app.emails.builders.coming_soon import build_radarr_coming_soon_html_with_cids
    html = build_radarr_coming_soon_html_with_cids(_movies(), None, THEME, view=view)
    assert marker in html
    assert 'A Movie' in html


def test_views_keep_the_section_title(stub_images):
    from app.emails.builders.coming_soon import build_sonarr_coming_soon_html_with_cids
    for view in ('calendar', 'agenda'):
        assert 'Coming Soon (TV)' in build_sonarr_coming_soon_html_with_cids(_episodes(), None, THEME, view=view)


def test_views_attach_downscaled_thumbnails_not_full_posters(monkeypatch):
    """A 90-day window in calendar view would carry dozens of full posters."""
    from app.emails.builders import coming_soon
    heights = []

    def _thumb(url, msg_root, cid, base_url="", height=40, **kwargs):
        heights.append(height)
        return 'cid:thumb'

    monkeypatch.setattr(coming_soon, 'fetch_and_attach_small_thumbnail', _thumb)
    monkeypatch.setattr(coming_soon, 'fetch_and_attach_image', lambda *a, **k: pytest.fail("full poster attached"))
    coming_soon.build_sonarr_coming_soon_html_with_cids(_episodes(), None, THEME, view='calendar')
    coming_soon.build_sonarr_coming_soon_html_with_cids(_episodes(), None, THEME, view='agenda')
    assert heights and all(h <= 120 for h in heights)


# --- layout renderers

@pytest.fixture()
def stub_layout_images(monkeypatch):
    from app.emails.builders import coming_soon, layouts
    monkeypatch.setattr(layouts, 'fetch_and_attach_image', lambda *a, **k: 'cid:full')
    monkeypatch.setattr(coming_soon, 'fetch_and_attach_small_thumbnail', lambda *a, **k: 'cid:thumb')


@pytest.mark.parametrize("layout", ['classic', 'editorial', 'digest', 'spotlight'])
def test_every_layout_honors_the_calendar_view(stub_layout_images, layout):
    from app.emails.builders import layouts
    html = layouts.render_sonarr_coming_soon(layout, _episodes(), None, THEME, view='calendar')
    assert 'class="cs-cal-table"' in html
    assert 'Coming Soon (TV)' in html


@pytest.mark.parametrize("layout", ['classic', 'editorial', 'digest', 'spotlight'])
def test_every_layout_honors_the_agenda_view(stub_layout_images, layout):
    from app.emails.builders import layouts
    html = layouts.render_radarr_coming_soon(layout, _movies(), None, THEME, view='agenda')
    assert 'class="cs-agenda-table"' in html


def test_grid_view_overrides_a_layouts_dated_rows(stub_layout_images):
    """digest normally renders coming soon as text rows, not cards."""
    from app.emails.builders import layouts
    default = layouts.render_sonarr_coming_soon('digest', _episodes(), None, THEME)
    forced = layouts.render_sonarr_coming_soon('digest', _episodes(), None, THEME, view='grid')
    assert 'coming-soon-card' not in default
    assert 'coming-soon-card' in forced


def test_blank_view_leaves_each_layout_untouched(stub_layout_images):
    from app.emails.builders import layouts
    for layout in ('classic', 'editorial', 'digest', 'spotlight'):
        assert (layouts.render_sonarr_coming_soon(layout, _episodes(), None, THEME)
                == layouts.render_sonarr_coming_soon(layout, _episodes(), None, THEME, view=''))


# --- tokens

@pytest.mark.parametrize("token,expected", [
    ("coming_soon_tv", None),
    ("coming_soon_tv:calendar", "calendar"),
    ("coming_soon_movies:agenda", "agenda"),
    ("coming_soon_movies:GRID", "grid"),
    ("coming_soon_tv:bogus", None),
])
def test_coming_soon_tokens_take_a_view_argument(token, expected):
    from app.emails.snapin_tokens import synthesize_snapin_item
    name, _, raw_args = token.partition(':')
    args = [a.strip() for a in raw_args.split(':')] if raw_args else []
    item = synthesize_snapin_item(name, args, [])
    assert item['type'].endswith('coming_soon')
    assert item.get('csView') == expected


# --- the reflow contract with app/theme.py

def test_every_view_class_has_a_narrow_screen_rule():
    """The views and the media block in app/theme.py are hand-synced; a class
    emitted without a matching rule silently loses its reflow."""
    from app.theme import build_email_css_from_theme

    css = build_email_css_from_theme(THEME, 100)
    media = css.split('@media only screen and (max-width: 600px)', 1)[1]

    html = _calendar([_event(1), _event(80)]) + _agenda([_event(1)])
    emitted = set(re.findall(r'class="([a-z0-9 -]+)"', html))
    classes = {c for group in emitted for c in group.split() if c.startswith('cs-')}

    assert classes  # guards against the regex silently matching nothing
    for name in classes:
        assert f'.{name}' in media, f"{name} has no narrow-screen rule in theme.py"


def test_empty_day_rule_wins_over_the_cell_rule():
    """Same specificity and both !important, so source order decides whether
    blank days disappear on a phone."""
    from app.theme import build_email_css_from_theme

    media = build_email_css_from_theme(THEME, 100).split('@media only screen and (max-width: 600px)', 1)[1]
    assert media.index('.cs-cal-cell') < media.index('.cs-cal-empty')
