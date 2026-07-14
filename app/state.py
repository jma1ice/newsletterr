import threading

# Mutable runtime state shared across modules and background threads.
# Always access as attributes (state.X), from-imports would copy the
# binding and break cross-module mutation.

cache_storage = {
    'stats': {'data': None, 'timestamp': 0, 'params': None},
    'users': {'data': None, 'timestamp': 0, 'params': None},
    'graph_data': {'data': None, 'timestamp': 0, 'params': None},
    'recent_data': {'data': None, 'timestamp': 0, 'params': None}
}

_update_cache = {
    "latest": None,
    "is_newer": False,
    "release_url": None,
    "notes": None,
    "checked_at": 0.0,
    "etag": None,
}

_WORKERS_STARTED = False
_WORKERS_LOCK = threading.Lock()
_RENDER_LOCK = threading.Lock()
_REFRESH_LOCK = threading.Lock()
_CACHE_LOCK = threading.Lock()

_hsts_enabled = False

plex_headers = None

# Set by POST /pull_recommendations/cancel to stop an in-progress conjurr
# recommendations pull between users. run_conjurr_command clears it at the
# start of a run and checks it between users, returning partial results.
recommendations_cancel = threading.Event()
