from datetime import datetime, timedelta

import pytest

from app.crypto import decrypt, encrypt
from app.security import escape_html_output, sanitize_html, sanitize_html_input
from app.store import calculate_next_send, next_future_send

# (frequency, start_date, send_time, last_sent, expected)
NEXT_SEND_CASES = [
    # daily: +1 day from start, or from last_sent
    ("daily", "2026-03-01T09:00:00", "09:00", None, datetime(2026, 3, 2, 9, 0)),
    ("daily", "2026-03-01T09:00:00", "09:00", "2026-03-05T09:00:00", datetime(2026, 3, 6, 9, 0)),
    # weekly: lands on the start date's weekday; same-day rolls a full week
    ("weekly", "2026-03-02T09:00:00", "09:00", None, datetime(2026, 3, 9, 9, 0)),          # Mon -> next Mon
    ("weekly", "2026-03-02T09:00:00", "09:00", "2026-03-04T09:00:00", datetime(2026, 3, 9, 9, 0)),  # Wed -> Mon
    # biweekly: flat +14 days
    ("biweekly", "2026-03-01T09:00:00", "09:00", None, datetime(2026, 3, 15, 9, 0)),
    # bimonthly: fixed 1st/15th cadence regardless of start day
    ("bimonthly", "2026-03-05T09:00:00", "09:00", None, datetime(2026, 3, 15, 9, 0)),   # before 15th -> 15th
    ("bimonthly", "2026-03-05T09:00:00", "09:00", "2026-03-20T09:00:00", datetime(2026, 4, 1, 9, 0)),  # after 15th -> next 1st
    ("bimonthly", "2026-03-20T09:00:00", "09:00", None, datetime(2026, 4, 1, 9, 0)),    # start after 15th -> next 1st (was buggy: gave the 15th)
    ("bimonthly", "2026-03-15T09:00:00", "09:00", None, datetime(2026, 4, 1, 9, 0)),    # exactly 15th -> next 1st
    ("bimonthly", "2026-12-20T09:00:00", "09:00", None, datetime(2027, 1, 1, 9, 0)),    # year wrap
    # monthly: clamps to short months (Jan 31 -> Feb 28 in a non-leap year)
    ("monthly", "2026-01-31T09:00:00", "09:00", None, datetime(2026, 2, 28, 9, 0)),
    ("monthly", "2026-04-15T09:00:00", "09:00", "2026-05-15T09:00:00", datetime(2026, 6, 15, 9, 0)),
    # interval frequencies: +2 / +3 / +6 months with year wrap
    ("bimonthly_interval", "2026-11-15T09:00:00", "09:00", None, datetime(2027, 1, 15, 9, 0)),
    ("quarterly", "2026-11-15T09:00:00", "09:00", None, datetime(2027, 2, 15, 9, 0)),
    ("biannually", "2026-08-10T09:00:00", "09:00", None, datetime(2027, 2, 10, 9, 0)),
    # yearly incl. Feb-29 handling both directions
    ("yearly", "2024-02-29T09:00:00", "09:00", None, datetime(2025, 2, 28, 9, 0)),
    ("yearly", "2024-02-29T09:00:00", "09:00", "2027-02-28T09:00:00", datetime(2028, 2, 29, 9, 0)),
    # unknown frequency falls back to daily
    ("fortnightly-ish", "2026-03-01T09:00:00", "09:00", None, datetime(2026, 3, 2, 9, 0)),
    # send_time is applied to the result
    ("daily", "2026-03-01T09:00:00", "18:30", None, datetime(2026, 3, 2, 18, 30)),
]

@pytest.mark.parametrize("frequency,start,send_time,last_sent,expected", NEXT_SEND_CASES)
def test_calculate_next_send(frequency, start, send_time, last_sent, expected):
    assert calculate_next_send(frequency, start, send_time, last_sent) == expected

@pytest.mark.parametrize("frequency", ["daily", "weekly", "biweekly", "bimonthly", "monthly"])
def test_next_future_send_rolls_past_start_forward(frequency):
    result = next_future_send(frequency, "2020-01-01T09:00:00", "09:00")
    assert result > datetime.now()

def test_next_future_send_matches_calculate_for_future_start():
    future = datetime.now().replace(microsecond=0)
    start = future.replace(year=future.year + 1).isoformat()
    assert next_future_send("daily", start, "09:00") == calculate_next_send("daily", start, "09:00")

def test_encrypt_decrypt_roundtrip():
    assert decrypt(encrypt("hunter2")) == "hunter2"

def test_decrypt_passes_through_plaintext():
    # legacy rows may hold unencrypted values; decrypt must return them as-is
    assert decrypt("not-a-fernet-token") == "not-a-fernet-token"

def test_decrypt_none_is_empty_string():
    assert decrypt(None) == ""

def test_sanitize_html_input_strips_scripts():
    out = sanitize_html_input("<script>alert(1)</script><b>hi</b>")
    assert "<script>" not in out
    assert "hi" in out

def test_escape_html_output():
    assert escape_html_output("<b>&</b>") == "&lt;b&gt;&amp;&lt;/b&gt;"

def test_sanitize_html_strips_event_handlers():
    out = sanitize_html('<img src="x" onerror="alert(1)">')
    assert "onerror" not in out

def test_plain_text_decodes_entities():
    from app.emails.assemble import convert_html_to_plain_text
    out = convert_html_to_plain_text("<p>Hi &amp; welcome to <b>Marvel&#39;s</b> show</p>")
    assert "&amp;" not in out and "&#39;" not in out
    assert "Hi & welcome to Marvel's show" in out

def test_plain_text_preserves_link_url():
    from app.emails.assemble import convert_html_to_plain_text
    out = convert_html_to_plain_text('<a href="https://plex.tv/watch">Watch Now</a>')
    assert "Watch Now (https://plex.tv/watch)" in out

def test_plain_text_separates_table_cells_and_lists():
    from app.emails.assemble import convert_html_to_plain_text
    table = convert_html_to_plain_text("<table><tr><td>A</td><td>B</td></tr></table>")
    assert "A" in table and "B" in table and "AB" not in table  # not mashed together
    lst = convert_html_to_plain_text("<ul><li>First</li><li>Second</li></ul>")
    assert "- First" in lst and "- Second" in lst

def test_plain_text_skips_script_style_and_surfaces_alt():
    from app.emails.assemble import convert_html_to_plain_text
    out = convert_html_to_plain_text('<style>.x{}</style><script>bad()</script><img alt="Poster"><p>Body</p>')
    assert "bad()" not in out and ".x{}" not in out
    assert "[Poster]" in out and "Body" in out

def test_plain_text_handles_empty_and_malformed():
    from app.emails.assemble import convert_html_to_plain_text
    assert convert_html_to_plain_text("") == ""
    assert convert_html_to_plain_text(None) == ""
    # unclosed tags must not raise
    assert "bold" in convert_html_to_plain_text("<p>unclosed <b>bold")

def test_ensure_secret_key_persists_and_is_stable(tmp_path, monkeypatch):
    from app import config, crypto

    env_file = tmp_path / ".env"
    env_file.touch()
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("NEWSLETTERR_SECRET_KEY", raising=False)

    first = crypto.ensure_secret_key()
    assert first and f"NEWSLETTERR_SECRET_KEY='{first}'" in env_file.read_text()
    # a second call (e.g. another create_app in the same process) must not rotate it
    assert crypto.ensure_secret_key() == first

    # a "restarted" process (env cleared, file present) gets the same key via load_dotenv;
    # simulate by reading the persisted value back
    monkeypatch.delenv("NEWSLETTERR_SECRET_KEY", raising=False)
    persisted = env_file.read_text().split("NEWSLETTERR_SECRET_KEY='")[1].split("'")[0]
    assert persisted == first

def test_app_secret_key_comes_from_persisted_value(app):
    import os
    assert app.secret_key == os.environ["NEWSLETTERR_SECRET_KEY"]

def test_collection_cards_link_to_plex_when_plex_url_present():
    from email.mime.multipart import MIMEMultipart
    from unittest.mock import patch
    from app.emails.builders.cards import build_individual_item_card_html, build_collection_card_html

    theme_colors = {'card_bg': '#2d2d2d', 'border': '#404040', 'text': '#fff', 'muted_text': '#ccc'}
    msg_root = MIMEMultipart()
    plex_url = 'https://app.plex.tv/web/app#!/server/abc/details?key=/library/metadata/1'

    with patch('app.emails.builders.cards.fetch_and_attach_image', return_value='fakecid123'):
        item = {'title': 'Test Movie', 'year': 2024, 'type': 'movie', 'thumb': '/library/x', 'key': '1', 'plex_url': plex_url}
        html = build_individual_item_card_html(item, theme_colors, msg_root)
        assert html.strip().startswith(f'<a href="{plex_url}"')
        assert html.strip().endswith('</a>')

        item_no_url = dict(item)
        del item_no_url['plex_url']
        html_no_link = build_individual_item_card_html(item_no_url, theme_colors, msg_root)
        assert not html_no_link.strip().startswith('<a ')

        collection = {'title': 'Marvel Collection', 'childCount': 12, 'subtype': 'movie', 'thumb': '/library/y', 'key': '2', 'plex_url': plex_url}
        collection_html = build_collection_card_html(collection, theme_colors, msg_root)
        assert collection_html.strip().startswith(f'<a href="{plex_url}"')

def test_recently_added_days_mode_title_shows_date_range():
    from email.mime.multipart import MIMEMultipart
    from app.emails.builders.recently_added import build_recently_added_html_with_cids

    theme_colors = {'card_bg': '#2d2d2d', 'border': '#404040', 'text': '#fff', 'muted_text': '#ccc'}
    msg_root = MIMEMultipart()
    # no thumb/art candidates -> no poster fetch, no network call
    recent_data = [{'recently_added': [{'title': 'No Poster Show', 'media_type': 'show'}]}]

    html = build_recently_added_html_with_cids(
        recent_data, msg_root, theme_colors,
        max_items=7, recently_added_mode="days"
    )

    since_date = (datetime.now() - timedelta(days=7)).strftime("%-m/%-d/%y")
    end_date = datetime.now().strftime("%-m/%-d/%y")
    assert f"{since_date} - {end_date}" in html
    assert "since" not in html.split("Recently Added")[1].split("</h2>")[0].lower()
