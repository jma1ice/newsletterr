# Golden-master tests for the scheduled send pipeline.
#
# They exercise send_scheduled_email_with_cids end-to-end with a recording
# fake SMTP and stubbed external clients, then compare the normalized MIME
# output against goldens in tests/goldens/. A missing golden is (re)created;
# set UPDATE_GOLDENS=1 to regenerate deliberately after an intended change.

import datetime as datetime_module
import email as email_lib
import json
import smtplib
import sqlite3
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).parent / "goldens"

USERS_FIXTURE = [
    {"user_id": 1, "email": "a@b.c", "is_active": True},
    {"user_id": 2, "email": "d@e.f", "is_active": True},
]

def _tautulli_data_stub(*args, **kwargs):
    # fresh dict per call: the senders mutate ["settings"]
    return {
        "settings": {"server_name": "TestPlex"},
        "stats": [],
        "graph_data": [],
        "recent_data": [],
        "graph_commands": [],
    }

class RecorderSMTP:
    instances = []

    def __init__(self, server, port):
        self.server, self.port = server, int(port)
        self.used_tls = False
        self.logins = []
        self.sent = []  # (from_addr, to_addrs, content)
        RecorderSMTP.instances.append(self)

    def starttls(self):
        self.used_tls = True

    def login(self, username, password):
        self.logins.append((username, password))

    def sendmail(self, from_addr, to_addrs, content):
        self.sent.append((from_addr, list(to_addrs), content))

    def quit(self):
        pass

@pytest.fixture()
def send_env(app, monkeypatch):
    from app import config
    from app.crypto import encrypt
    from app.emails import scheduled

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
    conn.execute("DELETE FROM suppressed_emails")
    conn.execute(
        """UPDATE settings SET
            from_email='news@example.com', alias_email='', reply_to_email='replies@example.com',
            password=?, smtp_username='news@example.com', smtp_server='smtp.example.com',
            smtp_port=465, smtp_protocol='SSL', server_name='TestPlex',
            tautulli_url='http://tt.local', tautulli_api=?, conjurr_url='http://cj.local',
            droppedneedle_url='', droppedneedle_api_key='', from_name='Newsletterr',
            logo_filename='Asset_94x.png', logo_width=80, custom_logo_filename='',
            scheduled_subject_prefix='enabled', send_mode='bcc', recipient_display_name='email',
            login_toggle='disabled', hosted_enabled='disabled', hosted_base_url=''
        WHERE id = 1""",
        (encrypt("smtp-pw"), encrypt("tt-key")),
    )
    conn.execute("INSERT OR REPLACE INTO email_lists (id, name, emails) VALUES (9001, 'golden-list', 'a@b.c, d@e.f')")
    conn.execute(
        "INSERT OR REPLACE INTO email_templates (id, name, selected_items, subject, email_header_title) VALUES (9001, 'golden-plain', ?, 'Monthly News', 'The Header')",
        (json.dumps([{"type": "textblock", "content": "Hello world"}]),),
    )
    conn.execute(
        "INSERT OR REPLACE INTO email_templates (id, name, selected_items, subject, email_header_title) VALUES (9002, 'golden-recs', ?, 'Your Picks', 'The Header')",
        (json.dumps([
            {"type": "textblock", "content": "Personal intro"},
            {"type": "recommendations", "userKey": "1"},
        ]),),
    )
    conn.execute(
        "INSERT OR REPLACE INTO email_schedules (id, name, email_list_id, template_id, frequency, start_date, next_send, date_range, items_count) "
        "VALUES (9001, 'golden-schedule', 9001, 9001, 'weekly', '2026-07-01T09:00:00', '2026-07-08T09:00:00', 7, 10)"
    )
    conn.commit()
    conn.close()

    # deterministic: logo/image fetches fail fast instead of reaching a live server
    monkeypatch.setattr(config, "INTERNAL_BASE_URL", "http://127.0.0.1:9")

    monkeypatch.setattr(scheduled, "capture_chart_images_via_headless", lambda *a, **k: {})
    monkeypatch.setattr(scheduled, "fetch_tautulli_data_for_email", _tautulli_data_stub)
    monkeypatch.setattr(scheduled, "run_tautulli_command", lambda *a, **k: (USERS_FIXTURE, None))
    monkeypatch.setattr(scheduled, "run_conjurr_command", lambda *a, **k: ({1: {}}, None))

    RecorderSMTP.instances = []
    monkeypatch.setattr(smtplib, "SMTP_SSL", RecorderSMTP)
    monkeypatch.setattr(smtplib, "SMTP", RecorderSMTP)

    return scheduled

def _normalize(content):
    msg = email_lib.message_from_string(content)

    cid_map = {}
    parts = []
    html_text = plain_text = ""
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        cid = part.get("Content-ID", "").strip("<>")
        if cid and cid not in cid_map:
            cid_map[cid] = f"CID{len(cid_map)}"
        payload = part.get_payload(decode=True) or b""
        if part.get_content_type() == "text/html":
            html_text = payload.decode("utf-8", "replace")
        elif part.get_content_type() == "text/plain":
            plain_text = payload.decode("utf-8", "replace")
        parts.append({
            "content_type": part.get_content_type(),
            "content_id": cid_map.get(cid, ""),
            "filename": part.get_filename() or "",
            "size": len(payload),
        })

    for real, norm in cid_map.items():
        html_text = html_text.replace(real, norm)

    headers = {k: msg[k] for k in ("Subject", "From", "To", "Reply-To") if msg[k]}
    return {"headers": headers, "parts": parts, "plain": plain_text, "html": html_text}

def _run_and_normalize(scheduled, template_id):
    ok = scheduled.send_scheduled_email_with_cids(9001, 9001, template_id)
    assert ok is True
    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1
    from_addr, to_addrs, content = sends[0]
    logins = [l for inst in RecorderSMTP.instances for l in inst.logins]
    normalized = _normalize(content)
    normalized["envelope"] = {"from": from_addr, "to": to_addrs}
    normalized["login"] = list(logins[0])
    normalized["protocol"] = type(RecorderSMTP.instances[0]).__name__
    return normalized

def _assert_golden(name, normalized):
    import os
    GOLDEN_DIR.mkdir(exist_ok=True)
    path = GOLDEN_DIR / f"{name}.json"
    if not path.exists() or os.environ.get("UPDATE_GOLDENS") == "1":
        path.write_text(json.dumps(normalized, indent=2, sort_keys=True))
    golden = json.loads(path.read_text())
    assert normalized == golden

def test_scheduled_single_email_golden(send_env):
    normalized = _run_and_normalize(send_env, 9001)
    # structural sanity on top of the golden comparison
    assert normalized["headers"]["Subject"] == "[SCHEDULED] Monthly News"
    assert normalized["envelope"]["to"] == ["news@example.com", "a@b.c", "d@e.f"]  # bcc mode
    assert normalized["login"] == ["news@example.com", "smtp-pw"]
    assert "Hello world" in normalized["html"]
    _assert_golden("scheduled_single", normalized)

def test_scheduled_user_email_golden(send_env):
    normalized = _run_and_normalize(send_env, 9002)
    assert normalized["headers"]["Subject"] == "[SCHEDULED] Your Picks"
    # user 2 has no recommendations block -> only user 1's group is sent
    assert normalized["envelope"]["to"] == ["news@example.com", "a@b.c"]
    assert "Personal intro" in normalized["html"]
    _assert_golden("scheduled_user", normalized)

@pytest.fixture()
def hosted_scheduled_env(send_env):
    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "UPDATE settings SET hosted_enabled='enabled', hosted_base_url='https://nl.example.com' WHERE id = 1"
    )
    conn.commit()
    conn.close()
    return send_env

def test_scheduled_single_email_hosted_gives_each_recipient_a_distinct_token(hosted_scheduled_env):
    ok = hosted_scheduled_env.send_scheduled_email_with_cids(9001, 9001, 9001)
    assert ok is True
    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 3  # from_addr + a@b.c + d@e.f, one transaction each

    tokens = set()
    for from_addr, to_addrs, content in sends:
        assert len(to_addrs) == 1
        msg = email_lib.message_from_string(content)
        list_unsub = msg.get("List-Unsubscribe", "")
        assert msg.get("List-Unsubscribe-Post") == "List-Unsubscribe=One-Click"
        assert "/u/" in list_unsub
        tokens.add(list_unsub.split("/u/")[1].split(">")[0])
        html_part = next(p for p in msg.walk() if p.get_content_type() == "text/html")
        assert "https://nl.example.com/newsletter" in html_part.get_payload(decode=True).decode("utf-8")
    assert len(tokens) == 3

@pytest.fixture()
def hosted_links_override_env(send_env):
    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "UPDATE settings SET hosted_enabled='enabled', hosted_base_url='https://nl.example.com', "
        "hosted_links_enabled='enabled', hosted_links_base_url='https://private.example.com' WHERE id = 1"
    )
    conn.commit()
    conn.close()
    return send_env

def test_scheduled_email_uses_separate_links_base_url_for_unsubscribe_and_view_online(hosted_links_override_env):
    ok = hosted_links_override_env.send_scheduled_email_with_cids(9001, 9001, 9001)
    assert ok is True
    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 3

    for from_addr, to_addrs, content in sends:
        msg = email_lib.message_from_string(content)
        list_unsub = msg.get("List-Unsubscribe", "")
        assert "https://private.example.com/u/" in list_unsub
        assert "https://nl.example.com/u/" not in list_unsub
        html_part = next(p for p in msg.walk() if p.get_content_type() == "text/html")
        html = html_part.get_payload(decode=True).decode("utf-8")
        assert "https://private.example.com/newsletter" in html
        assert "https://nl.example.com/newsletter" not in html

def test_scheduled_user_email_hosted_gives_each_recipient_a_distinct_token(hosted_scheduled_env):
    ok = hosted_scheduled_env.send_scheduled_email_with_cids(9001, 9001, 9002)
    assert ok is True
    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 2  # from_addr + a@b.c (only user 1's group matches)

    tokens = set()
    for from_addr, to_addrs, content in sends:
        assert len(to_addrs) == 1
        msg = email_lib.message_from_string(content)
        assert "/u/" in msg.get("List-Unsubscribe", "")
        tokens.add(msg.get("List-Unsubscribe").split("/u/")[1].split(">")[0])
    assert len(tokens) == 2

# --- standard (manual) send paths, driven through the HTTP route

def _fixed_tautulli_data(*args, **kwargs):
    return {
        "settings": {"server_name": "TestPlex", "logo_filename": "Asset_94x.png",
                     "logo_width": 80, "custom_logo_filename": "", "logo_position": "center"},
        "stats": [],
        "graph_data": [],
        "recent_data": [],
        "graph_commands": [],
    }

@pytest.fixture()
def manual_send_env(send_env, client, monkeypatch):
    from app.emails import send as send_mod

    monkeypatch.setattr(send_mod, "get_current_tautulli_data_for_email", _fixed_tautulli_data)
    monkeypatch.setattr(send_mod, "get_droppedneedle_server_stats_cached", lambda *a, **k: None)
    monkeypatch.setattr(send_mod, "get_yearly_wrapped_cached", lambda *a, **k: None)
    monkeypatch.setattr(send_mod, "get_sonarr_coming_soon_cached", lambda *a, **k: None)
    monkeypatch.setattr(send_mod, "get_radarr_coming_soon_cached", lambda *a, **k: None)
    monkeypatch.setattr(send_mod, "get_ombi_requests_cached", lambda *a, **k: None)
    monkeypatch.setattr(send_mod, "get_recommendations_for_users", lambda *a, **k: {"1": {}})
    monkeypatch.setattr(send_mod, "get_droppedneedle_wrapped_for_users", lambda *a, **k: {})
    monkeypatch.setattr(send_mod, "run_tautulli_command", lambda *a, **k: (USERS_FIXTURE, None))

    with client.session_transaction() as sess:
        sess["csrf_token"] = "golden-token"
    return client

def _post_send(client, payload):
    return client.post("/send_email", json=payload, headers={"X-CSRF-Token": "golden-token"})

@pytest.fixture()
def hosted_send_env(manual_send_env):
    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "UPDATE settings SET hosted_enabled='enabled', hosted_base_url='https://nl.example.com' WHERE id = 1"
    )
    conn.commit()
    conn.close()
    return manual_send_env

def test_bcc_send_gives_each_recipient_a_distinct_unsubscribe_token(hosted_send_env):
    client = hosted_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual News", "email_header_title": "The Header",
        "selected_items": [{"type": "textblock", "content": "Manual hello"}],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })
    assert resp.status_code == 200
    assert resp.get_json().get("success") is True

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    # bcc mode + hosted: one SMTP transaction per recipient (incl. the
    # operator's own from_addr copy), not one shared batched transaction
    assert len(sends) == 3

    tokens_by_recipient = {}
    for from_addr, to_addrs, content in sends:
        assert len(to_addrs) == 1
        recipient = to_addrs[0]
        msg = email_lib.message_from_string(content)
        list_unsub = msg.get("List-Unsubscribe", "")
        assert msg.get("List-Unsubscribe-Post") == "List-Unsubscribe=One-Click"
        assert "/u/" in list_unsub
        token = list_unsub.split("/u/")[1].split(">")[0]
        html_part = next(p for p in msg.walk() if p.get_content_type() == "text/html")
        html = html_part.get_payload(decode=True).decode("utf-8")
        assert f"/u/{token}" in html  # body link uses the same token as the header
        tokens_by_recipient[recipient] = token

    assert len(set(tokens_by_recipient.values())) == 3  # all distinct

    from app.tokens import verify_unsubscribe_token
    for recipient, token in tokens_by_recipient.items():
        assert verify_unsubscribe_token(token) == recipient.strip().lower()

def test_recommendations_send_gives_each_recipient_a_distinct_unsubscribe_token(hosted_send_env):
    client = hosted_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual Picks", "email_header_title": "The Header",
        "selected_items": [
            {"type": "textblock", "content": "Manual personal intro"},
            {"type": "recommendations", "userKey": "1"},
        ],
        "custom_html": "", "user_dict": {"1": "a@b.c", "2": "d@e.f"}, "expanded_collections": {},
    })
    assert resp.status_code == 200
    assert resp.get_json().get("success") is True

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    # only user 1's group matches the recommendations block (from_addr + a@b.c)
    assert len(sends) == 2

    tokens = set()
    for from_addr, to_addrs, content in sends:
        assert len(to_addrs) == 1
        msg = email_lib.message_from_string(content)
        list_unsub = msg.get("List-Unsubscribe", "")
        assert "/u/" in list_unsub
        tokens.add(list_unsub.split("/u/")[1].split(">")[0])
    assert len(tokens) == 2

def test_suppressed_recipient_filtered_from_manual_send(manual_send_env):
    from app.store import add_suppressed
    add_suppressed("d@e.f")

    client = manual_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual News", "email_header_title": "The Header",
        "selected_items": [{"type": "textblock", "content": "Manual hello"}],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })
    assert resp.status_code == 200

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1
    _, to_addrs, _ = sends[0]
    assert to_addrs == ["news@example.com", "a@b.c"]  # d@e.f excluded

def test_suppressed_recipient_filtered_from_scheduled_send(send_env):
    from app.store import add_suppressed
    add_suppressed("a@b.c")

    ok = send_env.send_scheduled_email_with_cids(9001, 9001, 9001)
    assert ok is True

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1
    _, to_addrs, _ = sends[0]
    assert to_addrs == ["news@example.com", "d@e.f"]  # a@b.c excluded

def test_bcc_send_without_hosted_mode_is_single_batched_transaction(manual_send_env):
    client = manual_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual News", "email_header_title": "The Header",
        "selected_items": [{"type": "textblock", "content": "Manual hello"}],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })
    assert resp.status_code == 200
    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1
    _, to_addrs, content = sends[0]
    assert len(to_addrs) == 3  # from_addr + 2 recipients, one shared transaction
    assert "List-Unsubscribe" not in content

def test_manual_standard_email_golden(manual_send_env):
    client = manual_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual News", "email_header_title": "The Header",
        "selected_items": [{"type": "textblock", "content": "Manual hello"}],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("success") is True

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1
    from_addr, to_addrs, content = sends[0]
    normalized = _normalize(content)
    normalized["envelope"] = {"from": from_addr, "to": to_addrs}
    normalized["response"] = body
    assert normalized["headers"]["Subject"] == "Manual News"  # no [SCHEDULED] prefix
    assert normalized["envelope"]["to"] == ["news@example.com", "a@b.c", "d@e.f"]
    assert "Manual hello" in normalized["html"]
    _assert_golden("manual_standard", normalized)

def test_manual_recommendations_email_golden(manual_send_env):
    client = manual_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual Picks", "email_header_title": "The Header",
        "selected_items": [
            {"type": "textblock", "content": "Manual personal intro"},
            {"type": "recommendations", "userKey": "1"},
        ],
        "custom_html": "", "user_dict": {"1": "a@b.c", "2": "d@e.f"}, "expanded_collections": {},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("success") is True

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1  # only user 1 matches the recommendations block
    from_addr, to_addrs, content = sends[0]
    normalized = _normalize(content)
    normalized["envelope"] = {"from": from_addr, "to": to_addrs}
    normalized["response"] = body
    assert normalized["envelope"]["to"] == ["news@example.com", "a@b.c"]
    assert "Manual personal intro" in normalized["html"]
    _assert_golden("manual_recommendations", normalized)

def test_manual_yearly_wrapped_email_golden(manual_send_env, monkeypatch):
    from app.emails import send as send_mod

    yearly_wrapped_fixture = [
        {"stat_title": "Most Watched Movies", "rows": [{"title": "Dune", "total_plays": 42}]},
        {"stat_title": "Most Watched TV Shows", "rows": [{"title": "Severance", "total_plays": 30}]},
    ]
    monkeypatch.setattr(send_mod, "get_yearly_wrapped_cached", lambda *a, **k: yearly_wrapped_fixture)

    client = manual_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual Wrapped", "email_header_title": "The Header",
        "selected_items": [
            {"type": "textblock", "content": "Here's your year"},
            {"type": "yearly_wrapped", "id": "yearly-wrapped"},
        ],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("success") is True

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1
    from_addr, to_addrs, content = sends[0]
    normalized = _normalize(content)
    normalized["envelope"] = {"from": from_addr, "to": to_addrs}
    normalized["response"] = body
    assert "Dune" in normalized["html"]
    assert "Severance" in normalized["html"]
    assert "Wrapped" in normalized["html"]
    _assert_golden("manual_yearly_wrapped", normalized)

SONARR_EPISODES_FIXTURE = [
    {
        "series": {"title": "Test Show", "year": 2026, "images": [{"coverType": "poster", "url": "/mediacover/1/poster.jpg"}]},
        "seasonNumber": 1, "episodeNumber": 2, "title": "Pilot Returns",
        "airDateUtc": "2026-07-15T00:00:00Z",
    },
]

SONARR_GROUPED_FIXTURE = [
    # A full-season drop: three episodes of the same series/season on one day.
    {
        "series": {"id": 10, "title": "Binge Show", "year": 2026, "images": [{"coverType": "poster", "url": "/mediacover/10/poster.jpg"}]},
        "seasonNumber": 1, "episodeNumber": 1, "title": "Chapter One",
        "airDate": "2026-07-15", "airDateUtc": "2026-07-15T00:00:00Z",
    },
    {
        "series": {"id": 10, "title": "Binge Show", "year": 2026, "images": [{"coverType": "poster", "url": "/mediacover/10/poster.jpg"}]},
        "seasonNumber": 1, "episodeNumber": 2, "title": "Chapter Two",
        "airDate": "2026-07-15", "airDateUtc": "2026-07-15T00:00:00Z",
    },
    {
        "series": {"id": 10, "title": "Binge Show", "year": 2026, "images": [{"coverType": "poster", "url": "/mediacover/10/poster.jpg"}]},
        "seasonNumber": 1, "episodeNumber": 3, "title": "Chapter Three",
        "airDate": "2026-07-15", "airDateUtc": "2026-07-15T00:00:00Z",
    },
    # A standalone episode of a different show that must not be grouped.
    {
        "series": {"id": 20, "title": "Solo Show", "year": 2025, "images": [{"coverType": "poster", "url": "/mediacover/20/poster.jpg"}]},
        "seasonNumber": 2, "episodeNumber": 5, "title": "On Its Own",
        "airDate": "2026-07-16", "airDateUtc": "2026-07-16T00:00:00Z",
    },
]

RADARR_MOVIES_FIXTURE = [
    {
        "title": "Test Movie", "year": 2026, "digitalRelease": "2026-07-20",
        "images": [{"coverType": "poster", "url": "/mediacover/2/poster.jpg"}],
    },
    # Already released (all dates before the frozen 2026-07-09) -> filtered out.
    {
        "title": "Released Movie", "year": 2025, "digitalRelease": "2025-01-01",
        "inCinemas": "2024-06-01", "physicalRelease": "2025-03-01",
    },
    # Already downloaded (hasFile) even though the date is upcoming -> filtered out.
    {
        "title": "Owned Movie", "year": 2026, "digitalRelease": "2026-08-01", "hasFile": True,
    },
]

class _FixedDatetime(datetime_module.datetime):
    """A frozen 'now' so relative-date text ('in N days') in coming-soon
    golden fixtures doesn't drift with the wall clock."""
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 7, 9, 12, 0, 0, tzinfo=tz)

def _freeze_coming_soon_clock(monkeypatch, coming_soon_mod):
    # format_relative_date lives in card_grid (shared by coming_soon.py and
    # ombi_requests.py), so its 'now' must be frozen there too, not just in
    # coming_soon_mod's own datetime (used by upcoming_release_date/_parse_release_date).
    from app.emails.builders import card_grid as card_grid_mod
    monkeypatch.setattr(coming_soon_mod, "datetime", _FixedDatetime)
    monkeypatch.setattr(card_grid_mod, "datetime", _FixedDatetime)

def test_manual_sonarr_coming_soon_email_golden(manual_send_env, monkeypatch):
    from app.emails import send as send_mod
    from app.emails.builders import coming_soon as coming_soon_mod

    monkeypatch.setattr(send_mod, "get_sonarr_coming_soon_cached", lambda *a, **k: SONARR_EPISODES_FIXTURE)
    monkeypatch.setattr(coming_soon_mod, "fetch_and_attach_image", lambda *a, **k: None)
    _freeze_coming_soon_clock(monkeypatch, coming_soon_mod)

    client = manual_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual Coming Soon TV", "email_header_title": "The Header",
        "selected_items": [
            {"type": "textblock", "content": "What's coming up"},
            {"type": "sonarr_coming_soon", "id": "sonarr-coming-soon"},
        ],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("success") is True

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1
    from_addr, to_addrs, content = sends[0]
    normalized = _normalize(content)
    normalized["envelope"] = {"from": from_addr, "to": to_addrs}
    normalized["response"] = body
    assert "Test Show" in normalized["html"]
    assert "S01E02" in normalized["html"]
    _assert_golden("manual_sonarr_coming_soon", normalized)

def test_manual_sonarr_coming_soon_grouped_email_golden(manual_send_env, monkeypatch):
    from app.emails import send as send_mod
    from app.emails.builders import coming_soon as coming_soon_mod

    monkeypatch.setattr(send_mod, "get_sonarr_coming_soon_cached", lambda *a, **k: SONARR_GROUPED_FIXTURE)
    monkeypatch.setattr(coming_soon_mod, "fetch_and_attach_image", lambda *a, **k: None)
    _freeze_coming_soon_clock(monkeypatch, coming_soon_mod)

    client = manual_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Grouped Coming Soon TV", "email_header_title": "The Header",
        "selected_items": [
            {"type": "sonarr_coming_soon", "id": "sonarr-coming-soon"},
        ],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("success") is True

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1
    from_addr, to_addrs, content = sends[0]
    normalized = _normalize(content)
    normalized["envelope"] = {"from": from_addr, "to": to_addrs}
    normalized["response"] = body
    # The three same-day season-1 episodes collapse into one grouped card.
    assert "Season 1 (3 episodes)" in normalized["html"]
    assert "S01E0" not in normalized["html"]  # individual grouped episodes are hidden
    assert "Binge Show" in normalized["html"]
    # The standalone episode of another show keeps its single-card form.
    assert "Solo Show" in normalized["html"]
    assert "S02E05" in normalized["html"]
    _assert_golden("manual_sonarr_coming_soon_grouped", normalized)

def test_manual_radarr_coming_soon_email_golden(manual_send_env, monkeypatch):
    from app.emails import send as send_mod
    from app.emails.builders import coming_soon as coming_soon_mod

    monkeypatch.setattr(send_mod, "get_radarr_coming_soon_cached", lambda *a, **k: RADARR_MOVIES_FIXTURE)
    monkeypatch.setattr(coming_soon_mod, "fetch_and_attach_image", lambda *a, **k: None)
    _freeze_coming_soon_clock(monkeypatch, coming_soon_mod)

    client = manual_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual Coming Soon Movies", "email_header_title": "The Header",
        "selected_items": [
            {"type": "textblock", "content": "What's coming up"},
            {"type": "radarr_coming_soon", "id": "radarr-coming-soon"},
        ],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("success") is True

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1
    from_addr, to_addrs, content = sends[0]
    normalized = _normalize(content)
    normalized["envelope"] = {"from": from_addr, "to": to_addrs}
    normalized["response"] = body
    assert "Test Movie" in normalized["html"]
    assert "2026" in normalized["html"]
    # Released and already-owned movies are filtered out before rendering.
    assert "Released Movie" not in normalized["html"]
    assert "Owned Movie" not in normalized["html"]
    _assert_golden("manual_radarr_coming_soon", normalized)

OMBI_REQUESTS_FIXTURE = {
    "movies": [
        {
            "title": "Requested Movie", "releaseDate": "2026-01-01T00:00:00Z",
            "posterPath": "/poster123.jpg",
            "approved": False, "available": False, "denied": False,
            "requestedDate": "2026-07-05T00:00:00Z",
        },
        # Already fulfilled -> filtered out before rendering.
        {
            "title": "Fulfilled Movie", "releaseDate": "2025-01-01T00:00:00Z",
            "approved": True, "available": True, "denied": False,
            "requestedDate": "2026-06-01T00:00:00Z",
        },
    ],
    "tv": [],
}

def test_manual_ombi_requests_email_golden(manual_send_env, monkeypatch):
    from app.emails import send as send_mod
    from app.emails.builders import coming_soon as coming_soon_mod
    from app.emails.builders import ombi_requests as ombi_requests_mod

    monkeypatch.setattr(send_mod, "get_ombi_requests_cached", lambda *a, **k: OMBI_REQUESTS_FIXTURE)
    monkeypatch.setattr(ombi_requests_mod, "fetch_and_attach_image", lambda *a, **k: None)
    _freeze_coming_soon_clock(monkeypatch, coming_soon_mod)

    client = manual_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual Recent Requests", "email_header_title": "The Header",
        "selected_items": [
            {"type": "textblock", "content": "What people are asking for"},
            {"type": "ombi_requests", "id": "ombi-requests"},
        ],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("success") is True

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1
    from_addr, to_addrs, content = sends[0]
    normalized = _normalize(content)
    normalized["envelope"] = {"from": from_addr, "to": to_addrs}
    normalized["response"] = body
    assert "Requested Movie" in normalized["html"]
    assert "Pending Approval" in normalized["html"]
    # Already-fulfilled requests are filtered out before rendering.
    assert "Fulfilled Movie" not in normalized["html"]
    _assert_golden("manual_ombi_requests", normalized)

def test_manual_coming_soon_degrades_when_only_one_service_configured(manual_send_env, monkeypatch):
    from app.emails import send as send_mod
    from app.emails.builders import coming_soon as coming_soon_mod

    monkeypatch.setattr(send_mod, "get_sonarr_coming_soon_cached", lambda *a, **k: SONARR_EPISODES_FIXTURE)
    monkeypatch.setattr(send_mod, "get_radarr_coming_soon_cached", lambda *a, **k: None)
    monkeypatch.setattr(coming_soon_mod, "fetch_and_attach_image", lambda *a, **k: None)
    _freeze_coming_soon_clock(monkeypatch, coming_soon_mod)

    client = manual_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Partial Coming Soon", "email_header_title": "The Header",
        "selected_items": [
            {"type": "sonarr_coming_soon", "id": "sonarr-coming-soon"},
            {"type": "radarr_coming_soon", "id": "radarr-coming-soon"},
        ],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body.get("success") is True

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1
    from_addr, to_addrs, content = sends[0]
    normalized = _normalize(content)
    assert "Test Show" in normalized["html"]
    assert "Coming Soon (Movies)" not in normalized["html"]

def test_resend_from_history_replays_stored_mime(manual_send_env):
    from app.store import record_email_history

    client = manual_send_env
    stored_mime = (
        "Subject: Original Subject\r\n"
        "From: news@example.com\r\n"
        "To: a@b.c\r\n"
        "\r\n"
        "<html><body>Original stored content</body></html>"
    )
    record_email_history("Original Subject", "a@b.c, d@e.f", stored_mime, 1.0, 2, "Manual")

    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    history_id = conn.execute("SELECT id FROM email_history ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()

    resp = client.post(f"/email_history/{history_id}/resend", headers={"X-CSRF-Token": "golden-token"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) == 1
    from_addr, to_addrs, content = sends[0]
    assert from_addr == "news@example.com"
    assert sorted(to_addrs) == ["a@b.c", "d@e.f"]
    assert content == stored_mime  # replayed verbatim, not rebuilt

    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    rows = conn.execute("SELECT subject, email_content FROM email_history ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert rows[0] == "Original Subject"
    assert rows[1] == stored_mime

def test_resend_from_history_rejects_failed_send(manual_send_env):
    from app.store import record_email_history

    client = manual_send_env
    record_email_history("Never sent", "a@b.c", "", 0, 1, "Manual", status="failed", error="SMTP down")

    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    history_id = conn.execute("SELECT id FROM email_history ORDER BY id DESC LIMIT 1").fetchone()[0]
    conn.close()

    resp = client.post(f"/email_history/{history_id}/resend", headers={"X-CSRF-Token": "golden-token"})
    assert resp.status_code == 500
    body = resp.get_json()
    assert body["status"] == "error"
    assert "failed" in body["message"].lower()

# --- hosted newsletter page (/newsletter)

def test_hosted_newsletter_disabled_by_default(manual_send_env):
    client = manual_send_env
    resp = client.get("/newsletter")
    assert resp.status_code == 404

def test_hosted_newsletter_empty_before_any_hosted_send(hosted_send_env):
    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("DELETE FROM email_history")
    conn.commit()
    conn.close()

    client = hosted_send_env
    resp = client.get("/newsletter")
    assert resp.status_code == 200
    assert b"No newsletter yet" in resp.data

def test_hosted_newsletter_shows_most_recent_standard_send(hosted_send_env):
    client = hosted_send_env
    _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual News", "email_header_title": "The Header",
        "selected_items": [{"type": "textblock", "content": "Manual hello"}],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })

    resp = client.get("/newsletter")
    assert resp.status_code == 200
    assert b"Manual hello" in resp.data
    # the hosted copy must never carry a real per-recipient unsubscribe token
    assert b"/u/__UNSUB_TOKEN_" not in resp.data
    assert b"List-Unsubscribe" not in resp.data

def test_hosted_newsletter_never_shows_personalized_recommendations_send(hosted_send_env):
    client = hosted_send_env
    _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual Picks", "email_header_title": "The Header",
        "selected_items": [
            {"type": "textblock", "content": "Manual personal intro"},
            {"type": "recommendations", "userKey": "1"},
        ],
        "custom_html": "", "user_dict": {"1": "a@b.c", "2": "d@e.f"}, "expanded_collections": {},
    })

    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute("SELECT hosted_html FROM email_history ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row[0] is None

    resp = client.get("/newsletter")
    assert resp.status_code == 200
    assert b"Manual personal intro" not in resp.data  # personalized content never leaks to the public page

def test_hosted_newsletter_never_populated_for_test_sends(hosted_send_env):
    client = hosted_send_env
    resp = client.post("/send_test_email", json={
        "subject": "Manual News", "email_header_title": "The Header",
        "selected_items": [{"type": "textblock", "content": "Test body"}],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    }, headers={"X-CSRF-Token": "golden-token"})
    assert resp.status_code == 200

    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute("SELECT hosted_html FROM email_history ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row[0] is None

# --- hosted images

class _FakeImageResponse:
    def __init__(self, content=b"\x89PNG\r\n\x1a\nfake-bytes-padded-out-past-the-100-byte-minimum-size-check-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", content_type="image/png"):
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.status_code = 200
    def raise_for_status(self):
        pass

@pytest.fixture()
def hosted_images_send_env(hosted_send_env, monkeypatch):
    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET hosted_images_enabled='enabled' WHERE id = 1")
    conn.commit()
    conn.close()

    from app.emails import images as images_mod
    monkeypatch.setattr(images_mod, "safe_get", lambda *a, **k: _FakeImageResponse())
    return hosted_send_env

def test_manual_standard_email_hosted_images_golden(hosted_images_send_env):
    client = hosted_images_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual News", "email_header_title": "The Header",
        "selected_items": [
            {"type": "textblock", "content": "Manual hello"},
            {"type": "image", "src": "https://example.com/test.png", "width": 400, "align": "center"},
        ],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })
    assert resp.status_code == 200
    assert resp.get_json().get("success") is True

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    assert len(sends) >= 1
    _, _, content = sends[0]
    normalized = _normalize(content)
    assert "https://nl.example.com/i/" in normalized["html"]
    # no image MIME parts attached, everything went hosted, not CID
    image_parts = [p for p in normalized["parts"] if p["content_type"].startswith("image/")]
    assert image_parts == []

def test_hosted_image_write_failure_falls_back_to_cid(hosted_images_send_env, monkeypatch):
    from app.emails import images as images_mod
    monkeypatch.setattr(images_mod, "save_hosted_image", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))

    client = hosted_images_send_env
    resp = _post_send(client, {
        "to_emails": "a@b.c, d@e.f", "subject": "Manual News", "email_header_title": "The Header",
        "selected_items": [
            {"type": "image", "src": "https://example.com/test.png", "width": 400, "align": "center"},
        ],
        "custom_html": "", "user_dict": {}, "expanded_collections": {},
    })
    assert resp.status_code == 200

    sends = [s for inst in RecorderSMTP.instances for s in inst.sent]
    _, _, content = sends[0]
    normalized = _normalize(content)
    assert "cid:" in normalized["html"]
    assert "https://nl.example.com/i/" not in normalized["html"]
    image_parts = [p for p in normalized["parts"] if p["content_type"].startswith("image/")]
    assert len(image_parts) >= 1
