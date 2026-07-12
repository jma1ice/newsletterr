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
