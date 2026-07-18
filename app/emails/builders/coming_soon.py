# Kept in sync by hand with buildSonarrComingSoonPreviewHTML/
# buildRadarrComingSoonPreviewHTML in static/js/app/04-stats-graphs.js.
from datetime import datetime, timezone

from app.emails.builders.card_grid import format_relative_date as _format_relative_date, empty_state_html as _empty_state_html, build_calendar_grid_html as _build_calendar_grid_html, build_card_html as _build_card_html
from app.emails.images import fetch_and_attach_image, truncate_text

import logging

logger = logging.getLogger(__name__)

def _poster_url(images):
    # Sonarr/Radarr calendar images often carry only remoteUrl (an absolute
    # thetvdb/tmdb CDN link) with no local 'url' path, so fall back to it.
    for img in images or []:
        if img.get('coverType') == 'poster' and (img.get('url') or img.get('remoteUrl')):
            return img.get('url') or img.get('remoteUrl')
    for img in images or []:
        if img.get('url') or img.get('remoteUrl'):
            return img.get('url') or img.get('remoteUrl')
    return None

def _arr_poster_src(poster, arr_prefix):
    """Given a raw poster reference and an *arr proxy prefix, return the URL to
    hand to fetch_and_attach_image. Absolute remoteUrls are fetched directly;
    local paths go through the authenticated /proxy-{sonarr,radarr}-art route."""
    if not poster:
        return None
    if poster.startswith('http'):
        return poster
    if poster.startswith(arr_prefix):
        return poster
    return f"{arr_prefix}{poster}"

def _parse_release_date(date_str):
    """Parse an *arr date string to a date. Mirrors _format_relative_date's
    tz handling: UTC for tz-aware strings, local for naive. Returns None on
    empty/unparseable input."""
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
        if dt.tzinfo:
            return dt.astimezone(timezone.utc).date()
        return dt.date()
    except Exception:
        logger.debug("suppressed exception; using fallback", exc_info=True)
        return None

def upcoming_release_date(movie, today=None):
    """Earliest of inCinemas/digitalRelease/physicalRelease that is today or
    later, as a date. None if the movie has no upcoming date. Mirrored by
    _comingSoonUpcomingReleaseDate in 04-stats-graphs.js (which uses browser-local
    time, so a UTC-midnight release can differ by a day between preview and email)."""
    if today is None:
        today = datetime.now(timezone.utc).date()
    candidates = []
    for field in ('inCinemas', 'digitalRelease', 'physicalRelease'):
        d = _parse_release_date(movie.get(field))
        if d is not None and d >= today:
            candidates.append(d)
    return min(candidates) if candidates else None

def filter_radarr_upcoming(movies, today=None):
    """Drop movies already downloaded (hasFile truthy) or with no upcoming
    release date. m.get('hasFile') degrades safely if the calendar omits the
    field. Mirrored in buildRadarrComingSoonPreviewHTML."""
    result = []
    for m in movies or []:
        if m.get('hasFile'):
            continue
        if upcoming_release_date(m, today) is None:
            continue
        result.append(m)
    return result

def _episode_air_day(ep):
    """The local air day (YYYY-MM-DD) used as a grouping key. Sonarr's airDate
    is already local and timezone-stable on both sides; fall back to the UTC
    date only when airDate is absent."""
    return ep.get('airDate') or (ep.get('airDateUtc') or '')[:10]

def group_sonarr_episodes(episodes):
    """Collapse full-season drops (2+ episodes of the same series/season airing
    the same day) into a single group entry, preserving first-appearance order.
    Episodes with seasonNumber None are never grouped. Returns a list of dicts:
    {'series', 'season', 'episodes', 'air_date'}. Mirrored by _groupSonarrEpisodes
    in static/js/app/04-stats-graphs.js."""
    groups = []
    index_by_key = {}
    for ep in episodes:
        series = ep.get('series') or {}
        season = ep.get('seasonNumber')
        air_day = _episode_air_day(ep)
        if season is not None:
            key = (series.get('id') or series.get('title') or ep.get('title'), season, air_day)
        else:
            key = None  # never groups
        if key is not None and key in index_by_key:
            groups[index_by_key[key]]['episodes'].append(ep)
            continue
        entry = {'series': series, 'season': season, 'episodes': [ep], 'air_date': air_day}
        if key is not None:
            index_by_key[key] = len(groups)
        groups.append(entry)
    return groups

def build_sonarr_coming_soon_html_with_cids(episodes, msg_root, theme_colors, base_url="", grid_columns=5, hosted_images_enabled=False, hosted_base_url=""):
    if not episodes:
        return _empty_state_html(theme_colors, "No upcoming episodes found.")

    groups = group_sonarr_episodes(episodes)
    cards = []
    for i, group in enumerate(groups):
        series = group['series']
        eps = group['episodes']
        first_ep = eps[0]
        series_title = series.get('title') or first_ep.get('title', 'Unknown')
        season = group['season']
        year = series.get('year') or first_ep.get('year') or ''
        year_prefix = str(year) if year else ""
        relative = _format_relative_date(first_ep.get('airDateUtc') or first_ep.get('airDate'))

        poster = _poster_url(series.get('images')) or _poster_url(first_ep.get('images'))
        poster_src = None
        poster_url = _arr_poster_src(poster, '/proxy-sonarr-art')
        if poster_url:
            poster_src = fetch_and_attach_image(poster_url, msg_root, f"sonarr-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

        if len(eps) >= 2:
            season_label = f"Season {season}" if season is not None else "New episodes"
            subtitle_text = f"{season_label} ({len(eps)} episodes)"
            subtitle = truncate_text(' • '.join(filter(None, [year_prefix, subtitle_text])), 40)
        else:
            episode_num = first_ep.get('episodeNumber')
            se_label = f"S{int(season):02d}E{int(episode_num):02d}" if season is not None and episode_num is not None else ""
            episode_title = first_ep.get('title', '')
            se_text = ' - '.join(filter(None, [se_label, episode_title]))
            subtitle = truncate_text(' • '.join(filter(None, [year_prefix, se_text])), 40)
        meta_text = truncate_text(' • '.join(filter(None, [f'Airs {relative}' if relative else ''])), 46)

        cards.append(_build_card_html(theme_colors, truncate_text(series_title, 23), subtitle, meta_text, poster_src))

    return _build_calendar_grid_html(cards, msg_root, theme_colors, "Coming Soon (TV)", base_url, grid_columns)

def build_radarr_coming_soon_html_with_cids(movies, msg_root, theme_colors, base_url="", grid_columns=5, hosted_images_enabled=False, hosted_base_url=""):
    movies = filter_radarr_upcoming(movies)
    if not movies:
        return _empty_state_html(theme_colors, "No upcoming movies found.")

    cards = []
    for i, movie in enumerate(movies):
        title = movie.get('title', 'Unknown')
        year = movie.get('year', '')
        release_date = upcoming_release_date(movie)
        relative = _format_relative_date(release_date.isoformat() if release_date else None)

        poster = _poster_url(movie.get('images'))
        poster_src = None
        poster_url = _arr_poster_src(poster, '/proxy-radarr-art')
        if poster_url:
            poster_src = fetch_and_attach_image(poster_url, msg_root, f"radarr-{i}", base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

        subtitle = str(year) if year else ""
        meta_text = truncate_text(' • '.join(filter(None, [f'Releases {relative}' if relative else ''])), 46)

        cards.append(_build_card_html(theme_colors, truncate_text(title, 23), subtitle, meta_text, poster_src))

    return _build_calendar_grid_html(cards, msg_root, theme_colors, "Coming Soon (Movies)", base_url, grid_columns)
