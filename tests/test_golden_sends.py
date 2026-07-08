# Golden-master tests for the scheduled send pipeline.
#
# They exercise send_scheduled_email_with_cids end-to-end with a recording
# fake SMTP and stubbed external clients, then compare the normalized MIME
# output against goldens in tests/goldens/. A missing golden is (re)created;
# set UPDATE_GOLDENS=1 to regenerate deliberately after an intended change.

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
    conn.execute(
        """UPDATE settings SET
            from_email='news@example.com', alias_email='', reply_to_email='replies@example.com',
            password=?, smtp_username='news@example.com', smtp_server='smtp.example.com',
            smtp_port=465, smtp_protocol='SSL', server_name='TestPlex',
            tautulli_url='http://tt.local', tautulli_api=?, conjurr_url='http://cj.local',
            droppedneedle_url='', droppedneedle_api_key='', from_name='Newsletterr',
            logo_filename='Asset_94x.png', logo_width=80, custom_logo_filename='',
            scheduled_subject_prefix='enabled', send_mode='bcc', recipient_display_name='email',
            login_toggle='disabled'
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
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://127.0.0.1:9")

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
    monkeypatch.setattr(send_mod, "get_recommendations_for_users", lambda *a, **k: {"1": {}})
    monkeypatch.setattr(send_mod, "get_droppedneedle_wrapped_for_users", lambda *a, **k: {})
    monkeypatch.setattr(send_mod, "run_tautulli_command", lambda *a, **k: (USERS_FIXTURE, None))

    with client.session_transaction() as sess:
        sess["csrf_token"] = "golden-token"
    return client

def _post_send(client, payload):
    return client.post("/send_email", json=payload, headers={"X-CSRF-Token": "golden-token"})

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
