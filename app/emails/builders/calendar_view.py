# Calendar and agenda renderings of the Coming Soon snap-ins.

from datetime import timedelta

from app.emails import headings
from app.security import escape_html_output as esc

import logging

logger = logging.getLogger(__name__)

FONT = "'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif"

VIEWS = ('grid', 'calendar', 'agenda')

# Sunday-first, matching the *arr calendars' default week start.
WEEKDAY_LABELS = ('Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat')

# A wide days-ahead window (the setting allows up to 90) would otherwise emit a
# 13-row table that no mail client renders comfortably. Weeks past the cap are
# summarized in a trailing line rather than dropped silently.
MAX_CALENDAR_WEEKS = 6

def make_event(date, title, subtitle="", poster_src=None):
    """One normalized calendar entry. date is a datetime.date or None; entries
    without a date are dropped by both views since neither can place them."""
    return {'date': date, 'title': title or '', 'subtitle': subtitle or '', 'poster_src': poster_src}

def _week_start(day):
    """The Sunday on or before day."""
    return day - timedelta(days=(day.weekday() + 1) % 7)

def group_events_by_day(events):
    """{date: [event, ...]} for events carrying a date, insertion order kept
    within each day."""
    by_day = {}
    for event in events or []:
        if not event.get('date'):
            continue
        by_day.setdefault(event['date'], []).append(event)
    return by_day

def calendar_span(by_day, today):
    """(first_cell_day, last_day, overflow_days) for the month grid.

    Starts at the Sunday of the current week so the reader sees where today
    sits, and runs to the last day holding an event. overflow_days lists the
    event days past MAX_CALENDAR_WEEKS, which the caller footnotes."""
    if not by_day:
        return None, None, []
    days = sorted(by_day)
    start = _week_start(min(today, days[0]))
    last_cell = start + timedelta(days=MAX_CALENDAR_WEEKS * 7 - 1)
    overflow = [d for d in days if d > last_cell]
    end = min(days[-1], last_cell)
    return start, end, overflow

def _event_html(event, theme):
    """Poster over title. The media rules turn this into poster-beside-title on
    narrow screens, so the poster carries its own class: the global
    .card-poster-img rule forces width 100% and would blow it up there."""
    title = esc(event.get('title') or '')
    subtitle = esc(event.get('subtitle') or '')
    poster_src = event.get('poster_src')
    poster_html = ""
    if poster_src:
        poster_html = (f'<img class="cs-cal-poster" src="{poster_src}" alt="{title}" '
                       f'style="width: 100%; height: auto; display: block; margin: 0 0 3px 0; '
                       f'border-radius: 4px; background-color: #f8f9fa;">')
    sub_html = ""
    if subtitle:
        sub_html = (f'<div style="font-size: 9.5px; color: {theme["muted_text"]}; line-height: 1.25; '
                    f'word-wrap: break-word; overflow-wrap: break-word;">{subtitle}</div>')
    return f"""
        <div class="cs-cal-event" style="margin: 0 0 6px 0; font-family: {FONT};">
            {poster_html}
            <div class="cs-cal-event-text">
                <div style="font-size: 10px; font-weight: 600; color: {theme['text']}; line-height: 1.25;
                    word-wrap: break-word; overflow-wrap: break-word;">{title}</div>
                {sub_html}
            </div>
        </div>
    """

def _day_cell_html(day, events, theme, today, cell_width_pct):
    """One day of the month grid. Empty days keep their number on desktop and
    are dropped entirely on narrow screens (cs-cal-empty), which is what turns
    the grid into a readable list rather than a column of blank blocks."""
    classes = "cs-cal-cell"
    if not events:
        classes += " cs-cal-empty"
    is_today = day == today
    bg = theme['card_bg'] if not is_today else theme['border']
    day_color = theme['primary'] if is_today else theme['muted_text']
    number_weight = "700" if is_today else "600"
    body = "".join(_event_html(event, theme) for event in events)
    # Both date labels ship in every cell; the media rules swap which one shows,
    # because a bare "15" reads fine under a weekday header but not in a list.
    long_label = day.strftime('%a, %b ') + str(day.day)
    return f"""
        <td class="{classes}" valign="top" style="width: {cell_width_pct}; padding: 6px 5px;
            background-color: {bg}; border: 1px solid {theme['border']};
            font-family: {FONT}; vertical-align: top;">
            <div class="cs-cal-daynum" style="font-size: 11px; font-weight: {number_weight};
                color: {day_color}; margin-bottom: 4px;">{day.day}</div>
            <div class="cs-cal-daylong" style="display: none; font-size: 12px; font-weight: 700;
                color: {day_color}; margin-bottom: 5px;">{esc(long_label)}</div>
            {body}
        </td>
    """

def build_month_calendar_html(events, theme, today, container=None):
    """Month-style grid: a weekday header row and one row per week."""
    by_day = group_events_by_day(events)
    start, end, overflow = calendar_span(by_day, today)
    if start is None:
        return None

    cell_width_pct = f"{100 / 7:.4f}%"
    head_cells = "".join(
        f'<td align="center" style="width: {cell_width_pct}; padding: 5px 2px; font-size: 10px; '
        f'font-weight: 700; letter-spacing: .06em; text-transform: uppercase; '
        f'color: {theme["muted_text"]}; font-family: {FONT};">{label}</td>'
        for label in WEEKDAY_LABELS
    )
    rows_html = (f'<tr class="cs-cal-head">{head_cells}</tr>')

    week = start
    while week <= end:
        cells = ""
        for offset in range(7):
            day = week + timedelta(days=offset)
            cells += _day_cell_html(day, by_day.get(day, []), theme, today, cell_width_pct)
        rows_html += f'<tr class="cs-cal-row">{cells}</tr>'
        week += timedelta(days=7)

    footnote = ""
    if overflow:
        count = sum(len(by_day[d]) for d in overflow)
        label = "item" if count == 1 else "items"
        footnote = (f'<div style="padding: 8px 10px 0 10px; font-size: 11px; '
                    f'color: {theme["muted_text"]}; font-family: {FONT};">'
                    f'Plus {count} more {label} after {end.strftime("%b ")}{end.day}.</div>')

    inner = f"""
        <table class="cs-cal-table" width="100%" cellpadding="0" cellspacing="0" border="0"
            style="width: 100%; border-collapse: collapse; table-layout: fixed; margin: 0;">
            {rows_html}
        </table>
        {footnote}
    """
    return container(inner) if container else inner

def _agenda_item_html(event, theme):
    """One agenda entry: small poster beside the title at every width, so this
    row needs no reflow of its own."""
    title = esc(event.get('title') or '')
    subtitle = esc(event.get('subtitle') or '')
    poster_src = event.get('poster_src')
    poster_cell = ""
    if poster_src:
        # no class: 44px reads at every width, so this poster never reflows
        poster_cell = (f'<td width="44" valign="top" style="padding: 0 10px 0 0;">'
                       f'<img src="{poster_src}" alt="{title}" width="44" '
                       f'style="width: 44px; height: auto; display: block; border-radius: 4px; '
                       f'background-color: #f8f9fa;"></td>')
    sub_html = ""
    if subtitle:
        sub_html = (f'<div style="font-size: 11.5px; color: {theme["muted_text"]}; padding-top: 2px; '
                    f'line-height: 1.3;">{subtitle}</div>')
    return f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin: 0 0 8px 0;"><tr>
            {poster_cell}
            <td valign="top" style="font-family: {FONT};">
                <div style="font-size: 13px; font-weight: 600; color: {theme['text']}; line-height: 1.3;">{title}</div>
                {sub_html}
            </td>
        </tr></table>
    """

def build_agenda_html(events, theme, today, container=None):
    """Dated rows: one row per day that has content, date on the left."""
    by_day = group_events_by_day(events)
    if not by_day:
        return None

    rows_html = ""
    for day in sorted(by_day):
        if day == today:
            date_label = "Today"
        elif day == today + timedelta(days=1):
            date_label = "Tomorrow"
        else:
            date_label = day.strftime('%a, %b ') + str(day.day)
        items = "".join(_agenda_item_html(event, theme) for event in by_day[day])
        rows_html += f"""
            <tr class="cs-agenda-row">
                <td class="cs-agenda-date" width="104" valign="top" style="padding: 10px 14px 10px 0;
                    border-top: 1px solid {theme['border']}; font-family: {FONT}; font-size: 12px;
                    font-weight: 700; color: {theme['primary']}; white-space: nowrap;">{esc(date_label)}</td>
                <td class="cs-agenda-items" valign="top" style="padding: 10px 0;
                    border-top: 1px solid {theme['border']};">{items}</td>
            </tr>
        """

    inner = f"""
        <table class="cs-agenda-table" width="100%" cellpadding="0" cellspacing="0" border="0"
            style="width: 100%; border-collapse: collapse; margin: 0;">
            {rows_html}
        </table>
    """
    return container(inner) if container else inner

def section_container_html(theme, title, inner):
    """The legacy (non-layout) section chrome, matching the poster grid's card
    so a view switch does not also change the surrounding frame."""
    title = headings.resolve(theme, title)
    title_html = (
        f"""<h2 style="text-align: center; color: {theme['text']}; margin: 0 0 10px 0; padding-top: 12px;
                font-size: 24px; font-weight: bold; font-family: {FONT};">{esc(title)}</h2>"""
        if title else ''
    )
    return f"""
        <div style="background-color: {theme['card_bg']}; padding: 0 10px 12px 10px; border-radius: 8px;
            margin: 20px 0; border: 1px solid {theme['border']}; font-family: {FONT};
            overflow: hidden; max-width: 100%;">
            {title_html}
            {inner}
        </div>
    """
