import os, math, uuid, base64, smtplib, sqlite3, requests, time, threading, re, json
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv, set_key, find_dotenv
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.utils import make_msgid
from flask import Flask, render_template, request, jsonify, Response, redirect, url_for
from pathlib import Path
from plex_api_client import PlexAPI
from urllib.parse import quote_plus

app = Flask(__name__)
app.jinja_env.globals["version"] = "v0.9.5"
app.jinja_env.globals["publish_date"] = "August 21, 2025"

def get_global_cache_status():
    """Get global cache status for display in navbar"""
    try:
        cache_keys = ['stats', 'users', 'graph_data', 'recent_data']
        present = []
        missing = []
        oldest_age = 0.0
        date_range_display = '—'
        max_range = 0

        for key in cache_keys:
            info = get_cache_info(key)
            if info.get('exists'):
                present.append(key)
                oldest_age = max(oldest_age, info.get('age_hours', 0))
                if info.get('params'):
                    param_days = info['params'].get('time_range') or info['params'].get('days')
                    try:
                        param_days = int(param_days)
                        if param_days > max_range:
                            max_range = param_days
                    except (TypeError, ValueError):
                        pass
            else:
                missing.append(key)

        if max_range > 0:
            date_range_display = f"{max_range} day" + ("s" if max_range != 1 else "")

        if not present:
            return {
                'has_data': False,
                'status': 'No cached data',
                'age_display': 'no data',
                'class': 'cache-badge-muted',
                'missing': missing,
                'present': present
            }

        # Determine freshness classification
        if missing:
            freshness_class = 'cache-badge-missing'  # force red if anything missing
            freshness_text = f"Missing: {', '.join(missing)}"
        elif oldest_age < 1:
            freshness_class = 'cache-badge-fresh'
            freshness_text = 'Fresh'
        elif oldest_age < 24:
            freshness_class = 'cache-badge-warn'
            freshness_text = f"~{int(oldest_age)}h old"
        elif oldest_age < 168:
            freshness_class = 'cache-badge-old'
            freshness_text = f"{int(oldest_age/24)}d old"
        else:
            freshness_class = 'cache-badge-stale'
            freshness_text = 'Very old'

        return {
            'has_data': True,
            'status': f"{freshness_text} • Range {date_range_display}",
            'age_display': date_range_display,
            'class': freshness_class,
            'missing': missing,
            'present': present
        }
    except:
        return {'has_data': False, 'status': 'Cache error', 'age_display': 'error', 'class': 'cache-badge-muted'}

# Make cache status available globally in templates
app.jinja_env.globals["get_cache_status"] = get_global_cache_status

def can_use_cached_data_for_preview(required_days):
    """Check if cached data is suitable for preview with required_days date range"""
    try:
        # Get cache info for key data types
        stats_info = get_cache_info('stats')
        graph_info = get_cache_info('graph_data')
        
        # Check if cache exists and is reasonably fresh (within extended duration)
        if not (stats_info.get('exists') and graph_info.get('exists')):
            return False, "Cache data missing"
        
        if not (stats_info.get('is_usable') and graph_info.get('is_usable')):
            return False, "Cache data too old"
        
        # Check if cached parameters cover the required date range
        stats_params = stats_info.get('params', {})
        if 'time_range' in stats_params:
            try:
                cached_days = int(stats_params.get('time_range', 0))
            except (TypeError, ValueError):
                cached_days = 0
            # Require exact match to avoid overstating recent period with longer cached data
            if cached_days == required_days:
                return True, f"Using cached data ({cached_days} days exact match)"
            else:
                return False, f"Cached range ({cached_days} days) != requested ({required_days} days)"
        return False, f"No cached range metadata (need {required_days} days)"
    except Exception as e:
        return False, f"Error checking cache: {str(e)}"

# Cache configuration
CACHE_DURATION = 86400  # 24 hours in seconds (daily refresh)
CACHE_EXTENDED_DURATION = 86400 * 7  # 1 week fallback duration
cache_storage = {
    'stats': {'data': None, 'timestamp': 0, 'params': None},
    'users': {'data': None, 'timestamp': 0, 'params': None},
    'graph_data': {'data': None, 'timestamp': 0, 'params': None},
    'recent_data': {'data': None, 'timestamp': 0, 'params': None}
}

app.config["GITHUB_OWNER"] = "jma1ice"
app.config["GITHUB_REPO"] = "newsletterr"
app.config["UPDATE_CHECK_INTERVAL_SEC"] = 60 * 60

_update_cache = {
    "latest": None,
    "is_newer": False,
    "release_url": None,
    "notes": None,
    "checked_at": 0.0,
    "etag": None,
}

DB_PATH = os.path.join("database", "data.db")
plex_headers = {
    "X-Plex-Client-Identifier": str(uuid.uuid4())
}
ROOT = Path(__file__).resolve().parent
ENV_PATH = find_dotenv(usecwd=True) or str(ROOT / ".env")
DATA_IMG_RE = re.compile(
    r'^data:(image/(png|jpeg|jpg|gif|webp));base64,([A-Za-z0-9+/=]+)$',
    re.IGNORECASE
)

load_dotenv(ENV_PATH)

def is_cache_valid(cache_key, strict=True):
    """Check if cache data is still valid
    Args:
        cache_key: The cache key to check
        strict: If True, use normal cache duration. If False, use extended duration for fallback
    """
    cache_entry = cache_storage.get(cache_key)
    if cache_entry and cache_entry['data'] is not None:
        age = time.time() - cache_entry['timestamp']
        duration = CACHE_DURATION if strict else CACHE_EXTENDED_DURATION
        return age < duration
    return False

def get_cached_data(cache_key, strict=True):
    """Get cached data if valid
    Args:
        cache_key: The cache key to retrieve
        strict: If True, use normal cache duration. If False, use extended duration for fallback
    """
    if is_cache_valid(cache_key, strict):
        return cache_storage[cache_key]['data']
    return None

def set_cached_data(cache_key, data, params=None):
    """Store data in cache with current timestamp and parameters"""
    cache_storage[cache_key] = {
        'data': data,
        'timestamp': time.time(),
        'params': params
    }

def get_cache_info(cache_key):
    """Get cache information including age and parameters"""
    cache_entry = cache_storage.get(cache_key)
    if cache_entry and cache_entry['data'] is not None:
        age = time.time() - cache_entry['timestamp']
        return {
            'exists': True,
            'age_hours': age / 3600,
            'params': cache_entry.get('params'),
            'is_fresh': age < CACHE_DURATION,
            'is_usable': age < CACHE_EXTENDED_DURATION
        }
    return {'exists': False}

def clear_cache(cache_key=None):
    """Clear specific cache or all cache if no key specified"""
    if cache_key:
        cache_storage[cache_key] = {'data': None, 'timestamp': 0, 'params': None}
    else:
        for key in cache_storage:
            cache_storage[key] = {'data': None, 'timestamp': 0, 'params': None}

def ensure_data_key() -> str:
    key = os.getenv("DATA_ENC_KEY")
    if key:
        return key

    new_key = Fernet.generate_key().decode()

    env_file = Path(ENV_PATH)
    if not env_file.exists():
        env_file.touch()
        try:
            env_file.chmod(0o600)
        except Exception:
            pass

    set_key(str(env_file), "DATA_ENC_KEY", new_key)
    return new_key

DATA_KEY = ensure_data_key()
fernet = Fernet(DATA_KEY)

def encrypt(token: str) -> str:
    return fernet.encrypt(token.encode()).decode()

def decrypt(encrypted: str) -> str:
    if encrypted is None:
        return ""
    try:
        return fernet.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        return encrypted

def init_db(db_path):
    """Initialize the unified database with all tables"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_email TEXT,
            alias_email TEXT,
            password TEXT,
            smtp_server TEXT,
            smtp_port INTEGER,
            server_name TEXT,
            plex_url TEXT,
            plex_token TEXT,
            tautulli_url TEXT,
            tautulli_api TEXT,
            conjurr_url TEXT
        )
    """)
    
    # Email lists table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            emails TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Email templates table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            selected_items TEXT NOT NULL,
            email_text TEXT,
            subject TEXT,
            layout TEXT DEFAULT 'standard',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Email history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            recipients TEXT NOT NULL,
            email_content TEXT,
            content_size_kb REAL,
            recipient_count INTEGER,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            template_name TEXT  -- Name of template used (NULL/Manual for legacy/manual sends)
        )
    """)

    # Backwards compatibility: add template_name column if missing
    try:
        cursor.execute("PRAGMA table_info(email_history)")
        cols = [r[1] for r in cursor.fetchall()]
        if 'template_name' not in cols:
            cursor.execute("ALTER TABLE email_history ADD COLUMN template_name TEXT")
    except Exception as _e:
        print(f"Warning: could not ensure template_name column exists: {_e}")
    
    # Email schedules table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email_list_id INTEGER NOT NULL,
            template_id INTEGER NOT NULL,
            frequency TEXT NOT NULL, -- 'daily', 'weekly', 'monthly'
            start_date TEXT NOT NULL,
            send_time TEXT DEFAULT '09:00', -- Time of day to send (HH:MM format)
            date_range INTEGER DEFAULT 7, -- Number of days of data to include
            last_sent TIMESTAMP,
            next_send TIMESTAMP NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (email_list_id) REFERENCES email_lists (id),
            FOREIGN KEY (template_id) REFERENCES email_templates (id)
        )
    """)
    
    conn.commit()
    
    # Check if send_time column exists, if not add it (for existing databases)
    cursor.execute("PRAGMA table_info(email_schedules)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'send_time' not in columns:
        print("Adding send_time column to email_schedules table...")
        cursor.execute("ALTER TABLE email_schedules ADD COLUMN send_time TEXT DEFAULT '09:00'")
        conn.commit()
    
    # Check if date_range column exists, if not add it (for existing databases)
    if 'date_range' not in columns:
        print("Adding date_range column to email_schedules table...")
        cursor.execute("ALTER TABLE email_schedules ADD COLUMN date_range INTEGER DEFAULT 7")
        conn.commit()
    
    conn.close()

def migrate_data_from_separate_dbs():
    """Migrate data from separate database files to the unified database"""
    import os
    import shutil
    
    # Database file paths
    separate_dbs = [
        os.path.join("database", "email_lists.db"),
        os.path.join("database", "email_templates.db"), 
        os.path.join("database", "email_history.db"),
        os.path.join("database", "schedules.db")
    ]
    
    # Check if any separate database files exist
    has_separate_data = any(os.path.exists(db_path) for db_path in separate_dbs)
    
    if not has_separate_data:
        return  # No migration needed
    
    print("Migrating data from separate database files to unified database...")
    
    # Connect to unified database
    unified_conn = sqlite3.connect(DB_PATH)
    unified_cursor = unified_conn.cursor()
    
    try:
        # Migrate email lists
        email_lists_path = os.path.join("database", "email_lists.db")
        if os.path.exists(email_lists_path):
            print("Migrating email lists...")
            old_conn = sqlite3.connect(email_lists_path)
            old_cursor = old_conn.cursor()
            old_cursor.execute("SELECT * FROM email_lists")
            rows = old_cursor.fetchall()
            for row in rows:
                unified_cursor.execute("""
                    INSERT OR IGNORE INTO email_lists (id, name, emails, created_at)
                    VALUES (?, ?, ?, ?)
                """, row)
            old_conn.close()
        
        # Migrate email templates
        email_templates_path = os.path.join("database", "email_templates.db")
        if os.path.exists(email_templates_path):
            print("Migrating email templates...")
            old_conn = sqlite3.connect(email_templates_path)
            old_cursor = old_conn.cursor()
            old_cursor.execute("SELECT * FROM email_templates")
            rows = old_cursor.fetchall()
            for row in rows:
                unified_cursor.execute("""
                    INSERT OR IGNORE INTO email_templates (id, name, selected_items, email_text, subject, layout, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, row)
            old_conn.close()
        
        # Migrate email history
        email_history_path = os.path.join("database", "email_history.db")
        if os.path.exists(email_history_path):
            print("Migrating email history...")
            old_conn = sqlite3.connect(email_history_path)
            old_cursor = old_conn.cursor()
            old_cursor.execute("SELECT * FROM email_history")
            rows = old_cursor.fetchall()
            for row in rows:
                unified_cursor.execute("""
                    INSERT OR IGNORE INTO email_history (id, subject, recipients, email_content, content_size_kb, recipient_count, sent_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, row)
            old_conn.close()
        
        # Migrate email schedules
        schedules_path = os.path.join("database", "schedules.db")
        if os.path.exists(schedules_path):
            print("Migrating email schedules...")
            old_conn = sqlite3.connect(schedules_path)
            old_cursor = old_conn.cursor()
            old_cursor.execute("SELECT * FROM email_schedules")
            rows = old_cursor.fetchall()
            for row in rows:
                unified_cursor.execute("""
                    INSERT OR IGNORE INTO email_schedules (id, name, email_list_id, template_id, frequency, start_date, last_sent, next_send, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, row)
            old_conn.close()
        
        unified_conn.commit()
        print("Data migration completed successfully!")
        
        # Create backups and remove old files
        backup_dir = os.path.join("database", "backup_" + str(int(time.time())))
        os.makedirs(backup_dir, exist_ok=True)
        
        for db_path in separate_dbs:
            if os.path.exists(db_path):
                backup_path = os.path.join(backup_dir, os.path.basename(db_path))
                shutil.move(db_path, backup_path)
                print(f"Moved {db_path} to {backup_path}")
                
    except Exception as e:
        print(f"Error during migration: {e}")
        unified_conn.rollback()
    finally:
        unified_conn.close()

def init_email_lists_db(db_path):
    """Deprecated: Use init_db() instead"""
    pass

def init_email_templates_db(db_path):
    """Deprecated: Use init_db() instead"""
    pass

def init_email_history_db(db_path):
    """Deprecated: Use init_db() instead"""
    pass

def init_schedules_db(db_path):
    """Deprecated: Use init_db() instead"""
    pass

def migrate_schema(column_def):
    conn = sqlite3.connect(DB_PATH)
    try:
        col_name = column_def.split()[0]
        cursor = conn.execute("PRAGMA table_info('settings')")
        has_column = any(row[1] == col_name for row in cursor.fetchall())
        if not has_column:
            conn.execute(f"ALTER TABLE settings ADD COLUMN {column_def}")
            conn.commit()
    finally:
        conn.close()

def get_saved_email_lists():
    """Get all saved email lists"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, emails FROM email_lists ORDER BY name")
    lists = cursor.fetchall()
    conn.close()
    return [{'id': row[0], 'name': row[1], 'emails': row[2]} for row in lists]

def save_email_list(name, emails):
    """Save a new email list"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO email_lists (name, emails) VALUES (?, ?)", (name, emails))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Name already exists
    finally:
        conn.close()

def delete_email_list(list_id):
    """Delete an email list by ID"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM email_lists WHERE id = ?", (list_id,))
    conn.commit()
    conn.close()

# Scheduling functions
def get_email_schedules():
    """Get all email schedules with email list and template names"""
    from datetime import datetime
    # Month abbreviations with trailing periods per UI spec
    MONTH_ABBR_PERIOD = ["Jan.", "Feb.", "Mar.", "Apr.", "May.", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            es.id, es.name, es.email_list_id, es.template_id, es.frequency, es.start_date, 
            es.send_time, es.last_sent, es.next_send, es.is_active, es.created_at, es.date_range,
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
        # next_send format: "Sunday Sep. 21, 2025  09:00" (24h, two spaces before time)
        next_send_formatted = None
        if schedule[8]:  # next_send
            try:
                next_dt = datetime.fromisoformat(schedule[8])
                weekday = next_dt.strftime('%A')
                month_abbr = MONTH_ABBR_PERIOD[next_dt.month - 1]
                next_send_formatted = f"{weekday} {month_abbr} {next_dt.day}, {next_dt.year}  {next_dt.strftime('%H:%M')}"
            except Exception:
                next_send_formatted = schedule[8]

        # last_sent format same as next_send format
        last_sent_formatted = None
        if schedule[7]:  # last_sent
            try:
                last_dt = datetime.fromisoformat(schedule[7])
                weekday = last_dt.strftime('%A')
                month_abbr = MONTH_ABBR_PERIOD[last_dt.month - 1]
                last_sent_formatted = f"{weekday} {month_abbr} {last_dt.day}, {last_dt.year}  {last_dt.strftime('%H:%M')}"
            except Exception:
                last_sent_formatted = schedule[7]

        # start_date display format: "Mar. 27, 2025"
        start_date_raw = schedule[5]
        start_date_formatted = start_date_raw
        try:
            start_dt = datetime.fromisoformat(start_date_raw)
            start_date_formatted = f"{MONTH_ABBR_PERIOD[start_dt.month - 1]} {start_dt.day}, {start_dt.year}"
        except Exception:
            pass

        result.append({
            'id': schedule[0],
            'name': schedule[1],
            'email_list_id': schedule[2],
            'template_id': schedule[3],
            'frequency': schedule[4],
            'start_date': start_date_raw,  # keep raw for form editing
            'start_date_formatted': start_date_formatted,
            'send_time': schedule[6],
            'last_sent': last_sent_formatted or 'Never',
            'next_send': next_send_formatted or 'Not scheduled',
            'is_active': bool(schedule[9]),
            'created_at': schedule[10],
            'date_range': schedule[11] or 7,
            'email_list_name': schedule[12],
            'template_name': schedule[13]
        })
    return result

def calculate_next_send(frequency, start_date, send_time='09:00', last_sent=None):
    """Calculate the next send time based on frequency and specific time"""
    from datetime import datetime, timedelta
    import calendar
    
    if last_sent:
        base_date = datetime.fromisoformat(last_sent.replace('Z', '+00:00')).replace(tzinfo=None)
    else:
        base_date = datetime.fromisoformat(start_date)
    
    # Parse send_time and set it on the base date
    hour, minute = map(int, send_time.split(':'))
    
    if frequency == 'daily':
        next_date = base_date + timedelta(days=1)
    elif frequency == 'weekly':
        # Weekly: maintain the same day of the week
        # Get the original day of the week from start_date
        start_dt = datetime.fromisoformat(start_date)
        target_weekday = start_dt.weekday()  # Monday=0, Sunday=6
        
        # Find the next occurrence of that weekday
        days_until_target = (target_weekday - base_date.weekday()) % 7
        if days_until_target == 0:
            days_until_target = 7  # If it's the same day, go to next week
        next_date = base_date + timedelta(days=days_until_target)
        
    elif frequency == 'monthly':
        # Monthly: maintain the same day of the month
        # Get the original day of the month from start_date
        start_dt = datetime.fromisoformat(start_date)
        target_day = start_dt.day
        
        # Calculate next month
        next_month = base_date.month + 1
        next_year = base_date.year
        if next_month > 12:
            next_month = 1
            next_year += 1
        
        # Get the last day of the target month
        last_day_of_month = calendar.monthrange(next_year, next_month)[1]
        
        # If target day exceeds the month's days, use the last day of the month
        actual_day = min(target_day, last_day_of_month)
        
        next_date = datetime(next_year, next_month, actual_day)
        
    else:
        next_date = base_date + timedelta(days=1)  # Default to daily
    
    # Set the specific time
    next_date = next_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return next_date

def create_email_schedule(name, email_list_id, template_id, frequency, start_date, send_time='09:00', date_range=7):
    """Create a new email schedule"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Calculate next send time
    next_send = calculate_next_send(frequency, start_date, send_time)
    
    try:
        cursor.execute("""
            INSERT INTO email_schedules (name, email_list_id, template_id, frequency, start_date, send_time, next_send, date_range)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, email_list_id, template_id, frequency, start_date, send_time, next_send.isoformat(), date_range))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error creating schedule: {e}")
        return False
    finally:
        conn.close()

def update_email_schedule(schedule_id, name, email_list_id, template_id, frequency, start_date, send_time='09:00', date_range=7):
    """Update an existing email schedule"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Calculate next send time based on new parameters
    next_send = calculate_next_send(frequency, start_date, send_time)
    
    try:
        cursor.execute("""
            UPDATE email_schedules 
            SET name = ?, email_list_id = ?, template_id = ?, frequency = ?, 
                start_date = ?, send_time = ?, next_send = ?, date_range = ?
            WHERE id = ?
        """, (name, email_list_id, template_id, frequency, start_date, send_time, next_send.isoformat(), date_range, schedule_id))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error updating schedule: {e}")
        return False
    finally:
        conn.close()

def delete_email_schedule(schedule_id):
    """Delete an email schedule"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM email_schedules WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()

def toggle_schedule_status(schedule_id, is_active):
    """Toggle schedule active/inactive status"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE email_schedules SET is_active = ? WHERE id = ?", (is_active, schedule_id))
    conn.commit()
    conn.close()

def update_schedule_last_sent(schedule_id):
    """Update the last sent time and calculate next send"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get current schedule details
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

# Background scheduler
def background_scheduler():
    """Background thread to check and send scheduled emails and refresh cache daily"""
    print("Background scheduler started...")
    last_cache_refresh = 0  # Track last cache refresh
    
    while True:
        try:
            now = datetime.now()
            current_time = time.time()
            
            # Check if we need to refresh cache (once per day)
            if current_time - last_cache_refresh > 86400:  # 24 hours
                print(f"Daily cache refresh triggered at {now.isoformat()}")
                refresh_daily_cache()
                last_cache_refresh = current_time
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Get all active schedules for debugging
            cursor.execute("SELECT id, name, next_send, is_active FROM email_schedules")
            all_schedules = cursor.fetchall()
            print(f"Scheduler check at {now.isoformat()}")
            print(f"Found {len(all_schedules)} total schedules:")
            for sched in all_schedules:
                print(f"  - ID {sched[0]}: {sched[1]}, next_send: {sched[2]}, active: {sched[3]}")
            
            # Get schedules that are due to send
            cursor.execute("""
                SELECT id, name, email_list_id, template_id, frequency 
                FROM email_schedules 
                WHERE is_active = 1 AND next_send <= ? 
            """, (now.isoformat(),))
            
            due_schedules = cursor.fetchall()
            conn.close()
            
            print(f"Found {len(due_schedules)} schedules due for sending")
            
            for schedule in due_schedules:
                schedule_id, name, email_list_id, template_id, frequency = schedule
                print(f"Processing schedule: {name} (ID: {schedule_id})")
                try:
                    # Send the scheduled email
                    success = send_scheduled_email(schedule_id, email_list_id, template_id)
                    if success:
                        update_schedule_last_sent(schedule_id)
                        print(f"Successfully sent scheduled email: {name}")
                    else:
                        print(f"Failed to send scheduled email: {name}")
                except Exception as e:
                    print(f"Error sending scheduled email {name}: {e}")
            
        except Exception as e:
            print(f"Error in background scheduler: {e}")
        
        # Check every 60 seconds
        time.sleep(60)

def refresh_daily_cache():
    """Refresh cache with latest data using last known parameters"""
    try:
        # Get settings
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT server_name, tautulli_url, tautulli_api FROM settings WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        
        if not row or not row[0]:
            print("No settings found for cache refresh")
            return
            
        settings = {
            "server_name": row[0],
            "tautulli_url": row[1],
            "tautulli_api": row[2]
        }
        
        tautulli_base_url = settings['tautulli_url'].rstrip('/')
        tautulli_api_key = settings['tautulli_api']
        
        # Use default parameters for daily refresh
        time_range = "30"  # Default to 30 days
        count = "10"       # Default to 10 items
        
        # Check if we have previous parameters
        stats_info = get_cache_info('stats')
        if stats_info['exists'] and stats_info['params']:
            time_range = stats_info['params'].get('time_range', time_range)
            count = stats_info['params'].get('count', count)
        
        print(f"Refreshing cache with time_range: {time_range}, count: {count}")
        
        # Graph commands
        graph_commands = [
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
            {'command': 'get_stream_type_by_top_10_users', 'name': 'Stream Type by Top Users'}
        ]
        
        recent_commands = [
            {'command': 'movie'},
            {'command': 'show'}
        ]
        
        # Create parameter signature
        cache_params = {
            'time_range': time_range,
            'count': count,
            'url': tautulli_base_url,
            'timestamp': time.time(),
            'refresh_type': 'daily_auto'
        }
        
        error = None
        
        # Refresh stats
        stats, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', error, time_range)
        if stats:
            set_cached_data('stats', stats, cache_params)
            print("✓ Stats cache refreshed")
        
        # Refresh users
        users, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_users', 'Users', error)
        if users:
            set_cached_data('users', users, cache_params)
            print("✓ Users cache refreshed")
        
        # Refresh graph data
        graph_data = []
        for command in graph_commands:
            gd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], error, time_range)
            if gd:
                graph_data.append(gd)
        
        if graph_data:
            set_cached_data('graph_data', graph_data, cache_params)
            print("✓ Graph data cache refreshed")
        
        # Refresh recent data
        recent_data = []
        for command in recent_commands:
            rd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_recently_added', command["command"], error, count)
            if rd:
                recent_data.append(rd)
        
        if recent_data:
            set_cached_data('recent_data', recent_data, cache_params)
            print("✓ Recent data cache refreshed")
        
        print("Daily cache refresh completed successfully")
        
    except Exception as e:
        print(f"Error in daily cache refresh: {e}")

def generate_email_content(template_id, settings, date_range=7):
    """Generate complete email content with graphs, stats, and template processing"""
    try:
        # Get template
        templates_conn = sqlite3.connect(DB_PATH)
        templates_cursor = templates_conn.cursor()
        templates_cursor.execute("SELECT name, subject, email_text, selected_items FROM email_templates WHERE id = ?", (template_id,))
        template_result = templates_cursor.fetchone()
        templates_conn.close()
        
        if not template_result:
            return None, None, "Template not found"
        
        template_name, subject, email_text, selected_items_json = template_result
        
        # Parse selected items
        try:
            selected_items = json.loads(selected_items_json) if selected_items_json else []
        except:
            selected_items = []
        
        # Get fresh data for the specified date range if Tautulli is configured
        stats = None
        graph_data = []
        recent_data = []
        
        # Check if Tautulli is configured
        tautulli_conn = sqlite3.connect(DB_PATH)
        tautulli_cursor = tautulli_conn.cursor()
        tautulli_cursor.execute("SELECT tautulli_url, tautulli_api FROM settings WHERE id = 1")
        tautulli_settings = tautulli_cursor.fetchone()
        tautulli_conn.close()
        
        if tautulli_settings and tautulli_settings[0] and tautulli_settings[1]:
            tautulli_base_url = tautulli_settings[0].rstrip('/')
            tautulli_api_key = tautulli_settings[1]
            
            print(f"Fetching fresh Tautulli data for scheduled email - {date_range} days")
            
            # Define graph commands (same as main page)
            graph_commands = [
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
                {'command': 'get_stream_type_by_top_10_users', 'name': 'Stream Type by Top Users'}
            ]
            
            recent_commands = [
                {'command': 'movie'},
                {'command': 'show'}
            ]
            
            # Fetch fresh stats data
            try:
                stats, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', None, str(date_range))
                if error:
                    print(f"Error fetching stats: {error}")
                    
                # Fetch graph data
                graph_data = []
                for command in graph_commands:
                    gd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], error, str(date_range))
                    if gd:
                        graph_data.append(gd)
                    if error:
                        print(f"Error fetching graph data for {command['name']}: {error}")
                
                # Fetch recent data
                recent_data = []
                for command in recent_commands:
                    rd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_recently_added', command["command"], error, "10")
                    if rd:
                        recent_data.append(rd)
                    if error:
                        print(f"Error fetching recent data for {command['command']}: {error}")
                        
            except Exception as e:
                print(f"Failed to fetch fresh stats: {e}")
                # Fallback to cached data
                stats = get_cached_data('stats') or []
                graph_data = get_cached_data('graph_data') or []
                recent_data = get_cached_data('recent_data') or []
        else:
            print("Tautulli not configured, using cached data")
            # Fallback to cached data
            stats = get_cached_data('stats') or []
            graph_data = get_cached_data('graph_data') or []
            recent_data = get_cached_data('recent_data') or []
        
        # Process all selected items in order to build the complete email content
        all_content_html = ""
        
        for item in selected_items:
            item_type = item.get('type', '')
            item_id = item.get('id', '')
            item_name = item.get('name', '')
            
            if item_type == 'textblock' or item_type == 'titleblock':
                # Get text content from the stored content in selected_items
                text_content = item.get('content', '')
                
                # Fallback to email_text if no individual content found
                if not text_content and email_text:
                    text_content = email_text.strip()
                
                if text_content:
                    if item_type == 'titleblock':
                        # Style title blocks with larger, bold, centered text
                        all_content_html += f"""
                        <div style="margin-bottom: 20px; font-size: 1.5em; font-weight: bold; text-align: center; color: #E5A00D;">
                            {text_content.replace(chr(10), '<br>')}
                        </div>
                        """
                    else:
                        # Regular text block
                        all_content_html += f"""
                        <div style="margin-bottom: 15px; color: #fff;">
                            {text_content.replace(chr(10), '<br>')}
                        </div>
                        """
                
            elif item_type == 'stat' and stats:
                try:
                    stat_index = int(item_id.split('-')[1])
                    if stat_index < len(stats):
                        stat = stats[stat_index]
                        stat_html = f"""
                        <div style="margin: 20px 0;">
                            <h3 style="color: #E5A00D; border-bottom: 1px solid #E5A00D; padding-bottom: 5px; margin-bottom: 15px;">{stat.get('stat_title', 'Stats')}</h3>
                            <table style="width: 100%; border-collapse: collapse; margin: 10px 0;">
                        """
                        if stat.get('rows'):
                            for row in stat['rows'][:10]:  # Limit to top 10
                                title = row.get('title', 'Unknown')
                                count = row.get('total_plays', row.get('count', 0))
                                year = row.get('year', '')
                                rating = row.get('rating', '')
                                
                                stat_html += f"""
                                <tr style="border-bottom: 1px solid #444;">
                                    <td style="padding: 8px; color: #fff; font-weight: bold;">{title}</td>
                                    {f'<td style="padding: 8px; color: #ccc; text-align: center;">{year}</td>' if year else ''}
                                    <td style="padding: 8px; color: #E5A00D; text-align: right; font-weight: bold;">{count}</td>
                                    {f'<td style="padding: 8px; color: #ccc; text-align: right;">{rating}</td>' if rating else ''}
                                </tr>
                                """
                        stat_html += """
                            </table>
                        </div>
                        """
                        all_content_html += stat_html
                except Exception as e:
                    print(f"Error processing stat {item_id}: {e}")
                    continue
            
            elif item_type == 'graph' and graph_data:
                try:
                    graph_index = int(item_id.split('-')[1])
                    if graph_index < len(graph_data):
                        # Generate a simple text-based representation of graph data
                        graph_info = graph_data[graph_index] if isinstance(graph_data, list) else graph_data
                        
                        graph_html = f"""
                        <div style="margin: 20px 0; padding: 20px; background: #333; border-radius: 5px; border-left: 4px solid #E5A00D;">
                            <h3 style="color: #E5A00D; margin-bottom: 15px;">{item_name}</h3>
                            <div style="color: #fff; font-family: monospace; font-size: 14px;">
                        """
                        
                        # Add some basic graph data representation
                        if isinstance(graph_info, dict) and 'series' in graph_info:
                            for series in graph_info.get('series', []):
                                series_name = series.get('name', 'Data')
                                series_data = series.get('data', [])
                                if series_data:
                                    total = sum(series_data)
                                    avg = total / len(series_data) if series_data else 0
                                    graph_html += f"""
                                    <p style="margin: 5px 0;"><strong>{series_name}:</strong> Total: {total}, Average: {avg:.1f}</p>
                                    """
                        else:
                            graph_html += f"""
                            <p style="margin: 5px 0;">Chart shows activity data for the past {date_range} days</p>
                            """
                        
                        graph_html += """
                            </div>
                        </div>
                        """
                        all_content_html += graph_html
                except Exception as e:
                    print(f"Error processing graph {item_id}: {e}")
                    # Fallback graph representation
                    graph_html = f"""
                    <div style="margin: 20px 0; padding: 20px; background: #333; border-radius: 5px; border-left: 4px solid #E5A00D;">
                        <h3 style="color: #E5A00D;">{item_name}</h3>
                        <p style="color: #fff;">Chart data for the past {date_range} days</p>
                    </div>
                    """
                    all_content_html += graph_html
        
        # If we have modular content, use it; otherwise fall back to legacy email_text
        if all_content_html.strip():
            final_content = all_content_html
        else:
            # Fallback to legacy handling
            final_content = email_text or ""
        
        # Apply layout with the assembled content
        processed_body = apply_layout(final_content, "", "", "", "", subject, settings['server_name'])
        
        return template_name, subject, processed_body
        
    except Exception as e:
        print(f"Error generating email content: {e}")
        import traceback
        traceback.print_exc()
        return None, None, str(e)

def send_scheduled_email(schedule_id, email_list_id, template_id):
    """Send an email based on schedule parameters"""
    print(f"Attempting to send scheduled email - Schedule ID: {schedule_id}, List ID: {email_list_id}, Template ID: {template_id}")
    try:
        # Get schedule details to get date_range
        schedule_conn = sqlite3.connect(DB_PATH)
        schedule_cursor = schedule_conn.cursor()
        schedule_cursor.execute("SELECT date_range FROM email_schedules WHERE id = ?", (schedule_id,))
        schedule_result = schedule_cursor.fetchone()
        schedule_conn.close()
        
        date_range = schedule_result[0] if schedule_result else 7
        print(f"Using date range: {date_range} days")
        
        # Get email list
        email_lists_conn = sqlite3.connect(DB_PATH)
        email_lists_cursor = email_lists_conn.cursor()
        email_lists_cursor.execute("SELECT emails FROM email_lists WHERE id = ?", (email_list_id,))
        email_list_result = email_lists_cursor.fetchone()
        email_lists_conn.close()
        
        if not email_list_result:
            print(f"Email list {email_list_id} not found")
            return False
        
        to_emails = email_list_result[0]
        print(f"Found email list with {len(to_emails.split(','))} recipients")
        
        # Get template
        templates_conn = sqlite3.connect(DB_PATH)
        templates_cursor = templates_conn.cursor()
        templates_cursor.execute("SELECT name, subject, email_text FROM email_templates WHERE id = ?", (template_id,))
        template_result = templates_cursor.fetchone()
        templates_conn.close()
        
        if not template_result:
            print(f"Template {template_id} not found")
            return False
        
        template_name, subject, email_text = template_result
        print(f"Found template: {template_name}")
        
        # Get SMTP settings from database
        settings_conn = sqlite3.connect(DB_PATH)
        settings_cursor = settings_conn.cursor()
        settings_cursor.execute("SELECT from_email, alias_email, password, smtp_server, smtp_port, server_name FROM settings WHERE id = 1")
        settings_result = settings_cursor.fetchone()
        settings_conn.close()
        
        if not settings_result:
            print("SMTP settings not found in database")
            return False
        
        from_email, alias_email, encrypted_password, smtp_server, smtp_port, server_name = settings_result
        
        if not all([from_email, encrypted_password, smtp_server]):
            print("Incomplete SMTP settings in database")
            print(f"FROM_EMAIL: {'Set' if from_email else 'Missing'}")
            print(f"PASSWORD: {'Set' if encrypted_password else 'Missing'}")
            print(f"SMTP_SERVER: {'Set' if smtp_server else 'Missing'}")
            return False
        
        # Decrypt the password
        try:
            password = decrypt(encrypted_password)
        except Exception as e:
            print(f"Failed to decrypt password: {e}")
            return False
        
        # Use default port if not set
        if not smtp_port:
            smtp_port = 587
        
        print(f"Using SMTP settings - Server: {smtp_server}, Port: {smtp_port}, From: {from_email}")
        
        # Generate complete email content with template processing and specified date range
        settings = {'server_name': server_name or ''}
        template_name, subject, email_html = generate_email_content(template_id, settings, date_range)
        
        if not email_html:
            print("Failed to generate email content")
            return False
        
        print(f"Generated email content for template: {template_name} with {date_range} days of data")
        
        # Create and send email
        msg_root = MIMEMultipart('related')
        msg_root['Subject'] = f"[SCHEDULED] {subject}"
        if alias_email:
            msg_root['From'] = alias_email
            msg_root['To'] = alias_email
        else:
            msg_root['From'] = from_email
            msg_root['To'] = from_email
        
        msg_alternative = MIMEMultipart('alternative')
        msg_root.attach(msg_alternative)
        
        # Use the processed template content
        msg_alternative.attach(MIMEText(email_html, 'html'))
        
        # Send email
        print("Attempting to send email...")
        try:
            # Use SSL for port 465, STARTTLS for port 587
            if int(smtp_port) == 465:
                server = smtplib.SMTP_SSL(smtp_server, int(smtp_port))
                server.login(from_email, password)
            else:
                server = smtplib.SMTP(smtp_server, int(smtp_port))
                server.starttls()
                server.login(from_email, password)
            
            email_content = msg_root.as_string()
            content_size_kb = len(email_content.encode('utf-8')) / 1024
            
            to_emails_list = [email.strip() for email in to_emails.split(",")]
            if alias_email:
                server.sendmail(alias_email, [alias_email] + to_emails_list, email_content)
                all_recipients = [alias_email] + to_emails_list
            else:
                server.sendmail(from_email, [from_email] + to_emails_list, email_content)
                all_recipients = [from_email] + to_emails_list
            
            server.quit()
            print(f"Email sent successfully to {len(all_recipients)} recipients")
            
            # Log to email_history
            try:
                history_conn = sqlite3.connect(DB_PATH)
                history_cursor = history_conn.cursor()
                history_cursor.execute('''INSERT INTO email_history (subject, recipients, email_content, content_size_kb, recipient_count, template_name)
                                VALUES (?, ?, ?, ?, ?, ?)''',
                                (f"[SCHEDULED] {subject}", ', '.join(all_recipients), email_content[:1000], content_size_kb, len(all_recipients), template_name))
                history_conn.commit()
                history_conn.close()
            except Exception as log_err:
                print(f"Error logging scheduled email history: {log_err}")
            
            return True
            
        except Exception as e:
            print(f"Failed to send email: {str(e)}")
            return False
        
    except Exception as e:
        print(f"Error in send_scheduled_email: {e}")
        import traceback
        traceback.print_exc()
        return False

def apply_layout(body, graphs_html_block, stats_html_block, ra_html_block, recs_html_block, subject, server_name):
    # Layout functionality deprecated - using standard layout only
    body = body.replace('\n', '<br>')
    body = body.replace('[GRAPHS]', graphs_html_block)
    body = body.replace('[STATS]', stats_html_block)
    body = body.replace('[RECENTLY_ADDED]', ra_html_block)
    body = body.replace('[RECOMENDATIONS]', recs_html_block)

    if subject.startswith(server_name):
        display_subject = subject[len(server_name):].lstrip()
    else:
        display_subject = subject

    # Always use standard layout (layout parameter ignored)
    return f"""
    <link href="https://fonts.googleapis.com/css?family=IBM+Plex+Sans:400,500,600,700&display=swap" rel="stylesheet">
    <html><body style="font-family: IBM Plex Sans;">
        <table class="body" style="border-collapse: separate; mso-table-lspace: 0pt; mso-table-rspace: 0pt; width: 100%;" border="0" cellspacing="0" cellpadding="0">
            <tbody>
                <tr>
                    <td class="container" style="font-family: IBM Plex Sans; font-size: 14px; vertical-align: top; display: block; max-width: 1042px; padding: 10px; width: 1042px; margin: 0 auto !important;">
                        <div class="content" style="box-sizing: border-box; display: block; margin: 0 auto; max-width: 1037px; padding: 10px;"><span class="preheader" style="color: transparent; display: none; height: 0; max-height: 0; max-width: 0; opacity: 0; overflow: hidden; mso-hide: all; visibility: hidden; width: 0;">{server_name} Newsletter</span>
                            <table class="main" style="border-collapse: separate; mso-table-lspace: 0pt; mso-table-rspace: 0pt; width: 100%; background: #282A2D; border-radius: 3px; color: #ffffff;" border="0" cellspacing="0" cellpadding="3">
                                <tbody>
                                    <tr>
                                        <td class="wrapper" style="font-family: IBM Plex Sans; font-size: 14px; vertical-align: top; box-sizing: border-box; padding: 5px; overflow: auto;">
                                            <div class="header" style="width: 50%; height: 10px; text-align: center;"><img class="header-img" style="border: none; -ms-interpolation-mode: bicubic; max-width: 9%; width: 492px; height: 20px; margin-left: -35px;" src="https://d15k2d11r6t6rl.cloudfront.net/public/users/Integrators/669d5713-9b6a-46bb-bd7e-c542cff6dd6a/3bef3c50f13f4320a9e31b8be79c6ad2/Plex%20Logo%20Update%202022/plex-logo-heavy-stroke.png" width="492" height="90" /></div>
                                            <div class="server-name" style="font-size: 25px; text-align: center; margin-bottom: 0;">{server_name} Newsletter</div>
                                        </td>
                                    </tr>
                                    <tr>
                                        <td class="footer" style="font-family: IBM Plex Sans; font-size: 12px; vertical-align: top; clear: both; margin-top: 0; text-align: center; width: 100%;">
                                            <h1 class="footer-bar" style="margin-left: auto; margin-right: auto; width: 300px; border-top: 1px solid #E5A00D; margin-top: 5px;">{display_subject}</h1>
                                            <p>
                                                {body}
                                            </p>
                                            <div class="footer-bar" style="margin-left: auto; margin-right: auto; width: 250px; border-top: 1px solid #E5A00D; margin-top: 25px;">&nbsp;</div>
                                            <div class="content-block powered-by" style="padding-bottom: 10px; padding-top: 0;">Generated for Plex Media Server by <a href="https://github.com/jma1ice/newsletterr" style="color: #E5A00D; text-decoration: none;">newsletterr</a></div>
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </td>
                </tr>
            </tbody>
        </table></body></html>"""

def run_tautulli_command(base_url, api_key, command, data_type, error, time_range='30'):
    out_data = None  # Initialize to prevent NameError
    
    if command == 'get_users':
        api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}"
    elif command == 'get_recently_added':
        api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}&count={time_range}&media_type={data_type}"
    else:
        if command == 'get_plays_per_month':
            month_range = str(math.ceil(int(time_range) / 30))
            api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}&time_range={month_range}"
        else:
            api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}&time_range={time_range}"

    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()

        if data.get('response', {}).get('result') == 'success':
            out_data = data['response']['data']
        else:
            if error == None:
                error = data.get('response', {}).get('message', 'Unknown error')
            else:
                error += f", {data.get('response', {}).get('message', 'Unknown error')}"
    except requests.exceptions.RequestException as e:
        if error == None:
            error = str(f"{data_type} Error: {e}")
        else:
            error += str(f", {data_type} Error: {e}")

    return [out_data, error]

def run_conjurr_command(base_url, user_dict, error):
    if base_url == None:
        if error == None:
            error = "Conjurr Error: No Base URL provided"
        else:
            error += ", Conjurr Error: No Base URL provided"

    api_base_url = f"{base_url}/recommendations?user_id="
    recommendations_dict = {}

    for user in user_dict.keys():
        try:
            api_url = f"{api_base_url}{user}"
            response = requests.get(api_url)
            response.raise_for_status()
            data = response.json()

            recommendations_dict[user] = data
        except requests.exceptions.RequestException as e:
            if error == None:
                error = str(f"Conjurr Error: {e}")
            else:
                error += str(f", Conjurr Error: {e}")

    return [recommendations_dict, error]

def inline_data_images_to_cid(html: str, msg_root, cid_prefix="img"):
    """
    - Finds <img src="data:image/...;base64,...."> in html
    - Replaces src with cid:<generated>
    - Attaches each image to msg_root (multipart/related)
    Returns (new_html, list_of_cids)
    """
    soup = BeautifulSoup(html or "", "html.parser")
    cids = []

    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        m = DATA_IMG_RE.match(src)
        if not m:
            continue
        mime, subtype, b64 = m.group(1), m.group(2).lower(), m.group(3)
        if subtype == "jpg":
            subtype = "jpeg"

        # Decode and attach
        raw = base64.b64decode(b64)
        cid = make_msgid(domain="newsletterr.local")[1:-1]  # strip <>; simple token
        img["src"] = f"cid:{cid}"

        part = MIMEImage(raw, _subtype=subtype)
        part.add_header("Content-ID", f"<{cid}>")
        part.add_header("Content-Disposition", "inline", filename=f"{cid}.{subtype}")
        msg_root.attach(part)
        cids.append(cid)

    return str(soup), cids

def ensure_cids_match_html(html: str, attachments_cids: list[str]):
    missing = [cid for cid in attachments_cids if f'src="cid:{cid}"' not in html]
    return missing  # for logging / debugging only

def _norm(v: str):
    if not v:
        return (0,)
    v = v.lstrip("vV").split("+", 1)[0].split("-", 1)[0]
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            num = ''.join(ch for ch in p if ch.isdigit())
            parts.append(int(num) if num else 0)
    return tuple(parts) if parts else (0,)

def _check_github_latest():
    headers = {"Accept": "application/vnd.github+json"}
    if _update_cache["etag"]:
        headers["If-None-Match"] = _update_cache["etag"]

    url = f"https://api.github.com/repos/{app.config['GITHUB_OWNER']}/{app.config['GITHUB_REPO']}/releases/latest"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 304:
            _update_cache["checked_at"] = time.time()
            return
        r.raise_for_status()
        if "application/json" not in r.headers.get("Content-Type", ""):
            raise RuntimeError(f"Unexpected content type: {r.headers.get('Content-Type')}")
        data = r.json()
        latest_tag = data.get("tag_name") or ""
        current = app.jinja_env.globals.get("version", "")
        is_newer = _norm(latest_tag) > _norm(current)

        _update_cache.update({
            "latest": latest_tag,
            "is_newer": is_newer,
            "release_url": data.get("html_url"),
            "notes": data.get("body", ""),
            "checked_at": time.time(),
            "etag": r.headers.get("ETag"),
        })
    except Exception as e:
        _update_cache["checked_at"] = time.time()

def _ensure_recent_check():
    now = time.time()
    if now - _update_cache["checked_at"] >= app.config["UPDATE_CHECK_INTERVAL_SEC"]:
        _check_github_latest()

def _background_update_checker():
    while True:
        try:
            _check_github_latest()
        finally:
            time.sleep(app.config["UPDATE_CHECK_INTERVAL_SEC"])

threading.Thread(target=_background_update_checker, daemon=True).start()

@app.context_processor
def inject_update_info():
    _ensure_recent_check()
    return {
        "update_info": {
            "current": app.jinja_env.globals.get("version", ""),
            "latest": _update_cache["latest"],
            "is_newer": _update_cache["is_newer"],
            "release_url": _update_cache["release_url"],
            "notes": _update_cache["notes"],
        }
    }

@app.route('/', methods=['GET', 'POST'])
def index():
    stats = None
    users = None
    user_dict = {}
    graph_commands = [
        {
            'command' : 'get_concurrent_streams_by_stream_type',
            'name' : 'Stream Type'
        },
        {
            'command' : 'get_plays_by_date',
            'name' : 'Plays by Date'
        },
        {
            'command' : 'get_plays_by_dayofweek',
            'name' : 'Plays by Day'
        },
        {
            'command' : 'get_plays_by_hourofday',
            'name' : 'Plays by Hour'
        },
        {
            'command' : 'get_plays_by_source_resolution',
            'name' : 'Plays by Source Res'
        },
        {
            'command' : 'get_plays_by_stream_resolution',
            'name' : 'Plays by Stream Res'
        },
        {
            'command' : 'get_plays_by_stream_type',
            'name' : 'Plays by Stream Type'
        },
        {
            'command' : 'get_plays_by_top_10_platforms',
            'name' : 'Plays by Top Platforms'
        },
        {
            'command' : 'get_plays_by_top_10_users',
            'name' : 'Plays by Top Users'
        },
        {
            'command' : 'get_plays_per_month',
            'name' : 'Plays per Month'
        },
        {
            'command' : 'get_stream_type_by_top_10_platforms',
            'name' : 'Stream Type by Top Platforms'
        },
        {
            'command' : 'get_stream_type_by_top_10_users',
            'name' : 'Stream Type by Top Users'
        }
    ]
    recent_commands = [
        {
            'command' : 'movie'
        },
        {
            'command' : 'show'
        }
    ]
    graph_data = []
    recent_data = []
    error = None
    alert = None

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT server_name, tautulli_url, tautulli_api FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        settings = {
            "server_name": row[0],
            "tautulli_url": row[1],
            "tautulli_api": row[2]
        }
    else:
        settings = {
            "server_name": ""
        }

    # Load cached data if available (for both GET and POST requests)
    if settings['server_name'] != "":
        # Try to get fresh cached data first, fall back to older data if needed
        stats = get_cached_data('stats', strict=True) or get_cached_data('stats', strict=False)
        users = get_cached_data('users', strict=True) or get_cached_data('users', strict=False)
        graph_data = get_cached_data('graph_data', strict=True) or get_cached_data('graph_data', strict=False) or []
        recent_data = get_cached_data('recent_data', strict=True) or get_cached_data('recent_data', strict=False) or []
        
        # Build user_dict if we have users
        if users:
            for user in users:
                if user['email'] != None and user['is_active']:
                    user_dict[user['user_id']] = user['email']

    if request.method == 'POST':
        if settings['server_name'] == "":
            return render_template('index.html', error='Please enter tautulli info on settings page',
                                    stats=stats, user_dict=user_dict, graph_data=graph_data,
                                    graph_commands=graph_commands, alert=alert, settings=settings)
        else:
            time_range = request.form.get("days_to_pull")
            count = request.form.get("items_to_pull")
            tautulli_base_url = settings['tautulli_url'].rstrip('/')
            tautulli_api_key = settings['tautulli_api']
            
            # Create parameter signature for caching
            cache_params = {
                'time_range': time_range,
                'count': count,
                'url': tautulli_base_url,
                'timestamp': time.time()
            }

            # Always fetch fresh data on POST request
            stats, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', error, time_range)
            set_cached_data('stats', stats, cache_params)
            
            users, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_users', 'Users', error)
            set_cached_data('users', users, cache_params)
            
            # Fetch graph data
            graph_data = []
            for command in graph_commands:
                try:
                    gd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], error, time_range)
                    # Only append valid data, use empty dict as fallback for failed commands
                    graph_data.append(gd if gd is not None else {})
                except Exception as e:
                    # If command fails completely, append empty dict and continue
                    graph_data.append({})
                    if error is None:
                        error = f"Graph Error: {str(e)}"
                    else:
                        error += f", Graph Error: {str(e)}"
            set_cached_data('graph_data', graph_data, cache_params)
            
            # Fetch recent data
            recent_data = []
            for command in recent_commands:
                try:
                    rd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_recently_added', command["command"], error, count)
                    # Only append valid data, use empty dict as fallback for failed commands
                    recent_data.append(rd if rd is not None else {})
                except Exception as e:
                    # If command fails completely, append empty dict and continue
                    recent_data.append({})
                    if error is None:
                        error = f"Recent Data Error: {str(e)}"
                    else:
                        error += f", Recent Data Error: {str(e)}"
            set_cached_data('recent_data', recent_data, cache_params)
            
            # Update user_dict with fresh users data
            user_dict = {}
            for user in users:
                if user['email'] != None and user['is_active']:
                    user_dict[user['user_id']] = user['email']
            
            alert = f"Fresh data loaded! Stats/graphs for {time_range} days, and {count} recently added items."

    if graph_data == []:
        graph_data = [{},{}]

    if recent_data == []:
        recent_data = [{},{}]
        
    libs = ['movies', 'shows']
    
    # Get saved email lists
    try:
        email_lists = get_saved_email_lists()
    except:
        email_lists = []
    
    # Get cache status information
    cache_info = {
        'stats': get_cache_info('stats'),
        'users': get_cache_info('users'), 
        'graph_data': get_cache_info('graph_data'),
        'recent_data': get_cache_info('recent_data')
    }
        
    return render_template('index.html',
                           stats=stats, user_dict=user_dict,
                           graph_data=graph_data, graph_commands=graph_commands,
                           recent_data=recent_data, libs=libs,
                           error=error, alert=alert, settings=settings,
                           email_lists=email_lists, cache_info=cache_info
                        )

@app.route('/proxy-art/<path:art_path>')
def proxy_art(art_path):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT plex_url, plex_token FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        settings = {
            "plex_url": row[0],
            "plex_token": row[1]
        }
    else:
        settings = {
            "plex_url": "",
            "plex_token": ""
        }

    if not settings['plex_token']:
        return Response("Please connect to Plex in settings.", status=400)

    plex_token = settings['plex_token']
    plex_url = settings['plex_url'].rstrip('/')

    full_url = f"{plex_url}/{art_path}?X-Plex-Token={decrypt(plex_token)}"
    r = requests.get(full_url, stream=True)
    return Response(r.content, content_type=r.headers['Content-Type'])

@app.get("/proxy-img")
def proxy_img():
    url = request.args.get("u", "")
    if not url.startswith(("http://","https://")):
        return Response(status=400)
    r = requests.get(url, timeout=15)
    ct = r.headers.get("Content-Type", "image/jpeg")
    return Response(r.content, headers={"Content-Type": ct, "Cache-Control": "public, max-age=86400"})

@app.route('/pull_recommendations', methods=['POST'])
def pull_recommendations():
    recommendations_json = {}
    error = None
    alert = None
    
    data = request.get_json()
    stats = data['stats']
    user_dict = data['user_dict']
    graph_data = data['graph_data']
    graph_commands = data['graph_commands']
    recent_data = data['recent_data']
    libs = data['libs']
    settings = data['settings']
    to_emails = data['to_emails']

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT conjurr_url FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()

    if row:
        conjurr_settings = {
            "conjurr_url": row[0]
        }
    else:
        conjurr_settings = {
            "conjurr_url": ""
        }

    filtered_users = {k: v for k, v in user_dict.items() if v in to_emails}

    if request.method == 'POST':
        if conjurr_settings['conjurr_url'] == "":
            return render_template('index.html', error='Please enter conjurr info on settings page',
                                    stats=stats, user_dict=user_dict, graph_data=graph_data,
                                    graph_commands=graph_commands, recent_data=recent_data,
                                    libs=libs, settings=settings)
        else:
            conjurr_base_url = conjurr_settings['conjurr_url']
            recommendations_json, error = run_conjurr_command(conjurr_base_url, filtered_users, error)
            alert = "User recommendations pulled from conjurr!"
    
    frag = render_template(
        'partials/_recommendations.html',
        recommendations_json=recommendations_json, user_dict=user_dict
    )
    return jsonify({"ok": True, "html": frag, "alert": alert})

@app.route('/send_email', methods=['POST'])
def send_email():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
        from_email, alias_email, password, smtp_server, smtp_port, server_name
        FROM settings WHERE id = 1
    """)
    row = cursor.fetchone()
    conn.close()

    if row:
        settings = {
            "from_email": row[0] or "",
            "alias_email": row[1] or "",
            "password": row[2] or "",
            "smtp_server": row[3] or "",
            "smtp_port": int(row[4]) if row[4] is not None else 587,
            "server_name": row[5] or ""
        }
    else:
        return jsonify({"error": "Please enter email info on settings page"}), 500

    data = request.get_json()
    
    # Debug logging
    print(f"DEBUG: Received email request")
    print(f"DEBUG: Subject: {data.get('subject', 'No subject')}")
    print(f"DEBUG: To emails: {data.get('to_emails', 'No recipients')}")
    print(f"DEBUG: Email HTML length: {len(data.get('email_html', ''))}")
    print(f"DEBUG: Number of images: {len(data.get('all_images', []))}")
    
    if data.get('all_images'):
        for i, img in enumerate(data.get('all_images', [])):
            print(f"DEBUG: Image {i}: CID={img.get('cid')}, MIME={img.get('mime')}, Data length={len(img.get('data', ''))}")

    # Get the new format data
    all_images = data.get('all_images', [])
    email_html = data.get('email_html', '')
    from_email = settings['from_email']
    alias_email = settings['alias_email']
    password = settings['password']
    smtp_server = settings['smtp_server']
    smtp_port = int(settings['smtp_port'])
    server_name = settings['server_name']
    to_emails = data['to_emails'].split(", ")
    subject = data['subject']

    msg_root = MIMEMultipart('related')
    msg_root['Subject'] = subject
    if alias_email == '':
        msg_root['From'] = from_email
        msg_root['To'] = from_email
    else:
        msg_root['From'] = alias_email
        msg_root['To'] = alias_email

    msg_alternative = MIMEMultipart('alternative')
    msg_root.attach(msg_alternative)

    # Use the complete HTML content from the preview
    html_content = email_html

    html_content, _cids_from_data = inline_data_images_to_cid(html_content, msg_root)

    # Process all images and attach them with CID references
    attached_cids = []
    for image_data in all_images:
        try:
            # Extract base64 data (remove data:image/png;base64, prefix if present)
            base64_data = image_data['data']
            if base64_data.startswith('data:'):
                base64_data = base64_data.split(',')[1]
            
            # Decode the image
            raw_image_data = base64.b64decode(base64_data)
            
            # Determine the image format
            mime_type = image_data.get('mime', 'image/png')
            subtype = mime_type.split('/')[-1] if '/' in mime_type else 'png'
            if subtype == 'jpg':
                subtype = 'jpeg'
            
            # Create the image attachment
            image_part = MIMEImage(raw_image_data, _subtype=subtype)
            cid = image_data['cid']
            image_part.add_header('Content-ID', f'<{cid}>')
            image_part.add_header('Content-Disposition', 'inline', filename=f'{cid}.{subtype}')
            msg_root.attach(image_part)
            attached_cids.append(cid)
        except Exception as e:
            print(f"Error processing image {image_data.get('cid', 'unknown')}: {str(e)}")
            continue
    
    # Add a plain-text alternative first (some clients like it)
    plain = re.sub(r'<[^>]+>', ' ', html_content)  # crude strip of tags
    msg_alternative.attach(MIMEText(plain, 'plain', 'utf-8'))

    msg_alternative.attach(MIMEText(html_content, 'html', 'utf-8'))

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(from_email, decrypt(password))
            
            # Calculate email size in KB
            email_content = msg_root.as_string()
            content_size_kb = len(email_content.encode('utf-8')) / 1024
            
            if alias_email == '':
                server.sendmail(from_email, [from_email] + to_emails, email_content)
                all_recipients = [from_email] + to_emails
            else:
                server.sendmail(alias_email, [alias_email] + to_emails, email_content)
                all_recipients = [alias_email] + to_emails
            
            # Save to email history
            try:
                history_conn = sqlite3.connect(DB_PATH)
                history_cursor = history_conn.cursor()
                history_cursor.execute("""
                    INSERT INTO email_history (subject, recipients, email_content, content_size_kb, recipient_count, template_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    subject,
                    ', '.join(all_recipients),
                    email_content,
                    round(content_size_kb, 2),
                    len(all_recipients),
                    'Manual'
                ))
                history_conn.commit()
                history_conn.close()
            except Exception as history_error:
                print(f"Error saving email history: {history_error}")
            
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if request.method == "POST":
        from_email = request.form.get("from_email")
        alias_email = request.form.get("alias_email")
        password = encrypt(request.form.get("password"))
        smtp_server = request.form.get("smtp_server")
        smtp_port = int(request.form.get("smtp_port"))
        server_name = request.form.get("server_name")
        tautulli_url = request.form.get("tautulli_url")
        tautulli_api = encrypt(request.form.get("tautulli_api"))
        conjurr_url = request.form.get("conjurr_url")

        cursor.execute("""
            INSERT INTO settings
            (id, from_email, alias_email, password, smtp_server, smtp_port, server_name, tautulli_url, tautulli_api, conjurr_url)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE
            SET from_email = excluded.from_email, alias_email = excluded.alias_email, password = excluded.password, smtp_server = excluded.smtp_server, smtp_port = excluded.smtp_port, server_name = excluded.server_name, tautulli_url = excluded.tautulli_url, tautulli_api = excluded.tautulli_api, conjurr_url = excluded.conjurr_url
        """, (from_email, alias_email, password, smtp_server, smtp_port, server_name, tautulli_url, tautulli_api, conjurr_url))
        conn.commit()
        cursor.execute("SELECT plex_token FROM settings WHERE id = 1")
        plex_token = cursor.fetchone()[0]
        conn.close()

        settings = {
            "from_email": from_email,
            "alias_email": alias_email,
            "password": decrypt(password),
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
            "server_name": server_name,
            "plex_token": plex_token,
            "tautulli_url": tautulli_url,
            "tautulli_api": decrypt(tautulli_api),
            "conjurr_url": conjurr_url
        }

        return render_template('settings.html', alert="Settings saved successfully!", settings=settings)

    cursor.execute("""
        SELECT
        from_email, alias_email, password, smtp_server, smtp_port, server_name, plex_token, tautulli_url, tautulli_api, conjurr_url
        FROM settings WHERE id = 1
    """)
    row = cursor.fetchone()
    conn.close()

    if row:
        settings = {
            "from_email": row[0] or "",
            "alias_email": row[1] or "",
            "password": decrypt(row[2]),
            "smtp_server": row[3] or "",
            "smtp_port": int(row[4]) if row[4] is not None else 587,
            "server_name": row[5] or "",
            "plex_token": row[6] or "",
            "tautulli_url": row[7] or "",
            "tautulli_api": decrypt(row[8]),
            "conjurr_url": row[9] or ""
        }
    else:
        settings = {
            "from_email": ""
        }

    return render_template('settings.html', settings=settings)

@app.post('/api/plex/pin')
def plex_create_pin():
    with PlexAPI() as plex_api:
        res = plex_api.plex.get_pin(request={
            "client_id": plex_headers["X-Plex-Client-Identifier"],
            "client_name": "newsletterr",
            "device_nickname": "newsletterr",
            "client_version": f"{app.jinja_env.globals['version']}",
            "platform": "Flask",
        })
    
    assert res.auth_pin_container is not None

    auth_url = (
        "https://plex.tv/link?"
        f"clientID={quote_plus(plex_headers['X-Plex-Client-Identifier'])}"
        f"&code={quote_plus(res.auth_pin_container.code)}"
    )
    return jsonify({"pin_id": res.auth_pin_container.id, "code": res.auth_pin_container.code, "auth_url": auth_url, "expires_in": res.auth_pin_container.expires_in})

@app.get('/api/plex/pin/<int:pin_id>')
def plex_poll_pin(pin_id: int):
    with PlexAPI() as plex_api:
        res = plex_api.plex.get_token_by_pin_id(request={
            "pin_id": pin_id,
            "client_id": plex_headers["X-Plex-Client-Identifier"],
            "client_name": "newsletterr",
            "device_nickname": "newsletterr",
            "client_version": f"{app.jinja_env.globals['version']}",
            "platform": "Flask",
        })
    
    assert res.auth_pin_container is not None

    token = res.auth_pin_container.auth_token
    if token:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (id, plex_token)
            VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET plex_token = excluded.plex_token
        """, (encrypt(token),))
        conn.commit()
        conn.close()

        return jsonify({"connected": True})
    return jsonify({"connected": False})

@app.get('/api/plex/info')
def plex_get_info():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT plex_token FROM settings WHERE id = 1")
    row = cursor.fetchone()
    token = row[0]

    url = "https://plex.tv/api/v2/resources"
    headers = {
        "Accept": "application/json",
        "X-Plex-Client-Identifier": plex_headers['X-Plex-Client-Identifier'],
        "X-Plex-Token": decrypt(token)
    }
    
    response = requests.get(url, headers=headers)
    data = response.json()

    cursor.execute("""
        INSERT INTO settings (id, server_name, plex_url)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET server_name = excluded.server_name, plex_url = excluded.plex_url
    """, (data[0]['name'], data[0]['connections'][0]['uri']))
    conn.commit()
    conn.close()

    if response.status_code == 200:
        return jsonify({"connected": True})
    return jsonify({"connected": False})

@app.route('/about', methods=['GET'])
def about():
    return render_template('about.html')

@app.route('/email_history', methods=['GET'])
def email_history():
    """Display email history page"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, subject, recipients, content_size_kb, recipient_count, sent_at, template_name
            FROM email_history 
            ORDER BY sent_at DESC
        """)
        emails = cursor.fetchall()
        conn.close()
        
        email_list = []
        for email in emails:
            # Convert UTC timestamp to local time
            try:
                # Parse the SQLite timestamp
                utc_dt = datetime.fromisoformat(email[5].replace('Z', '+00:00'))
                # Convert to local time
                local_dt = utc_dt.replace(tzinfo=timezone.utc).astimezone()
                # Format as readable string
                formatted_time = local_dt.strftime('%Y-%m-%d %I:%M:%S %p')
            except:
                # Fallback to original timestamp if parsing fails
                formatted_time = email[5]
            
            email_list.append({
                'id': email[0],
                'subject': email[1],
                'recipients': email[2],
                'content_size_kb': email[3],
                'recipient_count': email[4],
                'sent_at': formatted_time,
                'template_name': email[6] if len(email) > 6 and email[6] else 'Manual'
            })
        
        return render_template('email_history.html', emails=email_list)
    except Exception as e:
        print(f"Error loading email history: {e}")
        return render_template('email_history.html', emails=[])

@app.route('/email_history/clear', methods=['POST'])
def clear_email_history():
    """Clear all email history entries."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM email_history")
        conn.commit()
        conn.close()
        return redirect(url_for('email_history'))
    except Exception as e:
        print(f"Error clearing email history: {e}")
        return redirect(url_for('email_history'))

@app.route('/email_history/recipients/<int:email_id>', methods=['GET'])
def get_email_recipients(email_id):
    """Get recipients for a specific email"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT recipients, subject FROM email_history WHERE id = ?", (email_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            recipients = result[0].split(', ') if result[0] else []
            return jsonify({
                'subject': result[1],
                'recipients': recipients
            })
        else:
            return jsonify({'error': 'Email not found'}), 404
    except Exception as e:
        print(f"Error getting recipients: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/scheduling', methods=['GET'])
def scheduling():
    """Display email scheduling page"""
    try:
        schedules = get_email_schedules()
        email_lists = get_saved_email_lists()
        
        # Get email templates
        templates_conn = sqlite3.connect(DB_PATH)
        templates_cursor = templates_conn.cursor()
        templates_cursor.execute("SELECT id, name FROM email_templates ORDER BY name")
        templates = [{'id': row[0], 'name': row[1]} for row in templates_cursor.fetchall()]
        templates_conn.close()
        
        return render_template('scheduling.html', 
                             schedules=schedules, 
                             email_lists=email_lists, 
                             templates=templates)
    except Exception as e:
        print(f"Error loading scheduling page: {e}")
        return render_template('scheduling.html', schedules=[], email_lists=[], templates=[])

@app.route('/scheduling/create', methods=['POST'])
def create_schedule():
    """Create a new email schedule"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email_list_id = int(data.get('email_list_id'))
        template_id = int(data.get('template_id'))
        frequency = data.get('frequency')
        start_date = data.get('start_date')
        send_time = data.get('send_time', '09:00')
        date_range = int(data.get('date_range', 7))
        
        if not all([name, email_list_id, template_id, frequency, start_date]):
            return jsonify({"status": "error", "message": "All fields are required"}), 400
        
        success = create_email_schedule(name, email_list_id, template_id, frequency, start_date, send_time, date_range)
        if success:
            return jsonify({"status": "success", "message": f"Schedule '{name}' created successfully"})
        else:
            return jsonify({"status": "error", "message": "Failed to create schedule"}), 500
    except Exception as e:
        print(f"Error creating schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>', methods=['PUT'])
def update_schedule(schedule_id):
    """Update an existing email schedule"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email_list_id = int(data.get('email_list_id'))
        template_id = int(data.get('template_id'))
        frequency = data.get('frequency')
        start_date = data.get('start_date')
        send_time = data.get('send_time', '09:00')
        date_range = int(data.get('date_range', 7))
        
        if not all([name, email_list_id, template_id, frequency, start_date]):
            return jsonify({"status": "error", "message": "All fields are required"}), 400
        
        success = update_email_schedule(schedule_id, name, email_list_id, template_id, frequency, start_date, send_time, date_range)
        if success:
            return jsonify({"status": "success", "message": f"Schedule '{name}' updated successfully"})
        else:
            return jsonify({"status": "error", "message": "Failed to update schedule"}), 500
    except Exception as e:
        print(f"Error updating schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>', methods=['DELETE'])
def delete_schedule(schedule_id):
    """Delete an email schedule"""
    try:
        delete_email_schedule(schedule_id)
        return jsonify({"status": "success", "message": "Schedule deleted successfully"})
    except Exception as e:
        print(f"Error deleting schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>/send-now', methods=['POST'])
def send_schedule_now(schedule_id):
    """Manually trigger sending of a scheduled email without affecting the schedule"""
    try:
        # Get schedule details
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, email_list_id, template_id, frequency, is_active
            FROM email_schedules 
            WHERE id = ?
        """, (schedule_id,))
        schedule = cursor.fetchone()
        conn.close()
        
        if not schedule:
            return jsonify({"status": "error", "message": "Schedule not found"}), 404
        
        schedule_id, name, email_list_id, template_id, frequency, is_active = schedule
        
        # Send the email (this doesn't update the schedule's next_send time)
        print(f"Manual send triggered for schedule: {name}")
        success = send_scheduled_email(schedule_id, email_list_id, template_id)
        
        if success:
            # Update the last_sent timestamp for manual sends
            from datetime import datetime
            current_time = datetime.now().isoformat()
            
            update_conn = sqlite3.connect(DB_PATH)
            update_cursor = update_conn.cursor()
            update_cursor.execute("""
                UPDATE email_schedules 
                SET last_sent = ? 
                WHERE id = ?
            """, (current_time, schedule_id))
            update_conn.commit()
            update_conn.close()
            
            print(f"Updated last_sent timestamp for schedule {name}")
            return jsonify({"status": "success", "message": f"Email '{name}' sent successfully"})
        else:
            return jsonify({"status": "error", "message": f"Failed to send email '{name}'"})
            
    except Exception as e:
        print(f"Error in manual send: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>/toggle', methods=['POST'])
def toggle_schedule(schedule_id):
    """Toggle schedule active/inactive status"""
    try:
        data = request.get_json()
        is_active = data.get('is_active', True)
        toggle_schedule_status(schedule_id, is_active)
        status = "activated" if is_active else "deactivated"
        return jsonify({"status": "success", "message": f"Schedule {status} successfully"})
    except Exception as e:
        print(f"Error toggling schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>/preview', methods=['GET'])
def preview_schedule(schedule_id):
    """Generate a preview of the email for a specific schedule"""
    try:
        # Get schedule details
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT template_id, date_range
            FROM email_schedules 
            WHERE id = ?
        """, (schedule_id,))
        schedule_result = cursor.fetchone()
        conn.close()
        
        if not schedule_result:
            return jsonify({"status": "error", "message": "Schedule not found"}), 404
        
        template_id, date_range = schedule_result
        date_range = date_range or 7  # Default to 7 days if not set
        
        # Get template details
        templates_conn = sqlite3.connect(DB_PATH)
        templates_cursor = templates_conn.cursor()
        templates_cursor.execute("SELECT name, subject, email_text, selected_items FROM email_templates WHERE id = ?", (template_id,))
        template_result = templates_cursor.fetchone()
        templates_conn.close()
        
        if not template_result:
            return jsonify({"status": "error", "message": "Template not found"}), 404
        
        template_name, subject, email_text, selected_items_json = template_result
        
        # Parse selected items
        try:
            selected_items = json.loads(selected_items_json) if selected_items_json else []
        except:
            selected_items = []
        
        # Get settings
        settings_conn = sqlite3.connect(DB_PATH)
        settings_cursor = settings_conn.cursor()
        settings_cursor.execute("SELECT server_name, tautulli_url, tautulli_api FROM settings WHERE id = 1")
        settings_row = settings_cursor.fetchone()
        settings_conn.close()
        
        if settings_row:
            settings = {
                "server_name": settings_row[0],
                "tautulli_url": settings_row[1],
                "tautulli_api": settings_row[2]
            }
        else:
            settings = {"server_name": ""}
        
        # Check if we can use cached data for this date range
        can_use_cache, cache_reason = can_use_cached_data_for_preview(date_range)
        
        # Fetch data - use cache if suitable, otherwise fetch fresh
        stats = []
        graph_data = []
        recent_data = []
        
        if can_use_cache:
            print(f"Using cached data for preview: {cache_reason}")
            # Use cached data
            stats = get_cached_data('stats', strict=False) or []
            graph_data = get_cached_data('graph_data', strict=False) or []
            recent_data = get_cached_data('recent_data', strict=False) or []
        elif settings.get('tautulli_url') and settings.get('tautulli_api'):
            tautulli_base_url = settings['tautulli_url'].rstrip('/')
            tautulli_api_key = settings['tautulli_api']
            
            print(f"Fetching fresh Tautulli data for preview - {date_range} days ({cache_reason})")
            
            # Define graph commands (same as main page)
            graph_commands = [
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
                {'command': 'get_stream_type_by_top_10_users', 'name': 'Stream Type by Top Users'}
            ]
            
            recent_commands = [
                {'command': 'movie'},
                {'command': 'show'}
            ]
            
            try:
                # Fetch stats
                stats, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', None, str(date_range))
                if error:
                    print(f"Error fetching stats: {error}")
                
                # Fetch graph data
                graph_data = []
                for command in graph_commands:
                    gd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], error, str(date_range))
                    if gd:
                        graph_data.append(gd)
                    if error:
                        print(f"Error fetching graph data for {command['name']}: {error}")
                
                # Fetch recent data  
                recent_data = []
                for command in recent_commands:
                    rd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_recently_added', command["command"], error, "10")  # Default to 10 items
                    if rd:
                        recent_data.append(rd)
                    if error:
                        print(f"Error fetching recent data for {command['command']}: {error}")
                        
            except Exception as e:
                print(f"Failed to fetch fresh data: {e}")
                # Fallback to cached data
                stats = get_cached_data('stats') or []
                graph_data = get_cached_data('graph_data') or []
                recent_data = get_cached_data('recent_data') or []
        else:
            print("Tautulli not configured, using cached data")
            # Fallback to cached data
            stats = get_cached_data('stats') or []
            graph_data = get_cached_data('graph_data') or []
            recent_data = get_cached_data('recent_data') or []
        
        # Define graph commands (same as main page)
        graph_commands = [
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
            {'command': 'get_stream_type_by_top_10_users', 'name': 'Stream Type by Top Users'}
        ]
        
        recent_commands = [
            {'command': 'movie'},
            {'command': 'show'}
        ]
        
        # Return template data so frontend can generate preview using same logic as main page
        return jsonify({
            "status": "success",
            "template_name": template_name,
            "subject": subject,
            "email_text": email_text,
            "selected_items": selected_items,
            "date_range": date_range,
            "settings": settings,
            "stats": stats,
            "graph_data": graph_data,
            "recent_data": recent_data,
            "graph_commands": graph_commands,
            "recent_commands": recent_commands
        })
        
    except Exception as e:
        print(f"Error generating preview: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>/preview-page', methods=['GET'])
def preview_schedule_page(schedule_id):
    """Serve the preview page for a specific schedule"""
    
    # Get schedule details to determine required date range
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT date_range FROM email_schedules WHERE id = ?", (schedule_id,))
        schedule_result = cursor.fetchone()
        conn.close()
        
        date_range = schedule_result[0] if schedule_result else 7
    except:
        date_range = 7  # Default fallback
    
    # Check if we can use cached data for this date range
    can_use_cache, cache_reason = can_use_cached_data_for_preview(date_range)
    
    if can_use_cache:
        print(f"Preview page using cached data: {cache_reason}")
        # Use cached data (try strict first, then extended)
        stats = get_cached_data('stats', strict=True) or get_cached_data('stats', strict=False) or []
        graph_data = get_cached_data('graph_data', strict=True) or get_cached_data('graph_data', strict=False) or []
        recent_data = get_cached_data('recent_data', strict=True) or get_cached_data('recent_data', strict=False) or []
    else:
        print(f"Preview page using cached data (fallback): {cache_reason}")
        # Use whatever cached data we have as fallback
        stats = get_cached_data('stats', strict=False) or []
        graph_data = get_cached_data('graph_data', strict=False) or []
        recent_data = get_cached_data('recent_data', strict=False) or []
    
    # Define graph commands (same as main page)
    graph_commands = [
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
        {'command': 'get_stream_type_by_top_10_users', 'name': 'Stream Type by Top Users'}
    ]
    
    return render_template('schedule_preview.html', 
                         stats=stats, 
                         graph_data=graph_data, 
                         recent_data=recent_data,
                         graph_commands=graph_commands)

@app.route('/scheduling/calendar-data', methods=['GET'])
def get_calendar_data():
    """Get scheduled dates for calendar display"""
    try:
        from datetime import datetime, timedelta
        import calendar
        
        # Get month and year from query params, default to current
        month = int(request.args.get('month', datetime.now().month))
        year = int(request.args.get('year', datetime.now().year))
        
        # Get all active schedules
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, frequency, start_date, send_time, next_send, is_active, template_id
            FROM email_schedules 
            WHERE is_active = 1
        """)
        schedules = cursor.fetchall()
        conn.close()
        
        # Calculate dates for the requested month
        calendar_data = {}
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        
        for schedule in schedules:
            schedule_id, name, frequency, schedule_start_date, send_time, next_send, is_active, template_id = schedule
            
            if not is_active:
                continue
                
            # Parse the start date
            try:
                schedule_start = datetime.fromisoformat(schedule_start_date)
            except:
                continue
            
            # For weekly/monthly schedules, we need to generate the proper sequence
            # starting from the actual start date, not the month start
            current_date = schedule_start
            
            # Skip forward to get close to the target month if we're way behind
            if frequency == 'weekly' and current_date < start_date:
                # Calculate how many weeks to skip to get close to target month
                weeks_to_skip = (start_date - current_date).days // 7
                current_date += timedelta(weeks=weeks_to_skip)
                
                # Now use proper weekday logic to get to the exact weekday
                target_weekday = schedule_start.weekday()
                days_ahead = (target_weekday - current_date.weekday()) % 7
                current_date += timedelta(days=days_ahead)
                
                # If we're still before the month, advance one more week
                if current_date < start_date:
                    current_date += timedelta(days=7)
            
            elif frequency == 'monthly' and current_date < start_date:
                # For monthly, jump to the target month while preserving day
                target_day = schedule_start.day
                current_date = datetime(year, month, min(target_day, calendar.monthrange(year, month)[1]))
            
            # Generate dates within the target month
            while current_date <= end_date:
                if current_date >= start_date and current_date >= schedule_start:
                    date_key = current_date.strftime('%Y-%m-%d')
                    if date_key not in calendar_data:
                        calendar_data[date_key] = []
                    
                    calendar_data[date_key].append({
                        'id': schedule_id,
                        'name': name,
                        'time': send_time or '09:00',
                        'frequency': frequency,
                        'template_id': template_id
                    })
                
                # Calculate next occurrence using the same logic as calculate_next_send
                if frequency == 'daily':
                    current_date += timedelta(days=1)
                elif frequency == 'weekly':
                    current_date += timedelta(days=7)  # Simple 7-day increment for weekly
                elif frequency == 'monthly':
                    # Use the same day-of-month preservation logic as calculate_next_send
                    target_day = schedule_start.day
                    if current_date.month == 12:
                        next_year = current_date.year + 1
                        next_month = 1
                    else:
                        next_year = current_date.year
                        next_month = current_date.month + 1
                    
                    # Handle month boundary cases
                    last_day_of_month = calendar.monthrange(next_year, next_month)[1]
                    actual_day = min(target_day, last_day_of_month)
                    current_date = current_date.replace(year=next_year, month=next_month, day=actual_day)
                else:
                    break
        
        return jsonify({
            'status': 'success',
            'data': calendar_data,
            'month': month,
            'year': year
        })
    except Exception as e:
        print(f"Error getting calendar data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/clear_cache', methods=['POST'])
def clear_cache_route():
    """Clear the data cache and return a JSON response"""
    clear_cache()
    return jsonify({"status": "success", "message": "Cache cleared successfully"})

@app.route('/cache_status', methods=['GET'])
def cache_status():
    """Get cache status information"""
    status = {}
    for key in cache_storage:
        status[key] = {
            'has_data': cache_storage[key]['data'] is not None,
            'is_valid': is_cache_valid(key),
            'age_seconds': int(time.time() - cache_storage[key]['timestamp']) if cache_storage[key]['timestamp'] > 0 else 0
        }
    return jsonify(status)

@app.route('/email_lists', methods=['GET'])
def get_email_lists():
    """Get all saved email lists"""
    try:
        lists = get_saved_email_lists()
        return jsonify({"status": "success", "lists": lists})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/email_lists', methods=['POST'])
def save_email_list_route():
    """Save a new email list"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        emails = data.get('emails', '').strip()
        
        if not name:
            return jsonify({"status": "error", "message": "List name is required"}), 400
        if not emails:
            return jsonify({"status": "error", "message": "Email list cannot be empty"}), 400
            
        success = save_email_list(name, emails)
        if success:
            return jsonify({"status": "success", "message": f"List '{name}' saved successfully"})
        else:
            return jsonify({"status": "error", "message": f"List name '{name}' already exists"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/email_lists/<int:list_id>', methods=['DELETE'])
def delete_email_list_route(list_id):
    """Delete an email list"""
    try:
        delete_email_list(list_id)
        return jsonify({"status": "success", "message": "List deleted successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Email Template Routes
@app.route('/email_templates', methods=['GET'])
def get_email_templates():
    """Get all email templates"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, selected_items, email_text, subject FROM email_templates ORDER BY name")
        templates = cursor.fetchall()
        conn.close()
        
        template_list = []
        for template in templates:
            template_list.append({
                'id': template[0],
                'name': template[1],
                'selected_items': template[2],
                'email_text': template[3],
                'subject': template[4]
            })
        
        return jsonify(template_list)
    except Exception as e:
        print(f"Error getting templates: {e}")
        return jsonify([])

@app.route('/email_templates', methods=['POST'])
def save_email_template():
    """Save a new email template"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        selected_items = data.get('selected_items', '[]')  # JSON string
        email_text = data.get('email_text', '')
        subject = data.get('subject', '')
        
        if not name:
            return jsonify({"status": "error", "message": "Template name is required"}), 400
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if template with this name already exists
        cursor.execute("SELECT id FROM email_templates WHERE name = ?", (name,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing template
            cursor.execute("""
                UPDATE email_templates 
                SET selected_items = ?, email_text = ?, subject = ?, updated_at = CURRENT_TIMESTAMP
                WHERE name = ?
            """, (selected_items, email_text, subject, name))
            message = "Template updated successfully"
        else:
            # Create new template
            cursor.execute("""
                INSERT INTO email_templates (name, selected_items, email_text, subject)
                VALUES (?, ?, ?, ?)
            """, (name, selected_items, email_text, subject))
            message = "Template saved successfully"
        
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "message": message})
    except Exception as e:
        print(f"Error saving template: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/email_templates/<int:template_id>', methods=['DELETE'])
def delete_email_template(template_id):
    """Delete an email template"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM email_templates WHERE id = ?", (template_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "message": "Template deleted successfully"})
    except Exception as e:
        print(f"Error deleting template: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    os.makedirs("database", exist_ok=True)
    
    # Migrate data from separate database files if they exist
    migrate_data_from_separate_dbs()
    
    # Initialize unified database
    init_db(DB_PATH)
    migrate_schema("conjurr_url TEXT")
    
    # Start background scheduler in a separate thread
    scheduler_thread = threading.Thread(target=background_scheduler, daemon=True)
    scheduler_thread.start()
    
    app.run(host="127.0.0.1", port=6397, debug=True)
