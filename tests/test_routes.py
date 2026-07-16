import json

def _post_json(client, token, path, payload, method="post"):
    return getattr(client, method)(
        path,
        data=json.dumps(payload),
        content_type="application/json",
        headers={"X-CSRF-Token": token},
    )

# --- CSRF

def test_json_post_without_csrf_is_rejected(client, seeded_settings):
    resp = client.post("/email_lists", data=json.dumps({"name": "x", "emails": "a@b.c"}),
                       content_type="application/json")
    assert resp.status_code == 400

def test_json_post_with_wrong_csrf_is_rejected(csrf_client):
    client, _ = csrf_client
    resp = client.post("/email_lists", data=json.dumps({"name": "x", "emails": "a@b.c"}),
                       content_type="application/json", headers={"X-CSRF-Token": "wrong"})
    assert resp.status_code == 400

def test_clear_cache_requires_csrf(client, seeded_settings):
    assert client.post("/clear_cache").status_code == 400

def test_delete_routes_require_csrf(csrf_client):
    client, token = csrf_client
    # without a token the DELETE endpoints must be rejected
    assert client.delete("/email_lists/1").status_code == 400
    assert client.delete("/email_templates/1").status_code == 400
    assert client.delete("/scheduling/1").status_code == 400
    assert client.delete("/suppressed_emails/1").status_code == 400

# --- input validation returns 400, not 500

def test_send_email_rejects_non_json_body(csrf_client):
    client, token = csrf_client
    resp = client.post("/send_email", data="not json", content_type="application/json",
                       headers={"X-CSRF-Token": token})
    assert resp.status_code == 400

def test_send_email_rejects_missing_fields(csrf_client):
    client, token = csrf_client
    resp = _post_json(client, token, "/send_email", {"subject": "hi"})  # no to_emails
    assert resp.status_code == 400

def test_send_test_email_requires_from_address(csrf_client, app):
    client, token = csrf_client
    import sqlite3
    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET from_email = '' WHERE id = 1")
    conn.commit()
    conn.close()
    resp = _post_json(client, token, "/send_test_email", {"subject": "hi", "selected_items": []})
    assert resp.status_code == 400  # no From address configured

def test_pull_stats_without_tautulli_returns_400(csrf_client, seeded_settings):
    client, token = csrf_client
    import sqlite3
    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET tautulli_url = '' WHERE id = 1")
    conn.commit()
    conn.close()
    resp = _post_json(client, token, "/pull_stats", {})
    assert resp.status_code == 400  # was a 500 crash on None.rstrip

def test_schedule_create_missing_fields_returns_400(csrf_client):
    client, token = csrf_client
    resp = _post_json(client, token, "/scheduling/create", {"name": "x"})
    assert resp.status_code == 400

# --- email list CRUD

def test_email_list_crud(csrf_client):
    client, token = csrf_client

    resp = _post_json(client, token, "/email_lists", {"name": "testers", "emails": "a@b.c, d@e.f"})
    assert resp.status_code == 200 and resp.get_json()["status"] == "success"

    lists = client.get("/email_lists").get_json()["lists"]
    ours = [l for l in lists if l["name"] == "testers"]
    assert len(ours) == 1

    resp = client.delete(f"/email_lists/{ours[0]['id']}", headers={"X-CSRF-Token": token})
    assert resp.get_json()["status"] == "success"
    lists = client.get("/email_lists").get_json()["lists"]
    assert not [l for l in lists if l["name"] == "testers"]

def test_email_list_requires_name_and_emails(csrf_client):
    client, token = csrf_client
    assert _post_json(client, token, "/email_lists", {"name": "", "emails": "a@b.c"}).status_code == 400
    assert _post_json(client, token, "/email_lists", {"name": "x", "emails": ""}).status_code == 400

# --- suppressed (unsubscribed) recipients

def test_suppressed_emails_list_and_remove(csrf_client):
    client, token = csrf_client
    from app.store import add_suppressed
    add_suppressed("bye@example.com")

    rows = client.get("/suppressed_emails").get_json()["suppressed"]
    ours = [r for r in rows if r["email"] == "bye@example.com"]
    assert len(ours) == 1

    resp = client.delete(f"/suppressed_emails/{ours[0]['id']}", headers={"X-CSRF-Token": token})
    assert resp.get_json()["status"] == "success"
    rows = client.get("/suppressed_emails").get_json()["suppressed"]
    assert not [r for r in rows if r["email"] == "bye@example.com"]

# --- template CRUD

def test_email_template_crud(csrf_client):
    client, token = csrf_client

    payload = {"name": "tpl-1", "selected_items": '[{"type": "stats"}]', "subject": "Hello"}
    assert _post_json(client, token, "/email_templates", payload).get_json()["status"] == "success"

    templates = client.get("/email_templates").get_json()
    ours = [t for t in templates if t["name"] == "tpl-1"]
    assert len(ours) == 1 and ours[0]["subject"] == "Hello"

    # same name updates rather than duplicates
    payload["subject"] = "Hello v2"
    assert "updated" in _post_json(client, token, "/email_templates", payload).get_json()["message"]
    templates = client.get("/email_templates").get_json()
    ours = [t for t in templates if t["name"] == "tpl-1"]
    assert len(ours) == 1 and ours[0]["subject"] == "Hello v2"

    assert client.delete(f"/email_templates/{ours[0]['id']}", headers={"X-CSRF-Token": token}).get_json()["status"] == "success"

# --- schedule CRUD

def _make_list_and_template(client, token):
    _post_json(client, token, "/email_lists", {"name": "sched-list", "emails": "a@b.c"})
    list_id = [l for l in client.get("/email_lists").get_json()["lists"] if l["name"] == "sched-list"][0]["id"]
    _post_json(client, token, "/email_templates", {"name": "sched-tpl", "selected_items": "[]"})
    tpl_id = [t for t in client.get("/email_templates").get_json() if t["name"] == "sched-tpl"][0]["id"]
    return list_id, tpl_id

def test_schedule_crud(csrf_client, app):
    client, token = csrf_client
    list_id, tpl_id = _make_list_and_template(client, token)

    resp = _post_json(client, token, "/scheduling/create", {
        "name": "weekly test", "email_list_id": list_id, "template_id": tpl_id,
        "frequency": "weekly", "start_date": "2026-07-06T09:00:00", "send_time": "09:00",
    })
    assert resp.get_json()["status"] == "success"

    from app.store import get_email_schedules
    ours = [s for s in get_email_schedules() if s["name"] == "weekly test"]
    assert len(ours) == 1
    schedule_id = ours[0]["id"]

    resp = _post_json(client, token, f"/scheduling/{schedule_id}/toggle", {"is_active": False})
    assert resp.get_json()["status"] == "success"
    assert not [s for s in get_email_schedules() if s["id"] == schedule_id][0]["is_active"]

    resp = _post_json(client, token, f"/scheduling/{schedule_id}", {
        "name": "weekly test v2", "email_list_id": list_id, "template_id": tpl_id,
        "frequency": "monthly", "start_date": "2026-07-06T09:00:00",
    }, method="put")
    assert resp.get_json()["status"] == "success"
    assert [s for s in get_email_schedules() if s["id"] == schedule_id][0]["name"] == "weekly test v2"

    resp = client.delete(f"/scheduling/{schedule_id}", headers={"X-CSRF-Token": token})
    assert resp.get_json()["status"] == "success"

# --- settings save

SETTINGS_FORM = {
    "from_email": "news@example.com", "alias_email": "", "reply_to_email": "",
    "password": "smtp-pass", "smtp_username": "news@example.com",
    "smtp_server": "smtp.example.com", "smtp_port": "465", "smtp_protocol": "SSL",
    "server_name": "TestPlex", "plex_url": "", "tautulli_url": "", "tautulli_api": "",
    "conjurr_url": "", "droppedneedle_url": "", "droppedneedle_api_key": "",
    "logo_filename": "Asset_94x.png", "logo_width": "480", "from_name": "Newsletterr",
    "email_theme": "newsletterr_blue", "login_toggle": "disabled",
    "nl_username": "", "nl_password": "",
}

def test_settings_save_and_reload(csrf_client, app):
    client, token = csrf_client
    resp = client.post("/settings", data={**SETTINGS_FORM, "csrf_token": token})
    assert resp.status_code == 302
    assert "Settings+saved" in resp.headers["Location"] or "Settings%20saved" in resp.headers["Location"]

    import sqlite3
    from app import config
    from app.crypto import decrypt
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute("SELECT server_name, smtp_port, password FROM settings WHERE id = 1").fetchone()
    conn.close()
    assert row[0] == "TestPlex"
    assert str(row[1]) == "465"
    assert decrypt(row[2]) == "smtp-pass"  # stored encrypted, decrypts to the submitted value

    # with from_email configured, index renders instead of redirecting
    assert client.get("/").status_code == 200

def test_settings_post_without_csrf_is_rejected(client, seeded_settings):
    assert client.post("/settings", data=SETTINGS_FORM).status_code == 400

def test_secrets_never_rendered_to_browser(csrf_client, app):
    client, token = csrf_client
    # save a config with distinctive secret values
    form = {**SETTINGS_FORM, "csrf_token": token, "password": "SECRET-smtp-pw",
            "tautulli_url": "http://tt.local", "tautulli_api": "SECRET-tt-key"}
    client.post("/settings", data=form)

    settings_html = client.get("/settings").get_data(as_text=True)
    assert "SECRET-smtp-pw" not in settings_html
    assert "SECRET-tt-key" not in settings_html
    # the placeholder proves the field knows a value is stored without leaking it
    assert "leave blank to keep" in settings_html

    index_html = client.get("/").get_data(as_text=True)
    assert "SECRET-tt-key" not in index_html

def test_blank_secret_submission_keeps_existing(csrf_client, app):
    client, token = csrf_client
    client.post("/settings", data={**SETTINGS_FORM, "csrf_token": token, "password": "keep-me"})
    # resubmit with blank password (as the write-only field does)
    client.post("/settings", data={**SETTINGS_FORM, "csrf_token": token, "password": ""})

    import sqlite3
    from app import config
    from app.crypto import decrypt
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute("SELECT password FROM settings WHERE id = 1").fetchone()
    conn.close()
    assert decrypt(row[0]) == "keep-me"  # not clobbered to empty

# --- connection test endpoints fall back to saved credentials

def test_connection_test_falls_back_to_saved_key(client, app, monkeypatch):
    # Saved-key fallback: password fields render blank ("Saved - leave blank
    # to keep"), so a blank api_key in the POST must use the stored value
    # rather than erroring "API key is required".
    import sqlite3
    from app import config
    from app.crypto import encrypt
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "UPDATE settings SET tautulli_url = ?, tautulli_api = ? WHERE id = 1",
        ("http://tt.local", encrypt("saved-tt-key")),
    )
    conn.commit()
    conn.close()

    captured = {}
    def fake_test(url, api_key):
        captured["url"] = url
        captured["api_key"] = api_key
        return {"status": "ok", "message": "Connected"}
    from app.blueprints import api
    monkeypatch.setattr(api, "test_tautulli_connection", fake_test)

    resp = client.post("/api/test/tautulli", data=json.dumps({"url": "", "api_key": ""}),
                       content_type="application/json")
    assert resp.status_code == 200
    assert captured["url"] == "http://tt.local"
    assert captured["api_key"] == "saved-tt-key"

# --- auth gate (uses an unauthenticated client against the seeded admin)

def test_auth_gate_blocks_and_login_flow_works(anon_client, login_enabled):
    creds = login_enabled
    client = anon_client

    resp = client.get("/settings")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]

    login_page = client.get("/login")
    assert login_page.status_code == 200

    with client.session_transaction() as sess:
        token = sess["csrf_token"]

    resp = client.post("/login", data={"csrf_token": token, "username": creds["username"],
                                       "password": "wrong-password"})
    assert b"Invalid credentials" in resp.data

    resp = client.post("/login", data={"csrf_token": token, "username": creds["username"],
                                       "password": creds["password"]})
    assert resp.status_code == 302

    assert client.get("/settings").status_code == 200

    resp = client.get("/logout")
    assert resp.status_code == 302
    resp = client.get("/settings")
    assert resp.status_code == 302 and "/login" in resp.headers["Location"]
