# Random Pick snap-in (NEWS-17): a single wide featured card surfacing one
# random item from a chosen library. The pick itself is drawn at render time
# in assemble.py, so previews and every send get a fresh item.
from app.emails import density, headings
from app.emails.images import fetch_and_attach_image, truncate_text
from app.security import escape_html_output as esc

import logging

logger = logging.getLogger(__name__)

FONT = "'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif"

def random_pick_heading(library_label, genre_label=""):
    heading = "Random Pick"
    if library_label:
        heading += f" - {library_label}"
    if genre_label:
        heading += f" ({genre_label})"
    return heading

def random_pick_meta_text(pick):
    bits = []
    if pick.get('year'):
        bits.append(str(pick['year']))
    if pick.get('duration'):
        try:
            ms = int(pick['duration'])
            s = ms // 1000
            h = s // 3600
            m = (s % 3600) // 60
            bits.append(f"{h}h {m}m" if h else f"{m}m")
        except (TypeError, ValueError):
            pass
    if pick.get('content_rating'):
        bits.append(pick['content_rating'])
    if pick.get('genres'):
        bits.append(', '.join(pick['genres'][:3]))
    return ' • '.join(bits)

def attach_random_pick_poster(pick, msg_root, base_url, hosted_images_enabled=False, hosted_base_url="", target=(180, 270)):
    for candidate in (pick.get('thumb'), pick.get('art')):
        if candidate:
            poster_url = f"/proxy-art{candidate}" if not candidate.startswith('/proxy-art') else candidate
            poster_src = fetch_and_attach_image(
                poster_url,
                msg_root,
                f"random-pick-{pick.get('rating_key', 'item')}",
                base_url,
                target=target,
                hosted_images_enabled=hosted_images_enabled,
                hosted_base_url=hosted_base_url,
            )
            if poster_src:
                return poster_src
    return None

def build_random_pick_html(pick, msg_root, theme_colors, base_url="", library_label="", genre_label="", hosted_images_enabled=False, hosted_base_url="", heading=None):
    heading = heading or random_pick_heading(library_label, genre_label)

    if not pick:
        return f"""
        <div style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: {FONT};">
            <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: {FONT};">No random pick available{f' for {esc(library_label)}' if library_label else ''}.</p>
        </div>
        """

    title = pick.get('title', 'Unknown')
    meta_text = random_pick_meta_text(pick)
    summary = pick.get('tagline') or pick.get('summary', '')
    summary = truncate_text(summary, 380) if summary else ''  # re-capped per density below
    plex_url = pick.get('plex_url', '')

    p = density.picker(theme_colors)
    art_on = density.show_art(theme_colors)
    poster_px = 180
    poster_src = attach_random_pick_poster(pick, msg_root, base_url, hosted_images_enabled=hosted_images_enabled, hosted_base_url=hosted_base_url, target=(poster_px, int(poster_px * 1.5))) if art_on else None

    if poster_src:
        poster_html = f"""
            <td width="{poster_px}" style="width: {poster_px}px; padding: 0; vertical-align: top; line-height: 0; font-size: 0;">
                <img src="{poster_src}" alt="{esc(title)}" width="{poster_px}" style="width: {poster_px}px; height: auto; display: block; border-radius: 10px 0 0 10px; background-color: #f8f9fa;">
            </td>
        """
    else:
        poster_html = ""

    open_link = ""
    if plex_url:
        open_link = f"""
            <div style="margin-top: 10px;">
                <a href="{esc(plex_url)}" target="_blank" style="display: inline-block; padding: 6px 14px; border-radius: 6px; background-color: {theme_colors['primary']}; color: #ffffff; font-size: 12px; font-weight: bold; text-decoration: none; font-family: {FONT};">Open in Plex</a>
            </div>
        """

    heading = headings.resolve(theme_colors, heading)
    heading_html = (
        f"""<h2 style="text-align: center; color: {theme_colors['text']}; margin: {p('6px 0', '0 0 10px 0')}; font-size: {p('17px', '24px')}; font-weight: bold; font-family: {FONT};">{esc(heading)}</h2>"""
        if heading else ''
    )

    return f"""
        <div style="background-color: {theme_colors['card_bg']}; padding-bottom: {p('6px', '10px')}; border-radius: 8px; margin: {p('10px 0', '20px 0')}; border: 1px solid {theme_colors['border']}; font-family: {FONT}; overflow: hidden; max-width: 100%;">
            {heading_html}
            <table cellpadding="0" cellspacing="0" border="0" style="width: 100%; border-collapse: collapse; margin: 0; padding: 0;">
                <tr>
                    <td style="padding: {p('4px 12px', '8px 16px')};">
                        <table cellpadding="0" cellspacing="0" border="0" style="width: 100%; background-color: {theme_colors['card_bg']}; border: 1px solid {theme_colors['border']}; border-radius: 10px; box-shadow: 0 6px 18px rgba(0, 0, 0, 0.6);">
                            <tr>
                                {poster_html}
                                <td style="padding: {p('9px 12px', '14px 16px')}; vertical-align: top;">
                                    <div style="font-weight: bold; font-size: {p('16px', '20px')}; color: {theme_colors['text']}; line-height: 1.2; font-family: {FONT}; word-wrap: break-word; overflow-wrap: break-word;">{esc(title)}</div>
                                    {f'''<div style="font-size: {p('11px', '12px')}; color: {theme_colors['muted_text']}; margin-top: {p('3px', '4px')}; font-family: {FONT};">{esc(meta_text)}</div>''' if meta_text else ''}
                                    {f'''<div style="font-size: {p('12px', '13px')}; color: {theme_colors['text']}; opacity: 0.85; line-height: 1.4; margin-top: {p('5px', '8px')}; font-family: {FONT}; word-wrap: break-word; overflow-wrap: break-word;">{esc(truncate_text(summary, p(170, 380)))}</div>''' if summary else ''}
                                    {open_link}
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </div>
    """
