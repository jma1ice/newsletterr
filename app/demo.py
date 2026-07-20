# Demo mode (NEWS-15 enabling work). When DEMO_MODE=1 the container becomes a
# public read-only showcase: auth is short-circuited to a demo account, the
# caches are seeded with a convincing sample dataset so the UI has something to
# render, and every mutating request is intercepted with a friendly banner
# instead of a 403. The website team embeds or links this container; the
# website half of NEWS-15 is theirs.
import time

from flask import jsonify, redirect, request, session, url_for

from app import config
from app.cache import set_cached_data

import logging

logger = logging.getLogger(__name__)

DEMO_USERNAME = "demo"
DEMO_NOTICE = "Demo mode: changes are disabled. Explore freely; nothing you do here is saved."

# Endpoints allowed to run their POST/write path in demo: appearance toggle
# (harmless, in-memory theme flip), the auth pages, the CSP report sink, and
# the read-only pulls which only ever return the seeded caches here.
_ALLOWED_WRITE_ENDPOINTS = frozenset({
    'api.set_appearance',
    'auth.login',
    'auth.logout',
    'main.csp_report',
})

def is_demo():
    return config.DEMO_MODE

def _wants_json():
    return request.path.startswith('/api/') or 'application/json' in (request.headers.get('Accept') or '') \
        or request.is_json

def demo_before_request():
    """Seed a demo session so every page renders as a logged-in user, and
    intercept writes. Runs as a before_request only when DEMO_MODE is on."""
    if not is_demo():
        return None

    # Persistent demo identity so requires_auth and templates see a user.
    if not session.get('authenticated'):
        session['authenticated'] = True
        session['username'] = DEMO_USERNAME

    # Read-only guard: block state-changing methods except the small allowlist.
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        if request.endpoint in _ALLOWED_WRITE_ENDPOINTS:
            return None
        logger.debug(f"Demo mode blocked write to {request.endpoint}")
        if _wants_json():
            return jsonify({"status": "demo", "demo": True, "message": DEMO_NOTICE}), 200
        # A persistent banner (base.html, keyed off the demo_mode global) already
        # explains the read-only state, so just bounce back without saving.
        return redirect(request.referrer or url_for('main.index'))
    return None

def _demo_stats():
    return [
        {
            'stat_id': 'top_movies', 'stat_title': 'Most Watched Movies',
            'rows': [
                {'title': 'The Grand Voyage', 'year': '2024', 'total_plays': 42, 'total_duration': 9000, 'content_rating': 'PG-13', 'rating': 8.4, 'thumb': ''},
                {'title': 'Neon Harbor', 'year': '2023', 'total_plays': 33, 'total_duration': 7200, 'content_rating': 'R', 'rating': 7.9, 'thumb': ''},
                {'title': 'Paper Lanterns', 'year': '2025', 'total_plays': 28, 'total_duration': 6600, 'content_rating': 'PG', 'rating': 7.5, 'thumb': ''},
            ],
        },
        {
            'stat_id': 'top_tv', 'stat_title': 'Most Watched TV Shows',
            'rows': [
                {'title': 'Wanderers', 'year': '2024', 'total_plays': 71, 'total_duration': 12000, 'content_rating': 'TV-14', 'rating': 8.8, 'thumb': ''},
                {'title': 'Midnight Diner Tales', 'year': '2022', 'total_plays': 54, 'total_duration': 9000, 'content_rating': 'TV-PG', 'rating': 8.1, 'thumb': ''},
            ],
        },
        {
            'stat_id': 'library_item_counts', 'stat_title': 'Library Item Counts',
            'rows': [
                {'section_name': 'Movies', 'count': 1284},
                {'section_name': 'TV Shows', 'count': 342},
                {'section_name': 'Music', 'count': 5120},
            ],
        },
    ]

def _demo_recent_data():
    now = int(time.time())
    return [
        {'recently_added': [
            {'title': 'The Grand Voyage', 'rating_key': 'demo1', 'year': '2024', 'thumb': '', 'art': '', 'summary': 'A crew sails past the edge of the known map.', 'added_at': str(now - 3600), 'duration': '6900000', 'content_rating': 'PG-13', 'media_type': 'movie', 'type': 'movie', 'library_name': 'Movies', 'plex_url': '', 'rating': '8.4'},
            {'title': 'Paper Lanterns', 'rating_key': 'demo2', 'year': '2025', 'thumb': '', 'art': '', 'summary': 'A festival lights up a quiet town.', 'added_at': str(now - 7200), 'duration': '6300000', 'content_rating': 'PG', 'media_type': 'movie', 'type': 'movie', 'library_name': 'Movies', 'plex_url': '', 'rating': '7.5'},
        ]},
        {'recently_added': [
            {'title': 'Wanderers', 'rating_key': 'demo3', 'year': '2024', 'thumb': '', 'art': '', 'summary': 'Season 2 picks up on the far shore.', 'added_at': str(now - 5400), 'duration': '2700000', 'content_rating': 'TV-14', 'media_type': 'show', 'type': 'show', 'library_name': 'TV Shows', 'plex_url': '', 'rating': '8.8'},
        ]},
    ]

def seed_demo_cache():
    """Populate the in-memory caches with a sample dataset so the index page
    and previews render without any external service. Idempotent; safe to call
    at startup."""
    params = {'time_range': '30', 'count': '10', 'timestamp': time.time()}
    set_cached_data('stats', _demo_stats(), params)
    set_cached_data('recent_data', _demo_recent_data(), params)
    set_cached_data('most_watched_data', [], params)
    set_cached_data('graph_data', [], params)
    set_cached_data('users', [], params)
    logger.info("Demo mode: seeded sample caches")

def install(app):
    """Wire demo mode into the app when DEMO_MODE is set: seed caches and
    register the read-only/auth before_request guard."""
    if not is_demo():
        return
    logger.warning("DEMO_MODE is enabled: this instance is read-only and auth is bypassed")
    seed_demo_cache()
    app.before_request(demo_before_request)
    app.jinja_env.globals["demo_mode"] = True
    app.jinja_env.globals["demo_notice"] = DEMO_NOTICE
