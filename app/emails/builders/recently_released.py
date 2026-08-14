"""Recently Released snap-in."""
from datetime import datetime, timedelta

import logging

logger = logging.getLogger(__name__)

DEFAULT_TITLE = "Recently Released"


def release_date(item):
    raw = (item.get('originally_available_at') or '').strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:10]).date()
    except (ValueError, TypeError):
        logger.debug("unparseable release date %r; treating as missing", raw)
        return None


def flatten(recent_data):
    items = []
    if not isinstance(recent_data, list):
        return items
    for entry in recent_data:
        if isinstance(entry, dict) and 'recently_added' in entry:
            items.extend(entry['recently_added'])
        elif isinstance(entry, dict) and 'title' in entry:
            items.append(entry)
    return items


def resolve_cutoff(released_since_days, pull_window_days=None, today=None):
    today = today or datetime.now().date()

    def _days(value):
        try:
            days = int(value)
        except (TypeError, ValueError):
            return None
        return days if days > 0 else None

    days = _days(released_since_days) or _days(pull_window_days)
    return today - timedelta(days=days) if days else None


def select(recent_data, library_filter=None, released_since_days=None,
           pull_window_days=None, item_cap=0, today=None):
    items = flatten(recent_data)

    if library_filter:
        items = [i for i in items
                 if library_filter.lower() == (i.get('library_name') or '').lower()]

    cutoff = resolve_cutoff(released_since_days, pull_window_days, today)

    dated = []
    for item in items:
        released = release_date(item)
        if released is None:
            continue
        if cutoff and released < cutoff:
            continue
        dated.append((released, item))

    # Stable within a date so a same-day batch keeps the pull's own order.
    dated.sort(key=lambda pair: pair[0], reverse=True)
    items = [item for _, item in dated]

    try:
        cap = int(item_cap or 0)
    except (TypeError, ValueError):
        cap = 0
    if cap > 0:
        items = items[:cap]
    return items


def as_recent_data(items):
    return [{'recently_added': items}] if items else []
