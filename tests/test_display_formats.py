"""the date/time display formats, the week start day, and the default landing page."""
from datetime import date, datetime

import pytest

from app import dates

# A date with a single-digit day and month so the no-pad cases are exercised,
# and a time in the afternoon so the 12-hour conversion is not a no-op.
D = date(2026, 9, 5)          # a Saturday
DT = datetime(2026, 9, 5, 14, 5, 3)


# --- parity with the pre-v2026.4.4 hardcoded formats

def test_numeric_date_matches_old_recently_added_format():
    assert dates.fmt_numeric_date(D) == D.strftime("%-m/%-d/%y")


def test_month_day_matches_old_layout_format():
    assert dates.fmt_month_day(D) == D.strftime("%b %-d")


def test_weekday_date_matches_old_calendar_format():
    assert dates.fmt_weekday_date(D) == D.strftime("%a, %b ") + str(D.day)


def test_long_date_matches_old_digest_header_format():
    assert dates.fmt_long_date(D) == D.strftime("%B %-d, %Y")


def test_month_year_matches_old_editorial_header_format():
    assert dates.fmt_month_year(D) == D.strftime("%B %Y")


def test_iso_date_matches_old_history_format():
    assert dates.fmt_iso_date(DT) == DT.strftime("%Y-%m-%d")


def test_time_with_seconds_matches_old_history_format():
    assert dates.fmt_time(DT, '12', seconds=True) == DT.strftime("%I:%M:%S %p").lstrip("0")


def test_schedule_stamp_matches_old_store_format():
    month_abbr = ["Jan.", "Feb.", "Mar.", "Apr.", "May.", "Jun.",
                  "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]
    old = (f"{DT.strftime('%A')} {month_abbr[DT.month - 1]} {DT.day}, {DT.year}"
           f"  {DT.strftime('%H:%M')}")
    assert dates.fmt_schedule_stamp(DT, 'mdy', '24') == old


def test_short_stamp_matches_old_start_date_format():
    month_abbr = ["Jan.", "Feb.", "Mar.", "Apr.", "May.", "Jun.",
                  "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]
    assert dates.fmt_short_stamp(D) == f"{month_abbr[D.month - 1]} {D.day}, {D.year}"


# --- the field orders the setting actually selects

@pytest.mark.parametrize("fmt,expected", [
    ('mdy', "9/5/26"),
    ('dmy', "5/9/26"),
    ('ymd', "26/9/5"),
])
def test_numeric_date_orders(fmt, expected):
    assert dates.fmt_numeric_date(D, fmt) == expected


@pytest.mark.parametrize("fmt,expected", [
    ('mdy', "September 5, 2026"),
    ('dmy', "5 September 2026"),
    ('ymd', "2026 September 5"),
])
def test_long_date_orders(fmt, expected):
    assert dates.fmt_long_date(D, fmt) == expected


def test_month_day_has_no_year_to_lead_with_so_ymd_follows_mdy():
    assert dates.fmt_month_day(D, 'ymd') == dates.fmt_month_day(D, 'mdy') == "Sep 5"
    assert dates.fmt_month_day(D, 'dmy') == "5 Sep"


@pytest.mark.parametrize("mode,expected", [('12', "2:05 PM"), ('24', "14:05")])
def test_time_formats(mode, expected):
    assert dates.fmt_time(DT, mode) == expected


def test_midnight_and_noon_read_correctly_in_12_hour():
    assert dates.fmt_time(datetime(2026, 9, 5, 0, 7), '12') == "12:07 AM"
    assert dates.fmt_time(datetime(2026, 9, 5, 12, 7), '12') == "12:07 PM"


# --- unrecognized values never reach a formatter

@pytest.mark.parametrize("bad", ["", None, "nonsense", "MDY"])
def test_bad_stored_values_fall_back_to_defaults(bad):
    assert dates.resolve_date_format(bad) == 'mdy'
    assert dates.resolve_week_start(bad) == 'sunday'
    assert dates.fmt_numeric_date(D, bad) == "9/5/26"


def test_bad_time_format_falls_back():
    for bad in ["", None, "nonsense", 13]:
        assert dates.resolve_time_format(bad) == '12'


# --- week start

def test_week_start_offset_and_labels():
    assert dates.week_start_offset('sunday') == 0
    assert dates.week_start_offset('monday') == 1
    assert dates.weekday_labels('sunday')[0] == 'Sun'
    assert dates.weekday_labels('monday')[0] == 'Mon'
    assert len(set(dates.weekday_labels('monday'))) == 7


def test_start_of_week_moves_with_the_setting():
    wednesday = date(2026, 8, 12)
    assert dates.start_of_week(wednesday, 'sunday') == date(2026, 8, 9)
    assert dates.start_of_week(wednesday, 'monday') == date(2026, 8, 10)
    # a Sunday is its own week start under sunday, but belongs to the week
    # that began the previous Monday under monday
    sunday = date(2026, 8, 9)
    assert dates.start_of_week(sunday, 'sunday') == sunday
    assert dates.start_of_week(sunday, 'monday') == date(2026, 8, 3)


def test_email_calendar_grid_rotates_with_the_setting():
    from app.emails.builders.calendar_view import build_month_calendar_html, make_event

    theme = {
        'background': '#0f0f0f', 'card_bg': '#181818', 'border': '#2b2b2b',
        'muted_text': '#8e8e8e', 'text': '#c9c9c9', 'accent': '#62a1a4',
        'primary': '#8acbd4', 'secondary': '#222222',
    }
    today = date(2026, 8, 12)
    events = [make_event(date(2026, 8, 14), "Show")]

    sunday_html = build_month_calendar_html(events, dates.stamp(theme, week_start='sunday'), today)
    monday_html = build_month_calendar_html(events, dates.stamp(theme, week_start='monday'), today)

    # the header row order is the visible difference
    assert sunday_html.index('>Sun<') < sunday_html.index('>Mon<')
    assert monday_html.index('>Mon<') < monday_html.index('>Sun<')


def test_unstamped_theme_still_renders_sunday_first():
    """Callers that never stamp (older code paths, tests) must not change."""
    assert dates.week_start_of({}) == 'sunday'
    assert dates.date_format_of({}) == 'mdy'
    assert dates.time_format_of({}) == '12'


# --- theme carriage, mirroring the density axis

def test_stamp_writes_all_three_and_leaves_the_source_untouched():
    theme = {'text': '#fff'}
    stamped = dates.stamp(theme, 'dmy', '24', 'monday')
    assert stamped['date_format'] == 'dmy'
    assert stamped['time_format'] == '24'
    assert stamped['week_start'] == 'monday'
    assert stamped['text'] == '#fff'
    assert 'date_format' not in theme


# --- default landing page

def test_every_landing_page_maps_to_a_real_endpoint(app):
    from app.config import LANDING_ENDPOINTS

    known = {rule.endpoint for rule in app.url_map.iter_rules()}
    for page, endpoint in LANDING_ENDPOINTS.items():
        assert endpoint in known, f"{page} points at a missing endpoint {endpoint}"


def test_unknown_landing_value_falls_back_to_the_builder(app):
    from app.blueprints.auth import _landing_url

    with app.test_request_context():
        import app.blueprints.auth as auth_mod

        real = auth_mod.get_settings
        try:
            auth_mod.get_settings = lambda **kw: {'default_landing_page': 'nonsense'}
            assert _landing_url() == '/'
            auth_mod.get_settings = lambda **kw: {'default_landing_page': 'logs'}
            assert _landing_url() == '/logs'
            # a settings read that blows up must still return a usable page
            def _boom(**kw):
                raise RuntimeError("db gone")
            auth_mod.get_settings = _boom
            assert _landing_url() == '/'
        finally:
            auth_mod.get_settings = real


# --- settings round trip

def test_settings_form_round_trips_the_appearance_values(csrf_client):
    """Form -> DB, with validation rejecting anything outside the allowed sets
    so a hand-posted value can never reach url_for() or a formatter."""
    import sqlite3

    from tests.test_routes import SETTINGS_FORM
    from app import config

    client, token = csrf_client
    base = {**SETTINGS_FORM, "csrf_token": token}
    cols = "default_landing_page, week_start_day, date_format, time_format"

    client.post("/settings", data={**base, "default_landing_page": "logs",
                                   "week_start_day": "monday",
                                   "date_format": "dmy", "time_format": "24"})
    conn = sqlite3.connect(config.DB_PATH)
    assert conn.execute(f"SELECT {cols} FROM settings WHERE id = 1").fetchone() == (
        "logs", "monday", "dmy", "24")
    conn.close()

    client.post("/settings", data={**base, "default_landing_page": "../../etc",
                                   "week_start_day": "caturday",
                                   "date_format": "ydm", "time_format": "36"})
    conn = sqlite3.connect(config.DB_PATH)
    assert conn.execute(f"SELECT {cols} FROM settings WHERE id = 1").fetchone() == (
        "builder", "sunday", "mdy", "12")
    conn.close()
