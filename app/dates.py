"""Date and time display formatting."""

from datetime import timedelta

DATE_FORMATS = ('mdy', 'dmy', 'ymd')
TIME_FORMATS = ('12', '24')
WEEK_STARTS = ('sunday', 'monday')

DEFAULT_DATE_FORMAT = 'mdy'
DEFAULT_TIME_FORMAT = '12'
DEFAULT_WEEK_START = 'sunday'

MONTH_ABBR = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
              'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
MONTH_FULL = ('January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December')
# Monday-first, matching datetime.weekday()
WEEKDAY_ABBR = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
WEEKDAY_FULL = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')

def resolve_date_format(value):
    return value if value in DATE_FORMATS else DEFAULT_DATE_FORMAT

def resolve_time_format(value):
    return str(value) if str(value) in TIME_FORMATS else DEFAULT_TIME_FORMAT

def resolve_week_start(value):
    return value if value in WEEK_STARTS else DEFAULT_WEEK_START

def week_start_offset(value):
    """0 when weeks start on Sunday, 1 when they start on Monday. The offset
    rotates both the weekday header labels and the first-cell calculation."""
    return 1 if resolve_week_start(value) == 'monday' else 0

def weekday_labels(week_start=DEFAULT_WEEK_START):
    """Abbreviated weekday headers in display order for the chosen week start."""
    offset = week_start_offset(week_start)
    # WEEKDAY_ABBR is Monday-first; Sunday-first is that rotated by one
    order = WEEKDAY_ABBR if offset else (WEEKDAY_ABBR[-1],) + WEEKDAY_ABBR[:-1]
    return order

def start_of_week(day, week_start=DEFAULT_WEEK_START):
    """The Sunday (or Monday) on or before `day`."""
    if week_start_offset(week_start):
        back = day.weekday()
    else:
        back = (day.weekday() + 1) % 7
    return day - timedelta(days=back)

def fmt_numeric_date(d, fmt=DEFAULT_DATE_FORMAT):
    """9/5/26 | 5/9/26 | 26/9/5 - the compact range label."""
    fmt = resolve_date_format(fmt)
    yy = d.year % 100
    if fmt == 'dmy':
        return f"{d.day}/{d.month}/{yy}"
    if fmt == 'ymd':
        return f"{yy}/{d.month}/{d.day}"
    return f"{d.month}/{d.day}/{yy}"

def fmt_month_day(d, fmt=DEFAULT_DATE_FORMAT):
    """Sep 5 | 5 Sep | Sep 5 - no year. ymd has no year to lead with here, so
    it follows mdy rather than inventing a third order."""
    fmt = resolve_date_format(fmt)
    month = MONTH_ABBR[d.month - 1]
    if fmt == 'dmy':
        return f"{d.day} {month}"
    return f"{month} {d.day}"

def fmt_weekday_date(d, fmt=DEFAULT_DATE_FORMAT):
    """Tue, Sep 5 | Tue, 5 Sep - the agenda and calendar cell label."""
    return f"{WEEKDAY_ABBR[d.weekday()]}, {fmt_month_day(d, fmt)}"

def fmt_long_date(d, fmt=DEFAULT_DATE_FORMAT):
    """September 5, 2026 | 5 September 2026 | 2026 September 5."""
    fmt = resolve_date_format(fmt)
    month = MONTH_FULL[d.month - 1]
    if fmt == 'dmy':
        return f"{d.day} {month} {d.year}"
    if fmt == 'ymd':
        return f"{d.year} {month} {d.day}"
    return f"{month} {d.day}, {d.year}"

def fmt_month_year(d):
    """September 2026. No day, so the field order setting does not apply."""
    return f"{MONTH_FULL[d.month - 1]} {d.year}"

def fmt_iso_date(d):
    """2026-09-05. A display shape that is deliberately format independent,
    used where a sortable date reads better than a localized one."""
    return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"

def fmt_time(t, mode=DEFAULT_TIME_FORMAT, seconds=False):
    """9:05 AM | 09:05, optionally with seconds."""
    mode = resolve_time_format(mode)
    if mode == '24':
        core = f"{t.hour:02d}:{t.minute:02d}"
        return f"{core}:{t.second:02d}" if seconds else core
    hour = t.hour % 12 or 12
    meridiem = 'AM' if t.hour < 12 else 'PM'
    core = f"{hour}:{t.minute:02d}"
    if seconds:
        core = f"{core}:{t.second:02d}"
    return f"{core} {meridiem}"

def fmt_schedule_stamp(dt, fmt=DEFAULT_DATE_FORMAT, mode=DEFAULT_TIME_FORMAT):
    """Tuesday Sep. 5, 2026  09:05 - the scheduling page's next/last send
    label. The trailing month period and the double space before the time are
    both preserved from the original inline formatting."""
    fmt = resolve_date_format(fmt)
    weekday = WEEKDAY_FULL[dt.weekday()]
    month = f"{MONTH_ABBR[dt.month - 1]}."
    if fmt == 'dmy':
        datepart = f"{dt.day} {month} {dt.year}"
    elif fmt == 'ymd':
        datepart = f"{dt.year} {month} {dt.day}"
    else:
        datepart = f"{month} {dt.day}, {dt.year}"
    return f"{weekday} {datepart}  {fmt_time(dt, mode)}"

def fmt_short_stamp(d, fmt=DEFAULT_DATE_FORMAT):
    """Sep. 5, 2026 - the schedule start-date label."""
    fmt = resolve_date_format(fmt)
    month = f"{MONTH_ABBR[d.month - 1]}."
    if fmt == 'dmy':
        return f"{d.day} {month} {d.year}"
    if fmt == 'ymd':
        return f"{d.year} {month} {d.day}"
    return f"{month} {d.day}, {d.year}"

# Theme-dict carriage, mirroring app/emails/density.py. The values are stamped
# once where the theme dict is built and read from it downstream, so no builder
# re-reads settings mid-render.

def stamp(theme, date_format=None, time_format=None, week_start=None):
    merged = dict(theme)
    merged['date_format'] = resolve_date_format(date_format)
    merged['time_format'] = resolve_time_format(time_format)
    merged['week_start'] = resolve_week_start(week_start)
    return merged

def date_format_of(theme):
    return resolve_date_format((theme or {}).get('date_format'))

def time_format_of(theme):
    return resolve_time_format((theme or {}).get('time_format'))

def week_start_of(theme):
    return resolve_week_start((theme or {}).get('week_start'))
