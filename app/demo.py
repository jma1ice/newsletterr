# When DEMO_MODE=1 the container becomes a public read-only showcase: auth is
# short-circuited to a demo account, a sample install (settings plus caches) is
# synthesized so every page renders with content, and mutating requests either
# bounce or are redirected into a per-visitor session overlay instead of the
# database.
#
# Three rules keep this module honest:
#   1. Nothing here ever touches the database. Session state only.
#   2. No visitor action may reach a third-party service on the operator's
#      credentials. Every route that would call Plex/Tautulli/Sonarr/the GIF
#      search is answered from the sample data instead. (The version check
#      against the public GitHub API is the one exception; it carries nothing
#      and is rate limited by its own interval.)
#   3. The sample data uses the exact shapes the real clients return, so the
#      builders, previews and layouts run their normal code paths.
import json
import random
import time

from datetime import datetime, timedelta

from flask import Response, abort, jsonify, redirect, request, send_from_directory, session, url_for

from app import config
from app.cache import get_cache_info, set_cached_data

import logging

logger = logging.getLogger(__name__)

DEMO_USERNAME = "demo"
DEMO_NOTICE = (
    "Demo mode: a sandbox loaded with sample data. Appearance, layout and email options "
    "apply to your session only, nothing is saved, and no email is ever sent."
)
DEMO_SETTINGS_SAVED = (
    "Applied to your demo session only. Nothing was saved; reload with a fresh session to reset."
)

# Sample artwork lives in static/img/demo and is reached through the same
# /proxy-art chokepoint every real thumb uses, so builders and frontend stay
# unaware that there is no media server behind it.
ART_PREFIX = "library/demo/"
ART_DIR = config.ASSET_ROOT / "static" / "img" / "demo"

def _art(slug):
    return f"/{ART_PREFIX}{slug}.png"

def _proxied_art(slug):
    """Artwork for the snap-ins whose posters are absolute CDN references on a
    real install (Ombi and seerr both resolve TMDB paths). install() blanks
    their TMDB base in demo mode, so these have to carry the proxy prefix
    themselves."""
    return f"/proxy-art{_art(slug)}"

# Endpoints allowed to run their real POST path in demo: the read-only email
# renderers (they only read the seeded caches), the recommendations cancel flag
# (in-process event) and the CSP report sink.
_ALLOWED_WRITE_ENDPOINTS = frozenset({
    'emails.preview_email',
    'emails.export_pdf',
    'main.csp_report',
    'stats.pull_recommendations_cancel',
})

def is_demo():
    return config.DEMO_MODE

def _wants_json():
    return request.path.startswith('/api/') or 'application/json' in (request.headers.get('Accept') or '') \
        or request.is_json

# ---------------------------------------------------------------- settings --

# A plausible fully-configured install. Every service carries a URL and key so
# get_service_flags() lights the pull buttons up; the requests those buttons
# make are intercepted below and never leave the process.
BASE_SETTINGS = {
    "id": 1,
    "from_email": "newsletter@demo.newsletterr.app",
    "from_name": "Newsletterr Demo",
    "alias_email": "",
    "reply_to_email": "",
    "smtp_server": "smtp.demo.newsletterr.app",
    "smtp_port": 587,
    "smtp_protocol": "TLS",
    "smtp_username": "newsletter@demo.newsletterr.app",
    "server_name": "Demo Media Server",
    "media_server_type": "plex",
    "plex_url": "http://demo-plex:32400",
    "plex_token": "demo-plex-token",
    "tautulli_url": "http://demo-tautulli:8181",
    "tautulli_api": "demo-tautulli-key",
    "conjurr_url": "http://demo-conjurr:8000",
    "droppedneedle_url": "http://demo-droppedneedle:5000",
    "droppedneedle_api_key": "demo-droppedneedle-key",
    "sonarr_url": "http://demo-sonarr:8989",
    "sonarr_api_key": "demo-sonarr-key",
    "radarr_url": "http://demo-radarr:7878",
    "radarr_api_key": "demo-radarr-key",
    "ombi_url": "http://demo-ombi:5000",
    "ombi_api_key": "demo-ombi-key",
    "seerr_url": "http://demo-seerr:5055",
    "seerr_api_key": "demo-seerr-key",
    "logo_filename": "Asset_94x.png",
    "logo_width": 80,
    "custom_logo_filename": "",
    "default_intro_text": (
        "Here is what landed on the server this month, plus a look at what everyone has been "
        "watching. Everything below is sample data: this is the newsletterr demo."
    ),
    "default_outro_text": (
        "Thanks for reading. Requests are always welcome, and the request link in your account "
        "still works while you are here."
    ),
    "email_layout": "classic",
    "email_density": "",
    "email_theme": "newsletterr_blue",
    "recipient_display_name": "friendly_name",
    "stat_cover_art": "enabled",
    "hosted_enabled": "disabled",
    "hosted_images_enabled": "disabled",
    "hosted_links_enabled": "disabled",
}

# Everything a visitor is allowed to change, grouped by how it is validated.
# Anything not listed here is dropped: credentials, SMTP, hosted mode, the
# admin account and the media server type all stay exactly as seeded.
_SHOWCASE_CHOICES = {
    "email_layout": {"legacy", "classic", "editorial", "digest", "spotlight"},
    "email_density": {"", "compact", "expanded"},
    "recipient_display_name": {"email", "username", "friendly_name"},
    "logo_position": {"left", "center", "right"},
    "appearance_theme": {"light", "dark"},
    # "custom" is the build-your-own UI palette (NEWS-29), not a flag
    "pride_flag": {"off", "rainbow", "trans", "bi", "pan", "nonbinary", "lesbian", "ace", "progress", "custom"},
    "snapins_floating": {"0", "1"},
    "stats_type": {"plays", "duration"},
    "recently_added_mode": {"items", "days"},
    "recently_added_sort": {"date", "rating"},
    "wrapped_rank_depth": {"1", "3", "5"},
    "date_format": {"mdy", "dmy", "ymd"},
    "time_format": {"12", "24"},
    "week_start_day": {"sunday", "monday"},
}

# Plain enabled/disabled switches.
_SHOWCASE_TOGGLES = (
    "hide_stat_play_counts", "hide_graph_play_counts", "stat_cover_art",
    "ra_show_description", "recs_show_description", "email_show_server_name",
    "email_auto_header_text", "dn_show_artists", "dn_show_tracks",
    "dn_show_albums", "dn_show_genres", "dn_cover_art", "scheduled_subject_prefix",
)

_SHOWCASE_COLORS = (
    "primary_color", "secondary_color", "accent_color", "background_color", "text_color",
)

# key -> (minimum, maximum)
_SHOWCASE_INTS = {
    "ra_grid_columns": (1, 10),
    "recs_grid_columns": (1, 10),
    "coming_soon_grid_columns": (1, 10),
    "collections_grid_columns": (1, 10),
    "poster_max_height": (0, 800),
    "logo_width": (0, 800),
    "coming_soon_days_ahead": (1, 365),
}

# key -> maximum length kept in the session cookie
_SHOWCASE_TEXT = {
    "server_name": 60,
    "email_eyebrow_text": 120,
    "default_intro_text": 400,
    "default_outro_text": 400,
}

# The session cookie is the storage, so the overlay has a hard ceiling. Text
# fields are dropped first when a visitor pastes an essay into the intro box.
_OVERLAY_BUDGET_BYTES = 2200

def _stored_overlay():
    overlay = session.get('demo_settings')
    return dict(overlay) if isinstance(overlay, dict) else {}

def _store_overlay(overlay):
    while len(json.dumps(overlay)) > _OVERLAY_BUDGET_BYTES:
        droppable = [k for k in _SHOWCASE_TEXT if k in overlay]
        if not droppable:
            overlay = {}
            break
        overlay.pop(droppable[-1])
    session['demo_settings'] = overlay
    session.modified = True

def apply_settings_overlay(s):
    """Merge the demo baseline and the visitor's session choices into a
    settings dict. Called from settings_store.get_settings(), which is the one
    chokepoint every page, builder and layout reads settings through, so a
    theme or layout picked on the settings page shows up in the live preview
    without a single write."""
    merged = dict(s)
    merged.update(BASE_SETTINGS)
    try:
        merged.update(_stored_overlay())
    except RuntimeError:
        pass  # outside a request context (scheduler threads); baseline is enough
    return merged

def update_session_settings(updates):
    """Record validated settings for this visitor only."""
    overlay = _stored_overlay()
    overlay.update(updates)
    _store_overlay(overlay)

def _clean_form_settings(form):
    """Whitelist-validate a settings form POST into session-safe values."""
    from app.blueprints.settings import THEME_PRESETS, PRESET_LOGO_FILES
    from app.theme import CUSTOM_UI_KEYS, is_hex_color

    updates = {}

    for key, allowed in _SHOWCASE_CHOICES.items():
        if key in form:
            value = (form.get(key) or "").strip()
            if value in allowed:
                updates[key] = value

    for key in _SHOWCASE_TOGGLES:
        if key in form:
            updates[key] = "enabled" if (form.get(key) or "").strip() == "enabled" else "disabled"

    for key, (low, high) in _SHOWCASE_INTS.items():
        if key in form:
            try:
                updates[key] = str(min(high, max(low, int((form.get(key) or "").strip() or low))))
            except (TypeError, ValueError):
                pass

    for key, cap in _SHOWCASE_TEXT.items():
        if key in form:
            updates[key] = (form.get(key) or "").strip()[:cap]
    # A blank server name switches the whole builder off (index only surfaces
    # cached data when one is set), which reads as a broken demo rather than a
    # setting. Keep the sample name instead.
    if not updates.get("server_name", "x"):
        updates.pop("server_name")

    # Email theme drives the palette exactly as the real save does: a preset
    # name wins over the color pickers, "custom" keeps them.
    email_theme = (form.get("email_theme") or "").strip()
    if email_theme in THEME_PRESETS:
        updates["email_theme"] = email_theme
        updates.update(THEME_PRESETS[email_theme])
    elif email_theme == "custom":
        updates["email_theme"] = "custom"
        for key in _SHOWCASE_COLORS:
            value = (form.get(key) or "").strip()
            if is_hex_color(value):
                updates[key] = value

    logo_choice = (form.get("logo_filename") or "").strip()
    if logo_choice in PRESET_LOGO_FILES:
        updates["logo_filename"] = PRESET_LOGO_FILES[logo_choice]
    elif logo_choice == "none":
        updates["logo_filename"] = ""

    header_bg = (form.get("email_header_bg") or "").strip()
    if form.get("email_header_bg_mode") == "solid" and is_hex_color(header_bg):
        updates["email_header_bg"] = header_bg
    elif "email_header_bg_mode" in form:
        updates["email_header_bg"] = ""

    # Custom UI palettes, stored the same way the real save stores them so
    # app/theme.py parses them unchanged.
    for column, prefix in (("ui_custom_light", "ui_light"), ("ui_custom_dark", "ui_dark")):
        if any(f"{prefix}_{k}" in form for k in CUSTOM_UI_KEYS):
            colors = {k: (form.get(f"{prefix}_{k}") or "").strip() for k in CUSTOM_UI_KEYS}
            updates[column] = json.dumps(colors) if any(colors.values()) else ""

    return updates

# ------------------------------------------------------------ sample data --

_MOVIES = [
    ("The Grand Voyage", "the-grand-voyage", "2024", "PG-13", "8.4",
     "A salvage crew sails past the edge of the charted world and finds the map was the only thing missing."),
    ("Neon Harbor", "neon-harbor", "2023", "R", "7.9",
     "A dock worker moonlighting as a courier gets one delivery too many in a city that never dries out."),
    ("Paper Lanterns", "paper-lanterns", "2025", "PG", "7.5",
     "A festival returns to a town that had quietly agreed to forget it."),
    ("Salt and Stone", "salt-and-stone", "2024", "PG-13", "8.0",
     "Two rival quarry families spend a summer discovering they have been carving the same statue."),
    ("The Quiet Orbit", "the-quiet-orbit", "2025", "PG-13", "8.6",
     "The last technician on a decommissioned station keeps the lights on for a ship that may not come."),
    ("Midnight Cartography", "midnight-cartography", "2023", "R", "7.2",
     "A night-shift surveyor starts drawing streets that do not exist yet."),
]

_SHOWS = [
    ("Wanderers", "wanderers", "2024", "TV-14", "8.8",
     "Season two picks up on the far shore, where the caravan finally stops running."),
    ("Midnight Diner Tales", "midnight-diner-tales", "2022", "TV-PG", "8.1",
     "Every booth has a story and the cook has heard all of them twice."),
    ("Copper Coast", "copper-coast", "2025", "TV-MA", "8.3",
     "A harbor town, a closing smelter, and three siblings who each want a different ending."),
    ("The Lighthouse Frequency", "the-lighthouse-frequency", "2024", "TV-14", "7.8",
     "A radio hobbyist picks up a broadcast from a light that was dismantled in 1974."),
]

_ALBUMS = [
    ("Slow Tide", "slow-tide", "Analog Hearts", "2025"),
    ("Paper Radio", "paper-radio", "Velvet Antenna", "2024"),
    ("North Window", "north-window", "Sable Choir", "2025"),
]

_USERS = [
    (1, "avery", "Avery", "avery@demo.newsletterr.app"),
    (2, "jules", "Jules", "jules@demo.newsletterr.app"),
    (3, "sam", "Sam", "sam@demo.newsletterr.app"),
    (4, "robin", "Robin", "robin@demo.newsletterr.app"),
]

def _ago(hours):
    return str(int(time.time() - hours * 3600))

def demo_users():
    return [
        {
            "user_id": user_id, "username": username, "friendly_name": friendly,
            "email": email, "is_active": 1, "is_admin": user_id == 1,
            "user_thumb": "", "last_seen": int(time.time() - user_id * 4000),
        }
        for user_id, username, friendly, email in _USERS
    ]

def demo_stats():
    movie_rows = []
    for index, (title, slug, year, rating, score, _summary) in enumerate(_MOVIES, start=1):
        plays = 42 - (index - 1) * 6
        movie_rows.append({
            "title": title, "year": year, "total_plays": plays, "total_duration": plays * 6900,
            "content_rating": rating, "rating": score, "users_watched": min(4, plays // 9 + 1),
            "thumb": _art(slug), "art": _art(slug), "grandparent_thumb": "",
            "rating_key": f"demo-movie-{index}", "plex_url": "",
        })

    show_rows = []
    for index, (title, slug, year, rating, score, _summary) in enumerate(_SHOWS, start=1):
        plays = 71 - (index - 1) * 11
        show_rows.append({
            "title": title, "year": year, "total_plays": plays, "total_duration": plays * 2700,
            "content_rating": rating, "rating": score, "users_watched": min(4, plays // 18 + 1),
            "thumb": _art(slug), "art": _art(slug), "grandparent_thumb": _art(slug),
            "rating_key": f"demo-show-{index}", "plex_url": "",
        })

    user_rows = [
        {
            "user": friendly, "friendly_name": friendly, "user_id": user_id,
            "total_plays": 64 - user_id * 9, "total_duration": (64 - user_id * 9) * 2400,
            "user_thumb": "", "platform": platform,
        }
        for (user_id, _username, friendly, _email), platform in zip(
            _USERS, ("Apple TV", "Android", "Chrome", "Roku")
        )
    ]

    return [
        {"stat_id": "top_movies", "stat_title": "Most Watched Movies", "rows": movie_rows},
        {"stat_id": "popular_movies", "stat_title": "Most Popular Movies", "rows": movie_rows[:4]},
        {"stat_id": "top_tv", "stat_title": "Most Watched TV Shows", "rows": show_rows},
        {"stat_id": "popular_tv", "stat_title": "Most Popular TV Shows", "rows": show_rows[:3]},
        {"stat_id": "top_users", "stat_title": "Most Active Users", "rows": user_rows},
        {
            "stat_id": "top_platforms", "stat_title": "Most Active Platforms",
            "rows": [
                {"platform": "Apple TV", "total_plays": 118, "total_duration": 286000},
                {"platform": "Android", "total_plays": 94, "total_duration": 214000},
                {"platform": "Chrome", "total_plays": 61, "total_duration": 151000},
                {"platform": "Roku", "total_plays": 47, "total_duration": 122000},
            ],
        },
        {
            "stat_id": "library_item_counts", "stat_title": "Library Item Counts",
            "rows": [
                {"section_name": "Movies", "count": 1284},
                {"section_name": "TV Shows", "count": 342},
                {"section_name": "Music", "count": 5120},
            ],
        },
    ]

def demo_graph_data():
    """One entry per graph command, in the order get_current_tautulli_data_for_email
    lists them. Shape matches Tautulli's graph endpoints (categories + series)."""
    days = [(datetime.now() - timedelta(days=offset)).strftime('%Y-%m-%d') for offset in range(29, -1, -1)]
    weekdays = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    hours = [f"{hour}" for hour in range(24)]
    months = [(datetime.now() - timedelta(days=30 * offset)).strftime('%b %Y') for offset in range(11, -1, -1)]

    rng = random.Random(20260815)

    def series(names, categories, low, high):
        return {
            "categories": categories,
            "series": [
                {"name": name, "data": [rng.randint(low, high) for _ in categories]}
                for name in names
            ],
        }

    stream_types = ["Direct Play", "Direct Stream", "Transcode"]
    platforms = ["Apple TV", "Android", "Chrome", "Roku", "iOS"]
    user_names = [friendly for _id, _username, friendly, _email in _USERS]

    return [
        series(stream_types, days[-14:], 0, 4),
        series(["Movies", "TV", "Music"], days, 0, 14),
        series(["Movies", "TV", "Music"], weekdays, 4, 30),
        series(["Movies", "TV", "Music"], hours, 0, 12),
        series(["4k", "1080", "720", "SD"], days[-14:], 0, 8),
        series(["4k", "1080", "720", "SD"], days[-14:], 0, 8),
        series(stream_types, days[-14:], 0, 9),
        series(["Movies", "TV", "Music"], platforms, 3, 40),
        series(["Movies", "TV", "Music"], user_names, 3, 44),
        series(["Movies", "TV", "Music"], months, 20, 160),
        series(stream_types, platforms, 2, 26),
        series(stream_types, user_names, 2, 26),
    ]

def demo_recent_data():
    movies = [
        {
            "title": title, "rating_key": f"demo-movie-{index}", "year": year,
            "thumb": _art(slug), "art": _art(f"{slug}-art" if slug == "the-grand-voyage" else slug),
            "summary": summary, "tagline": "", "added_at": _ago(6 * index),
            "updated_at": _ago(6 * index), "originally_available_at": f"{year}-04-0{(index % 9) + 1}",
            "duration": "6900000", "content_rating": rating, "rating": score,
            "media_type": "movie", "type": "movie", "library_name": "Movies", "plex_url": "",
        }
        for index, (title, slug, year, rating, score, summary) in enumerate(_MOVIES, start=1)
    ]
    shows = [
        {
            "title": title, "rating_key": f"demo-show-{index}", "year": year,
            "thumb": _art(slug), "art": _art(f"{slug}-art" if slug == "wanderers" else slug),
            "grandparent_thumb": _art(slug), "grandparent_title": title,
            "grandparent_summary": summary, "parent_title": "Season 2",
            "summary": summary, "tagline": "", "added_at": _ago(5 * index),
            "updated_at": _ago(5 * index), "originally_available_at": f"{year}-05-1{index % 9}",
            "duration": "2700000", "content_rating": rating, "rating": score,
            "media_type": "show", "type": "show", "library_name": "TV Shows",
            "new_episode_count": 2 + index, "plex_url": "",
        }
        for index, (title, slug, year, rating, score, summary) in enumerate(_SHOWS, start=1)
    ]
    albums = [
        {
            "title": title, "rating_key": f"demo-album-{index}", "year": year,
            "thumb": _art(slug), "art": _art(slug), "parent_thumb": _art(slug),
            "parent_title": artist, "grandparent_title": artist,
            "summary": f"New from {artist}.", "added_at": _ago(9 * index),
            "updated_at": _ago(9 * index), "duration": "2400000", "content_rating": "",
            "rating": "", "media_type": "album", "type": "album",
            "library_name": "Music", "plex_url": "",
        }
        for index, (title, slug, artist, year) in enumerate(_ALBUMS, start=1)
    ]
    return [{"recently_added": movies}, {"recently_added": shows}, {"recently_added": albums}]

def demo_most_watched():
    return [
        {
            "library_name": "Movies",
            "items": [
                {"title": title, "year": year, "play_count": 44 - index * 7,
                 "thumb": _art(slug), "plex_url": ""}
                for index, (title, slug, year, _r, _s, _sum) in enumerate(_MOVIES[:4])
            ],
        },
        {
            "library_name": "TV Shows",
            "items": [
                {"title": title, "year": year, "play_count": 73 - index * 12,
                 "thumb": _art(slug), "plex_url": ""}
                for index, (title, slug, year, _r, _s, _sum) in enumerate(_SHOWS[:4])
            ],
        },
    ]

def demo_recommendations():
    """conjurr's per-user payload: available items in *_posters, unavailable
    ones in *_posters_unavailable."""
    def poster(entry, vote):
        title, slug, year, _rating, _score, summary = entry
        return {
            "title": title, "year": year, "vote": vote, "overview": summary,
            "poster": _art(slug), "cover_art": _art(slug),
            "rating_key": "", "runtime": "1h 54m", "url": "",
        }

    return {
        str(user_id): {
            "display_name": friendly,
            "movie_posters": [poster(_MOVIES[(user_id + i) % len(_MOVIES)], 8.1 - i * 0.4) for i in range(3)],
            "movie_posters_unavailable": [poster(_MOVIES[(user_id + 4) % len(_MOVIES)], 7.4)],
            "show_posters": [poster(_SHOWS[(user_id + i) % len(_SHOWS)], 8.6 - i * 0.5) for i in range(2)],
            "show_posters_unavailable": [],
        }
        for user_id, _username, friendly, _email in _USERS
    }

def demo_filtered_users():
    return {str(user_id): email for user_id, _username, _friendly, email in _USERS}

def demo_droppedneedle_wrapped():
    return {
        str(user_id): {
            "has_data": True,
            "year": datetime.now().year,
            "display_name": friendly,
            "listen_count": 1840 - user_id * 260,
            "loved_tracks_count": 96 - user_id * 11,
            "top_artists": [
                {"name": "Analog Hearts", "listen_count": 214, "cover_art": _art("slow-tide")},
                {"name": "Velvet Antenna", "listen_count": 168, "cover_art": _art("paper-radio")},
                {"name": "Sable Choir", "listen_count": 141, "cover_art": _art("north-window")},
            ],
            "top_albums": [
                {"name": "Slow Tide", "artist_name": "Analog Hearts", "listen_count": 132, "cover_art": _art("slow-tide")},
                {"name": "Paper Radio", "artist_name": "Velvet Antenna", "listen_count": 118, "cover_art": _art("paper-radio")},
            ],
            "top_tracks": [
                {"name": "Harbor Song", "artist_name": "Analog Hearts", "listen_count": 61, "cover_art": _art("slow-tide")},
                {"name": "Paper Radio", "artist_name": "Velvet Antenna", "listen_count": 54, "cover_art": _art("paper-radio")},
            ],
            "top_genres": [
                {"genre": "Dream Pop", "listen_count": 402},
                {"genre": "Ambient", "listen_count": 311},
            ],
        }
        for user_id, _username, friendly, _email in _USERS
    }

def demo_droppedneedle_server():
    return {
        "total_users_tracked": len(_USERS),
        "total_listens_estimated": 6120,
        "top_artist_sitewide": {"name": "Analog Hearts", "listen_count": 690, "cover_art": _art("slow-tide")},
        "top_album_sitewide": {"name": "Slow Tide", "artist_name": "Analog Hearts", "listen_count": 402, "cover_art": _art("slow-tide")},
        "leaderboard": [
            {"display_name": friendly, "listen_count": 1840 - user_id * 260}
            for user_id, _username, friendly, _email in _USERS
        ],
    }

def demo_sonarr_calendar():
    """Sonarr /api/v3/calendar entries with the embedded series object."""
    episodes = []
    for index, (title, slug, year, _rating, _score, summary) in enumerate(_SHOWS):
        for episode_offset in range(2):
            air = datetime.now() + timedelta(days=2 + index * 3 + episode_offset * 7)
            episodes.append({
                "id": 9000 + index * 10 + episode_offset,
                "seriesId": 900 + index,
                "seasonNumber": 2,
                "episodeNumber": 4 + episode_offset,
                "title": ["The Long Way Round", "Low Tide", "Signal Lost", "Copper Sky"][(index + episode_offset) % 4],
                "airDate": air.strftime('%Y-%m-%d'),
                "airDateUtc": air.strftime('%Y-%m-%dT%H:%M:%SZ'),
                "hasFile": False,
                "overview": summary,
                "series": {
                    "title": title,
                    "year": int(year),
                    "overview": summary,
                    "images": [{"coverType": "poster", "remoteUrl": _art(slug), "url": _art(slug)}],
                },
            })
    return episodes

def demo_radarr_calendar():
    movies = []
    for index, (title, slug, year, _rating, _score, summary) in enumerate(_MOVIES[:4]):
        release = datetime.now() + timedelta(days=3 + index * 4)
        movies.append({
            "id": 800 + index,
            "title": title,
            "year": int(year),
            "overview": summary,
            "hasFile": False,
            "inCinemas": release.strftime('%Y-%m-%dT00:00:00Z'),
            "physicalRelease": release.strftime('%Y-%m-%dT00:00:00Z'),
            "digitalRelease": release.strftime('%Y-%m-%dT00:00:00Z'),
            "images": [{"coverType": "poster", "remoteUrl": _art(slug), "url": _art(slug)}],
        })
    return movies

def demo_ombi_requests():
    def requested(days):
        return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')

    return {
        "movies": [
            {
                "id": 501, "title": _MOVIES[4][0], "releaseDate": f"{_MOVIES[4][2]}-01-01T00:00:00",
                "posterPath": _proxied_art(_MOVIES[4][1]), "approved": True, "available": False,
                "denied": False, "requestedDate": requested(2),
                "requestedUser": {"userAlias": "Avery", "userName": "avery"},
            },
            {
                "id": 502, "title": _MOVIES[5][0], "releaseDate": f"{_MOVIES[5][2]}-01-01T00:00:00",
                "posterPath": _proxied_art(_MOVIES[5][1]), "approved": False, "available": False,
                "denied": False, "requestedDate": requested(5),
                "requestedUser": {"userAlias": "Jules", "userName": "jules"},
            },
        ],
        "tv": [
            {
                "id": 601, "title": _SHOWS[2][0], "releaseDate": f"{_SHOWS[2][2]}-01-01T00:00:00",
                "posterPath": _proxied_art(_SHOWS[2][1]),
                "requestedUser": {"userAlias": "Sam", "userName": "sam"},
                "childRequests": [{
                    "id": 6011, "approved": True, "available": False, "denied": False,
                    "requestedDate": requested(3),
                    "requestedUser": {"userAlias": "Sam", "userName": "sam"},
                }],
            },
        ],
    }

def demo_seerr_requests():
    def requested(days):
        return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')

    return {
        "requests": [
            {
                "mediaType": "movie", "title": _MOVIES[2][0],
                "releaseDate": f"{_MOVIES[2][2]}-03-14", "posterPath": _proxied_art(_MOVIES[2][1]),
                "status": 2, "mediaStatus": 3, "requestedDate": requested(1), "requestedBy": "Robin",
            },
            {
                "mediaType": "tv", "title": _SHOWS[3][0],
                "releaseDate": f"{_SHOWS[3][2]}-09-02", "posterPath": _proxied_art(_SHOWS[3][1]),
                "status": 1, "mediaStatus": 2, "requestedDate": requested(4), "requestedBy": "Avery",
            },
            {
                "mediaType": "movie", "title": _MOVIES[3][0],
                "releaseDate": f"{_MOVIES[3][2]}-06-21", "posterPath": _proxied_art(_MOVIES[3][1]),
                "status": 2, "mediaStatus": 4, "requestedDate": requested(7), "requestedBy": "Jules",
            },
        ]
    }

def demo_collections(collection_type='movie'):
    if collection_type == 'show':
        return [{
            "key": "demo-collection-shows", "title": "Coastal Dramas",
            "summary": "Series set where the land runs out.",
            "thumb": _art("copper-coast"), "art": _art("wanderers-art"),
            "childCount": 3, "subtype": "show", "sectionTitle": "TV Shows",
            "sectionId": "2", "plex_url": "",
        }]
    if collection_type == 'artist':
        return [{
            "key": "demo-collection-music", "title": "Late Night Listening",
            "summary": "Records for the small hours.",
            "thumb": _art("slow-tide"), "art": _art("north-window"),
            "childCount": 3, "subtype": "artist", "sectionTitle": "Music",
            "sectionId": "3", "plex_url": "",
        }]
    return [{
        "key": "demo-collection-movies", "title": "Voyages and Harbors",
        "summary": "Six films about leaving and arriving.",
        "thumb": _art("the-grand-voyage"), "art": _art("the-grand-voyage-art"),
        "childCount": 4, "subtype": "movie", "sectionTitle": "Movies",
        "sectionId": "1", "plex_url": "",
    }]

def demo_collection_items(collection_key=""):
    source = _SHOWS if 'shows' in (collection_key or '') else _MOVIES
    return [
        {
            "key": f"demo-collection-item-{index}", "title": title, "type": "movie" if source is _MOVIES else "show",
            "year": int(year), "tagline": "", "summary": summary, "rating": float(score),
            "duration": 6900000, "addedAt": int(time.time()) - index * 90000,
            "thumb": _art(slug), "art": _art(slug), "childCount": 0, "leafCount": 0,
            "parentTitle": None, "grandparentTitle": None,
            "subtype": "movie" if source is _MOVIES else "show", "plex_url": "",
        }
        for index, (title, slug, year, _rating, score, summary) in enumerate(source[:4], start=1)
    ]

def demo_library_sections():
    return [
        {"section_id": "1", "title": "Movies", "type": "movie",
         "genres": [{"id": "1", "title": "Drama"}, {"id": "2", "title": "Science Fiction"}]},
        {"section_id": "2", "title": "TV Shows", "type": "show",
         "genres": [{"id": "3", "title": "Drama"}, {"id": "4", "title": "Mystery"}]},
        {"section_id": "3", "title": "Music", "type": "artist", "genres": []},
    ]

def _pick_entry(source, index, section_title):
    title, slug, year, rating, score, summary = source[index]
    media_type = "show" if source is _SHOWS else "movie"
    return {
        "title": title, "rating_key": f"demo-pick-{slug}", "year": year,
        "thumb": _art(slug), "art": _art(slug), "summary": summary, "tagline": "",
        "added_at": _ago(48), "updated_at": _ago(48), "content_rating": rating,
        "duration": "6900000", "guid": "", "key": "", "media_type": media_type,
        "type": media_type, "genres": ["Drama", "Adventure"],
        "library_name": section_title, "plex_url": "", "rating": score,
    }

def demo_random_item(section_id=None, genre=None, machine_id=None):
    source, section_title = (_SHOWS, "TV Shows") if str(section_id) == "2" else (_MOVIES, "Movies")
    return _pick_entry(source, random.randrange(len(source)), section_title)

def demo_item_by_rating_key(rating_key):
    for source, section_title in ((_MOVIES, "Movies"), (_SHOWS, "TV Shows")):
        for index, entry in enumerate(source):
            if f"demo-pick-{entry[1]}" == rating_key:
                return _pick_entry(source, index, section_title)
    return _pick_entry(_MOVIES, 0, "Movies")

def demo_search_items(query, section_id=None, limit=20):
    needle = (query or '').strip().lower()
    if not needle:
        return []
    results = []
    for source, section_title, media_type in ((_MOVIES, "Movies", "movie"), (_SHOWS, "TV Shows", "show")):
        for title, slug, year, _rating, _score, _summary in source:
            if needle in title.lower():
                results.append({
                    "rating_key": f"demo-pick-{slug}", "title": title, "year": year,
                    "type": media_type, "thumb": _art(slug), "library_name": section_title,
                })
    return results[:int(limit)]

def seed_demo_cache():
    """Populate the in-memory caches with the sample dataset so every page and
    the previews render without an external service. Idempotent; safe to call
    at startup and whenever the entries age out."""
    params = {'time_range': '30', 'count': '10', 'url': BASE_SETTINGS['tautulli_url'], 'timestamp': time.time()}
    set_cached_data('stats', demo_stats(), params)
    set_cached_data('yearly_wrapped_json', demo_stats(), params)
    set_cached_data('graph_data', demo_graph_data(), params)
    set_cached_data('recent_data', demo_recent_data(), params)
    set_cached_data('most_watched_data', demo_most_watched(), params)
    set_cached_data('most_watched_recent_data', demo_most_watched(), params)
    set_cached_data('users', demo_users(), params)
    set_cached_data('recommendations_json', demo_recommendations(), params)
    set_cached_data('filtered_users', demo_filtered_users(), params)
    set_cached_data('droppedneedle_wrapped_json', demo_droppedneedle_wrapped(), params)
    set_cached_data('droppedneedle_filtered_users', demo_filtered_users(), params)
    set_cached_data('droppedneedle_server_json', demo_droppedneedle_server(), params)
    set_cached_data('sonarr_coming_soon_json', demo_sonarr_calendar(), params)
    set_cached_data('radarr_coming_soon_json', demo_radarr_calendar(), params)
    set_cached_data('ombi_requests_json', demo_ombi_requests(), params)
    set_cached_data('seerr_requests_json', demo_seerr_requests(), params)
    logger.info("Demo mode: seeded sample caches")

def _reseed_if_stale():
    # The sample data has no upstream to refresh from, so it is re-seeded the
    # moment it ages past the usable window rather than falling back to a
    # network call that could never succeed here.
    if not get_cache_info('stats').get('is_usable'):
        seed_demo_cache()

# ------------------------------------------------------------- interceptors --

def _serve_demo_art():
    """Sample artwork for /proxy-art. Anything that is not a demo asset 404s
    here rather than falling through to the real proxy, which would reach for
    a media server that does not exist."""
    art_path = (request.view_args or {}).get('art_path') or ''
    name = art_path[len(ART_PREFIX):].split('?')[0] if art_path.startswith(ART_PREFIX) else ''
    if name and '/' not in name and name.endswith('.png') and (ART_DIR / name).is_file():
        return send_from_directory(str(ART_DIR), name, max_age=3600)
    return Response("No artwork for that path in demo mode.", status=404)

def _index_response():
    """Re-render the builder page from the seeded caches. The pull routes that
    answer with HTML all rebuild index.html this way, so the frontend's
    element-swapping (recs rows, cache card, alerts) works unchanged."""
    from app.blueprints.main import index
    return index()

def _demo_pull_stats():
    data = request.get_json(silent=True) or {}
    time_range = str(data.get('time_range', 30))
    count = str(data.get('count', 10))
    seed_demo_cache()

    stats = demo_stats()
    graph_data = demo_graph_data()
    recent_data = demo_recent_data()
    users = demo_users()

    return jsonify({
        "success": True,
        "demo": True,
        "alert": f"Sample data loaded. Stats and graphs for {time_range} days, {count} recently added items.",
        "stats": stats,
        "yearly_wrapped_json": stats,
        "graph_data": graph_data,
        "graph_commands": [
            {'command': 'get_concurrent_streams_by_stream_type', 'name': 'Stream Type'},
            {'command': 'get_plays_by_date', 'name': 'Plays by Date'},
            {'command': 'get_plays_by_dayofweek', 'name': 'Plays by Day'},
            {'command': 'get_plays_by_hourofday', 'name': 'Plays by Hour'},
            {'command': 'get_plays_by_source_resolution', 'name': 'Plays by Source Res'},
            {'command': 'get_plays_by_stream_resolution', 'name': 'Plays by Stream Res'},
            {'command': 'get_plays_by_stream_type', 'name': 'Plays by Stream Type'},
            {'command': 'get_plays_by_top_10_platforms', 'name': 'Plays by Top Platforms'},
            {'command': 'get_plays_by_top_10_users', 'name': 'Plays by Top Users'},
            {'command': 'get_plays_per_month', 'name': 'Plays per Month'},
            {'command': 'get_stream_type_by_top_10_platforms', 'name': 'Stream Type by Top Platforms'},
            {'command': 'get_stream_type_by_top_10_users', 'name': 'Stream Type by Top Users'},
        ],
        "recent_data": recent_data,
        "most_watched_data": demo_most_watched(),
        "user_dict": demo_filtered_users(),
        "users_full_data": users,
        "cache_info": {key: get_cache_info(key) for key in (
            'stats', 'users', 'graph_data', 'recent_data', 'recommendations_json', 'filtered_users')},
        "time_range": time_range,
        "count": count,
        "plex_unavailable": False,
        "error": None,
    })

def _demo_pull_html():
    seed_demo_cache()
    return _index_response()

def _demo_collection_items():
    data = request.get_json(silent=True) or {}
    return jsonify({
        "status": "success",
        "items": demo_collection_items(data.get('collection_key') or ''),
    })

def _demo_fetch_collections():
    collection_type = (request.view_args or {}).get('collection_type') or 'movie'
    return jsonify({
        "status": "success",
        "collections": demo_collections(collection_type),
        "type": collection_type,
    })

def _demo_random_pick_options():
    return jsonify({"status": "success", "libraries": demo_library_sections()})

def _demo_featured_pick_search():
    return jsonify({
        "status": "success",
        "results": demo_search_items(request.args.get('q') or '', limit=20),
    })

def _demo_clear_cache():
    seed_demo_cache()
    return jsonify({"status": "success", "demo": True,
                    "message": "Demo mode: the sample dataset was reloaded."})

def _demo_settings_save():
    token = (request.form.get("csrf_token") or "").strip()
    if not token or token != session.get("csrf_token"):
        abort(400)
    update_session_settings(_clean_form_settings(request.form))
    return redirect(url_for('settings.settings', alert=DEMO_SETTINGS_SAVED))

def _demo_appearance():
    # Mirrors api.set_appearance exactly (same validation, same response), but
    # the three columns land in the session instead of the settings row.
    from app.blueprints.api import PRIDE_FLAGS
    from app.security import require_csrf_for_json
    require_csrf_for_json()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    updates = {}
    if 'theme' in data:
        theme = str(data.get('theme') or '').strip().lower()
        if theme not in ('light', 'dark'):
            return jsonify({"error": "theme must be light or dark"}), 400
        updates['appearance_theme'] = theme
    if 'pride' in data:
        pride = str(data.get('pride') or 'off').strip().lower()
        if pride not in PRIDE_FLAGS:
            return jsonify({"error": "invalid pride flag"}), 400
        updates['pride_flag'] = pride
    if 'snapins_floating' in data:
        updates['snapins_floating'] = '0' if str(data.get('snapins_floating')).lower() in ('0', 'false') else '1'

    if not updates:
        return jsonify({"error": "no appearance fields provided"}), 400

    update_session_settings(updates)
    return jsonify({"status": "ok", **updates})

def _demo_test_connection():
    return jsonify({"status": "ok", "demo": True,
                    "message": "Demo mode: connections are simulated, nothing was contacted."})

def _demo_gif_search():
    """The GIF picker without the GIF service: a public showcase has no
    business spending the shared search key, so it offers the mascot GIFs that
    ship with the app."""
    if not (request.args.get('q') or '').strip():
        return jsonify({"results": []})
    gifs = sorted(p.name for p in (config.ASSET_ROOT / "static" / "img").glob("Asset_*.gif"))
    return jsonify({
        "results": [
            {"id": name, "title": "newsletterr", "url": f"/static/img/{name}", "width": 300, "height": 300}
            for name in gifs
        ],
        "page": 1,
        "per_page": len(gifs),
        "demo": True,
    })

def _demo_plex_info():
    return jsonify({
        "connected": True,
        "demo": True,
        "server_name": BASE_SETTINGS["server_name"],
        "connections": [{
            "uri": BASE_SETTINGS["plex_url"], "local": True, "relay": False,
            "protocol": "http", "label": "Local",
        }],
        "recommended_url": BASE_SETTINGS["plex_url"],
        "plex_url": BASE_SETTINGS["plex_url"],
    })

# GET endpoints that would otherwise call a media server (or plex.tv) on the
# demo's behalf. Answered from the sample data instead.
_DEMO_GET_HANDLERS = {
    'stats.fetch_collections': _demo_fetch_collections,
    'stats.random_pick_options': _demo_random_pick_options,
    'stats.featured_pick_search': _demo_featured_pick_search,
    'api.plex_get_info': _demo_plex_info,
    'api.gif_search': _demo_gif_search,
}

# Writes that are answered rather than blocked, because a dead button is a
# worse demo than a simulated one. None of these touch the database.
_DEMO_WRITE_HANDLERS = {
    'stats.pull_stats': _demo_pull_stats,
    'stats.pull_recommendations': _demo_pull_html,
    'stats.pull_droppedneedle_stats': _demo_pull_html,
    'stats.pull_coming_soon': _demo_pull_html,
    'stats.pull_ombi_requests': _demo_pull_html,
    'stats.pull_seerr_requests': _demo_pull_html,
    'stats.get_collection_items': _demo_collection_items,
    'main.clear_cache_route': _demo_clear_cache,
    'settings.settings': _demo_settings_save,
    'api.set_appearance': _demo_appearance,
}

def demo_before_request():
    """Seed a demo session so every page renders as a logged-in user, answer
    the routes that would call out to a media server from the sample data, and
    intercept everything else that writes. Registered as a before_request only
    when DEMO_MODE is on."""
    if not is_demo():
        return None

    _reseed_if_stale()

    # Persistent demo identity so requires_auth and templates see a user.
    if not session.get('authenticated'):
        session['authenticated'] = True
        session['username'] = DEMO_USERNAME

    endpoint = request.endpoint or ''

    # Every artwork proxy (media server, Sonarr, Radarr) answers from the same
    # committed sample images here.
    if endpoint in ('main.proxy_art', 'main.proxy_sonarr_art', 'main.proxy_radarr_art'):
        return _serve_demo_art()

    # A public showcase has no account to log in or out of: the logout button
    # would otherwise clear the session and drop the visitor into first-run
    # setup, which is not a demo of anything.
    if endpoint in ('auth.login', 'auth.logout') or endpoint.startswith('auth.setup'):
        return redirect(url_for('main.index'))

    if request.method == 'GET':
        handler = _DEMO_GET_HANDLERS.get(endpoint)
        return handler() if handler else None

    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        handler = _DEMO_WRITE_HANDLERS.get(endpoint)
        if handler:
            return handler()
        if endpoint in _ALLOWED_WRITE_ENDPOINTS:
            return None
        if endpoint.startswith('api.test_') or endpoint.startswith('api.plex_'):
            return _demo_test_connection()
        logger.debug(f"Demo mode blocked write to {endpoint}")
        if _wants_json():
            return jsonify({"status": "demo", "demo": True, "message": DEMO_NOTICE}), 200
        # A persistent banner (base.html, keyed off the demo_mode global) already
        # explains the read-only state, so just bounce back without saving.
        return redirect(request.referrer or url_for('main.index'))
    return None

def install(app):
    """Wire demo mode into the app when DEMO_MODE is set: seed caches, swap the
    render-time media server lookups for sample data, and register the
    read-only/auth before_request guard."""
    if not is_demo():
        return
    logger.warning("DEMO_MODE is enabled: this instance is read-only and auth is bypassed")
    seed_demo_cache()
    app.before_request(demo_before_request)
    app.jinja_env.globals["demo_mode"] = True
    app.jinja_env.globals["demo_notice"] = DEMO_NOTICE
