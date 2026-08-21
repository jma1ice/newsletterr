import calendar, os, secrets, sqlite3
from datetime import datetime, timedelta

from app import config, dates
from app.db import db_connect
from app.settings_store import get_settings

import logging

logger = logging.getLogger(__name__)

HOSTED_IMAGES_DIR = os.path.join("database", "hosted_images")

def save_hosted_image(image_bytes, content_type):
    token = secrets.token_urlsafe(24)
    with open(os.path.join(HOSTED_IMAGES_DIR, token), 'wb') as f:
        f.write(image_bytes)
    conn = db_connect()
    conn.execute("INSERT INTO hosted_images (token, content_type) VALUES (?, ?)", (token, content_type))
    conn.commit()
    conn.close()
    return token

def get_hosted_image(token):
    conn = db_connect()
    row = conn.execute("SELECT content_type FROM hosted_images WHERE token = ?", (token,)).fetchone()
    conn.close()
    if not row:
        return None
    path = os.path.join(HOSTED_IMAGES_DIR, token)
    if not os.path.exists(path):
        return None
    return path, row[0]

def cleanup_expired_hosted_images():
    retention_days = get_settings().get("hosted_image_retention_days", 90)
    conn = db_connect()
    cutoff = f'-{retention_days} days'
    rows = conn.execute("SELECT token FROM hosted_images WHERE created_at < datetime('now', ?)", (cutoff,)).fetchall()
    for (token,) in rows:
        try:
            os.remove(os.path.join(HOSTED_IMAGES_DIR, token))
        except FileNotFoundError:
            pass
    conn.execute("DELETE FROM hosted_images WHERE created_at < datetime('now', ?)", (cutoff,))
    conn.commit()
    conn.close()

def get_saved_email_lists():
    if config.DEMO_MODE:
        from app.demo import demo_email_list_rows
        lists = demo_email_list_rows()
    else:
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, emails FROM email_lists ORDER BY name")
        lists = cursor.fetchall()
        conn.close()
    return [{'id': row[0], 'name': row[1], 'emails': row[2]} for row in lists]

def save_email_list(name, emails):
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO email_lists
            (name, emails)
            VALUES (?, ?)
            ON CONFLICT (name) DO UPDATE
            SET emails = excluded.emails
        """, (name, emails))
        conn.commit()
        return True
    except:
        logger.debug("suppressed exception; using fallback", exc_info=True)
        return False
    finally:
        conn.close()

def delete_email_list(list_id):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM email_lists WHERE id = ?", (list_id,))
    cursor.execute("DELETE FROM contacts WHERE list_id = ?", (list_id,))
    conn.commit()
    conn.close()

# --- contacts
#
# email_lists.emails stays the address of record for sends; every write here
# rewrites it from the contacts rows so the two can never drift. Contacts adds
# the name column that standalone mode needs and that Tautulli used to supply.

def get_contacts(list_id):
    conn = db_connect()
    try:
        rows = conn.execute(
            "SELECT id, email, name FROM contacts WHERE list_id = ? ORDER BY email",
            (list_id,),
        ).fetchall()
    finally:
        conn.close()
    return [{'id': r[0], 'email': r[1], 'name': r[2] or ''} for r in rows]

def get_contact_names():
    """{email_lower: name} across every list, for personalization."""
    conn = db_connect()
    try:
        rows = conn.execute(
            "SELECT email, name FROM contacts WHERE name IS NOT NULL AND name != ''"
        ).fetchall()
    finally:
        conn.close()
    return {(r[0] or '').strip().lower(): r[1] for r in rows}

def _sync_list_emails(cursor, list_id):
    """Rewrite email_lists.emails from the list's contact rows."""
    rows = cursor.execute(
        "SELECT email FROM contacts WHERE list_id = ? ORDER BY email", (list_id,)
    ).fetchall()
    cursor.execute(
        "UPDATE email_lists SET emails = ? WHERE id = ?",
        (', '.join(r[0] for r in rows), list_id),
    )

def add_contacts(list_id, entries):
    conn = db_connect()
    cursor = conn.cursor()
    added = 0
    try:
        for email, name in entries:
            cursor.execute(
                "INSERT OR IGNORE INTO contacts (list_id, email, name) VALUES (?, ?, ?)",
                (list_id, email, name or ''),
            )
            added += cursor.rowcount or 0
        _sync_list_emails(cursor, list_id)
        conn.commit()
        return added
    except sqlite3.Error as e:
        logger.error(f"Error adding contacts: {e}")
        conn.rollback()
        return 0
    finally:
        conn.close()

def delete_contact(contact_id):
    conn = db_connect()
    cursor = conn.cursor()
    try:
        row = cursor.execute("SELECT list_id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
        if not row:
            return False
        cursor.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        _sync_list_emails(cursor, row[0])
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error deleting contact: {e}")
        return False
    finally:
        conn.close()

# --- media user emails
#
# Jellyfin has no email field on a user, so the link between a media-server
# account and an address lives here. Everything downstream consumes the same
# {user_id: email} dict it always did, so filling this in is all it takes for
# per-user recommendations, wrapped cards and personalized sends to work on a
# server that cannot supply addresses itself.

def get_media_user_emails(server_type='jellyfin'):
    """{user_id: email} for one server type."""
    conn = db_connect()
    try:
        rows = conn.execute(
            "SELECT user_id, email FROM media_user_emails WHERE server_type = ?",
            (server_type,),
        ).fetchall()
    finally:
        conn.close()
    return {r[0]: r[1] for r in rows}

def set_media_user_email(user_id, email, server_type='jellyfin'):
    """Link (or, with a blank email, unlink) one media-server user."""
    user_id = str(user_id or '').strip()
    email = (email or '').strip().lower()
    if not user_id:
        return False
    conn = db_connect()
    try:
        if email:
            conn.execute(
                """INSERT INTO media_user_emails (server_type, user_id, email) VALUES (?, ?, ?)
                   ON CONFLICT (server_type, user_id) DO UPDATE SET email = excluded.email""",
                (server_type, user_id, email),
            )
        else:
            conn.execute(
                "DELETE FROM media_user_emails WHERE server_type = ? AND user_id = ?",
                (server_type, user_id),
            )
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error saving media user email: {e}")
        return False
    finally:
        conn.close()

def set_media_user_emails(mapping, server_type='jellyfin'):
    written = 0
    for user_id, email in (mapping or {}).items():
        if set_media_user_email(user_id, email, server_type):
            written += 1
    return written

def add_suppressed(email):
    conn = db_connect()
    conn.execute("INSERT OR IGNORE INTO suppressed_emails (email) VALUES (?)", ((email or "").strip().lower(),))
    conn.commit()
    conn.close()

def filter_suppressed(emails):
    """Returns (deliverable, suppressed). Called before any send content is
    built, so suppressed recipients never cost a wasted render/image-fetch."""
    conn = db_connect()
    rows = conn.execute("SELECT email FROM suppressed_emails").fetchall()
    conn.close()
    blocked = {r[0].strip().lower() for r in rows}
    deliverable, suppressed = [], []
    for e in emails or []:
        (suppressed if (e or "").strip().lower() in blocked else deliverable).append(e)
    return deliverable, suppressed

def get_suppressed_emails():
    conn = db_connect()
    rows = conn.execute("SELECT id, email, unsubscribed_at FROM suppressed_emails ORDER BY unsubscribed_at DESC").fetchall()
    conn.close()
    return [{"id": r[0], "email": r[1], "unsubscribed_at": r[2]} for r in rows]

def remove_suppressed(entry_id):
    conn = db_connect()
    conn.execute("DELETE FROM suppressed_emails WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()

EMAIL_HISTORY_RETENTION = 1000

# email_content stores the full raw MIME (msg_root.as_string()) so a send can
# be replayed verbatim from history; the cap is a sanity ceiling against
# pathological cases (e.g. unoptimized attachments), not a normal-case limit.
EMAIL_CONTENT_MAX_CHARS = 5 * 1024 * 1024
RECIPIENTS_MAX_CHARS = 50_000

def get_email_history_page(limit, offset):
    if config.DEMO_MODE:
        from app.demo import demo_history_rows
        return demo_history_rows(limit, offset)

    conn = db_connect()
    cursor = conn.cursor()
    total = cursor.execute("SELECT COUNT(*) FROM email_history").fetchone()[0]
    cursor.execute("""
        SELECT id, subject, recipients, content_size_kb, recipient_count, sent_at, template_name, status, error
        FROM email_history
        ORDER BY sent_at DESC, id DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    rows = cursor.fetchall()
    conn.close()
    return rows, total

def record_email_history(subject, recipients, email_content, content_size_kb,
                         recipient_count, template_name="Manual",
                         status="sent", error=None, hosted_html=None):
    recipients = (recipients or "")[:RECIPIENTS_MAX_CHARS]
    email_content = (email_content or "")[:EMAIL_CONTENT_MAX_CHARS]
    try:
        conn = db_connect()
        cur = conn.execute(
            """INSERT INTO email_history
               (subject, recipients, email_content, content_size_kb, recipient_count, template_name, status, error, hosted_html)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (subject, recipients, email_content, content_size_kb, recipient_count,
             template_name, status, error, hosted_html),
        )
        last_id = cur.lastrowid
        conn.execute(
            """DELETE FROM email_history WHERE id NOT IN (
                   SELECT id FROM email_history ORDER BY sent_at DESC, id DESC LIMIT ?
               )""",
            (EMAIL_HISTORY_RETENTION,),
        )
        conn.commit()
        conn.close()
        return last_id
    except Exception:
        logger.warning("could not record email history", exc_info=True)
        return None

def get_most_recent_hosted_newsletter():
    conn = db_connect()
    row = conn.execute(
        """SELECT subject, hosted_html, sent_at FROM email_history
           WHERE status = 'sent' AND hosted_html IS NOT NULL
           ORDER BY sent_at DESC, id DESC LIMIT 1"""
    ).fetchone()
    conn.close()
    return row

def get_email_schedules():
    _s = get_settings(decrypt_secrets=False)
    _date_format = dates.resolve_date_format(_s.get('date_format'))
    _time_format = dates.resolve_time_format(_s.get('time_format'))

    if config.DEMO_MODE:
        from app.demo import demo_schedule_rows
        schedules = demo_schedule_rows()
    else:
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                es.id, es.name, es.email_list_id, es.template_id, es.frequency, es.start_date,
                es.send_time, es.last_sent, es.next_send, es.is_active, es.created_at, es.date_range,
                es.items_count, es.skip_if_no_new, es.skip_if_empty,
                el.name as email_list_name,
                et.name as template_name,
                es.skip_triggers, es.skip_min_items
            FROM email_schedules es
            LEFT JOIN email_lists el ON es.email_list_id = el.id
            LEFT JOIN email_templates et ON es.template_id = et.id
            ORDER BY es.created_at DESC
        """)
        schedules = cursor.fetchall()
        conn.close()
    
    result = []
    for schedule in schedules:
        next_send_formatted = None
        if schedule[8]:
            try:
                next_dt = datetime.fromisoformat(schedule[8])
                next_send_formatted = dates.fmt_schedule_stamp(next_dt, _date_format, _time_format)
            except Exception:
                logger.debug("suppressed exception; using fallback", exc_info=True)
                next_send_formatted = schedule[8]

        last_sent_formatted = None
        if schedule[7]:
            try:
                last_dt = datetime.fromisoformat(schedule[7])
                last_sent_formatted = dates.fmt_schedule_stamp(last_dt, _date_format, _time_format)
            except Exception:
                logger.debug("suppressed exception; using fallback", exc_info=True)
                last_sent_formatted = schedule[7]

        start_date_raw = schedule[5]
        start_date_formatted = start_date_raw
        try:
            start_dt = datetime.fromisoformat(start_date_raw)
            start_date_formatted = dates.fmt_short_stamp(start_dt, _date_format)
        except Exception:
            logger.debug("suppressed exception; using fallback", exc_info=True)
            pass

        email_list_id = schedule[2]
        email_list_name = schedule[15]
        
        if email_list_id == 0:
            email_list_id = 'ALL'
            email_list_name = 'ALL (All active users)'
        elif email_list_name is None:
            email_list_name = 'Unknown'

        result.append({
            'id': schedule[0],
            'name': schedule[1],
            'email_list_id': email_list_id,
            'template_id': schedule[3],
            'frequency': schedule[4],
            'start_date': start_date_raw,
            'start_date_formatted': start_date_formatted,
            'send_time': schedule[6],
            'last_sent': last_sent_formatted or 'Never',
            'next_send': next_send_formatted or 'Not scheduled',
            'is_active': bool(schedule[9]),
            'created_at': schedule[10],
            'date_range': schedule[11] or 7,
            'items_count': schedule[12] or 10,
            'skip_if_no_new': bool(schedule[13]),
            'skip_if_empty': bool(schedule[14]),
            'skip_triggers': schedule[17] or '',
            'skip_min_items': schedule[18] or 1,
            'email_list_name': email_list_name,
            'template_name': schedule[16]
        })
    return result

def calculate_next_send(frequency, start_date, send_time='09:00', last_sent=None):
    if last_sent:
        base_date = datetime.fromisoformat(last_sent.replace('Z', '+00:00')).replace(tzinfo=None)
    else:
        base_date = datetime.fromisoformat(start_date)
    
    hour, minute = map(int, send_time.split(':'))
    
    if frequency == 'daily':
        next_date = base_date + timedelta(days=1)

    elif frequency == 'weekly':
        start_dt = datetime.fromisoformat(start_date)
        target_weekday = start_dt.weekday()
        
        days_until_target = (target_weekday - base_date.weekday()) % 7
        if days_until_target == 0:
            days_until_target = 7
        next_date = base_date + timedelta(days=days_until_target)
    
    elif frequency == 'biweekly':
        next_date = base_date + timedelta(days=14)

    elif frequency == 'bimonthly':
        if base_date.day < 15:
            next_date = datetime(base_date.year, base_date.month, 15)
        else:
            next_month = base_date.month + 1
            next_year = base_date.year
            if next_month > 12:
                next_month = 1
                next_year += 1
            next_date = datetime(next_year, next_month, 1)

    elif frequency == 'monthly':
        start_dt = datetime.fromisoformat(start_date)
        target_day = start_dt.day
        
        next_month = base_date.month + 1
        next_year = base_date.year
        if next_month > 12:
            next_month = 1
            next_year += 1
        
        last_day_of_month = calendar.monthrange(next_year, next_month)[1]
        actual_day = min(target_day, last_day_of_month)
        
        next_date = datetime(next_year, next_month, actual_day)

    elif frequency == 'bimonthly_interval':
        start_dt = datetime.fromisoformat(start_date)
        target_day = start_dt.day
        
        next_month = base_date.month + 2
        next_year = base_date.year
        while next_month > 12:
            next_month -= 12
            next_year += 1
        
        last_day_of_month = calendar.monthrange(next_year, next_month)[1]
        actual_day = min(target_day, last_day_of_month)
        
        next_date = datetime(next_year, next_month, actual_day)
        
    elif frequency == 'quarterly':
        start_dt = datetime.fromisoformat(start_date)
        target_day = start_dt.day
        
        next_month = base_date.month + 3
        next_year = base_date.year
        while next_month > 12:
            next_month -= 12
            next_year += 1
        
        last_day_of_month = calendar.monthrange(next_year, next_month)[1]
        actual_day = min(target_day, last_day_of_month)
        
        next_date = datetime(next_year, next_month, actual_day)
        
    elif frequency == 'biannually':
        start_dt = datetime.fromisoformat(start_date)
        target_day = start_dt.day
        
        next_month = base_date.month + 6
        next_year = base_date.year
        while next_month > 12:
            next_month -= 12
            next_year += 1
        
        last_day_of_month = calendar.monthrange(next_year, next_month)[1]
        actual_day = min(target_day, last_day_of_month)
        
        next_date = datetime(next_year, next_month, actual_day)
        
    elif frequency == 'yearly':
        start_dt = datetime.fromisoformat(start_date)
        target_month = start_dt.month
        target_day = start_dt.day
        
        next_year = base_date.year + 1
        
        if target_month == 2 and target_day == 29:
            if not calendar.isleap(next_year):
                target_day = 28
        
        last_day_of_month = calendar.monthrange(next_year, target_month)[1]
        actual_day = min(target_day, last_day_of_month)
        
        next_date = datetime(next_year, target_month, actual_day)
        
    else:
        next_date = base_date + timedelta(days=1)
    
    next_date = next_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return next_date

def next_future_send(frequency, start_date, send_time='09:00'):
    nxt = calculate_next_send(frequency, start_date, send_time)
    now = datetime.now()
    guard = 0
    while nxt <= now and guard < 10000:
        nxt = calculate_next_send(frequency, start_date, send_time, last_sent=nxt.isoformat())
        guard += 1
    return nxt

def create_email_schedule(name, email_list_id, template_id, frequency, start_date, send_time='09:00', date_range=7, items_count=10, skip_if_no_new=0, skip_triggers='', skip_min_items=1, skip_if_empty=0):
    conn = db_connect()
    cursor = conn.cursor()

    next_send = next_future_send(frequency, start_date, send_time)

    try:
        list_id_value = 0 if email_list_id == 'ALL' else int(email_list_id)

        cursor.execute("""
            INSERT INTO email_schedules (name, email_list_id, template_id, frequency, start_date, send_time, next_send, date_range, items_count, skip_if_no_new, skip_triggers, skip_min_items, skip_if_empty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, list_id_value, template_id, frequency, start_date, send_time, next_send.isoformat(), date_range, items_count, int(bool(skip_if_no_new)), skip_triggers, skip_min_items, int(bool(skip_if_empty))))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error creating schedule: {e}")
        return False
    finally:
        conn.close()

def update_email_schedule(schedule_id, name, email_list_id, template_id, frequency, start_date, send_time='09:00', date_range=7, items_count=10, skip_if_no_new=0, skip_triggers='', skip_min_items=1, skip_if_empty=0):
    conn = db_connect()
    cursor = conn.cursor()

    next_send = next_future_send(frequency, start_date, send_time)

    try:
        list_id_value = 0 if email_list_id == 'ALL' else int(email_list_id)

        cursor.execute("""
            UPDATE email_schedules
            SET name = ?, email_list_id = ?, template_id = ?, frequency = ?,
                start_date = ?, send_time = ?, next_send = ?, date_range = ?,
                items_count = ?, skip_if_no_new = ?, skip_triggers = ?, skip_min_items = ?, skip_if_empty = ?
            WHERE id = ?
        """, (name, list_id_value, template_id, frequency, start_date, send_time, next_send.isoformat(), date_range, items_count, int(bool(skip_if_no_new)), skip_triggers, skip_min_items, int(bool(skip_if_empty)), schedule_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error updating schedule: {e}")
        return False
    finally:
        conn.close()

def delete_email_schedule(schedule_id):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM email_schedules WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()

def toggle_schedule_status(schedule_id, is_active):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE email_schedules SET is_active = ? WHERE id = ?", (is_active, schedule_id))
    conn.commit()
    conn.close()

def advance_schedule_next_send(schedule_id):
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("SELECT frequency, start_date, send_time FROM email_schedules WHERE id = ?", (schedule_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return
    frequency, start_date, send_time = result
    next_send = next_future_send(frequency, start_date, send_time or '09:00')
    cursor.execute("UPDATE email_schedules SET next_send = ? WHERE id = ?", (next_send.isoformat(), schedule_id))
    conn.commit()
    conn.close()

def update_schedule_last_sent(schedule_id):
    conn = db_connect()
    cursor = conn.cursor()

    cursor.execute("SELECT frequency, start_date, send_time FROM email_schedules WHERE id = ?", (schedule_id,))
    result = cursor.fetchone()
    if not result:
        conn.close()
        return

    frequency, start_date, send_time = result
    now = datetime.now()
    next_send = calculate_next_send(frequency, start_date, send_time or '09:00', now.isoformat())

    cursor.execute("""
        UPDATE email_schedules
        SET last_sent = ?, next_send = ?
        WHERE id = ?
    """, (now.isoformat(), next_send.isoformat(), schedule_id))
    conn.commit()
    conn.close()
