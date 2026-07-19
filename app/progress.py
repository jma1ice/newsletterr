import threading
import time

from app import state

# Per-operation progress registry backing GET /pull_progress. Correct only
# because gunicorn runs a single process; gthread workers share state, so
# a lock is all the coordination needed.

_LOCK = threading.Lock()

# Entries older than this are treated as stale by readers; a crashed request
# must not leave a spinner pinned at a frozen percentage forever.
STALE_AFTER_SECONDS = 300


def progress_start(op, total, label=""):
    with _LOCK:
        state.progress_registry[op] = {
            'step': 0,
            'total': max(int(total), 1),
            'label': label,
            'active': True,
            'updated': time.time(),
        }


def progress_step(op, label=None, advance=1):
    with _LOCK:
        entry = state.progress_registry.get(op)
        if not entry:
            return
        entry['step'] = min(entry['step'] + advance, entry['total'])
        if label is not None:
            entry['label'] = label
        entry['updated'] = time.time()


def progress_done(op):
    with _LOCK:
        entry = state.progress_registry.get(op)
        if not entry:
            return
        entry['step'] = entry['total']
        entry['active'] = False
        entry['updated'] = time.time()


def progress_get(op):
    with _LOCK:
        entry = state.progress_registry.get(op)
        if not entry or (time.time() - entry['updated']) > STALE_AFTER_SECONDS:
            return {'active': False, 'step': 0, 'total': 0, 'label': ''}
        return {
            'active': entry['active'],
            'step': entry['step'],
            'total': entry['total'],
            'label': entry['label'],
        }
