import threading

from app.cache import clear_cache, set_cached_data, get_cached_data

def test_clear_cache_does_not_race_when_keys_are_added(app):
    # clear_cache used to iterate cache_storage directly; a concurrent
    # set_cached_data adding a new key caused "dict changed size during
    # iteration". With the snapshot + lock this must run clean.
    stop = threading.Event()

    def churn():
        i = 0
        while not stop.is_set():
            set_cached_data(f"key_{i % 50}", {"n": i})
            i += 1

    writers = [threading.Thread(target=churn) for _ in range(4)]
    for w in writers:
        w.start()
    try:
        for _ in range(500):
            clear_cache()  # must never raise RuntimeError
    finally:
        stop.set()
        for w in writers:
            w.join()

def test_set_and_get_roundtrip(app):
    set_cached_data("stats", {"hello": "world"})
    assert get_cached_data("stats", strict=False) == {"hello": "world"}
    clear_cache("stats")
    assert get_cached_data("stats", strict=False) is None


# --- sidebar badge payload

def _badge(client):
    return client.get("/cache_status").get_json()["badge"]


def test_cache_status_reports_the_badge_for_an_empty_cache(client, seeded_settings):
    """The sidebar is server-rendered once, so the client needs the computed
    class and text back to recolor without a page refresh."""
    clear_cache()
    badge = _badge(client)
    assert badge["has_data"] is False
    assert badge["class"] == "cache-badge-muted"
    assert badge["text"] == "none"


def test_badge_turns_fresh_once_every_tracked_key_is_populated(client, seeded_settings):
    import time as _time
    clear_cache()
    params = {"time_range": "30", "count": "10", "timestamp": _time.time()}
    for key in ("stats", "users", "graph_data", "recent_data"):
        set_cached_data(key, [{"x": 1}], params)

    badge = _badge(client)
    assert badge["has_data"] is True
    assert badge["class"] == "cache-badge-fresh"
    assert badge["text"] == "30 days"
    assert "Fresh" in badge["title"]


def test_badge_flags_a_partial_cache_as_missing(client, seeded_settings):
    import time as _time
    clear_cache()
    set_cached_data("stats", [{"x": 1}], {"time_range": "7", "timestamp": _time.time()})

    badge = _badge(client)
    assert badge["class"] == "cache-badge-missing"
    assert "Missing" in badge["title"]


def test_badge_goes_muted_again_after_clearing(client, seeded_settings):
    import time as _time
    clear_cache()
    for key in ("stats", "users", "graph_data", "recent_data"):
        set_cached_data(key, [{"x": 1}], {"time_range": "30", "timestamp": _time.time()})
    assert _badge(client)["class"] == "cache-badge-fresh"

    clear_cache()
    assert _badge(client)["class"] == "cache-badge-muted"


def test_badge_thresholds_are_not_duplicated_in_the_frontend():
    """The class names live in app/cache.py; the shell script may only paint
    what the endpoint hands it."""
    from pathlib import Path
    shell = Path(__file__).resolve().parent.parent / "static/js/app/25-shell.js"
    source = shell.read_text(encoding="utf-8")
    for marker in ("age_hours", "oldest_age", "< 24", "168"):
        assert marker not in source
