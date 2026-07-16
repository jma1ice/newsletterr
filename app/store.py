import calendar, os, secrets, sqlite3
from datetime import datetime, timedelta

from app.db import db_connect

import logging

logger = logging.getLogger(__name__)

HOSTED_IMAGES_DIR = os.path.join("database", "hosted_images")
HOSTED_IMAGE_RETENTION_DAYS = 90

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
    conn = db_connect()
    cutoff = f'-{HOSTED_IMAGE_RETENTION_DAYS} days'
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
    conn.commit()
    conn.close()

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
    MONTH_ABBR_PERIOD = ["Jan.", "Feb.", "Mar.", "Apr.", "May.", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]
    
    conn = db_connect()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            es.id, es.name, es.email_list_id, es.template_id, es.frequency, es.start_date, 
            es.send_time, es.last_sent, es.next_send, es.is_active, es.created_at, es.date_range,
            es.items_count,
            el.name as email_list_name,
            et.name as template_name
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
                weekday = next_dt.strftime('%A')
                month_abbr = MONTH_ABBR_PERIOD[next_dt.month - 1]
                next_send_formatted = f"{weekday} {month_abbr} {next_dt.day}, {next_dt.year}  {next_dt.strftime('%H:%M')}"
            except Exception:
                logger.debug("suppressed exception; using fallback", exc_info=True)
                next_send_formatted = schedule[8]

        last_sent_formatted = None
        if schedule[7]:
            try:
                last_dt = datetime.fromisoformat(schedule[7])
                weekday = last_dt.strftime('%A')
                month_abbr = MONTH_ABBR_PERIOD[last_dt.month - 1]
                last_sent_formatted = f"{weekday} {month_abbr} {last_dt.day}, {last_dt.year}  {last_dt.strftime('%H:%M')}"
            except Exception:
                logger.debug("suppressed exception; using fallback", exc_info=True)
                last_sent_formatted = schedule[7]

        start_date_raw = schedule[5]
        start_date_formatted = start_date_raw
        try:
            start_dt = datetime.fromisoformat(start_date_raw)
            start_date_formatted = f"{MONTH_ABBR_PERIOD[start_dt.month - 1]} {start_dt.day}, {start_dt.year}"
        except Exception:
            logger.debug("suppressed exception; using fallback", exc_info=True)
            pass

        email_list_id = schedule[2]
        email_list_name = schedule[13]
        
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
            'email_list_name': email_list_name,
            'template_name': schedule[14]
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

def create_email_schedule(name, email_list_id, template_id, frequency, start_date, send_time='09:00', date_range=7, items_count=10):
    conn = db_connect()
    cursor = conn.cursor()
    
    next_send = next_future_send(frequency, start_date, send_time)
    
    try:
        list_id_value = 0 if email_list_id == 'ALL' else int(email_list_id)

        cursor.execute("""
            INSERT INTO email_schedules (name, email_list_id, template_id, frequency, start_date, send_time, next_send, date_range, items_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, list_id_value, template_id, frequency, start_date, send_time, next_send.isoformat(), date_range, items_count))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error creating schedule: {e}")
        return False
    finally:
        conn.close()

def update_email_schedule(schedule_id, name, email_list_id, template_id, frequency, start_date, send_time='09:00', date_range=7, items_count=10):
    conn = db_connect()
    cursor = conn.cursor()
    
    next_send = next_future_send(frequency, start_date, send_time)

    try:
        list_id_value = 0 if email_list_id == 'ALL' else int(email_list_id)

        cursor.execute("""
            UPDATE email_schedules 
            SET name = ?, email_list_id = ?, template_id = ?, frequency = ?, 
                start_date = ?, send_time = ?, next_send = ?, date_range = ?,
                items_count = ?
            WHERE id = ?
        """, (name, list_id_value, template_id, frequency, start_date, send_time, next_send.isoformat(), date_range, items_count, schedule_id))
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
