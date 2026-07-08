from datetime import datetime

import pytest

from app.crypto import decrypt, encrypt
from app.security import escape_html_output, sanitize_html, sanitize_html_input
from app.store import calculate_next_send

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
    # bimonthly (1st/15th cadence when start day <= 15)
    ("bimonthly", "2026-03-05T09:00:00", "09:00", None, datetime(2026, 3, 15, 9, 0)),
    ("bimonthly", "2026-03-05T09:00:00", "09:00", "2026-03-20T09:00:00", datetime(2026, 4, 1, 9, 0)),
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
