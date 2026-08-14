# Top Viewer snap-in: a callout for whoever streamed the most over
# the pull's time range
from app.emails import density, headings
from app.emails.images import fetch_and_attach_small_thumbnail
from app.security import escape_html_output as esc

import logging

logger = logging.getLogger(__name__)

FONT = "'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif"

ANONYMOUS_SUBJECT = "One viewer led the way"

def top_viewer_heading(range_text=""):
    return f"Top Viewer{f' - {range_text}' if range_text else ''}"

def find_top_viewer(stats_data):
    for stat in stats_data or []:
        if (stat.get('stat_title') or '').strip().lower() == 'most active users':
            rows = [r for r in (stat.get('rows') or []) if r]
            if not rows:
                return None
            return max(rows, key=lambda r: _int(r.get('total_duration')) or _int(r.get('total_plays')))
    return None

def _int(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0

def watch_time_text(row):
    seconds = _int(row.get('total_duration'))
    if seconds <= 0:
        return ""
    hours, minutes = seconds // 3600, (seconds % 3600) // 60
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"

def play_count_text(row):
    plays = _int(row.get('total_plays'))
    if plays <= 0:
        return ""
    return f"{plays} play" if plays == 1 else f"{plays} plays"

def top_viewer_metrics(row):
    return [bit for bit in (watch_time_text(row), play_count_text(row)) if bit]

def attach_top_viewer_avatar(row, msg_root, base_url, size=56, hosted_images_enabled=False, hosted_base_url=""):
    thumb = row.get('user_thumb') or ''
    if not thumb:
        return None
    return fetch_and_attach_small_thumbnail(
        thumb, msg_root, "top-viewer-avatar", base_url, height=size,
        hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url)

def build_top_viewer_html(row, msg_root, theme_colors, base_url="", range_text="",
                          include_user_info=True, hosted_images_enabled=False, hosted_base_url=""):
    heading = top_viewer_heading(range_text)
    if not row:
        return ""

    metrics = top_viewer_metrics(row)
    if not metrics:
        # nothing to say without at least one number
        return ""

    p = density.picker(theme_colors)
    name = esc(row.get('user') or row.get('friendly_name') or '')
    # the avatar is artwork, so the compact density drops it; the name still
    # follows the user-info setting
    avatar_src = attach_top_viewer_avatar(
        row, msg_root, base_url,
        hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url) if (include_user_info and density.show_art(theme_colors)) else None

    avatar_html = ""
    if avatar_src:
        avatar_html = (f'<td width="56" valign="middle" style="padding-right: 14px;">'
                       f'<img src="{avatar_src}" alt="" width="56" height="56" style="width: 56px; height: 56px; '
                       f'border-radius: 50%; object-fit: cover; display: block;"></td>')

    subject = name if (include_user_info and name) else ANONYMOUS_SUBJECT

    heading = headings.resolve(theme_colors, heading)
    heading_html = (
        f"""<div style="background-color: {theme_colors['primary']}; color: white; padding: {p('8px 12px', '12px 15px')}; font-weight: bold; font-size: {p('13.5px', '16px')}; font-family: {FONT};">{esc(heading)}</div>"""
        if heading else ''
    )

    return f"""
        <div style="margin: {p('10px 0', '20px 0')}; border-radius: 8px; overflow: hidden; border: 1px solid {theme_colors['border']}; background-color: {theme_colors['card_bg']}; font-family: {FONT};">
            {heading_html}
            <table width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
                <td style="padding: {p('10px 12px', '16px 15px')}; font-family: {FONT};">
                    <table cellpadding="0" cellspacing="0" border="0"><tr>
                        {avatar_html}
                        <td valign="middle" style="font-family: {FONT};">
                            <div style="font-size: {p('16px', '20px')}; font-weight: bold; color: #ffffff; line-height: 1.2;">{esc(subject)}</div>
                            <div style="padding-top: {p('3px', '5px')}; font-size: {p('12px', '13px')}; color: {theme_colors['muted_text']};">{' &middot; '.join(esc(bit) for bit in metrics)}</div>
                        </td>
                    </tr></table>
                </td>
            </tr></table>
        </div>
    """
