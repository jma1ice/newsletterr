import os, math, uuid, base64, smtplib, sqlite3, requests, time, threading, re, json, mimetypes, shutil, calendar, traceback, io
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv, set_key, find_dotenv
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.utils import make_msgid, formataddr
from flask import Flask, render_template, request, jsonify, Response, redirect, url_for
from pathlib import Path
from PIL import Image, ImageFilter, ImageEnhance
from playwright.sync_api import sync_playwright
from plex_api_client import PlexAPI
from urllib.parse import quote_plus, urljoin

app = Flask(__name__)
app.jinja_env.globals["version"] = "v0.9.16"
app.jinja_env.globals["publish_date"] = "September 18, 2025"

def get_global_cache_status():
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

        if missing:
            freshness_class = 'cache-badge-missing'
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

app.jinja_env.globals["get_cache_status"] = get_global_cache_status

def can_use_cached_data_for_preview(required_days):
    try:
        stats_info = get_cache_info('stats')
        graph_info = get_cache_info('graph_data')
        
        if not (stats_info.get('exists') and graph_info.get('exists')):
            return False, "Cache data missing"
        
        if not (stats_info.get('is_usable') and graph_info.get('is_usable')):
            return False, "Cache data too old"
        
        stats_params = stats_info.get('params', {})
        if 'time_range' in stats_params:
            try:
                cached_days = int(stats_params.get('time_range', 0))
            except (TypeError, ValueError):
                cached_days = 0
            if cached_days == required_days:
                return True, f"Using cached data ({cached_days} days exact match)"
            else:
                return False, f"Cached range ({cached_days} days) != requested ({required_days} days)"
        return False, f"No cached range metadata (need {required_days} days)"
    except Exception as e:
        return False, f"Error checking cache: {str(e)}"

CACHE_DURATION = 86400
CACHE_EXTENDED_DURATION = 86400 * 7
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
os.makedirs(ROOT / "env", exist_ok = True)
if os.path.exists(ROOT / ".env"):
    shutil.move(ROOT / ".env", ROOT / "env" / ".env")
ENV_PATH = find_dotenv(usecwd=True) or str(ROOT / "env" / ".env")
DATA_IMG_RE = re.compile(
    r'^data:(image/(png|jpeg|jpg|gif|webp));base64,([A-Za-z0-9+/=]+)$',
    re.IGNORECASE
)
_WORKERS_STARTED = False
_WORKERS_LOCK = threading.Lock()
_RENDER_LOCK = threading.Lock()

load_dotenv(ENV_PATH)

def start_background_workers():
    global _WORKERS_STARTED
    with _WORKERS_LOCK:
        if _WORKERS_STARTED:
            return
        threading.Thread(target=background_scheduler, daemon=True, name="scheduler").start()
        threading.Thread(target=_background_update_checker, daemon=True, name="update-checker").start()
        _WORKERS_STARTED = True
        print("Background workers started.")

def is_cache_valid(cache_key, strict=True):
    cache_entry = cache_storage.get(cache_key)
    if cache_entry and cache_entry['data'] is not None:
        age = time.time() - cache_entry['timestamp']
        duration = CACHE_DURATION if strict else CACHE_EXTENDED_DURATION
        return age < duration
    return False

def get_cached_data(cache_key, strict=True):
    if is_cache_valid(cache_key, strict):
        return cache_storage[cache_key]['data']
    return None

def set_cached_data(cache_key, data, params=None):
    cache_storage[cache_key] = {
        'data': data,
        'timestamp': time.time(),
        'params': params
    }

def get_cache_info(cache_key):
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
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_email TEXT,
            alias_email TEXT,
            reply_to_email TEXT,
            password TEXT,
            smtp_username TEXT,
            smtp_server TEXT,
            smtp_port INTEGER,
            smtp_protocol TEXT,
            server_name TEXT,
            plex_url TEXT,
            plex_token TEXT,
            tautulli_url TEXT,
            tautulli_api TEXT,
            conjurr_url TEXT,
            logo_filename TEXT DEFAULT 'Asset_94x.png',
            logo_width INTEGER DEFAULT 80,
            primary_color TEXT DEFAULT "#8acbd4",
            secondary_color TEXT DEFAULT "#222222",
            accent_color TEXT DEFAULT "#62a1a4",
            background_color TEXT DEFAULT "#333333",
            text_color TEXT DEFAULT "#62a1a4",
            email_theme TEXT DEFAULT "newsletterr_blue",
            from_name TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            emails TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
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

    try:
        cursor.execute("PRAGMA table_info(email_history)")
        cols = [r[1] for r in cursor.fetchall()]
        if 'template_name' not in cols:
            cursor.execute("ALTER TABLE email_history ADD COLUMN template_name TEXT")
    except Exception as _e:
        print(f"Warning: could not ensure template_name column exists: {_e}")
    
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
    
    cursor.execute("PRAGMA table_info(email_schedules)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'send_time' not in columns:
        print("Adding send_time column to email_schedules table...")
        cursor.execute("ALTER TABLE email_schedules ADD COLUMN send_time TEXT DEFAULT '09:00'")
        conn.commit()
    
    if 'date_range' not in columns:
        print("Adding date_range column to email_schedules table...")
        cursor.execute("ALTER TABLE email_schedules ADD COLUMN date_range INTEGER DEFAULT 7")
        conn.commit()
    
    cursor.execute("PRAGMA table_info(settings)")
    settings_columns = [column[1] for column in cursor.fetchall()]
    if 'smtp_username' not in settings_columns:
        print("Adding smtp_username column to settings table...")
        cursor.execute("ALTER TABLE settings ADD COLUMN smtp_username TEXT")
        conn.commit()

    if 'smtp_protocol' not in settings_columns:
        print("Adding smtp_protocol column to settings table...")
        cursor.execute("ALTER TABLE settings ADD COLUMN smtp_protocol TEXT")
        conn.commit()

    if 'reply_to_email' not in settings_columns:
        print("Adding reply_to_email column to settings table...")
        cursor.execute("ALTER TABLE settings ADD COLUMN reply_to_email TEXT")
        conn.commit()

    cursor.execute("PRAGMA table_info(settings)")
    columns = [column[1] for column in cursor.fetchall()]
    theme_columns = [
        ('primary_color', 'TEXT DEFAULT "#8acbd4"'),
        ('secondary_color', 'TEXT DEFAULT "#222222"'),
        ('accent_color', 'TEXT DEFAULT "#62a1a4"'),
        ('background_color', 'TEXT DEFAULT "#333333"'),
        ('text_color', 'TEXT DEFAULT "#62a1a4"'),
        ('email_theme', 'TEXT DEFAULT "newsletterr_blue"')
    ]
    for col_name, col_def in theme_columns:
        if col_name not in columns:
            print(f"Adding {col_name} column to settings table...")
            cursor.execute(f'ALTER TABLE settings ADD COLUMN {col_name} {col_def}')
            conn.commit()

    if 'from_name' not in settings_columns:
        print("Adding from_name column to settings table...")
        cursor.execute("ALTER TABLE settings ADD COLUMN from_name TEXT")
        conn.commit()
    
    conn.close()

def get_theme_settings():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT primary_color, secondary_color, accent_color, background_color, text_color, email_theme
            FROM settings WHERE id = 1
        """)
        row = cursor.fetchone()
        
        if row:
            return {
                'primary_color': row[0] or '#8acbd4',
                'secondary_color': row[1] or '#222222',
                'accent_color': row[2] or '#62a1a4',
                'background_color': row[3] or '#333333',
                'text_color': row[4] or '#62a1a4',
                'email_theme': row[5] or 'newsletterr_blue'
            }
    except Exception as e:
        print(f"Error getting theme settings: {e}")
    finally:
        conn.close()
    
    return {
        'primary_color': '#8acbd4',
        'secondary_color': '#222222',
        'accent_color': '#62a1a4',
        'background_color': '#333333',
        'text_color': '#62a1a4',
        'email_theme': 'newsletterr_blue'
    }

def get_email_theme_colors():
    theme_settings = get_theme_settings()
    
    return {
        'background': theme_settings['background_color'],
        'text': theme_settings['text_color'],
        'primary': theme_settings['primary_color'],
        'secondary': theme_settings['secondary_color'],
        'accent': theme_settings['accent_color'],
        'card_bg': '#2d2d2d',
        'border': '#404040',
        'muted_text': '#cccccc'
    }

def build_email_css_from_theme(theme_colors, logo_width):
    return f"""
        <style>
            @import url(https://fonts.googleapis.com/css?family=IBM+Plex+Sans:400,700&display=swap);
            
            body {{
                margin: 0 !important;
                padding: 0 !important;
                font-family: 'IBM Plex Sans' !important;
                background-color: {theme_colors['background']} !important;
                line-height: 1.6 !important;
                color: {theme_colors['text']} !important;
                -webkit-text-size-adjust: 100% !important;
                -ms-text-size-adjust: 100% !important;
            }}
            
            table, td {{
                border-collapse: collapse !important;
                mso-table-lspace: 0pt !important;
                mso-table-rspace: 0pt !important;
            }}
            
            img {{
                border: 0 !important;
                height: auto !important;
                line-height: 100% !important;
                outline: none !important;
                text-decoration: none !important;
                -ms-interpolation-mode: bicubic !important;
            }}
            
            .ReadMsgBody {{ width: 100% !important; }}
            .ExternalClass {{ width: 100% !important; }}
            .ExternalClass * {{ line-height: 100% !important; }}

            @media only screen and (max-width: 8) {{
                .email-container {{
                    width: 100% !important;
                    max-width: 100% !important;
                    margin: 0 !important;
                }}
                
                .email-logo {{
                    max-width: 60px !important;
                    width: 60px !important;
                }}
                
                .grid-table {{
                    width: 100% !important;
                }}
                
                .grid-cell {{
                    width: 50% !important;
                    display: inline-block !important;
                    vertical-align: top !important;
                }}
                
                .card-container {{
                    max-width: 150px !important;
                    margin: 0 auto 10px auto !important;
                }}
            }}
            
            @media only screen and (max-device-width: 8) {{
                .email-logo {{
                    max-width: 60px !important;
                    height: auto !important;
                }}
            }}
            
            .email-container {{
                max-width: 800px !important;
                width: 100% !important;
            }}
            
            .email-logo {{
                max-width: {logo_width}px !important;
                width: auto !important;
                height: auto !important;
            }}
        </style>
    """

def migrate_data_from_separate_dbs():
    separate_dbs = [
        os.path.join("database", "email_lists.db"),
        os.path.join("database", "email_templates.db"), 
        os.path.join("database", "email_history.db"),
        os.path.join("database", "schedules.db")
    ]
    
    has_separate_data = any(os.path.exists(db_path) for db_path in separate_dbs)
    
    if not has_separate_data:
        return
    
    print("Migrating data from separate database files to unified database...")
    
    unified_conn = sqlite3.connect(DB_PATH)
    unified_cursor = unified_conn.cursor()
    
    try:
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, emails FROM email_lists ORDER BY name")
    lists = cursor.fetchall()
    conn.close()
    return [{'id': row[0], 'name': row[1], 'emails': row[2]} for row in lists]

def save_email_list(name, emails):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO email_lists (name, emails) VALUES (?, ?)", (name, emails))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def delete_email_list(list_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM email_lists WHERE id = ?", (list_id,))
    conn.commit()
    conn.close()

def get_email_schedules():
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
        next_send_formatted = None
        if schedule[8]:
            try:
                next_dt = datetime.fromisoformat(schedule[8])
                weekday = next_dt.strftime('%A')
                month_abbr = MONTH_ABBR_PERIOD[next_dt.month - 1]
                next_send_formatted = f"{weekday} {month_abbr} {next_dt.day}, {next_dt.year}  {next_dt.strftime('%H:%M')}"
            except Exception:
                next_send_formatted = schedule[8]

        last_sent_formatted = None
        if schedule[7]:
            try:
                last_dt = datetime.fromisoformat(schedule[7])
                weekday = last_dt.strftime('%A')
                month_abbr = MONTH_ABBR_PERIOD[last_dt.month - 1]
                last_sent_formatted = f"{weekday} {month_abbr} {last_dt.day}, {last_dt.year}  {last_dt.strftime('%H:%M')}"
            except Exception:
                last_sent_formatted = schedule[7]

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
            'start_date': start_date_raw,
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
        
    else:
        next_date = base_date + timedelta(days=1)
    
    next_date = next_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return next_date

def create_email_schedule(name, email_list_id, template_id, frequency, start_date, send_time='09:00', date_range=7):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM email_schedules WHERE id = ?", (schedule_id,))
    conn.commit()
    conn.close()

def toggle_schedule_status(schedule_id, is_active):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE email_schedules SET is_active = ? WHERE id = ?", (is_active, schedule_id))
    conn.commit()
    conn.close()

def update_schedule_last_sent(schedule_id):
    conn = sqlite3.connect(DB_PATH)
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

def background_scheduler():
    print("Background scheduler started...")
    last_cache_refresh = 0
    
    while True:
        try:
            now = datetime.now()
            current_time = time.time()
            
            if current_time - last_cache_refresh > 86400:
                print(f"Daily cache refresh triggered at {now.isoformat()}")
                refresh_daily_cache()
                last_cache_refresh = current_time
            
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, name, next_send, is_active FROM email_schedules")
            all_schedules = cursor.fetchall()
            print(f"Scheduler check at {now.isoformat()}")
            print(f"Found {len(all_schedules)} total schedules:")
            for sched in all_schedules:
                print(f"  - ID {sched[0]}: {sched[1]}, next_send: {sched[2]}, active: {sched[3]}")
            
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
        
        time.sleep(60)

def refresh_daily_cache():
    try:
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
        
        time_range = "30"
        count = "10"
        
        stats_info = get_cache_info('stats')
        if stats_info['exists'] and stats_info['params']:
            time_range = stats_info['params'].get('time_range', time_range)
            count = stats_info['params'].get('count', count)
        
        print(f"Refreshing cache with time_range: {time_range}, count: {count}")
        
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
            { 'command': 'movie' },
            { 'command': 'show' },
            { 'command' : 'artist' },
            { 'command' : 'live' },
        ]
        
        cache_params = {
            'time_range': time_range,
            'count': count,
            'url': tautulli_base_url,
            'timestamp': time.time(),
            'refresh_type': 'daily_auto'
        }
        
        error = None
        
        stats, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', error, time_range)
        if stats:
            set_cached_data('stats', stats, cache_params)
            print("✓ Stats cache refreshed")
        
        users, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_users', 'Users', error)
        user_list = []
        if users:
            user_list = [
                u
                for u in users
                if u.get('email') != None and u.get('email') != '' and u.get('is_active')
            ]
        if user_list:
            set_cached_data('users', user_list, cache_params)
            print("✓ Users cache refreshed")
        
        graph_data = []
        for command in graph_commands:
            gd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], error, time_range)
            if gd:
                graph_data.append(gd)
        
        if graph_data:
            set_cached_data('graph_data', graph_data, cache_params)
            print("✓ Graph data cache refreshed")
        
        libraries, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_library_names', None, None, "10")
        library_section_ids = {}
        for library in libraries:
            library_section_ids[f"{library['section_id']}"] = library["section_name"]

        recent_data = []
        for section_id in library_section_ids.keys():
            rd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_recently_added', section_id, error, count)
            if rd:
                for item in rd['recently_added']:
                    item['library_name'] = library_section_ids[section_id]
                recent_data.append(rd)
        
        if recent_data:
            set_cached_data('recent_data', recent_data, cache_params)
            print("✓ Recent data cache refreshed")
        
        print("Daily cache refresh completed successfully")
        
    except Exception as e:
        print(f"Error in daily cache refresh: {e}")

def capture_chart_images_via_headless(schedule_id: int, base: str, theme: str) -> dict:
    url = f"{base}/scheduling/{schedule_id}/preview-page?schedule_id={schedule_id}"
    
    with _RENDER_LOCK:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                color_scheme="dark" if theme == "dark" else "light"
            )
            page = context.new_page()
            page.goto(url, wait_until="load")
            
            try:
                page.wait_for_function("typeof loadPreview === 'function'", timeout=30_000)
                page.evaluate("loadPreview()")
                page.wait_for_function("typeof Highcharts !== 'undefined' && Highcharts.charts && Highcharts.charts.filter(Boolean).length > 0", timeout=60_000)
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"Error waiting for charts to load: {e}")

            selected_items = page.evaluate("selectedItems || []")
            chart_images = {}
            
            for item in selected_items:
                if item.get('type') == 'graph':
                    chart_id = item.get('id')
                    chart_name = item.get('name', 'Chart')
                    
                    print(f"Processing chart: {chart_id}")
                    
                    try:
                        page.evaluate(f"""
                            (() => {{
                                const element = document.getElementById('{chart_id}');
                                if (element) {{
                                    element.classList.remove('d-none');
                                    element.style.display = 'block';
                                    element.style.visibility = 'visible';
                                    element.style.opacity = '1';
                                    element.style.position = 'static';
                                    element.style.zIndex = '1';
                                    
                                    let parent = element.parentElement;
                                    while (parent && parent !== document.body) {{
                                        parent.style.display = 'block';
                                        parent.style.visibility = 'visible';
                                        parent.style.opacity = '1';
                                        parent = parent.parentElement;
                                    }}
                                    
                                    console.log('Made element visible:', '{chart_id}');
                                    return true;
                                }}
                                return false;
                            }})()
                        """)
                        
                        page.wait_for_timeout(1000)
                        
                        is_visible = page.evaluate(f"""
                            (() => {{
                                const element = document.getElementById('{chart_id}');
                                if (!element) return false;
                                const rect = element.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0;
                            }})()
                        """)
                        
                        print(f"Element #{chart_id} visible after adjustment: {is_visible}")
                        
                        if is_visible:
                            chart_element = page.locator(f"#{chart_id}")
                            screenshot_bytes = chart_element.screenshot(type='png', timeout=10000)
                            
                            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                            data_url = f"data:image/png;base64,{screenshot_b64}"
                            
                            chart_images[chart_id] = {
                                'name': chart_name,
                                'dataUrl': data_url
                            }
                            
                            print(f"Successfully captured screenshot for chart: {chart_id}")
                        else:
                            print(f"Chart element #{chart_id} still not visible after adjustments")
                        
                    except Exception as e:
                        print(f"Error capturing screenshot for chart {chart_id}: {e}")

            context.close()
            browser.close()
            
            print(f"Total chart images captured: {len(chart_images)}")
            return chart_images

def group_recipients_by_user(to_emails_list, user_dict):
    email_to_user = { (v or '').strip().lower(): k for k, v in (user_dict or {}).items() if v }
    groups = defaultdict(list)
    for email in (to_emails_list or []):
        key = email_to_user.get((email or '').strip().lower())
        groups[key].append(email)
    return groups

def send_scheduled_email(schedule_id, email_list_id, template_id):
    return send_scheduled_email_with_cids(schedule_id, email_list_id, template_id)

def run_tautulli_command(base_url, api_key, command, section_id, error, time_range='30'):
    out_data = None
    
    if command == 'get_users' or command == 'get_library_names':
        api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}"
    elif command == 'get_recently_added':
        api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}&count={time_range}&section_id={section_id}"
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
            print(f"Tautulli API Error: {data.get('response', {}).get('message', 'Unknown error')}")
            if error == None:
                error = f"Tautulli API Error: {data.get('response', {}).get('message', 'Unknown error')}"
            else:
                if "Multiple Tautulli API calls failed" not in error:
                    error = "Multiple Tautulli API calls failed"
    except requests.exceptions.RequestException as e:
        print(f"Tautulli Connection Error: {str(e)}")
        if error == None:
            error = f"Tautulli Connection Error: {str(e)}"
        else:
            if "Multiple Tautulli API calls failed" not in error:
                error = "Multiple Tautulli API calls failed"

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

def get_stat_headers(title):
    """Updated to match the exact logic from the dashboard template"""
    if title == "Most Watched Movies" or title == "Most Watched TV Shows":
        return ["Title", "Year", "Plays", "Hours Played", "Rating"]
    elif title == "Most Popular Movies" or title == "Most Popular TV Shows":
        return ["Title", "Year", "Plays", "Users", "Rating"]
    elif title == "Most Played Artists":
        return ["Author", "Year", "Plays", "Hours Played"]
    elif title == "Most Popular Artists":
        return ["Author", "Year", "Plays", "Users"]
    elif title == "Recently Watched":
        return ["Title", "Year", "Rating"]
    elif title == "Most Active Libraries":
        return ["Library", "Plays", "Hours Played"]
    elif title == "Most Active Users":
        return ["Username", "Plays", "Hours Played"]
    elif title == "Most Active Platforms":
        return ["Platform", "Plays", "Hours Played"]
    elif title == "Most Concurrent Streams":
        return ["Category", "Count"]
    else:
        return ["Title", "Value"]

def get_stat_cells(title, row):
    cells = []
    
    if title == "Most Active Libraries":
        cells.append(row.get('section_name', ''))
    elif title == "Most Active Users":
        cells.append(row.get('user', ''))
    elif title == "Most Active Platforms":
        cells.append(row.get('platform', ''))
    else:
        cells.append(row.get('title', ''))
    
    skip_year_stats = ["Most Active Libraries", "Most Active Users", "Most Active Platforms", "Most Concurrent Streams"]
    if title not in skip_year_stats:
        cells.append(row.get('year', ''))
    
    if "Recently" not in title and "Concurrent" not in title:
        cells.append(row.get('total_plays', 0))
    
    hours_stats = ["Most Watched Movies", "Most Watched TV Shows", "Most Played Artists", "Most Active Libraries", "Most Active Users", "Most Active Platforms"]
    users_stats = ["Most Popular Movies", "Most Popular TV Shows", "Most Popular Artists"]
    
    if title in hours_stats:
        hours = round(row.get('total_duration', 0) / 3600) if row.get('total_duration') else 0
        cells.append(int(hours))
    elif title in users_stats:
        cells.append(row.get('users_watched', ''))
    
    skip_rating_stats = ["Most Active Libraries", "Most Played Artists", "Most Popular Artists", "Most Active Users", "Most Active Platforms", "Most Concurrent Streams"]
    if title not in skip_rating_stats:
        cells.append(row.get('content_rating', ''))
    
    if title == "Most Concurrent Streams":
        cells.append(row.get('count', 0))
    
    return cells

def fetch_tautulli_data_for_email(tautulli_base_url, tautulli_api_key, date_range, server_name):
    data = {
        'settings': {'server_name': server_name},
        'stats': [],
        'graph_data': [],
        'recent_data': [],
        'graph_commands': []
    }
    
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
    
    try:
        stats, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', None, str(date_range))
        if stats:
            data['stats'] = stats
        
        graph_data = []
        for command in graph_commands:
            try:
                gd, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], None, str(date_range))
                graph_data.append(gd if gd is not None else {})
            except Exception as e:
                graph_data.append({})
                print(f"Error fetching graph data for {command['name']}: {e}")
        
        data['graph_data'] = graph_data
        data['graph_commands'] = graph_commands

        libraries, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_library_names', None, None, "10")
        library_section_ids = {}
        for library in libraries:
            library_section_ids[f"{library['section_id']}"] = library["section_name"]
        
        for section_id in library_section_ids.keys():
            recent, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_recently_added', section_id, None, "10")
            if recent:
                for item in recent['recently_added']:
                    item['library_name'] = library_section_ids[section_id]
                data['recent_data'].append(recent)
                
        print(f"Fetched Tautulli data: {len(data['stats'])} stats, {len(data['graph_data'])} graphs, {len(data['recent_data'])} recent sections")
        
    except Exception as e:
        print(f"Error fetching Tautulli data: {e}")
    
    return data

def convert_html_to_plain_text(html_content):
    html_content = re.sub(r'<script.*?</script>', '', html_content, flags=re.DOTALL)
    html_content = re.sub(r'<style.*?</style>', '', html_content, flags=re.DOTALL)
    
    html_content = re.sub(r'<br\s*/?>', '\n', html_content)
    html_content = re.sub(r'</p>', '\n\n', html_content)
    html_content = re.sub(r'</div>', '\n', html_content)
    html_content = re.sub(r'<h[1-6][^>]*>', '\n\n', html_content)
    html_content = re.sub(r'</h[1-6]>', '\n', html_content)
    
    html_content = re.sub(r'<[^>]+>', '', html_content)
    
    html_content = re.sub(r'\n\s*\n', '\n\n', html_content)
    html_content = html_content.strip()
    
    return html_content

def fetch_and_attach_image(image_url, msg_root, cid_name, base_url=""):
    try:
        print(f"fetch_and_attach_image called with: {image_url}")
        if image_url.startswith('/'):
            full_url = urljoin(base_url or "http://127.0.0.1:6397", image_url)
        else:
            full_url = image_url
        
        print(f"Final URL to fetch: {full_url}")
        response = requests.get(full_url, timeout=10)
        print(f"Response status: {response.status_code}")
        response.raise_for_status()
        
        content_type = response.headers.get('Content-Type')
        print(f"Content-Type: {content_type}")
        if not content_type or not content_type.startswith('image/'):
            content_type = mimetypes.guess_type(full_url)[0] or 'image/png'
        
        subtype = content_type.split('/')[-1]
        if subtype == 'jpg':
            subtype = 'jpeg'
        
        cid = make_msgid(domain="newsletterr.local")[1:-1]
        
        img_part = MIMEImage(response.content, _subtype=subtype)
        img_part.add_header('Content-ID', f'<{cid}>')
        img_part.add_header('Content-Disposition', 'inline', filename=f'{cid_name}.{subtype}')
        msg_root.attach(img_part)
        
        print(f"Successfully attached image with CID: {cid}")
        return cid
        
    except Exception as e:
        print(f"Error processing image {image_url}: {e}")
        return None

def fetch_and_attach_blurred_image(image_url, msg_root, cid_name, base_url=""):
    try:
        if image_url.startswith('/'):
            full_url = urljoin(base_url or "http://127.0.0.1:6397", image_url)
        else:
            full_url = image_url
        
        response = requests.get(full_url, timeout=10)
        response.raise_for_status()
        
        image = Image.open(io.BytesIO(response.content))
        
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')
        
        blurred = image.filter(ImageFilter.GaussianBlur(radius=30))
        
        enhancer = ImageEnhance.Brightness(blurred)
        darkened = enhancer.enhance(0.7)
        
        img_bytes = io.BytesIO()
        darkened.save(img_bytes, format='JPEG', quality=85)
        img_bytes.seek(0)
        
        cid = make_msgid(domain="newsletterr.local")[1:-1]
        
        img_part = MIMEImage(img_bytes.getvalue(), _subtype='jpeg')
        img_part.add_header('Content-ID', f'<{cid}>')
        img_part.add_header('Content-Disposition', 'inline', filename=f'{cid_name}-blurred.jpg')
        msg_root.attach(img_part)
        
        return cid
        
    except Exception as e:
        print(f"Error processing blurred image {image_url}: {e}")
        return fetch_and_attach_image(image_url, msg_root, cid_name, base_url)

def build_stats_html_with_cid_background(stat_data, msg_root, theme_colors, base_url=""):
    if not stat_data or not stat_data.get('rows'):
        return ""
    
    title = stat_data.get('stat_title', 'Statistics')
    rows = stat_data['rows']
    
    background_cid = None
    if rows and (rows[0].get('art') or rows[0].get('grandparent_thumb')):
        artwork_path = rows[0].get('art') or rows[0].get('grandparent_thumb')
        if artwork_path:
            image_url = f"/proxy-art{artwork_path}" if not artwork_path.startswith('/proxy-art') else artwork_path
            background_cid = fetch_and_attach_blurred_image(
                image_url, 
                msg_root, 
                f"stat-bg-{len(msg_root.get_payload())}", 
                base_url
            )
    
    headers = get_stat_headers(title)
    header_cells = "".join([
        f'<th style="padding: 12px; background-color: rgba(52, 58, 64, 0.9); color: white; font-weight: bold; border: none; font-family: \'IBM Plex Sans\'; font-size: 14px; text-align: left;">{h}</th>' 
        for h in headers
    ])
    
    rows_html = ""
    for row in rows:
        cells = get_stat_cells(title, row)
        cells_html = "".join([
            f'<td style="padding: 12px; background-color: rgba(255, 255, 255, 0.5); color: #333; border-bottom: 1px solid rgba(222, 226, 230, 0.8); font-family: \'IBM Plex Sans\'; font-size: 14px;">{cell}</td>' 
            for cell in cells
        ])
        rows_html += f'<tr>{cells_html}</tr>'
    
    container_style = f"""
        margin: 20px 0;
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        border: 1px solid {theme_colors['border']};
        position: relative;
        font-family: 'IBM Plex Sans';
    """
    
    if background_cid:
        container_style += f"""
            background-image: url('cid:{background_cid}');
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
        """
    else:
        container_style += f"background-color: {theme_colors['card_bg']};"
    
    overlay = ""
    if background_cid:
        overlay = f"""
            <div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; 
                        background-color: rgba(0, 0, 0, 0.3); z-index: 0;"></div>
        """
    
    header_style = f"""
        background-color: {theme_colors['primary']};
        color: white;
        padding: 15px;
        text-align: center;
        font-weight: bold;
        font-size: 18px;
        font-family: 'IBM Plex Sans';
        margin: 0;
        position: relative;
        z-index: 2;
    """
    
    table_style = """
        width: 100%;
        border-collapse: collapse;
        position: relative;
        z-index: 2;
        font-family: 'IBM Plex Sans';
    """
    
    return f"""
        <div style="{container_style}">
            {overlay}
            <div style="position: relative; z-index: 1;">
                <div style="{header_style}">{title}</div>
                <table style="{table_style}">
                    <thead>
                        <tr>{header_cells}</tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </div>
    """

def build_recently_added_html_with_cids(recent_data, msg_root, theme_colors, library_filter=None, base_url=""):
    if not recent_data:
        return f"""
        <div style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans';">
            <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans';">No recently added items available.</p>
        </div>
        """
    
    items = []
    if isinstance(recent_data, list):
        for item in recent_data:
            if isinstance(item, dict) and 'recently_added' in item:
                items.extend(item['recently_added'])
            elif isinstance(item, dict) and 'title' in item:
                items.append(item)
    
    if library_filter:
        items = [item for item in items if library_filter.lower() in item.get('library_name', '').lower()]
    
    if not items:
        return f"""
        <div style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans';">
            <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans';">No recently added items found{f' for {library_filter}' if library_filter else ''}.</p>
        </div>
        """
    
    items_html = ""
    items_per_row = 5
    
    for i in range(0, len(items), items_per_row):
        row_items = items[i:i + items_per_row]
        row_html = "<tr>"
        
        for j, item in enumerate(row_items):
            title = item.get('title', 'Unknown')
            year = item.get('year', '')
            library = item.get('library_name', '')
            summary = item.get('tagline') or item.get('summary', '')
            added_date = ""
            duration = ""
            
            poster_cid = None
            poster_candidates = [item.get('thumb'), item.get('art'), item.get('parent_thumb'), item.get('grandparent_thumb')]
            for candidate in poster_candidates:
                if candidate:
                    poster_url = f"/proxy-art{candidate}" if not candidate.startswith('/proxy-art') else candidate
                    poster_cid = fetch_and_attach_image(
                        poster_url, 
                        msg_root, 
                        f"recent-{i}-{j}", 
                        base_url
                    )
                    break
                        
            if item.get('added_at'):
                try:
                    timestamp = item['added_at']
                    if isinstance(timestamp, str) and timestamp.isdigit():
                        timestamp = int(timestamp)
                    
                    if isinstance(timestamp, (int, float)):
                        dt = datetime.fromtimestamp(timestamp)
                        added_date = dt.strftime('%m/%d/%Y')
                    else:
                        dt = datetime.fromisoformat(str(timestamp))
                        added_date = dt.strftime('%m/%d/%Y')
                except Exception as e:
                    if item.get('originally_available_at'):
                        try:
                            timestamp = item['originally_available_at']
                            if isinstance(timestamp, str) and timestamp.isdigit():
                                timestamp = int(timestamp)
                            
                            if isinstance(timestamp, (int, float)):
                                dt = datetime.fromtimestamp(timestamp)
                                added_date = dt.strftime('%m/%d/%Y')
                            else:
                                dt = datetime.fromisoformat(str(timestamp))
                                added_date = dt.strftime('%m/%d/%Y')
                        except Exception as e2:
                            added_date = ""
            
            if item.get('duration'):
                try:
                    ms = int(item['duration'])
                    s = ms // 1000
                    h = s // 3600
                    m = (s % 3600) // 60
                    duration = f"{h}h {m}m" if h else f"{m}m"
                except:
                    pass
            
            cell_style = f"""
                width: 20%;
                padding: 8px;
                vertical-align: top;
                font-family: 'IBM Plex Sans';
            """

            if poster_cid:
                poster_bg_url = f"cid:{poster_cid}"
                
                card_html = f"""
                    <div style="
                        background-color: {theme_colors['card_bg']};
                        border-radius: 12px;
                        overflow: hidden;
                        border: 1px solid {theme_colors['border']};
                        width: 124px;
                        margin: 0 auto;
                        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.6);
                    ">
                        <div style="
                            background-image: url('{poster_bg_url}');
                            background-size: cover;
                            background-position: center;
                            background-repeat: no-repeat;
                            height: 185px;
                            position: relative;
                            background-color: #f8f9fa;
                        ">
                            {f'''
                            <div style="
                                float: right;
                                background-color: rgba(0, 0, 0, 0.7);
                                color: white;
                                padding: 2px 8px;
                                border-radius: 12px;
                                font-size: 10px;
                                margin: 2px;
                                font-family: 'IBM Plex Sans';
                                line-height: 1;
                            ">{library}</div>
                            ''' if library else ''}
                            
                            {f'''
                            <div style="
                                float: right;
                                clear: right;
                                background-color: rgba(0, 0, 0, 0.6);
                                color: rgba(255, 255, 255, 0.9);
                                padding: 2px 6px;
                                border-radius: 4px;
                                font-size: 9px;
                                margin: 153px 2px 2px 2px;
                                font-family: 'IBM Plex Sans';
                                line-height: 1;
                            ">{added_date}</div>
                            ''' if added_date else ''}
                        </div>
                        
                        <div style="
                            padding: 12px;
                            background-color: {theme_colors['card_bg']};
                            color: {theme_colors['text']};
                        ">
                            <div style="
                                font-weight: bold;
                                font-size: 14px;
                                color: {theme_colors['text']};
                                margin-bottom: 4px;
                                line-height: 1.2;
                                font-family: 'IBM Plex Sans';
                            ">{title}</div>
                            
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['muted_text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans';
                            ">{' • '.join(filter(None, [str(year) if year else '', duration]))}</div>
                            
                            {f'''
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['text']};
                                opacity: 0.8;
                                line-height: 1.3;
                                font-family: 'IBM Plex Sans';
                            ">{summary[:100]}{'...' if len(summary) > 100 else ''}</div>
                            ''' if summary else ''}
                        </div>
                    </div>
                """
            else:
                card_html = f"""
                    <div style="
                        background-color: {theme_colors['card_bg']};
                        border-radius: 12px;
                        border: 1px solid {theme_colors['border']};
                        padding: 12px;
                        text-align: center;
                        max-width: 200px;
                        margin: 0 auto;
                        height: 300px;
                        display: table;
                    ">
                        <div style="display: table-cell; vertical-align: middle;">
                            <div style="
                                font-weight: bold;
                                font-size: 14px;
                                color: {theme_colors['text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans';
                            ">{title}</div>
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['muted_text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans';
                            ">{' • '.join(filter(None, [str(year) if year else '', duration, library, f'Added {added_date}' if added_date else '']))}</div>
                            {f'''
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['text']};
                                opacity: 0.8;
                                font-family: 'IBM Plex Sans';
                            ">{summary[:100]}{'...' if len(summary) > 100 else ''}</div>
                            ''' if summary else ''}
                        </div>
                    </div>
                """
            
            row_html += f'<td style="{cell_style}">{card_html}</td>'
        
        while len(row_items) < items_per_row:
            row_html += f'<td style="width: 20%; padding: 8px;"></td>'
            row_items.append(None)
        
        row_html += "</tr>"
        items_html += row_html
    
    container_style = f"""
        background-color: {theme_colors['card_bg']};
        padding: 20px;
        border-radius: 8px;
        margin: 20px 0;
        border: 1px solid {theme_colors['border']};
        font-family: 'IBM Plex Sans';
    """
    
    title_style = f"""
        text-align: center;
        color: {theme_colors['text']};
        margin: 0 0 20px 0;
        font-size: 24px;
        font-weight: bold;
        font-family: 'IBM Plex Sans';
    """
    
    table_style = """
        width: 100%;
        border-collapse: collapse;
        margin: 0;
        padding: 0;
    """
    
    return f"""
        <div style="{container_style}">
            <h2 style="{title_style}">Recently Added{f' - {library_filter}' if library_filter else ''}</h2>
            <table style="{table_style}">
                {items_html}
            </table>
        </div>
    """

def build_recommendations_html_with_cids(recs_data, msg_root, theme_colors, user_emails=None, base_url=""):
    if not recs_data:
        return ""
    
    html_sections = []
    
    for user_id, user_recs in recs_data.items():
        if user_emails and user_id not in user_emails:
            continue
            
        user_email = user_emails.get(user_id, user_id) if user_emails else user_id
        
        movies_html = build_recommendations_section_with_cids(
            user_recs.get('movie_posters', []),
            user_recs.get('movie_posters_unavailable', []),
            "Recommended Movies",
            msg_root,
            f"recs-movies-{user_id}",
            theme_colors,
            base_url
        )
        
        shows_html = build_recommendations_section_with_cids(
            user_recs.get('show_posters', []),
            user_recs.get('show_posters_unavailable', []),
            "Recommended TV Shows",
            msg_root,
            f"recs-shows-{user_id}",
            theme_colors,
            base_url
        )
        
        if movies_html or shows_html:
            container_style = f"""
                margin: 30px 0;
                padding: 20px;
                background-color: {theme_colors['card_bg']};
                border-radius: 8px;
                border: 1px solid {theme_colors['border']};
                font-family: 'IBM Plex Sans';
            """
            
            user_title_style = f"""
                text-align: center;
                color: {theme_colors['text']};
                margin: 0 0 20px 0;
                font-size: 24px;
                font-weight: bold;
                font-family: 'IBM Plex Sans';
            """
            
            user_section = f"""
                <div style="{container_style}" data-recs-user="{user_id}">
                    <h2 style="{user_title_style}">Recommendations for {user_email}</h2>
                    {movies_html}
                    {shows_html}
                </div>
            """
            html_sections.append(user_section)
    
    return '\n'.join(html_sections)

def build_recommendations_section_with_cids(available_items, unavailable_items, title, msg_root, section_prefix, theme_colors, base_url=""):
    if not available_items and not unavailable_items:
        return ""
    
    all_items = available_items + unavailable_items
    items_per_row = 5
    
    rows_html = ""
    for i in range(0, len(all_items), items_per_row):
        row_items = all_items[i:i + items_per_row]
        row_html = "<tr>"
        
        for j, item in enumerate(row_items):
            is_unavailable = (i + j) >= len(available_items)
            
            poster_cid = None
            if item.get('url'):
                poster_cid = fetch_and_attach_image(
                    f"/proxy-img?u={item['url']}", 
                    msg_root, 
                    f"{section_prefix}-{i}-{j}", 
                    base_url
                )
            
            title_text = item.get('title', 'Unknown')
            year = item.get('year', '')
            vote = item.get('vote', '')
            href = item.get('href', '#')
            overview = item.get('overview', '')[:100] + "..." if item.get('overview') else ""
            runtime = item.get('runtime', '')
            
            vote_text = f"★ {vote:.1f}" if isinstance(vote, (int, float)) and vote > 0 else ""
            
            cell_style = f"""
                width: 20%;
                padding: 6px;
                vertical-align: top;
                font-family: 'IBM Plex Sans';
                {'opacity: 0.7; filter: grayscale(30%);' if is_unavailable else ''}
            """

            if poster_cid:
                poster_bg_url = f"cid:{poster_cid}"
                
                card_content = f"""
                    <div style="
                        background-color: {theme_colors['card_bg']};
                        border-radius: 12px;
                        overflow: hidden;
                        border: 1px solid {theme_colors['border']};
                        width: 125px;
                        margin: 0 auto;
                        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                    ">
                        <div style="
                            background-image: url('{poster_bg_url}');
                            background-size: cover;
                            background-position: center;
                            background-repeat: no-repeat;
                            height: 185px;
                            position: relative;
                            background-color: #f8f9fa;
                        ">
                            {f'''
                            <div style="
                                float: left;
                                background-color: rgba(0, 0, 0, 0.7);
                                color: white;
                                padding: 2px 6px;
                                border-radius: 4px;
                                font-size: 9px;
                                margin: 4px;
                                font-family: 'IBM Plex Sans';
                                line-height: 1;
                            ">{year} {vote_text}</div>
                            ''' if year or vote_text else ''}
                            
                            {'''
                            <div style="
                                float: left;
                                background-color: rgba(255, 0, 0, 0.8);
                                color: white;
                                padding: 2px 6px;
                                border-radius: 4px;
                                font-size: 9px;
                                margin: 0px 10px 0px 4px;
                                font-family: 'IBM Plex Sans';
                                line-height: 1;
                            ">Unavailable</div>
                            ''' if is_unavailable else ''}
                            
                            <div style="
                                padding: 8px;
                                height: 60px;
                            ">
                                <div style="
                                    font-weight: bold;
                                    font-size: 12px;
                                    color: white;
                                    line-height: 1.2;
                                    font-family: 'IBM Plex Sans';
                                    margin-top: 132px;
                                ">{title_text}</div>
                                {f'''
                                <div style="
                                    font-size: 10px;
                                    color: rgba(255, 255, 255, 0.8);
                                    margin-top: 2px;
                                    font-family: 'IBM Plex Sans';
                                ">{runtime}</div>
                                ''' if runtime else ''}
                            </div>
                        </div>
                        
                        {f'''
                        <div style="
                            padding: 8px;
                            background-color: {theme_colors['card_bg']};
                            color: {theme_colors['text']};
                            font-size: 10px;
                            line-height: 1.3;
                            font-family: 'IBM Plex Sans';
                            border-top: 1px solid {theme_colors['border']};
                        ">
                            {overview[:80]}{'...' if len(overview) > 80 else ''}
                        </div>
                        ''' if overview else ''}
                    </div>
                """
                
                if href != '#':
                    card_html = f'<a href="{href}" style="text-decoration: none; color: inherit; display: block;" target="_blank">{card_content}</a>'
                else:
                    card_html = card_content
                    
            else:
                card_html = f"""
                    <div style="
                        background-color: {theme_colors['card_bg']};
                        border-radius: 12px;
                        border: 1px solid {theme_colors['border']};
                        padding: 12px;
                        text-align: center;
                        max-width: 200px;
                        margin: 0 auto;
                        height: 300px;
                        display: table;
                    ">
                        <div style="display: table-cell; vertical-align: middle;">
                            <div style="
                                font-weight: bold;
                                font-size: 12px;
                                color: {theme_colors['text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans';
                            ">{title_text}</div>
                            <div style="
                                font-size: 10px;
                                color: {theme_colors['muted_text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans';
                            ">{' • '.join(filter(None, [str(year) if year else '', vote_text, runtime, 'Unavailable' if is_unavailable else '']))}</div>
                            {f'''
                            <div style="
                                font-size: 10px;
                                color: {theme_colors['text']};
                                opacity: 0.8;
                                font-family: 'IBM Plex Sans';
                                line-height: 1.3;
                            ">{overview[:100]}{'...' if len(overview) > 100 else ''}</div>
                            ''' if overview else ''}
                        </div>
                    </div>
                """
            
            row_html += f'<td style="{cell_style}">{card_html}</td>'
        
        while len(row_items) < items_per_row:
            row_html += f'<td style="width: 20%; padding: 6px;"></td>'
            row_items.append(None)
        
        row_html += "</tr>"
        rows_html += row_html
    
    section_title_style = f"""
        color: {theme_colors['text']};
        margin: 0 0 15px 0;
        font-size: 20px;
        font-weight: bold;
        font-family: 'IBM Plex Sans';
    """
    
    table_style = """
        width: 100%;
        border-collapse: collapse;
        padding: 0;
        margin: 0;
    """
    
    return f"""
        <div style="margin: 20px 0;">
            <h3 style="{section_title_style}">{title}</h3>
            <table style="{table_style}">
                {rows_html}
            </table>
        </div>
    """

def build_collections_html_with_cids(collections_data, title, msg_root, theme_colors, base_url=""):
    """Build HTML for collections with embedded images using CIDs"""
    if not collections_data:
        return ""
    
    section_title_style = f"""
        color: {theme_colors['text_color']};
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-size: 24px;
        font-weight: 700;
        margin: 30px 0 20px 0;
        padding-bottom: 10px;
        border-bottom: 2px solid {theme_colors['accent_color']};
        text-align: left;
        line-height: 1.2;
    """
    
    collections_html = []
    for collection in collections_data:
        # Debug: Print collection data
        print(f"Processing collection: {collection.get('title', 'Unknown')}")
        print(f"Collection subtype: {collection.get('subtype', 'Unknown')}")
        print(f"Collection thumb URL: {collection.get('thumb', 'No thumb')}")
        print(f"Collection art URL: {collection.get('art', 'No art')}")
        
        # Attach collection poster image
        poster_url = collection.get('thumb', '')
        collection_cid = None
        if poster_url:
            print(f"Attempting to fetch thumb image: {poster_url}")
            # Check if it's already a full URL or needs proxy-art prefix
            if poster_url.startswith('http'):
                # It's already a full URL from the API
                collection_cid = fetch_and_attach_image(poster_url, msg_root, f"collection_{hash(poster_url)}", base_url)
            else:
                # It's a relative path, use proxy-art
                full_poster_url = f"/proxy-art{poster_url if poster_url.startswith('/') else '/' + poster_url}"
                collection_cid = fetch_and_attach_image(full_poster_url, msg_root, f"collection_{hash(poster_url)}", base_url)
            print(f"Thumb CID result: {collection_cid}")
        
        if not collection_cid:
            print("No thumb CID, trying art URL...")
            art_url = collection.get('art', '')
            if art_url:
                print(f"Attempting to fetch art image: {art_url}")
                if art_url.startswith('http'):
                    collection_cid = fetch_and_attach_image(art_url, msg_root, f"collection_{hash(art_url)}", base_url)
                else:
                    full_art_url = f"/proxy-art{art_url if art_url.startswith('/') else '/' + art_url}"
                    collection_cid = fetch_and_attach_image(full_art_url, msg_root, f"collection_{hash(art_url)}", base_url)
                print(f"Art CID result: {collection_cid}")
        
        poster_src = f"cid:{collection_cid}" if collection_cid else "/static/img/Asset_94x.png"
        print(f"Final poster src for {collection.get('title')}: {poster_src}")
        print("---")
        
        # Collection details
        collection_title = collection.get('title', 'Unknown Collection')
        count = collection.get('childCount', 0)
        subtype = collection.get('subtype', 'unknown')
        type_icon = '🎬' if subtype == 'movie' else '📺'
        
        # Disable links for now - Plex Web URLs are complex and server-specific
        collection_url = "#"
        
        collection_html = f"""
            <td style="width: 33.33%; vertical-align: top; padding: 12px;">
                <div style="
                    position: relative;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
                    background: #1a1a1a;
                    transition: transform 0.2s ease;
                ">
                    <img src="{poster_src}" 
                         alt="{collection_title}"
                         style="
                             width: 100%;
                             height: 400px;
                             object-fit: cover;
                             display: block;
                             aspect-ratio: 2/3;
                         ">
                    <div style="
                        position: absolute;
                        top: 12px;
                        right: 12px;
                        background: rgba(0, 0, 0, 0.8);
                        color: white;
                        padding: 6px 12px;
                        border-radius: 4px;
                        font-size: 14px;
                        font-weight: bold;
                        font-family: 'Segoe UI', Arial, sans-serif;
                    ">
                        {type_icon} {count}
                    </div>
                    <div style="
                        position: absolute;
                        bottom: 0;
                        left: 0;
                        right: 0;
                        padding: 12px;
                        background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent);
                    ">
                        <div style="
                            font-weight: bold;
                            font-size: 14px;
                            color: white;
                            line-height: 1.2;
                            font-family: 'Segoe UI', Arial, sans-serif;
                            overflow: hidden;
                            text-overflow: ellipsis;
                            display: -webkit-box;
                            -webkit-line-clamp: 2;
                            -webkit-box-orient: vertical;
                        ">
                            {collection_title}
                        </div>
                    </div>
                </div>
            </td>
        """
        collections_html.append(collection_html)
    
    # Split into rows of 3 collections each
    rows_html = []
    for i in range(0, len(collections_html), 3):
        row_collections = collections_html[i:i+3]
        # Pad row with empty cells if needed
        while len(row_collections) < 3:
            row_collections.append('<td style="width: 33.33%; padding: 12px;"></td>')
        
        row_html = f"""
            <tr>
                {''.join(row_collections)}
            </tr>
        """
        rows_html.append(row_html)
    
    return f"""
        <div style="margin: 20px 0;">
            <h3 style="{section_title_style}">{title}</h3>
            <table style="
                width: 100%;
                border-collapse: collapse;
                margin: 0;
                padding: 0;
            ">
                {''.join(rows_html)}
            </table>
        </div>
    """

def attach_logo_image(msg_root, logo_filename, base_url=""):
    logo_url = f"/static/img/{logo_filename}"
    return fetch_and_attach_image(logo_url, msg_root, "logo", base_url)

def build_email_html_with_all_cids(template_data, tautulli_data, msg_root, recommendations_data=None, user_dict=None, base_url="", target_user_key=None, is_scheduled=False):
    selected_items = json.loads(template_data.get('selected_items', '[]'))
    email_text = template_data.get('email_text', '')
    subject = template_data.get('subject', '')
    server_name = tautulli_data.get('settings', {}).get('server_name', 'Plex Server')
    logo_filename = tautulli_data.get('settings', {}).get('logo_filename', 'Asset_94x.png')
    logo_width = tautulli_data.get('settings', {}).get('logo_width', 80)
    
    theme_colors = get_email_theme_colors()
    
    logo_cid = attach_logo_image(msg_root, logo_filename, base_url)
    logo_src = f"cid:{logo_cid}" if logo_cid else f"/static/img/{logo_filename}"
    
    content_html = ""
    
    if email_text.strip():
        content_html += build_text_block_html(email_text, 'textblock', theme_colors)
    
    for item in selected_items:
        item_type = item.get('type', '')
        
        if item_type in ['textblock', 'titleblock', 'headerblock']:
            content = item.get('content', '').strip()
            if content:
                content_html += build_text_block_html(content, item_type, theme_colors)
        
        elif item_type == 'stat':
            stat_index = int(item['id'].split('-')[1])
            if stat_index < len(tautulli_data.get('stats', [])):
                stat_data = tautulli_data['stats'][stat_index]
                content_html += build_stats_html_with_cid_background(stat_data, msg_root, theme_colors, base_url)
        
        elif item_type == 'graph':
            content_html += build_graph_html_with_frontend_image(item, msg_root)
        
        elif item_type == 'ra':
            library_filter = item.get('raLibrary')
            recent_data = tautulli_data.get('recent_data', [])
            content_html += build_recently_added_html_with_cids(recent_data, msg_root, theme_colors, library_filter, base_url)
        
        elif item_type == 'recs':
            if recommendations_data:
                if target_user_key:
                    if item.get('userKey') == str(target_user_key):
                        filtered_recommendations = {target_user_key: recommendations_data.get(target_user_key, {})}
                        filtered_user_dict = {target_user_key: user_dict.get(target_user_key, target_user_key)} if user_dict else {target_user_key: target_user_key}
                        content_html += build_recommendations_html_with_cids(filtered_recommendations, msg_root, theme_colors, filtered_user_dict, base_url)
                else:
                    content_html += build_recommendations_html_with_cids(recommendations_data, msg_root, theme_colors, user_dict, base_url)
        
        elif item_type == 'collection':
            collection_data = item.get('collection', {})
            if collection_data:
                collection_title = f"{collection_data.get('title', 'Unknown')} Collection"
                content_html += build_collections_html_with_cids([collection_data], collection_title, msg_root, theme_colors, base_url)
    
    return build_complete_email_html_with_cid_logo(content_html, server_name, subject, logo_src, logo_width, is_scheduled)

def build_complete_email_html_with_cid_logo(content_html, server_name, subject, logo_src, logo_width, is_scheduled=False):
    theme_colors = get_email_theme_colors()
    
    css = build_email_css_from_theme(theme_colors, logo_width)
    
    body_style = f"""
        margin: 0;
        padding: 0;
        font-family: 'IBM Plex Sans';
        background-color: {theme_colors['background']};
        line-height: 1.6;
        color: {theme_colors['text']};
        -webkit-text-size-adjust: 100%;
        -ms-text-size-adjust: 100%;
    """
    
    container_style = f"""
        width: 100%;
        max-width: 800px;
        margin: 0 auto;
        background-color: {theme_colors['card_bg']};
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
        border: 1px solid {theme_colors['border']};
        font-family: 'IBM Plex Sans', Arial;
    """
    
    header_style = f"""
        background: linear-gradient(135deg, {theme_colors['accent']} 0%, {theme_colors['primary']} 100%);
        color: white;
        padding: 30px 20px;
        text-align: center;
        font-family: 'IBM Plex Sans';
    """
    
    logo_style = f"""
        max-width: {logo_width}px;
        width: auto;
        height: auto;
        margin-bottom: 15px;
        border: 0;
        line-height: 100%;
        outline: none;
        text-decoration: none;
        display: block;
        margin-left: auto;
        margin-right: auto;
    """
    
    title_style = """
        font-size: 28px;
        font-weight: bold;
        margin: 0;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        font-family: 'IBM Plex Sans';
        color: white;
    """
    
    content_style = f"""
        padding: 20px 15px;
        color: {theme_colors['text']};
        background-color: {theme_colors['card_bg']};
        font-family: 'IBM Plex Sans';
    """
    
    footer_style = f"""
        background-color: {theme_colors['secondary']};
        padding: 20px;
        text-align: center;
        border-top: 3px solid {theme_colors['primary']};
        color: {theme_colors['muted_text']};
        font-size: 12px;
        font-family: 'IBM Plex Sans';
    """
    
    footer_link_style = f"""
        color: {theme_colors['accent']};
        text-decoration: none;
    """
    
    return f"""<!DOCTYPE html>
        <html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <meta http-equiv="X-UA-Compatible" content="IE=edge">
                <meta name="x-apple-disable-message-reformatting">
                <meta name="format-detection" content="telephone=no">
                <title>{subject}</title>
                <!--[if mso]>
                <noscript>
                    <xml>
                        <o:OfficeDocumentSettings>
                            <o:PixelsPerInch>96</o:PixelsPerInch>
                        </o:OfficeDocumentSettings>
                    </xml>
                </noscript>
                <![endif]-->
                {css}
            </head>
            <body style="{body_style}">
                <div style="width: 100%; background-color: {theme_colors['background']}; padding: 20px 0;">
                    <!--[if mso | IE]>
                    <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600" align="center" style="width:8;">
                    <tr>
                    <td>
                    <![endif]-->
                    <div class="email-container" style="{container_style}">
                        <div style="{header_style}">
                            <img src="{logo_src}" alt="{server_name}" class="email-logo" style="{logo_style}">
                            <h1 style="{title_style}">{server_name} Newsletter</h1>
                        </div>
                        
                        <div style="{content_style}">
                            {content_html}
                        </div>
                        
                        <div style="{footer_style}">
                            <div style="margin-bottom: 10px;">
                                Generated for Plex Media Server by 
                                <a href="https://github.com/jma1ice/newsletterr" style="{footer_link_style}">newsletterr</a>
                            </div>
                            <div>
                                newsletterr is not affiliated with or a product of Plex, Inc.
                            </div>
                        </div>
                    </div>
                    <!--[if mso | IE]>
                    </td>
                    </tr>
                    </table>
                    <![endif]-->
                </div>
            </body>
        </html>"""

def send_standard_email_with_cids(to_emails, subject, selected_items, from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, settings, from_name):
    try:
        print(f"SMTP Config: {smtp_server}:{smtp_port} using {smtp_protocol}")

        if smtp_port == 465 and smtp_protocol == 'TLS':
            print("WARNING: Port 465 with TLS protocol detected!")
            print("Port 465 requires SSL protocol. Consider changing to:")
            print("- Port 587 with TLS, OR")
            print("- Port 465 with SSL")
        
        if smtp_port == 587 and smtp_protocol == 'SSL':
            print("WARNING: Port 587 with SSL protocol detected!")
            print("Port 587 typically uses TLS (STARTTLS)")

        msg_root = MIMEMultipart('related')
        msg_root['Subject'] = subject
        if alias_email == '':
            if from_name == '':
                msg_root['From'] = from_email
            else:
                msg_root['From'] = formataddr((from_name, from_email))
            msg_root['To'] = from_email
        else:
            if from_name == '':
                msg_root['From'] = alias_email
            else:
                msg_root['From'] = formataddr((from_name, alias_email))
            msg_root['To'] = alias_email
        
        if reply_to_email != '':
            msg_root['Reply-To'] = reply_to_email

        msg_alternative = MIMEMultipart('alternative')
        msg_root.attach(msg_alternative)

        print("Building email content...")
        tautulli_data = get_current_tautulli_data_for_email(settings)
        
        template_data = {
            'selected_items': json.dumps(selected_items),
            'email_text': '',
            'subject': subject
        }
        
        base_url = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:6397")
        
        email_html = build_email_html_with_all_cids(
            template_data, 
            tautulli_data, 
            msg_root,
            None,
            None,
            base_url,
            None,
            False
        )

        plain_text = convert_html_to_plain_text(email_html)
        msg_alternative.attach(MIMEText(plain_text, 'plain', 'utf-8'))
        msg_alternative.attach(MIMEText(email_html, 'html', 'utf-8'))

        print(f"Attempting SMTP connection...")

        if smtp_protocol == 'SSL':
            print(f"Using SMTP_SSL on port {smtp_port}")
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, decrypt(password))
        else:
            print(f"Using SMTP with STARTTLS on port {smtp_port}")
            server = smtplib.SMTP(smtp_server, smtp_port)
            print("Starting TLS...")
            server.starttls()
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, decrypt(password))

        print("SMTP connection established successfully")
            
        email_content = msg_root.as_string()

        content_size_kb = len(email_content.encode('utf-8')) / 1024
        content_size_mb = len(email_content.encode('utf-8')) / (1024 * 1024)
        print(f"Email size: {content_size_mb:.2f} MB")
        if content_size_mb > 25:
            print("WARNING: Email exceeds typical size limits")

        print("Sending email...")

        if alias_email == '':
            server.sendmail(from_email, [from_email] + to_emails, email_content)
            all_recipients = [from_email] + to_emails
        else:
            server.sendmail(alias_email, [alias_email] + to_emails, email_content)
            all_recipients = [alias_email] + to_emails

        print(f"Email sent successfully!")
        
        try:
            history_conn = sqlite3.connect(DB_PATH)
            history_cursor = history_conn.cursor()
            history_cursor.execute("""
                INSERT INTO email_history (subject, recipients, email_content, content_size_kb, recipient_count, template_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                subject,
                ', '.join(all_recipients),
                email_content[:1000],
                round(content_size_kb, 2),
                len(all_recipients),
                'Manual'
            ))
            history_conn.commit()
            history_conn.close()
        except Exception as history_error:
            print(f"Error saving email history: {history_error}")
        
        server.quit()
        return jsonify({"success": True, "sent_to": ', '.join(all_recipients), "size": content_size_kb})
    except smtplib.SMTPConnectError as e:
        print(f"SMTP Connection Error: {e}")
        print("This often indicates wrong port/protocol combination")
        return False
    except smtplib.SMTPServerDisconnected as e:
        print(f"SMTP Server Disconnected: {e}")
        print("Server closed connection - likely protocol mismatch")
        return False
    except Exception as e:
        print("SMTP send error:", e)
        return jsonify({"error": str(e)}), 500

def send_recommendations_email_with_cids(to_emails, subject, user_dict, selected_items, from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, settings, from_name):
    try:
        rec_user_keys = set()
        for item in selected_items:
            if item.get('type') == 'recs' and item.get('userKey'):
                rec_user_keys.add(item['userKey'])
        
        if not rec_user_keys:
            return send_standard_email_with_cids(
                to_emails, subject, selected_items, from_email, alias_email, 
                reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, settings, from_name
            )
        
        recommendations_data = get_recommendations_for_users(rec_user_keys, to_emails, user_dict, use_cache=True)

        if not recommendations_data:
            return jsonify({"error": "No recommendations data available. Please pull recommendations first."}), 400
        
        groups = group_recipients_by_user(to_emails, user_dict)
        
        total_sent = 0
        sent_info = []
        
        for user_key, recipients in groups.items():
            if user_key is None or user_key not in rec_user_keys:
                print("Skipping recipients without recommendations:", recipients)
                continue

            success = send_single_user_email_with_cids(
                recipients, subject, selected_items, user_key, recommendations_data,
                from_email, alias_email, reply_to_email, password, smtp_username, 
                smtp_server, smtp_port, smtp_protocol, settings, from_name
            )
            
            if success:
                total_sent += len(recipients)
                sent_info.append(', '.join(recipients))

        if total_sent == 0:
            return jsonify({"error": "No recipients matched a recommendations block. No emails sent."}), 400

        return jsonify({"success": True, "sent_groups": sent_info})
        
    except Exception as e:
        print("Error in send_recommendations_email_with_cids:", e)
        return jsonify({"error": str(e)}), 500

def send_single_user_email_with_cids(recipients, subject, selected_items, user_key, recommendations_data, from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, settings, from_name):
    try:
        print(f"SMTP Config: {smtp_server}:{smtp_port} using {smtp_protocol}")

        if smtp_port == 465 and smtp_protocol == 'TLS':
            print("WARNING: Port 465 with TLS protocol detected!")
            print("Port 465 requires SSL protocol. Consider changing to:")
            print("- Port 587 with TLS, OR")
            print("- Port 465 with SSL")
        
        if smtp_port == 587 and smtp_protocol == 'SSL':
            print("WARNING: Port 587 with SSL protocol detected!")
            print("Port 587 typically uses TLS (STARTTLS)")

        msg_root = MIMEMultipart('related')
        msg_root['Subject'] = subject
        
        if alias_email:
            if from_name == '':
                msg_root['From'] = alias_email
            else:
                msg_root['From'] = formataddr((from_name, alias_email))
            msg_root['To'] = alias_email
        else:
            if from_name == '':
                msg_root['From'] = from_email
            else:
                msg_root['From'] = formataddr((from_name, from_email))
            msg_root['To'] = from_email
        
        if reply_to_email:
            msg_root['Reply-To'] = reply_to_email

        msg_alternative = MIMEMultipart('alternative')
        msg_root.attach(msg_alternative)

        print("Building email content...")
        tautulli_data = get_current_tautulli_data_for_email(settings)
        
        template_data = {
            'selected_items': json.dumps(selected_items),
            'email_text': '',
            'subject': subject
        }
        
        base_url = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:6397")
        
        user_dict = {user_key: recipients[0]} if recipients else {}
        
        email_html = build_email_html_with_all_cids(
            template_data, 
            tautulli_data, 
            msg_root,
            recommendations_data,
            user_dict,
            base_url,
            target_user_key=user_key,
            is_scheduled=False
        )

        plain_text = convert_html_to_plain_text(email_html)
        msg_alternative.attach(MIMEText(plain_text, 'plain', 'utf-8'))
        msg_alternative.attach(MIMEText(email_html, 'html', 'utf-8'))

        print(f"Attempting SMTP connection...")

        if smtp_protocol == 'SSL':
            print(f"Using SMTP_SSL on port {smtp_port}")
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, decrypt(password))
        else:
            print(f"Using SMTP with STARTTLS on port {smtp_port}")
            server = smtplib.SMTP(smtp_server, smtp_port)
            print("Starting TLS...")
            server.starttls()
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, decrypt(password))

        print("SMTP connection established successfully")
            
        email_content = msg_root.as_string()

        content_size_kb = len(email_content.encode('utf-8')) / 1024
        content_size_mb = len(email_content.encode('utf-8')) / (1024 * 1024)
        print(f"Email size: {content_size_mb:.2f} MB")
        if content_size_mb > 25:
            print("WARNING: Email exceeds typical size limits")
        
        print("Sending email...")
        
        if alias_email:
            server.sendmail(alias_email, [alias_email] + recipients, email_content)
            all_recipients = [alias_email] + recipients
        else:
            server.sendmail(from_email, [from_email] + recipients, email_content)
            all_recipients = [from_email] + recipients
        
        server.quit()
        print(f"Email sent successfully!")
        
        try:
            history_conn = sqlite3.connect(DB_PATH)
            history_cursor = history_conn.cursor()
            history_cursor.execute("""
                INSERT INTO email_history (subject, recipients, email_content, content_size_kb, recipient_count, template_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                subject,
                ', '.join(all_recipients),
                email_content[:1000],
                round(content_size_kb, 2),
                len(all_recipients),
                'Manual'
            ))
            history_conn.commit()
            history_conn.close()
        except Exception as history_error:
            print(f"Error saving email history: {history_error}")
        
        return True
    except smtplib.SMTPConnectError as e:
        print(f"SMTP Connection Error: {e}")
        print("This often indicates wrong port/protocol combination")
        return False
    except smtplib.SMTPServerDisconnected as e:
        print(f"SMTP Server Disconnected: {e}")
        print("Server closed connection - likely protocol mismatch")
        return False
    except Exception as e:
        print(f"Error sending single user email: {e}")
        return False

def get_current_tautulli_data_for_email(settings):
    data = {
        'settings': settings,
        'stats': [],
        'graph_data': [],
        'recent_data': [],
        'graph_commands': []
    }
    
    try:
        stats = get_cached_data('stats', strict=False)
        if stats:
            data['stats'] = stats
        
        recent_data = get_cached_data('recent_data', strict=False)
        if recent_data:
            data['recent_data'] = recent_data
            
        graph_data = get_cached_data('graph_data', strict=False)
        if graph_data:
            data['graph_data'] = graph_data
            
        data['graph_commands'] = [
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
        
    except Exception as e:
        print(f"Error getting current Tautulli data: {e}")
    
    return data

def get_recommendations_for_users(user_keys, to_emails, user_dict, use_cache=True):
    try:
        if use_cache:
            cached_recommendations = get_cached_data('recommendations_json', strict=True) or get_cached_data('recommendations_json', strict=False)
            cached_filtered_users = get_cached_data('filtered_users', strict=True) or get_cached_data('filtered_users', strict=False)
            
            if cached_recommendations and cached_filtered_users:
                filtered_users = {k: v for k, v in user_dict.items() if k in user_keys and v in to_emails}
                
                cached_user_keys = set(str(k) for k in cached_filtered_users.keys())
                required_user_keys = set(str(k) for k in filtered_users.keys())
                
                if required_user_keys.issubset(cached_user_keys):
                    print(f"Using cached recommendations for users: {list(required_user_keys)}")
                    return {k: v for k, v in cached_recommendations.items() if str(k) in required_user_keys}
                else:
                    print(f"Cache miss - need users {required_user_keys}, cache has {cached_user_keys}")
            else:
                print("No cached recommendations available")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT conjurr_url FROM settings WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
        
        if not row or not row[0]:
            return {}
            
        conjurr_url = row[0].strip()
        
        filtered_users = {k: v for k, v in user_dict.items() if k in user_keys and v in to_emails}
        
        if not filtered_users:
            return {}
            
        recommendations_data, _ = run_conjurr_command(conjurr_url, filtered_users, None)

        if use_cache and recommendations_data:
            cache_params = {'timestamp': time.time(), 'manual_fetch': True}
            set_cached_data('recommendations_json', recommendations_data, cache_params)
            set_cached_data('filtered_users', filtered_users, cache_params)
            print("Cached fresh recommendations data")

        return recommendations_data or {}
        
    except Exception as e:
        print(f"Error getting recommendations: {e}")
        return {}

def send_scheduled_email_with_cids(schedule_id, email_list_id, template_id):
    try:
        schedule_conn = sqlite3.connect(DB_PATH)
        schedule_cursor = schedule_conn.cursor()
        schedule_cursor.execute("SELECT date_range FROM email_schedules WHERE id = ?", (schedule_id,))
        schedule_result = schedule_cursor.fetchone()
        schedule_conn.close()
        
        date_range = schedule_result[0] if schedule_result else 7
        
        email_lists_conn = sqlite3.connect(DB_PATH)
        email_lists_cursor = email_lists_conn.cursor()
        email_lists_cursor.execute("SELECT emails FROM email_lists WHERE id = ?", (email_list_id,))
        email_list_result = email_lists_cursor.fetchone()
        email_lists_conn.close()
        
        if not email_list_result:
            print(f"Email list {email_list_id} not found")
            return False
        
        to_emails = email_list_result[0]
        to_emails_list = [email.strip() for email in to_emails.split(",")]
        
        templates_conn = sqlite3.connect(DB_PATH)
        templates_cursor = templates_conn.cursor()
        templates_cursor.execute("SELECT name, subject, email_text, selected_items FROM email_templates WHERE id = ?", (template_id,))
        template_result = templates_cursor.fetchone()
        templates_conn.close()
        
        if not template_result:
            print(f"Template {template_id} not found")
            return False
        
        template_name, subject, email_text, selected_items_json = template_result
        selected_items = json.loads(selected_items_json) if selected_items_json else []
        
        settings_conn = sqlite3.connect(DB_PATH)
        settings_cursor = settings_conn.cursor()
        settings_cursor.execute("SELECT from_email, alias_email, reply_to_email, password, smtp_server, smtp_port, smtp_protocol, server_name, tautulli_url, tautulli_api, logo_filename, logo_width, from_name FROM settings WHERE id = 1")
        settings_result = settings_cursor.fetchone()
        settings_conn.close()
        
        if not settings_result:
            print("SMTP settings not found in database")
            return False
        
        from_email, alias_email, reply_to_email, encrypted_password, smtp_server, smtp_port, smtp_protocol, server_name, tautulli_base_url, tautulli_api_key, logo_filename, logo_width, from_name = settings_result
        
        public_base = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:6397")
        theme = 'dark'
        
        print("Capturing chart images...")
        chart_images = capture_chart_images_via_headless(schedule_id, public_base, theme)
        print(f"Captured {len(chart_images)} chart images")
        
        for item in selected_items:
            if item.get('type') == 'graph' and item.get('id') in chart_images:
                chart_data = chart_images[item['id']]
                item['chartImage'] = chart_data.get('dataUrl', '')
                item['chartSVG'] = chart_data.get('svg', '')

        has_recs = any(item.get('type') == 'recs' for item in selected_items)
        
        if has_recs:
            print("Template contains recommendations, splitting emails by user...")
            
            users_data, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_users', 'Users', None)
            user_dict = {}
            if users_data:
                user_dict = {
                    u['user_id']: u['email']
                    for u in users_data
                    if u.get('email') != None and u.get('email') != '' and u.get('is_active')
                }
            
            rec_user_keys = set()
            for item in selected_items:
                if item.get('type') == 'recs' and item.get('userKey'):
                    rec_user_keys.add(item['userKey'])
            
            if not rec_user_keys:
                print("No recommendation user keys found in template")
                return False
            
            conjurr_conn = sqlite3.connect(DB_PATH)
            conjurr_cursor = conjurr_conn.cursor()
            conjurr_cursor.execute("SELECT conjurr_url FROM settings WHERE id = 1")
            conjurr_result = conjurr_cursor.fetchone()
            conjurr_conn.close()
            
            if not conjurr_result or not conjurr_result[0]:
                print("Conjurr URL not configured")
                return False
            
            conjurr_url = conjurr_result[0].strip()
            filtered_users = {k: v for k, v in user_dict.items() if str(k) in rec_user_keys and v in to_emails_list}
            
            if not filtered_users:
                print("No users found matching recommendation blocks and email recipients")
                return False
            
            recommendations_data, _ = run_conjurr_command(conjurr_url, filtered_users, None)
            if not recommendations_data:
                print("Failed to fetch recommendations data")
                return False
            
            groups = group_recipients_by_user(to_emails_list, user_dict)
            
            total_sent = 0
            sent_info = []
            
            for user_key, recipients in groups.items():
                if user_key is None or str(user_key) not in rec_user_keys:
                    print(f"Skipping recipients without recommendations: {recipients}")
                    continue
                
                success = send_scheduled_user_email_with_cids(
                    recipients, subject, selected_items, user_key, recommendations_data,
                    from_email, alias_email, reply_to_email, encrypted_password,
                    smtp_server, smtp_port, smtp_protocol, 
                    server_name, tautulli_base_url, tautulli_api_key, date_range, template_name,
                    logo_filename, logo_width, from_name
                )
                
                if success:
                    total_sent += len(recipients)
                    sent_info.append(', '.join(recipients))
                    print(f"Successfully sent scheduled email to user {user_key}: {recipients}")
                else:
                    print(f"Failed to send scheduled email to user {user_key}: {recipients}")
            
            if total_sent == 0:
                print("No emails were sent successfully")
                return False
            
            print(f"Scheduled email sent successfully to {total_sent} total recipients across {len(sent_info)} user groups")
            return True
            
        else:
            print("Template has no recommendations, sending single email to all recipients...")
            return send_scheduled_single_email_with_cids(
                to_emails_list, subject, selected_items,
                from_email, alias_email, reply_to_email, encrypted_password,
                smtp_server, smtp_port, smtp_protocol,
                server_name, tautulli_base_url, tautulli_api_key, date_range, template_name,
                logo_filename, logo_width, from_name
            )
        
    except Exception as e:
        print(f"Error in send_scheduled_email_with_cids: {e}")
        traceback.print_exc()
        return False

def send_scheduled_user_email_with_cids(recipients, subject, selected_items, user_key, recommendations_data, from_email, alias_email, reply_to_email, encrypted_password, smtp_server, smtp_port, smtp_protocol, server_name, tautulli_base_url, tautulli_api_key, date_range, template_name, logo_filename, logo_width, from_name):
    try:
        print(f"SMTP Config: {smtp_server}:{smtp_port} using {smtp_protocol}")

        if smtp_port == 465 and smtp_protocol == 'TLS':
            print("WARNING: Port 465 with TLS protocol detected!")
            print("Port 465 requires SSL protocol. Consider changing to:")
            print("- Port 587 with TLS, OR")
            print("- Port 465 with SSL")
        
        if smtp_port == 587 and smtp_protocol == 'SSL':
            print("WARNING: Port 587 with SSL protocol detected!")
            print("Port 587 typically uses TLS (STARTTLS)")

        msg_root = MIMEMultipart('related')
        msg_root['Subject'] = f"[SCHEDULED] {subject}"
        
        if alias_email:
            if from_name == '':
                msg_root['From'] = alias_email
            else:
                msg_root['From'] = formataddr((from_name, alias_email))
            msg_root['To'] = alias_email
        else:
            if from_name == '':
                msg_root['From'] = from_email
            else:
                msg_root['From'] = formataddr((from_name, from_email))
            msg_root['To'] = from_email
        
        if reply_to_email:
            msg_root['Reply-To'] = reply_to_email

        msg_alternative = MIMEMultipart('alternative')
        msg_root.attach(msg_alternative)

        print("Building email content...")
        tautulli_data = fetch_tautulli_data_for_email(tautulli_base_url, tautulli_api_key, date_range, server_name)
        tautulli_data["settings"]["logo_filename"] = logo_filename
        tautulli_data["settings"]["logo_width"] = logo_width
        
        template_data = {
            'selected_items': json.dumps(selected_items),
            'email_text': '',
            'subject': subject
        }
        
        base_url = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:6397")
        
        user_dict = {user_key: recipients[0]} if recipients else {}
        
        email_html = build_email_html_with_all_cids(
            template_data, 
            tautulli_data, 
            msg_root,
            recommendations_data,
            user_dict,
            base_url,
            target_user_key=user_key,
            is_scheduled=True
        )

        plain_text = convert_html_to_plain_text(email_html)
        msg_alternative.attach(MIMEText(plain_text, 'plain', 'utf-8'))
        msg_alternative.attach(MIMEText(email_html, 'html', 'utf-8'))

        print(f"Attempting SMTP connection...")

        if smtp_protocol == 'SSL':
            print(f"Using SMTP_SSL on port {smtp_port}")
            server = smtplib.SMTP_SSL(smtp_server, int(smtp_port))
            server.login(from_email, decrypt(encrypted_password))
        else:
            print(f"Using SMTP with STARTTLS on port {smtp_port}")
            server = smtplib.SMTP(smtp_server, int(smtp_port))
            print("Starting TLS...")
            server.starttls()
            server.login(from_email, decrypt(encrypted_password))
        
        print("SMTP connection established successfully")
        
        email_content = msg_root.as_string()

        content_size_kb = len(email_content.encode('utf-8')) / 1024
        content_size_mb = len(email_content.encode('utf-8')) / (1024 * 1024)
        print(f"Email size: {content_size_mb:.2f} MB")
        if content_size_mb > 25:
            print("WARNING: Email exceeds typical size limits")

        print("Sending email...")
        
        if alias_email:
            server.sendmail(alias_email, [alias_email] + recipients, email_content)
            all_recipients = [alias_email] + recipients
        else:
            server.sendmail(from_email, [from_email] + recipients, email_content)
            all_recipients = [from_email] + recipients
        
        server.quit()
        print(f"Email sent successfully!")
        
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
    except smtplib.SMTPConnectError as e:
        print(f"SMTP Connection Error: {e}")
        print("This often indicates wrong port/protocol combination")
        return False
    except smtplib.SMTPServerDisconnected as e:
        print(f"SMTP Server Disconnected: {e}")
        print("Server closed connection - likely protocol mismatch")
        return False
    except Exception as e:
        print(f"Error sending scheduled user email: {e}")
        traceback.print_exc()
        return False

def send_scheduled_single_email_with_cids(to_emails_list, subject, selected_items, from_email, alias_email, reply_to_email, encrypted_password, smtp_server, smtp_port, smtp_protocol, server_name, tautulli_base_url, tautulli_api_key, date_range, template_name, logo_filename, logo_width, from_name, email_text=""):
    try:
        print(f"SMTP Config: {smtp_server}:{smtp_port} using {smtp_protocol}")

        if smtp_port == 465 and smtp_protocol == 'TLS':
            print("WARNING: Port 465 with TLS protocol detected!")
            print("Port 465 requires SSL protocol. Consider changing to:")
            print("- Port 587 with TLS, OR")
            print("- Port 465 with SSL")
        
        if smtp_port == 587 and smtp_protocol == 'SSL':
            print("WARNING: Port 587 with SSL protocol detected!")
            print("Port 587 typically uses TLS (STARTTLS)")

        msg_root = MIMEMultipart('related')
        msg_root['Subject'] = f"[SCHEDULED] {subject}"
        
        if alias_email:
            if from_name == '':
                msg_root['From'] = alias_email
            else:
                msg_root['From'] = formataddr((from_name, alias_email))
            msg_root['To'] = alias_email
        else:
            if from_name == '':
                msg_root['From'] = from_email
            else:
                msg_root['From'] = formataddr((from_name, from_email))
            msg_root['To'] = from_email

        if reply_to_email:
            msg_root['Reply-To'] = reply_to_email
        
        msg_alternative = MIMEMultipart('alternative')
        msg_root.attach(msg_alternative)

        print("Building email content...")
        tautulli_data = fetch_tautulli_data_for_email(tautulli_base_url, tautulli_api_key, date_range, server_name)
        tautulli_data["settings"]["logo_filename"] = logo_filename
        tautulli_data["settings"]["logo_width"] = logo_width
        
        template_data = {
            'selected_items': json.dumps(selected_items),
            'email_text': email_text,
            'subject': subject
        }
        
        base_url = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:6397")
        
        email_html = build_email_html_with_all_cids(
            template_data, 
            tautulli_data, 
            msg_root,
            None,
            None,
            base_url,
            None,
            True
        )

        plain_text = convert_html_to_plain_text(email_html)
        msg_alternative.attach(MIMEText(plain_text, 'plain', 'utf-8'))
        msg_alternative.attach(MIMEText(email_html, 'html', 'utf-8'))

        print(f"Attempting SMTP connection...")

        if smtp_protocol == 'SSL':
            print(f"Using SMTP_SSL on port {smtp_port}")
            server = smtplib.SMTP_SSL(smtp_server, int(smtp_port))
            server.login(from_email, decrypt(encrypted_password))
        else:
            print(f"Using SMTP with STARTTLS on port {smtp_port}")
            server = smtplib.SMTP(smtp_server, int(smtp_port))
            print("Starting TLS...")
            server.starttls()
            server.login(from_email, decrypt(encrypted_password))
        
        print("SMTP connection established successfully")
        
        email_content = msg_root.as_string()

        content_size_kb = len(email_content.encode('utf-8')) / 1024
        content_size_mb = len(email_content.encode('utf-8')) / (1024 * 1024)
        print(f"Email size: {content_size_mb:.2f} MB")
        if content_size_mb > 25:
            print("WARNING: Email exceeds typical size limits")

        print("Sending email...")
        
        if alias_email:
            server.sendmail(alias_email, [alias_email] + to_emails_list, email_content)
            all_recipients = [alias_email] + to_emails_list
        else:
            server.sendmail(from_email, [from_email] + to_emails_list, email_content)
            all_recipients = [from_email] + to_emails_list
        
        server.quit()
        print(f"Email sent successfully!")
        
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
        
        print(f"Scheduled email sent successfully to {len(all_recipients)} recipients")
        return True
    except smtplib.SMTPConnectError as e:
        print(f"SMTP Connection Error: {e}")
        print("This often indicates wrong port/protocol combination")
        return False
    except smtplib.SMTPServerDisconnected as e:
        print(f"SMTP Server Disconnected: {e}")
        print("Server closed connection - likely protocol mismatch")
        return False
    except Exception as e:
        print(f"Error in send_scheduled_single_email_with_cids: {e}")
        traceback.print_exc()
        return False

def build_graph_html_with_frontend_image(item, msg_root):
    chart_name = item.get('name', 'Chart')
    chart_image_data = item.get('chartImage', '')
    
    print(f"Processing graph: {chart_name}")
    
    if chart_image_data and chart_image_data.startswith('data:image/png'):
        try:
            header, encoded = chart_image_data.split(',', 1)
            image_data = base64.b64decode(encoded)
            
            cid = make_msgid(domain="newsletterr.local")[1:-1]
            
            img_part = MIMEImage(image_data, _subtype='png')
            img_part.add_header('Content-ID', f'<{cid}>')
            img_part.add_header('Content-Disposition', 'inline', filename=f'chart-{cid}.png')
            msg_root.attach(img_part)
            
            print(f"Successfully attached PNG chart with CID: {cid}")
            
            container_style = """
                border-radius: 8px;
                text-align: center;
                font-family: 'IBM Plex Sans';
            """
            
            image_style = """
                max-width: 100%;
                height: auto;
                border-radius: 4px;
                border: 0;
                line-height: 100%;
                outline: none;
                text-decoration: none;
                display: block;
                margin: 0 auto;
            """
            
            return f"""
            <div style="{container_style}">
                <img src="cid:{cid}" alt="{chart_name}" style="{image_style}">
            </div>
            """
            
        except Exception as e:
            print(f"Error processing chart image for {chart_name}: {e}")
    
    print(f"No valid chart data for {chart_name}")
    
    placeholder_style = """
        margin: 20px 0;
        padding: 30px;
        background-color: #f8f9fa;
        border: 2px dashed #dee2e6;
        border-radius: 8px;
        text-align: center;
        font-family: 'IBM Plex Sans';
    """
    
    placeholder_title_style = """
        color: #6c757d;
        margin: 0 0 10px 0;
        font-size: 18px;
        font-weight: bold;
        font-family: 'IBM Plex Sans';
    """
    
    placeholder_text_style = """
        color: #6c757d;
        margin: 0;
        font-size: 14px;
        font-family: 'IBM Plex Sans';
    """
    
    placeholder_subtext_style = """
        color: #6c757d;
        margin: 5px 0 0;
        font-size: 12px;
        font-style: italic;
        font-family: 'IBM Plex Sans';
    """
    
    return f"""
    <div style="{placeholder_style}">
        <h3 style="{placeholder_title_style}">{chart_name}</h3>
        <p style="{placeholder_text_style}">Chart image not available</p>
        <p style="{placeholder_subtext_style}">Interactive charts available in dashboard</p>
    </div>
    """

def build_text_block_html(content, block_type='textblock', theme_colors=None):
    if not theme_colors:
        theme_colors = get_email_theme_colors()
    
    if not content or not content.strip():
        print(f"Textblock called but no text present: {content}")
        return ""
    
    formatted_content = content.strip().replace('\n', '<br>')
    
    base_style = f"""
        margin-bottom: 20px;
        line-height: 1.6;
        color: {theme_colors['text']};
        font-family: 'IBM Plex Sans';
    """
    
    if block_type == 'titleblock':
        style = base_style + """
            font-size: 2em;
            font-weight: bold;
            text-align: center;
        """
    elif block_type == 'headerblock':
        style = base_style + """
            font-size: 1.5em;
            font-weight: bold;
            text-align: center;
        """
    else:
        style = base_style + """
            margin-bottom: 15px;
            text-align: center;
        """
    
    return f'<div style="{style}">{formatted_content}</div>'

@app.before_request
def _boot_workers():
    start_background_workers()

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
        { 'command' : 'movie' },
        { 'command' : 'show' },
        { 'command' : 'artist' },
        { 'command' : 'live' }
    ]
    graph_data = []
    recent_data = []
    recommendations_json = {}
    filtered_users = {}
    error = None
    alert = None

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        from_email = cursor.execute("SELECT from_email FROM settings WHERE id = 1").fetchone()[0]
        server_name = cursor.execute("SELECT server_name FROM settings WHERE id = 1").fetchone()[0]
        tautulli_url = cursor.execute("SELECT tautulli_url FROM settings WHERE id = 1").fetchone()[0]
        tautulli_api = cursor.execute("SELECT tautulli_api FROM settings WHERE id = 1").fetchone()[0]
        logo_filename = cursor.execute("SELECT logo_filename FROM settings WHERE id = 1").fetchone()[0]
        logo_width = cursor.execute("SELECT logo_width FROM settings WHERE id = 1").fetchone()[0]
    except:
        from_email = cursor.execute("SELECT from_email FROM settings WHERE id = 1").fetchone()
        server_name = cursor.execute("SELECT server_name FROM settings WHERE id = 1").fetchone()
        tautulli_url = cursor.execute("SELECT tautulli_url FROM settings WHERE id = 1").fetchone()
        tautulli_api = cursor.execute("SELECT tautulli_api FROM settings WHERE id = 1").fetchone()
        logo_filename = cursor.execute("SELECT logo_filename FROM settings WHERE id = 1").fetchone()
        logo_width = cursor.execute("SELECT logo_width FROM settings WHERE id = 1").fetchone()

    settings = {
        "from_email": from_email or "",
        "server_name": server_name or "",
        "tautulli_url": tautulli_url or "",
        "tautulli_api": decrypt(tautulli_api),
    }
    if logo_filename == '' or logo_filename is None:
        settings['logo_filename'] = 'Asset_94x.png'
        cursor.execute("""
            INSERT INTO settings (id, logo_filename) VALUES (1, 'Asset_94x.png')
            ON CONFLICT (id) DO UPDATE
            SET logo_filename = excluded.logo_filename
        """)
        conn.commit()
    else:
        settings['logo_filename'] = logo_filename
    if logo_width == '' or logo_width is None:
        settings['logo_width'] = 80
        cursor.execute("""
            INSERT INTO settings (id, logo_width) VALUES (1, 80)
            ON CONFLICT (id) DO UPDATE
            SET logo_width = excluded.logo_width
        """)
        conn.commit()
    else:
        settings['logo_width'] = int(logo_width)

    if settings['from_email'] == "":
        return redirect(url_for('settings'))
    
    conn.close()

    if settings['server_name'] != "":
        stats = get_cached_data('stats', strict=True) or get_cached_data('stats', strict=False)
        users = get_cached_data('users', strict=True) or get_cached_data('users', strict=False)
        graph_data = get_cached_data('graph_data', strict=True) or get_cached_data('graph_data', strict=False) or []
        recent_data = get_cached_data('recent_data', strict=True) or get_cached_data('recent_data', strict=False) or []
        recommendations_json = get_cached_data('recommendations_json', strict=True) or get_cached_data('recommendations_json', strict=False) or {}
        filtered_users = get_cached_data('filtered_users', strict=True) or get_cached_data('filtered_users', strict=False) or {}
        
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
            
            cache_params = {
                'time_range': time_range,
                'count': count,
                'url': tautulli_base_url,
                'timestamp': time.time()
            }

            stats, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', error, time_range)
            set_cached_data('stats', stats, cache_params)
            
            users, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_users', 'Users', error)
            set_cached_data('users', users, cache_params)
            
            graph_data = []
            for command in graph_commands:
                try:
                    gd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], error, time_range)
                    graph_data.append(gd if gd is not None else {})
                except Exception as e:
                    graph_data.append({})
                    if error is None:
                        error = f"Graph Error: {str(e)}"
                    else:
                        error += f", Graph Error: {str(e)}"
            set_cached_data('graph_data', graph_data, cache_params)

            libraries, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_library_names', None, None, "10")
            library_section_ids = {}
            for library in libraries:
                library_section_ids[f"{library['section_id']}"] = library["section_name"]
            
            recent_data = []
            for section_id in library_section_ids.keys():
                try:
                    rd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_recently_added', section_id, error, count)
                    for item in rd['recently_added']:
                        item['library_name'] = library_section_ids[section_id]
                    recent_data.append(rd if rd is not None else {})
                except Exception as e:
                    recent_data.append({})
                    if error is None:
                        error = f"Recent Data Error: {str(e)}"
                    else:
                        error += f", Recent Data Error: {str(e)}"
            set_cached_data('recent_data', recent_data, cache_params)
            
            user_dict = {}
            if users:
                for user in users:
                    if user['email'] != None and user['email'] != '' and user['is_active']:
                        user_dict[user['user_id']] = user['email']
            
            alert = f"Fresh data loaded! Stats/graphs for {time_range} days, and {count} recently added items."

    if graph_data == []:
        graph_data = [{},{}]
        
    libs = ['movies', 'shows']
    
    try:
        email_lists = get_saved_email_lists()
    except:
        email_lists = []
    
    cache_info = {
        'stats': get_cache_info('stats'),
        'users': get_cache_info('users'), 
        'graph_data': get_cache_info('graph_data'),
        'recent_data': get_cache_info('recent_data'),
        'recommendations_json': get_cache_info('recommendations_json'),
        'filtered_users': get_cache_info('filtered_users')
    }

    theme_settings = get_theme_settings()
        
    return render_template('index.html',
                           stats=stats, user_dict=user_dict,
                           graph_data=graph_data, graph_commands=graph_commands,
                           recent_data=recent_data, libs=libs,
                           error=error, alert=alert, settings=settings,
                           email_lists=email_lists, cache_info=cache_info,
                           recommendations_json=recommendations_json, filtered_users=filtered_users,
                           theme_settings=theme_settings
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

@app.route('/fetch_collections/<collection_type>', methods=['GET'])
def fetch_collections(collection_type):
    """Fetch Plex collections for specified type (movies or shows)"""
    try:
        # Get Plex settings
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT plex_url, plex_token FROM settings WHERE id = 1")
        row = cursor.fetchone()
        conn.close()

        if not row or not row[0] or not row[1]:
            return jsonify({"status": "error", "message": "Plex connection not configured"})

        plex_url = row[0].rstrip('/')
        plex_token = decrypt(row[1])

        # Get library sections first
        sections_url = f"{plex_url}/library/sections"
        headers = {"X-Plex-Token": plex_token, "Accept": "application/json"}
        
        sections_response = requests.get(sections_url, headers=headers, timeout=10)
        if sections_response.status_code != 200:
            return jsonify({"status": "error", "message": "Failed to fetch library sections"})

        sections_data = sections_response.json()
        collections = []

        # Filter sections by type and get collections
        target_type = "movie" if collection_type == "movies" else "show"
        
        for section in sections_data.get("MediaContainer", {}).get("Directory", []):
            if section.get("type") == target_type:
                section_id = section.get("key")
                section_title = section.get("title", "Unknown Library")
                
                # Fetch collections for this section
                collections_url = f"{plex_url}/library/sections/{section_id}/collections"
                collections_response = requests.get(collections_url, headers=headers, timeout=10)
                
                if collections_response.status_code == 200:
                    collections_data = collections_response.json()
                    
                    for collection in collections_data.get("MediaContainer", {}).get("Metadata", []):
                        # Build full image URLs
                        thumb = collection.get("thumb", "")
                        if thumb and not thumb.startswith("http"):
                            thumb = f"{plex_url}{thumb}?X-Plex-Token={plex_token}"
                        
                        art = collection.get("art", "")
                        if art and not art.startswith("http"):
                            art = f"{plex_url}{art}?X-Plex-Token={plex_token}"
                        
                        collections.append({
                            "key": collection.get("ratingKey"),
                            "title": collection.get("title", "Unknown Collection"),
                            "summary": collection.get("summary", ""),
                            "thumb": thumb,
                            "art": art,
                            "childCount": collection.get("childCount", 0),
                            "subtype": collection.get("subtype", target_type),
                            "sectionTitle": section_title,
                            "sectionId": section_id
                        })

        return jsonify({
            "status": "success", 
            "collections": collections,
            "type": collection_type
        })

    except Exception as e:
        print(f"Error fetching collections: {e}")
        return jsonify({"status": "error", "message": str(e)})

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

            cache_params = {'timestamp': time.time()}

            set_cached_data('filtered_users', filtered_users, cache_params)
            set_cached_data('recommendations_json', recommendations_json, cache_params)

    cache_info = {
        'stats': get_cache_info('stats'),
        'users': get_cache_info('users'), 
        'graph_data': get_cache_info('graph_data'),
        'recent_data': get_cache_info('recent_data'),
        'recommendations_json': get_cache_info('recommendations_json'),
        'filtered_users': get_cache_info('filtered_users')
    }
    
    theme_settings = get_theme_settings()

    return render_template('index.html', stats=stats, user_dict=user_dict, graph_data=graph_data, cache_info=cache_info,
                            graph_commands=graph_commands, recent_data=recent_data, libs=libs, settings=settings,
                            recommendations_json=recommendations_json, filtered_users=filtered_users, alert=alert, theme_settings=theme_settings)

@app.route('/send_email', methods=['POST'])
def send_email():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
        from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, server_name, logo_filename, logo_width, from_name
        FROM settings WHERE id = 1
    """)
    row = cursor.fetchone()
    conn.close()

    if row:
        settings = {
            "from_email": row[0] or "",
            "alias_email": row[1] or "",
            "reply_to_email": row[2] or "",
            "password": row[3] or "",
            "smtp_username": row[4] or "",
            "smtp_server": row[5] or "",
            "smtp_port": int(row[6]) if row[6] is not None else 587,
            "smtp_protocol": row[7] or "TLS",
            "server_name": row[8] or "",
            "logo_filename": row[9] or "Asset_94x.png",
            "logo_width": row[10] or 80,
            "from_name": row[11] or ""
        }
    else:
        return jsonify({"error": "Please enter email info on settings page"}), 500

    data = request.get_json()

    from_email = settings['from_email']
    alias_email = settings['alias_email']
    reply_to_email = settings['reply_to_email']
    password = settings['password']
    smtp_username = settings['smtp_username']
    smtp_server = settings['smtp_server']
    smtp_port = int(settings['smtp_port'])
    smtp_protocol = settings['smtp_protocol']
    to_emails = data['to_emails'].split(", ")
    subject = data['subject']
    user_dict = data.get('user_dict', {})
    selected_items = data.get('selected_items', [])
    from_name = settings['from_name']

    has_recommendations = any(item.get('type') == 'recs' for item in selected_items)

    if has_recommendations and user_dict:
        return send_recommendations_email_with_cids(
            to_emails, subject, user_dict, selected_items,
            from_email, alias_email, reply_to_email, password, smtp_username, 
            smtp_server, smtp_port, smtp_protocol, settings, from_name
        )
    else:
        return send_standard_email_with_cids(
            to_emails, subject, selected_items,
            from_email, alias_email, reply_to_email, password, smtp_username,
            smtp_server, smtp_port, smtp_protocol, settings, from_name
        )

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    theme_presets = {
        "newsletterr_blue": {
            "primary_color": "#8acbd4",
            "secondary_color": "#222222",
            "accent_color": "#62a1a4",
            "background_color": "#333333",
            "text_color": "#62a1a4",
            "logo_filename": "Asset_94x.png"
        },
        "plex_orange": {
            "primary_color": "#e5a00d",
            "secondary_color": "#222222",
            "accent_color": "#cc7b19",
            "background_color": "#333333",
            "text_color": "#cc7b19",
            "logo_filename": "Asset_45x.png"
        }
    }

    if request.method == "POST":
        from_email = request.form.get("from_email")
        alias_email = request.form.get("alias_email")
        reply_to_email = request.form.get("reply_to_email")
        password = encrypt(request.form.get("password"))
        smtp_username = request.form.get("smtp_username")
        smtp_server = request.form.get("smtp_server")
        smtp_port = int(request.form.get("smtp_port"))
        smtp_protocol = request.form.get("smtp_protocol")
        server_name = request.form.get("server_name")
        plex_url = request.form.get("plex_url")
        tautulli_url = request.form.get("tautulli_url")
        tautulli_api = encrypt(request.form.get("tautulli_api"))
        conjurr_url = request.form.get("conjurr_url")
        logo_filename = request.form.get("logo_filename")
        logo_width = request.form.get("logo_width")
        email_theme = request.form.get("email_theme", "newsletterr_blue")
        from_name = request.form.get("from_name")

        if email_theme in theme_presets:
            preset = theme_presets[email_theme]
            primary_color = preset["primary_color"]
            secondary_color = preset["secondary_color"]
            accent_color = preset["accent_color"]
            background_color = preset["background_color"]
            text_color = preset["text_color"]
            logo_filename = preset["logo_filename"]
        else:
            primary_color = request.form.get("primary_color", "#8acbd4")
            secondary_color = request.form.get("secondary_color", "#222222")
            accent_color = request.form.get("accent_color", "#62a1a4")
            background_color = request.form.get("background_color", "#333333")
            text_color = request.form.get("text_color", "#62a1a4")

        cursor.execute("""
            INSERT INTO settings
            (id, from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, server_name, plex_url, tautulli_url,
                tautulli_api, conjurr_url, logo_filename, logo_width, email_theme, primary_color, secondary_color, accent_color, background_color,
                text_color, from_name)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE
            SET from_email = excluded.from_email, alias_email = excluded.alias_email, reply_to_email = excluded.reply_to_email, password = excluded.password,
                smtp_username = excluded.smtp_username, smtp_server = excluded.smtp_server, smtp_port = excluded.smtp_port, smtp_protocol = excluded.smtp_protocol,
                server_name = excluded.server_name, plex_url = excluded.plex_url, tautulli_url = excluded.tautulli_url, tautulli_api = excluded.tautulli_api,
                conjurr_url = excluded.conjurr_url, logo_filename = excluded.logo_filename, logo_width = excluded.logo_width, email_theme = excluded.email_theme,
                primary_color = excluded.primary_color, secondary_color = excluded.secondary_color, accent_color = excluded.accent_color,
                background_color = excluded.background_color, text_color = excluded.text_color, from_name = excluded.from_name
        """, (from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, server_name, plex_url, tautulli_url, tautulli_api,
              conjurr_url, logo_filename, logo_width, email_theme, primary_color, secondary_color, accent_color, background_color, text_color, from_name))
        conn.commit()
        cursor.execute("SELECT plex_token FROM settings WHERE id = 1")
        plex_token = cursor.fetchone()[0]
        conn.close()

        settings = {
            "from_email": from_email,
            "alias_email": alias_email,
            "reply_to_email": reply_to_email,
            "password": decrypt(password),
            "smtp_username": smtp_username,
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
            "smtp_protocol": smtp_protocol,
            "server_name": server_name,
            "plex_url": plex_url,
            "plex_token": plex_token,
            "tautulli_url": tautulli_url,
            "tautulli_api": decrypt(tautulli_api),
            "conjurr_url": conjurr_url,
            "logo_filename": logo_filename,
            "logo_width": logo_width,
            "email_theme": email_theme,
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "accent_color": accent_color,
            "background_color": background_color,
            "text_color": text_color,
            "from_name": from_name,
        }

        return render_template('settings.html', alert="Settings saved successfully!", settings=settings)

    try:
        from_email = cursor.execute("SELECT from_email FROM settings WHERE id = 1").fetchone()[0]
        alias_email = cursor.execute("SELECT alias_email FROM settings WHERE id = 1").fetchone()[0]
        reply_to_email = cursor.execute("SELECT reply_to_email FROM settings WHERE id = 1").fetchone()[0]
        password = cursor.execute("SELECT password FROM settings WHERE id = 1").fetchone()[0]
        smtp_username = cursor.execute("SELECT smtp_username FROM settings WHERE id = 1").fetchone()[0]
        smtp_server = cursor.execute("SELECT smtp_server FROM settings WHERE id = 1").fetchone()[0]
        smtp_port = cursor.execute("SELECT smtp_port FROM settings WHERE id = 1").fetchone()[0]
        smtp_protocol = cursor.execute("SELECT smtp_protocol FROM settings WHERE id = 1").fetchone()[0]
        server_name = cursor.execute("SELECT server_name FROM settings WHERE id = 1").fetchone()[0]
        plex_url = cursor.execute("SELECT plex_url FROM settings WHERE id = 1").fetchone()[0]
        plex_token = cursor.execute("SELECT plex_token FROM settings WHERE id = 1").fetchone()[0]
        tautulli_url = cursor.execute("SELECT tautulli_url FROM settings WHERE id = 1").fetchone()[0]
        tautulli_api = cursor.execute("SELECT tautulli_api FROM settings WHERE id = 1").fetchone()[0]
        conjurr_url = cursor.execute("SELECT conjurr_url FROM settings WHERE id = 1").fetchone()[0]
        logo_filename = cursor.execute("SELECT logo_filename FROM settings WHERE id = 1").fetchone()[0]
        logo_width = cursor.execute("SELECT logo_width FROM settings WHERE id = 1").fetchone()[0]
        email_theme = cursor.execute("SELECT email_theme FROM settings WHERE id = 1").fetchone()[0]
        primary_color = cursor.execute("SELECT primary_color FROM settings WHERE id = 1").fetchone()[0]
        secondary_color = cursor.execute("SELECT secondary_color FROM settings WHERE id = 1").fetchone()[0]
        accent_color = cursor.execute("SELECT accent_color FROM settings WHERE id = 1").fetchone()[0]
        background_color = cursor.execute("SELECT background_color FROM settings WHERE id = 1").fetchone()[0]
        text_color = cursor.execute("SELECT text_color FROM settings WHERE id = 1").fetchone()[0]
        from_name = cursor.execute("SELECT from_name FROM settings WHERE id = 1").fetchone()[0]
    except:
        from_email = cursor.execute("SELECT from_email FROM settings WHERE id = 1").fetchone()
        alias_email = cursor.execute("SELECT alias_email FROM settings WHERE id = 1").fetchone()
        reply_to_email = cursor.execute("SELECT reply_to_email FROM settings WHERE id = 1").fetchone()
        password = cursor.execute("SELECT password FROM settings WHERE id = 1").fetchone()
        smtp_username = cursor.execute("SELECT smtp_username FROM settings WHERE id = 1").fetchone()
        smtp_server = cursor.execute("SELECT smtp_server FROM settings WHERE id = 1").fetchone()
        smtp_port = cursor.execute("SELECT smtp_port FROM settings WHERE id = 1").fetchone()
        smtp_protocol = cursor.execute("SELECT smtp_protocol FROM settings WHERE id = 1").fetchone()
        server_name = cursor.execute("SELECT server_name FROM settings WHERE id = 1").fetchone()
        plex_url = cursor.execute("SELECT plex_url FROM settings WHERE id = 1").fetchone()
        plex_token = cursor.execute("SELECT plex_token FROM settings WHERE id = 1").fetchone()
        tautulli_url = cursor.execute("SELECT tautulli_url FROM settings WHERE id = 1").fetchone()
        tautulli_api = cursor.execute("SELECT tautulli_api FROM settings WHERE id = 1").fetchone()
        conjurr_url = cursor.execute("SELECT conjurr_url FROM settings WHERE id = 1").fetchone()
        logo_filename = cursor.execute("SELECT logo_filename FROM settings WHERE id = 1").fetchone()
        logo_width = cursor.execute("SELECT logo_width FROM settings WHERE id = 1").fetchone()
        email_theme = cursor.execute("SELECT email_theme FROM settings WHERE id = 1").fetchone()
        primary_color = cursor.execute("SELECT primary_color FROM settings WHERE id = 1").fetchone()
        secondary_color = cursor.execute("SELECT secondary_color FROM settings WHERE id = 1").fetchone()
        accent_color = cursor.execute("SELECT accent_color FROM settings WHERE id = 1").fetchone()
        background_color = cursor.execute("SELECT background_color FROM settings WHERE id = 1").fetchone()
        text_color = cursor.execute("SELECT text_color FROM settings WHERE id = 1").fetchone()
        from_name = cursor.execute("SELECT from_name FROM settings WHERE id = 1").fetchone()

    current_theme = email_theme or "newsletterr_blue"
    if current_theme in theme_presets and current_theme != "custom":
        preset = theme_presets[current_theme]
        primary_color = preset["primary_color"]
        secondary_color = preset["secondary_color"]
        accent_color = preset["accent_color"]
        background_color = preset["background_color"]
        text_color = preset["text_color"]

    settings = {
        "from_email": from_email or "",
        "alias_email": alias_email or "",
        "reply_to_email": reply_to_email or "",
        "smtp_username": smtp_username or "",
        "smtp_server": smtp_server or "",
        "smtp_protocol": smtp_protocol or "TLS",
        "server_name": server_name or "",
        "plex_url": plex_url or "",
        "plex_token": plex_token or "",
        "tautulli_url": tautulli_url or "",
        "conjurr_url": conjurr_url or "",
        "logo_filename": logo_filename or "",
        "email_theme": email_theme or "newsletterr_blue",
        "primary_color": primary_color or "#8acbd4",
        "secondary_color": secondary_color or "#222222",
        "accent_color": accent_color or "#62a1a4",
        "background_color": background_color or "#333333",
        "text_color": text_color or "#62a1a4",
        "from_name": from_name or ""
    }
    if password == '' or password is None:
        settings["password"] = ""
    else:
        settings["password"] = decrypt(password)
    if smtp_port == '' or smtp_port is None:
        settings["smtp_port"] = 587
        cursor.execute("""
            INSERT INTO settings (id, smtp_port) VALUES (1, 587)
            ON CONFLICT (id) DO UPDATE
            SET smtp_port = excluded.smtp_port
        """)
        conn.commit()
    else:
        settings["smtp_port"] = int(smtp_port)
    if tautulli_api == '' or tautulli_api is None:
        settings["tautulli_api"] = ""
    else:
        settings["tautulli_api"] = decrypt(tautulli_api)
    if logo_width == '' or logo_width is None:
        settings["logo_width"] = 80
        cursor.execute("""
            INSERT INTO settings (id, logo_width) VALUES (1, 80)
            ON CONFLICT (id) DO UPDATE
            SET logo_width = excluded.logo_width
        """)
        conn.commit()
    else:
        settings["logo_width"] = int(logo_width)
    
    conn.close()
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
            try:
                utc_dt = datetime.fromisoformat(email[5].replace('Z', '+00:00'))
                local_dt = utc_dt.replace(tzinfo=timezone.utc).astimezone()
                formatted_time = local_dt.strftime('%Y-%m-%d %I:%M:%S %p')
            except:
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
    try:
        schedules = get_email_schedules()
        email_lists = get_saved_email_lists()
        
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
    try:
        delete_email_schedule(schedule_id)
        return jsonify({"status": "success", "message": "Schedule deleted successfully"})
    except Exception as e:
        print(f"Error deleting schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>/send-now', methods=['POST'])
def send_schedule_now(schedule_id):
    try:
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
        
        print(f"Manual send triggered for schedule: {name}")
        success = send_scheduled_email(schedule_id, email_list_id, template_id)
        
        if success:
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
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT template_id, date_range, email_list_id
            FROM email_schedules 
            WHERE id = ?
        """, (schedule_id,))
        schedule_result = cursor.fetchone()
        conn.close()
        
        if not schedule_result:
            return jsonify({"status": "error", "message": "Schedule not found"}), 404
        
        template_id, date_range, email_list_id = schedule_result
        date_range = date_range or 7
        
        templates_conn = sqlite3.connect(DB_PATH)
        templates_cursor = templates_conn.cursor()
        templates_cursor.execute("SELECT name, subject, email_text, selected_items FROM email_templates WHERE id = ?", (template_id,))
        template_result = templates_cursor.fetchone()
        templates_conn.close()
        
        if not template_result:
            return jsonify({"status": "error", "message": "Template not found"}), 404
        
        template_name, subject, email_text, selected_items_json = template_result
        
        try:
            selected_items = json.loads(selected_items_json) if selected_items_json else []
        except:
            selected_items = []

        email_lists_conn = sqlite3.connect(DB_PATH)
        email_lists_cursor = email_lists_conn.cursor()
        email_lists_cursor.execute("SELECT emails FROM email_lists WHERE id = ?", (email_list_id,))
        email_list_result = email_lists_cursor.fetchone()
        email_lists_conn.close()
        
        if not email_list_result:
            return jsonify({"status": "error", "message": "Email list not found"}), 404
        
        to_emails = email_list_result[0]
        to_emails_list = [email.strip() for email in to_emails.split(",")]
        
        settings_conn = sqlite3.connect(DB_PATH)
        settings_cursor = settings_conn.cursor()
        settings_cursor.execute("SELECT server_name, tautulli_url, tautulli_api, logo_filename, logo_width FROM settings WHERE id = 1")
        settings_row = settings_cursor.fetchone()
        settings_conn.close()
        
        if settings_row:
            settings = {
                "server_name": settings_row[0],
                "tautulli_url": settings_row[1],
                "tautulli_api": settings_row[2],
                "logo_filename": settings_row[3],
                "logo_width": settings_row[4]
            }
        else:
            settings = {"server_name": ""}

        user_dict = {}
        if settings.get('tautulli_url') and settings.get('tautulli_api'):
            try:
                users_data, _ = run_tautulli_command(settings['tautulli_url'].rstrip('/'), settings['tautulli_api'], 'get_users', 'Users', None)
                if users_data:
                    user_dict = {
                        str(u['user_id']): u['email']
                        for u in users_data
                        if u.get('email') != None and u.get('email') != '' and u.get('is_active')
                    }
            except Exception as e:
                print(f"Error fetching user_dict for preview API: {e}")
        
        tautulli_data = fetch_tautulli_data_for_email(
            settings['tautulli_url'].rstrip('/'), 
            settings['tautulli_api'], 
            date_range, 
            settings['server_name']
        ) if settings.get('tautulli_url') and settings.get('tautulli_api') else {
            'settings': settings,
            'stats': [],
            'graph_data': [],
            'recent_data': [],
            'graph_commands': []
        }
        tautulli_data["settings"]["logo_filename"] = settings["logo_filename"]
        tautulli_data["settings"]["logo_width"] = settings["logo_width"]
        
        recommendations_data = None
        has_recs = any(item.get('type') == 'recs' for item in selected_items)
        
        if has_recs:
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT conjurr_url FROM settings WHERE id = 1")
                row = c.fetchone()
                conn.close()
                conjurr_url = (row[0] or "").strip() if row else ""

                if conjurr_url and user_dict:
                    filtered_users = {k: v for k, v in user_dict.items() if v in to_emails_list}
                    recommendations_data, _ = run_conjurr_command(conjurr_url, filtered_users, error=None)

            except Exception as e:
                print("preview_schedule: recommendations unavailable:", e)
                recommendations_data = {}
        
        return jsonify({
            "status": "success",
            "message": "ok",
            "template_name": template_name,
            "subject": subject,
            "email_text": email_text,
            "selected_items": selected_items,
            "date_range": date_range,
            "settings": settings,
            "stats": tautulli_data.get('stats', []),
            "graph_data": tautulli_data.get('graph_data', []),
            "recent_data": tautulli_data.get('recent_data', []),
            "graph_commands": tautulli_data.get('graph_commands', []),
            "recent_commands": [{'command': 'movie'}, {'command': 'show'}],
            "recommendations": recommendations_data or {},
            "user_dict": user_dict
        })
        
    except Exception as e:
        print(f"Error generating preview: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>/preview-page', methods=['GET'])
def preview_schedule_page(schedule_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT date_range FROM email_schedules WHERE id = ?", (schedule_id,))
        schedule_result = cursor.fetchone()
        
        date_range = schedule_result[0] if schedule_result else 7
    except:
        date_range = 7

    cursor.execute("SELECT logo_filename, logo_width, tautulli_url, tautulli_api FROM settings WHERE id = 1")
    settings_row = cursor.fetchone()
    logo_filename = settings_row[0] if settings_row else 'Asset_94x.png'
    logo_width = settings_row[1] if settings_row else 80
    tautulli_url = settings_row[2] if settings_row else ''
    tautulli_api = settings_row[3] if settings_row else ''

    settings = {
        "logo_filename": logo_filename,
        "logo_width": logo_width
    }
    conn.close()

    user_dict = {}
    if tautulli_url and tautulli_api:
        try:
            users_data, _ = run_tautulli_command(tautulli_url.rstrip('/'), tautulli_api, 'get_users', 'Users', None)
            if users_data:
                user_dict = {
                    str(u['user_id']): u['email']
                    for u in users_data
                    if u.get('email') != None and u.get('email') != '' and u.get('is_active')
                }
        except Exception as e:
            print(f"Error fetching user_dict for preview: {e}")
    
    can_use_cache, cache_reason = can_use_cached_data_for_preview(date_range)
    
    if can_use_cache:
        print(f"Preview page using cached data: {cache_reason}")
        stats = get_cached_data('stats', strict=True) or get_cached_data('stats', strict=False) or []
        graph_data = get_cached_data('graph_data', strict=True) or get_cached_data('graph_data', strict=False) or []
        recent_data = get_cached_data('recent_data', strict=True) or get_cached_data('recent_data', strict=False) or []
        recommendations = (get_cached_data('recommendations', strict=True) or get_cached_data('recommendations', strict=False) or {})
    else:
        print(f"Preview page using cached data (fallback): {cache_reason}")
        stats = get_cached_data('stats', strict=False) or []
        graph_data = get_cached_data('graph_data', strict=False) or []
        recent_data = get_cached_data('recent_data', strict=False) or []
        recommendations = get_cached_data('recommendations', strict=False) or {}
    
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

    theme_settings = get_theme_settings()
    
    return render_template(
        'schedule_preview.html', 
        stats=stats, 
        graph_data=graph_data, 
        recent_data=recent_data,
        graph_commands=graph_commands,
        recommendations=recommendations,
        settings=settings,
        user_dict=user_dict,
        theme_settings=theme_settings
    )

@app.route('/scheduling/calendar-data', methods=['GET'])
def get_calendar_data():
    try:
        month = int(request.args.get('month', datetime.now().month))
        year = int(request.args.get('year', datetime.now().year))
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, frequency, start_date, send_time, next_send, is_active, template_id
            FROM email_schedules 
            WHERE is_active = 1
        """)
        schedules = cursor.fetchall()
        conn.close()
        
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
                
            try:
                schedule_start = datetime.fromisoformat(schedule_start_date)
            except:
                continue
            
            current_date = schedule_start
            
            if frequency == 'weekly' and current_date < start_date:
                weeks_to_skip = (start_date - current_date).days // 7
                current_date += timedelta(weeks=weeks_to_skip)
                
                target_weekday = schedule_start.weekday()
                days_ahead = (target_weekday - current_date.weekday()) % 7
                current_date += timedelta(days=days_ahead)
                
                if current_date < start_date:
                    current_date += timedelta(days=7)
            
            elif frequency == 'monthly' and current_date < start_date:
                target_day = schedule_start.day
                current_date = datetime(year, month, min(target_day, calendar.monthrange(year, month)[1]))
            
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
                
                if frequency == 'daily':
                    current_date += timedelta(days=1)
                elif frequency == 'weekly':
                    current_date += timedelta(days=7)
                elif frequency == 'monthly':
                    target_day = schedule_start.day
                    if current_date.month == 12:
                        next_year = current_date.year + 1
                        next_month = 1
                    else:
                        next_year = current_date.year
                        next_month = current_date.month + 1
                    
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
    clear_cache()
    return jsonify({"status": "success", "message": "Cache cleared successfully"})

@app.route('/cache_status', methods=['GET'])
def cache_status():
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
    try:
        lists = get_saved_email_lists()
        return jsonify({"status": "success", "lists": lists})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/email_lists', methods=['POST'])
def save_email_list_route():
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
    try:
        delete_email_list(list_id)
        return jsonify({"status": "success", "message": "List deleted successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/email_templates', methods=['GET'])
def get_email_templates():
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
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        selected_items = data.get('selected_items', '[]')
        email_text = data.get('email_text', '')
        subject = data.get('subject', '')
        
        if not name:
            return jsonify({"status": "error", "message": "Template name is required"}), 400
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM email_templates WHERE name = ?", (name,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE email_templates 
                SET selected_items = ?, email_text = ?, subject = ?, updated_at = CURRENT_TIMESTAMP
                WHERE name = ?
            """, (selected_items, email_text, subject, name))
            message = "Template updated successfully"
        else:
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
    migrate_data_from_separate_dbs()
    init_db(DB_PATH)
    migrate_schema("logo_filename TEXT")
    migrate_schema("logo_width INTEGER")
    app.run(host="0.0.0.0", port=6397, debug=True)
