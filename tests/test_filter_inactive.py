# Unit tests for the Tautulli inactivity recipient filter (app.emails.send.filter_inactive).

import time


def _patch_tautulli(monkeypatch, users, table):
    from app.emails import send as send_mod

    calls = {"get_users": users, "get_users_table": table}

    def fake_run(base_url, api_key, command, section_id, error, *a, **k):
        return calls.get(command, None), None

    monkeypatch.setattr(send_mod, "run_tautulli_command", fake_run)
    return send_mod


BASE_SETTINGS = {
    "tautulli_url": "http://tt.local",
    "tautulli_api": "key",
    "exclude_inactive_days": 30,
}


def test_zero_days_is_passthrough_without_api_call(monkeypatch):
    from app.emails import send as send_mod

    def boom(*a, **k):
        raise AssertionError("Tautulli should not be called when filtering is off")

    monkeypatch.setattr(send_mod, "run_tautulli_command", boom)
    kept, excluded = send_mod.filter_inactive(
        ["a@b.c"], {**BASE_SETTINGS, "exclude_inactive_days": 0}
    )
    assert kept == ["a@b.c"]
    assert excluded == []


def test_inactive_recipient_excluded(monkeypatch):
    now = time.time()
    users = [{"user_id": 1, "email": "recent@b.c"}, {"user_id": 2, "email": "stale@b.c"}]
    table = {"data": [
        {"user_id": 1, "last_seen": now - 5 * 86400},    # active
        {"user_id": 2, "last_seen": now - 400 * 86400},  # inactive
    ]}
    send_mod = _patch_tautulli(monkeypatch, users, table)

    kept, excluded = send_mod.filter_inactive(["recent@b.c", "stale@b.c"], BASE_SETTINGS)
    assert kept == ["recent@b.c"]
    assert excluded == ["stale@b.c"]


def test_never_streamed_excluded(monkeypatch):
    users = [{"user_id": 3, "email": "never@b.c"}]
    table = {"data": [{"user_id": 3, "last_seen": None}]}
    send_mod = _patch_tautulli(monkeypatch, users, table)

    kept, excluded = send_mod.filter_inactive(["never@b.c"], BASE_SETTINGS)
    assert kept == []
    assert excluded == ["never@b.c"]


def test_unknown_email_kept(monkeypatch):
    users = [{"user_id": 1, "email": "known@b.c"}]
    table = {"data": [{"user_id": 1, "last_seen": time.time() - 400 * 86400}]}
    send_mod = _patch_tautulli(monkeypatch, users, table)

    # manually-added address not present in Tautulli is kept
    kept, excluded = send_mod.filter_inactive(["stranger@x.y"], BASE_SETTINGS)
    assert kept == ["stranger@x.y"]
    assert excluded == []


def test_case_insensitive_match(monkeypatch):
    users = [{"user_id": 1, "email": "Mixed@Case.Com"}]
    table = {"data": [{"user_id": 1, "last_seen": time.time() - 400 * 86400}]}
    send_mod = _patch_tautulli(monkeypatch, users, table)

    kept, excluded = send_mod.filter_inactive(["MIXED@case.com"], BASE_SETTINGS)
    assert excluded == ["MIXED@case.com"]
    assert kept == []


def test_api_failure_is_passthrough(monkeypatch):
    from app.emails import send as send_mod

    def fail(*a, **k):
        return None, "Tautulli Connection Error"

    monkeypatch.setattr(send_mod, "run_tautulli_command", fail)
    kept, excluded = send_mod.filter_inactive(["a@b.c", "d@e.f"], BASE_SETTINGS)
    assert kept == ["a@b.c", "d@e.f"]
    assert excluded == []


def test_email_directly_on_table_rows(monkeypatch):
    # some Tautulli versions include email on get_users_table rows directly
    users = [{"user_id": 1, "email": ""}]
    table = {"data": [{"user_id": 1, "email": "direct@b.c", "last_seen": time.time() - 400 * 86400}]}
    send_mod = _patch_tautulli(monkeypatch, users, table)

    kept, excluded = send_mod.filter_inactive(["direct@b.c"], BASE_SETTINGS)
    assert excluded == ["direct@b.c"]
    assert kept == []
