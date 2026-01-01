import os, math, uuid, base64, smtplib, sqlite3, requests, time, threading, re, json, mimetypes, shutil, calendar, traceback, io, sys, secrets, html, bleach
from collections import defaultdict
from cryptography.fernet import Fernet, InvalidToken
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv, set_key, find_dotenv
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid, formataddr
from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, session, abort, make_response
from functools import wraps
from pathlib import Path
from PIL import Image, ImageFilter, ImageEnhance
from playwright.sync_api import sync_playwright
from plex_api_client import PlexAPI
from urllib.parse import quote_plus, urljoin, urlparse, parse_qs, urlencode, quote

app = Flask(__name__, template_folder = 'templates', static_folder = 'static')

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
    set_key(str(ENV_FILE), "DATA_ENC_KEY", new_key)
    return new_key

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
            from_name TEXT,
            login_toggle TEXT,
            nl_username TEXT,
            nl_password TEXT
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
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expanded_collections TEXT DEFAULT '{}'
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
            items_count INTEGER DEFAULT 10,
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

    if 'items_count' not in columns:
        print("Adding items_count column to email_schedules table...")
        cursor.execute("ALTER TABLE email_schedules ADD COLUMN items_count INTEGER DEFAULT 10")
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

    login_columns = [
        ('login_toggle', 'TEXT DEFAULT "disabled"'),
        ('nl_username', 'TEXT'),
        ('nl_password', 'TEXT')
    ]
    for col_name, col_def in login_columns:
        if col_name not in settings_columns:
            print(f"Adding {col_name} column to settings table...")
            cursor.execute(f'ALTER TABLE settings ADD COLUMN {col_name} {col_def}')
            conn.commit()

    cursor.execute("PRAGMA table_info(settings)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'custom_logo_filename' not in columns:
        print("Adding custom_logo_filename column to settings table...")
        cursor.execute("ALTER TABLE settings ADD COLUMN custom_logo_filename TEXT")
        conn.commit()
    
    conn.close()

def require_csrf_for_json():
    token = request.headers.get('X-CSRF-Token') or request.form.get('csrf_token')
    if not token or token.strip() != session.get('csrf_token'):
        abort(400)

def sanitize_html_input(text):
    if not text:
        return ""

    allowed_tags = [
        'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'blockquote', 'a', 'img', 'div', 'span'
    ]

    allowed_attributes = {
        'a': ['href', 'title'],
        'img': ['src', 'alt', 'title', 'width', 'height'],
        'div': ['class'],
        'span': ['class', 'style']
    }

    allowed_protocols = ['http', 'https', 'mailto']

    return bleach.clean(
        text,
        tags=allowed_tags,
        attributes=allowed_attributes,
        protocols=allowed_protocols,
        strip=True
    )

def escape_html_output(text):
    if not text:
        return ""
    return html.escape(text)

def requires_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT login_toggle FROM settings WHERE id = 1")
        login_toggle = cursor.fetchone()
        conn.close()

        if login_toggle[0] != 'enabled':
            return f(*args, **kwargs)

        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def check_credentials(username, password):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT nl_username, nl_password FROM settings WHERE id = 1")
    login_info = cursor.fetchone()
    conn.close()

    expected_username, expected_password = login_info

    if not expected_password:
        return False

    return username == expected_username and password == decrypt(expected_password)

def safe_get(url: str, *, timeout: int = 15, retries: int = 2, **kwargs):
    for attempt in range(retries + 1):
        try:
            return requests.get(url, timeout=timeout, **kwargs)
        except requests.RequestException as e:
            if attempt == retries:
                raise
            time.sleep(1.0 * (attempt + 1))

def sanitize_html(html: str) -> str:
    allowed_tags = [
        'p','br','strong','em','b','i','u','ul','ol','li','a','h1','h2','h3','h4','h5','h6',
        'blockquote','code','pre','span'
    ]
    allowed_attrs = {
        'a': ['href','title','target','rel'],
        'span': ['style'],
        '*': ['style']
    }
    cleaned = bleach.clean(html, tags=allowed_tags, attributes=allowed_attrs, strip=True)
    return cleaned

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
        'muted_text': '#cccccc',
        'email_theme': theme_settings['email_theme']
    }

def build_email_css_from_theme(theme_colors, logo_width):
    return f"""
        <style>
            @import url(https://fonts.googleapis.com/css?family=IBM+Plex+Sans:400,700&display=swap);
            
            body {{
                margin: 0 !important;
                padding: 0 !important;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif !important;
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

            .email-container {{
                max-width: 800px !important;
                width: 100% !important;
                margin: 0 auto !important;
            }}
            
            .email-logo {{
                max-width: {logo_width}px !important;
                width: auto !important;
                height: auto !important;
            }}

            .card-poster-wrapper {{
                position: relative !important;
                display: block !important;
            }}

            .card-poster {{
                background-size: cover !important;
                background-position: center !important;
                background-repeat: no-repeat !important;
                width: 100% !important;
                height: auto;
                padding-top: 135%;
                position: relative !important;
                background-color: #f8f9fa !important;
                border-radius: 10px 10px 0 0 !important;
            }}

            .card-poster-badge {{
                position: absolute !important;
                bottom: 1px !important;
                right: 1px !important;
                background-color: rgba(0, 0, 0, 0.6);
                color: rgba(255, 255, 255, 0.9);
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 9px;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                line-height: 1;
                max-width: fit-content;
            }}

            @media only screen and (max-width: 600px) {{
                .email-container {{
                    width: 100% !important;
                    max-width: 100% !important;
                    margin: 0 !important;
                }}
                
                .email-logo {{
                    max-width: 60px !important;
                    width: 60px !important;
                }}

                .recently-added-table {{
                    display: block !important;
                    width: 100% !important;
                    text-align: center !important;
                }}

                .recently-added-row {{
                    display: inline !important;
                }}
                
                .recently-added-table td {{
                    width: 30% !important;
                    padding: 6px !important;
                    display: inline-block !important;
                    vertical-align: top !important;
                    box-sizing: border-box !important;
                }}
                
                .recently-added-card {{
                    width: 100% !important;
                    max-width: 150px !important;
                    margin: 0 auto 10px auto !important;
                    height: auto !important;
                    overflow: hidden !important;
                    border-radius: 10px !important;
                }}

                .card-poster {{
                    padding-top: 125% !important;
                    min-height: 25px;
                }}
                
                .card-content {{
                    height: auto !important;
                    min-height: 165px !important;
                    text-align: left !important;
                }}
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

def migrate_ra_recs_to_recently_added_recommendations():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, selected_items FROM email_templates")
    rows = cursor.fetchall()

    updated = 0
    for template_id, selected_json in rows:
        if not selected_json:
            continue
        try:
            items = json.loads(selected_json)
        except json.JSONDecodeError:
            continue

        changed = False
        for item in items:
            if isinstance(item, dict) and "type" in item:
                if item["type"] == "ra":
                    item["type"] = "recently added"
                    changed = True
                elif item["type"] == "recs":
                    item["type"] = "recommendations"
                    changed = True

        if changed:
            new_json = json.dumps(items, ensure_ascii=False)
            cursor.execute("UPDATE email_templates SET selected_items = ? WHERE id = ?", (new_json, template_id))
            updated += 1

    conn.commit()
    conn.close()

    print(f"Updated {updated} templates successfully.")

def migrate_email_templates_for_expanded_collections():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(email_templates)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'expanded_collections' not in columns:
            print("Adding expanded_collections column to email_templates table...")
            cursor.execute("ALTER TABLE email_templates ADD COLUMN expanded_collections TEXT DEFAULT '{}'")
            conn.commit()
            print("Successfully added expanded_collections column")
            
        conn.close()
        
    except Exception as e:
        print(f"Error migrating email_templates table: {e}")
        traceback.print_exc()

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
        start_dt = datetime.fromisoformat(start_date)

        if start_dt.day <= 15:
            target_days = [1, 15]
        else:
            target_days = [15, 1]
        
        current_month = base_date.month
        current_year = base_date.year
        current_day = base_date.day
        
        next_target_day = None
        for day in target_days:
            if day > current_day:
                next_target_day = day
                break
        
        if next_target_day:
            next_date = datetime(current_year, current_month, next_target_day)
        else:
            next_month = current_month + 1
            next_year = current_year
            if next_month > 12:
                next_month = 1
                next_year += 1
            next_date = datetime(next_year, next_month, target_days[0])
        
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

def create_email_schedule(name, email_list_id, template_id, frequency, start_date, send_time='09:00', date_range=7, items_count=10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    next_send = calculate_next_send(frequency, start_date, send_time)
    
    try:
        list_id_value = 0 if email_list_id == 'ALL' else int(email_list_id)

        cursor.execute("""
            INSERT INTO email_schedules (name, email_list_id, template_id, frequency, start_date, send_time, next_send, date_range, items_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, list_id_value, template_id, frequency, start_date, send_time, next_send.isoformat(), date_range, items_count))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error creating schedule: {e}")
        return False
    finally:
        conn.close()

def update_email_schedule(schedule_id, name, email_list_id, template_id, frequency, start_date, send_time='09:00', date_range=7, items_count=10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    next_send = calculate_next_send(frequency, start_date, send_time)

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
            
            if current_time - last_cache_refresh > CACHE_DURATION:
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
        
        recent_data = fetch_recent_data_for_index(tautulli_base_url, tautulli_api_key, count)
        
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
            page.on("console", lambda msg: print(f"PAGE LOG: {msg.text}"))
            page.goto(url, wait_until="load")
            print(f"Loaded URL (before waiting): {page.url}")
            
            try:
                page.wait_for_function("typeof loadPreview === 'function'", timeout=30_000)
                page.evaluate("loadPreview()")
                page.wait_for_function("typeof Highcharts !== 'undefined' && Highcharts.charts && Highcharts.charts.filter(Boolean).length > 0", timeout=60_000)
                page.wait_for_timeout(2000)
            except Exception as e:
                print(f"Error waiting for charts to load: {e}")

            try:
                page.wait_for_function("typeof selectedItems !== 'undefined'", timeout=10_000)
                selected_items = page.evaluate("selectedItems || []")
            except Exception as e:
                print(f"selectedItems never defined or timeout: {e}")
                selected_items = []

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

def get_plex_machine_id():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT plex_url, plex_token FROM settings WHERE id = 1")
        plex_settings = cursor.fetchone()
        conn.close()
        
        if not plex_settings or not plex_settings[0] or not plex_settings[1]:
            return None
        
        plex_url = plex_settings[0].rstrip('/')
        plex_token = decrypt(plex_settings[1])
        
        with PlexAPI(
            access_token=plex_token,
            server_url=plex_url
        ) as plex_api:
            res = plex_api.server.get_server_identity()
            if res.object:
                return res.object.media_container.machine_identifier
        
        return None
    except Exception as e:
        print(f"Error getting Plex machine ID: {e}")
        return None

def build_plex_web_link(rating_key, machine_id):
    if not machine_id or not rating_key:
        return ""
    
    return f"https://app.plex.tv/web/app#!/server/{machine_id}/details?key=/library/metadata/{rating_key}"

def search_plex_for_rating_key(title, year, media_type, plex_url, plex_token, tmdb_id=None):
    try:
        decrypted_token = decrypt(plex_token)
        
        if tmdb_id:
            guid = f"tmdb://{tmdb_id}"
            search_query = quote_plus(title)
            api_url = f"{plex_url}/search?query={search_query}&X-Plex-Token={decrypted_token}"
            
            headers = {
                'Accept': 'application/json',
                'X-Plex-Client-Identifier': str(uuid.uuid4())
            }
            
            response = safe_get(api_url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            for provider in data.get('MediaContainer', {}).get('Metadata', []):
                item_type = provider.get('type', '')
                
                if (media_type == 'movie' and item_type == 'movie') or \
                   (media_type == 'show' and item_type == 'show'):
                    
                    guids = provider.get('Guid', [])
                    if isinstance(guids, list):
                        for guid_obj in guids:
                            if isinstance(guid_obj, dict):
                                guid_id = guid_obj.get('id', '')
                                if f"tmdb://{tmdb_id}" in guid_id or f"themoviedb://{tmdb_id}" in guid_id:
                                    print(f"Found exact TMDB match for {title} (tmdb:{tmdb_id})")
                                    return provider.get('ratingKey')
                    
                    single_guid = provider.get('guid', '')
                    if f"tmdb://{tmdb_id}" in single_guid or f"themoviedb://{tmdb_id}" in single_guid:
                        print(f"Found exact TMDB match for {title} (tmdb:{tmdb_id})")
                        return provider.get('ratingKey')
        
        search_query = quote_plus(title)
        api_url = f"{plex_url}/search?query={search_query}&X-Plex-Token={decrypted_token}"
        
        headers = {
            'Accept': 'application/json',
            'X-Plex-Client-Identifier': str(uuid.uuid4())
        }
        
        response = safe_get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        best_match = None
        for provider in data.get('MediaContainer', {}).get('Metadata', []):
            item_title = provider.get('title', '').lower()
            item_year = str(provider.get('year', ''))
            item_type = provider.get('type', '')
            
            if not ((media_type == 'movie' and item_type == 'movie') or \
                    (media_type == 'show' and item_type == 'show')):
                continue
            
            if tmdb_id:
                guids = provider.get('Guid', [])
                guid_match = False
                
                if isinstance(guids, list):
                    for guid_obj in guids:
                        if isinstance(guid_obj, dict):
                            guid_id = guid_obj.get('id', '')
                            if f"tmdb://{tmdb_id}" in guid_id or f"themoviedb://{tmdb_id}" in guid_id:
                                guid_match = True
                                break
                
                single_guid = provider.get('guid', '')
                if f"tmdb://{tmdb_id}" in single_guid or f"themoviedb://{tmdb_id}" in single_guid:
                    guid_match = True
                
                if guid_match:
                    print(f"Found TMDB match for {title} via fallback search (tmdb:{tmdb_id})")
                    return provider.get('ratingKey')
            
            title_match = title.lower() in item_title or item_title in title.lower()
            year_match = not year or str(year) == item_year
            
            if title_match and year_match:
                if item_title == title.lower():
                    print(f"Found exact title match for {title}")
                    return provider.get('ratingKey')
                elif not best_match:
                    best_match = provider.get('ratingKey')
        
        if best_match:
            print(f"Found approximate match for {title}")
            return best_match
        
        print(f"No match found in Plex for {title} ({year})" + (f" [tmdb:{tmdb_id}]" if tmdb_id else ""))
        return None
        
    except Exception as e:
        print(f"Error searching Plex for {title}: {e}")
        traceback.print_exc()
        return None

def fetch_tv_shows_from_plex_sdk(section_id, limit=10, machine_id=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT plex_url, plex_token FROM settings WHERE id = 1")
        plex_settings = cursor.fetchone()
        conn.close()
        
        if not plex_settings or not plex_settings[0] or not plex_settings[1]:
            print("Plex not configured")
            return []
        
        plex_url = plex_settings[0].rstrip('/')
        plex_token = decrypt(plex_settings[1])
        
        api_url = (
            f"{plex_url}/library/sections/{section_id}/all"
            f"?type=2"
            f"&sort=episode.addedAt:desc"
            f"&X-Plex-Container-Start=0"
            f"&X-Plex-Container-Size={limit}"
            f"&X-Plex-Token={plex_token}"
        )
        
        headers = {
            'Accept': 'application/json',
            'X-Plex-Client-Identifier': str(uuid.uuid4())
        }
        
        response = safe_get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        shows = []
        media_container = data.get('MediaContainer', {})
        library_name = media_container.get('librarySectionTitle', '')
        
        for directory in media_container.get('Metadata', []):
            rating_key = str(directory.get('ratingKey', ''))

            show = {
                'title': directory.get('title', 'Unknown'),
                'rating_key': rating_key,
                'year': str(directory.get('year', '')),
                'thumb': directory.get('thumb', ''),
                'art': directory.get('art', ''),
                'summary': directory.get('summary', ''),
                'added_at': str(directory.get('addedAt', '')),
                'updated_at': str(directory.get('updatedAt', '')),
                'content_rating': directory.get('contentRating', ''),
                'duration': str(directory.get('duration', '')),
                'guid': directory.get('guid', ''),
                'key': directory.get('key', ''),
                'media_type': 'show',
                'type': 'show',
                'library_name': library_name,
                'plex_url': build_plex_web_link(rating_key, machine_id) if rating_key else ''
            }
            shows.append(show)
        
        print(f"Fetched {len(shows)} TV shows from Plex API (sorted by recent episode)")
        return shows
            
    except Exception as e:
        print(f"Error fetching TV shows from Plex API: {e}")
        traceback.print_exc()
        return []

def fetch_movies_from_plex_sdk(section_id, limit=10, machine_id=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT plex_url, plex_token FROM settings WHERE id = 1")
        plex_settings = cursor.fetchone()
        conn.close()
        
        if not plex_settings or not plex_settings[0] or not plex_settings[1]:
            print("Plex not configured")
            return []
        
        plex_url = plex_settings[0].rstrip('/')
        plex_token = decrypt(plex_settings[1])
        
        api_url = (
            f"{plex_url}/library/sections/{section_id}/all"
            f"?type=1"
            f"&sort=addedAt:desc"
            f"&X-Plex-Container-Start=0"
            f"&X-Plex-Container-Size={limit}"
            f"&X-Plex-Token={plex_token}"
        )
        
        headers = {
            'Accept': 'application/json',
            'X-Plex-Client-Identifier': str(uuid.uuid4())
        }
        
        response = safe_get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        movies = []
        media_container = data.get('MediaContainer', {})
        library_name = media_container.get('librarySectionTitle', '')
        
        for video in media_container.get('Metadata', []):
            rating_key = str(video.get('ratingKey', ''))
            
            movie = {
                'title': video.get('title', 'Unknown'),
                'rating_key': rating_key,
                'year': str(video.get('year', '')),
                'thumb': video.get('thumb', ''),
                'art': video.get('art', ''),
                'summary': video.get('summary', ''),
                'added_at': str(video.get('addedAt', '')),
                'updated_at': str(video.get('updatedAt', '')),
                'content_rating': video.get('contentRating', ''),
                'duration': str(video.get('duration', '')),
                'guid': video.get('guid', ''),
                'key': video.get('key', ''),
                'media_type': 'movie',
                'type': 'movie',
                'library_name': library_name,
                'plex_url': build_plex_web_link(rating_key, machine_id) if rating_key else ''
            }
            movies.append(movie)
        
        print(f"Fetched {len(movies)} movies from Plex API")
        return movies
            
    except Exception as e:
        print(f"Error fetching movies from Plex API: {e}")
        traceback.print_exc()
        return []

def fetch_albums_from_plex_sdk(section_id, limit=10, machine_id=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT plex_url, plex_token FROM settings WHERE id = 1")
        plex_settings = cursor.fetchone()
        conn.close()
        
        if not plex_settings or not plex_settings[0] or not plex_settings[1]:
            print("Plex not configured")
            return []
        
        plex_url = plex_settings[0].rstrip('/')
        plex_token = decrypt(plex_settings[1])
        
        api_url = (
            f"{plex_url}/library/sections/{section_id}/all"
            f"?type=9"
            f"&sort=addedAt:desc"
            f"&X-Plex-Container-Start=0"
            f"&X-Plex-Container-Size={limit}"
            f"&X-Plex-Token={plex_token}"
        )
        
        headers = {
            'Accept': 'application/json',
            'X-Plex-Client-Identifier': str(uuid.uuid4())
        }
        
        response = safe_get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        albums = []
        media_container = data.get('MediaContainer', {})
        library_name = media_container.get('librarySectionTitle', '')
        
        for album in media_container.get('Metadata', []):
            rating_key = str(album.get('ratingKey', ''))

            album_data = {
                'title': album.get('title', 'Unknown'),
                'rating_key': rating_key,
                'year': str(album.get('year', '')),
                'thumb': album.get('thumb', ''),
                'art': album.get('art', ''),
                'summary': album.get('summary', ''),
                'added_at': str(album.get('addedAt', '')),
                'updated_at': str(album.get('updatedAt', '')),
                'duration': str(album.get('Genre', '')[0]['tag']) if album.get('Genre', '') else '',
                'guid': album.get('guid', ''),
                'key': album.get('key', ''),
                'parent_title': album.get('parentTitle', ''),
                'parent_thumb': album.get('parentThumb', ''),
                'leaf_count': album.get('leafCount', 0),
                'media_type': 'album',
                'type': 'album',
                'library_name': library_name,
                'plex_url': build_plex_web_link(rating_key, machine_id) if rating_key else ''
            }
            albums.append(album_data)
        
        print(f"Fetched {len(albums)} albums from Plex API")
        return albums
            
    except Exception as e:
        print(f"Error fetching albums from Plex API: {e}")
        traceback.print_exc()
        return []

def fetch_recently_added_using_plex_sdk(tautulli_base_url, tautulli_api_key, items_count=10):
    recent_data = []
    
    machine_id = get_plex_machine_id()
    if machine_id:
        print(f"Plex machine ID: {machine_id}")
    else:
        print("Warning: Could not get Plex machine ID, links may not work")
    
    libraries, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_library_names', None, None, "10")
    
    if not libraries:
        print("No libraries found")
        return recent_data
    
    for library in libraries:
        section_id = library['section_id']
        section_type = library['section_type']
        library_name = library['section_name']
        
        print(f"\nFetching recently added for library: {library_name} (type: {section_type})")
        
        items = []
        
        if section_type == 'show':
            items = fetch_tv_shows_from_plex_sdk(section_id, items_count, machine_id)
        elif section_type == 'movie':
            items = fetch_movies_from_plex_sdk(section_id, items_count, machine_id)
        elif section_type == 'artist':
            items = fetch_albums_from_plex_sdk(section_id, items_count, machine_id)
        else:
            print(f"Using Tautulli fallback for library type: {section_type}")
            rd, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_recently_added', section_id, None, str(items_count), 0)
            if rd and rd.get('recently_added'):
                items = rd['recently_added']
                for item in items:
                    item['library_name'] = library_name
                    if 'rating_key' in item and machine_id:
                        item['plex_url'] = build_plex_web_link(item['rating_key'], machine_id)
        
        if items:
            recent_data.append({
                'recently_added': items
            })
    
    return recent_data

def get_collection_items_for_email(collection_key, settings):
    try:
        plex_url = settings.get('plex_url', '').rstrip('/')
        plex_token = settings.get('plex_token', '')
        
        if not plex_url or not plex_token:
            print(f"ERROR: Plex connection not configured for collection {collection_key}")
            return []
        
        collection_items_url = f"{plex_url}/library/metadata/{collection_key}/children"
        headers = {
            'X-Plex-Token': decrypt(plex_token),
            'Accept': 'application/json'
        }
        
        try:
            global plex_headers
            headers.update(plex_headers)
        except NameError:
            pass
        
        print(f"Fetching collection items from: {collection_items_url}")
        response = safe_get(collection_items_url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"ERROR: Failed to fetch collection items. Status: {response.status_code}")
            return []
        
        plex_data = response.json()
        items = []
        
        if 'MediaContainer' in plex_data and 'Metadata' in plex_data['MediaContainer']:
            for item in plex_data['MediaContainer']['Metadata']:
                thumb = item.get('thumb', '')
                if thumb and not thumb.startswith('http'):
                    thumb = f"{plex_url}{thumb}?X-Plex-Token={decrypt(plex_token)}"
                
                art = item.get('art', '')
                if art and not art.startswith('http'):
                    art = f"{plex_url}{art}?X-Plex-Token={decrypt(plex_token)}"
                
                item_info = {
                    'key': item.get('ratingKey'),
                    'title': item.get('title', 'Unknown Title'),
                    'type': item.get('type'),
                    'year': item.get('year'),
                    'tagline': item.get('tagline'),
                    'summary': item.get('summary'),
                    'rating': item.get('rating'),
                    'duration': item.get('duration'),
                    'addedAt': item.get('addedAt'),
                    'thumb': thumb,
                    'art': art,
                    'childCount': item.get('childCount', 0),
                    'leafCount': item.get('leafCount', 0),
                    'parentTitle': item.get('parentTitle'),
                    'grandparentTitle': item.get('grandparentTitle'),
                    'subtype': item.get('type')
                }
                items.append(item_info)
        
        print(f"Successfully fetched {len(items)} items from collection {collection_key}")
        return items
        
    except Exception as e:
        print(f"ERROR: Exception fetching collection items for {collection_key}: {e}")
        traceback.print_exc()
        return []

def run_tautulli_command(base_url, api_key, command, section_id, error, time_range='30', start='0'):
    out_data = None
    
    if command == 'get_users' or command == 'get_library_names':
        api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}"
    elif command == 'get_recently_added':
        api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}&count={time_range}&section_id={section_id}&start={start}"
        print(f"Tautulli API call: get_recently_added with count={time_range}, start={start}")
    else:
        if command == 'get_plays_per_month':
            month_range = str(math.ceil(int(time_range) / 30))
            api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}&time_range={month_range}"
        else:
            api_url = f"{base_url}/api/v2?apikey={decrypt(api_key)}&cmd={command}&time_range={time_range}"

    try:
        response = safe_get(api_url)
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

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT plex_url, plex_token FROM settings WHERE id = 1")
    plex_settings = cursor.fetchone()
    conn.close()
    
    plex_url = plex_settings[0].rstrip('/') if plex_settings and plex_settings[0] else None
    plex_token = plex_settings[1] if plex_settings and plex_settings[1] else None
    machine_id = get_plex_machine_id() if plex_url and plex_token else None

    api_base_url = f"{base_url}/recommendations?user_id="
    recommendations_dict = {}

    for user in user_dict.keys():
        try:
            api_url = f"{api_base_url}{user}"
            response = safe_get(api_url)
            response.raise_for_status()
            data = response.json()

            if plex_url and plex_token and machine_id:
                if 'movie_posters' in data:
                    for item in data['movie_posters']:
                        title = item.get('title', '')
                        year = item.get('year', '')
                        tmdb_id = item.get('tmdbId') or item.get('tmdb_id')
                        
                        rating_key = search_plex_for_rating_key(title, year, 'movie', plex_url, plex_token, tmdb_id=tmdb_id)
                        
                        if rating_key:
                            item['rating_key'] = rating_key
                            item['machine_id'] = machine_id
                            item['plex_url'] = build_plex_web_link(rating_key, machine_id)
                            print(f"Linked movie: {title} (tmdb:{tmdb_id}) -> ratingKey:{rating_key}")
                        else:
                            print(f"Could not find movie in Plex: {title} (tmdb:{tmdb_id})")
                
                if 'show_posters' in data:
                    for item in data['show_posters']:
                        title = item.get('title', '')
                        year = item.get('year', '')
                        tmdb_id = item.get('tmdbId') or item.get('tmdb_id')
                        
                        rating_key = search_plex_for_rating_key(title, year, 'show', plex_url, plex_token, tmdb_id=tmdb_id)
                        
                        if rating_key:
                            item['rating_key'] = rating_key
                            item['machine_id'] = machine_id
                            item['plex_url'] = build_plex_web_link(rating_key, machine_id)
                            print(f"Linked show: {title} (tmdb:{tmdb_id}) -> ratingKey:{rating_key}")
                        else:
                            print(f"Could not find show in Plex: {title} (tmdb:{tmdb_id})")

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
        r = safe_get(url, headers=headers, timeout=10)
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

def get_user_display_name(user_id, users_data, display_preference='email'):
    if not users_data:
        return str(user_id)
    
    user = next((u for u in users_data if str(u.get('user_id')) == str(user_id)), None)
    
    if not user:
        return str(user_id)
    
    if display_preference == 'username':
        return user.get('username') or user.get('email') or str(user_id)
    elif display_preference == 'friendly_name':
        return user.get('friendly_name') or user.get('username') or user.get('email') or str(user_id)
    else:
        return user.get('email') or user.get('username') or str(user_id)

def build_enhanced_user_dict(users_data):
    user_dict = {}
    if users_data:
        for user in users_data:
            if user.get('is_active'):
                user_dict[str(user['user_id'])] = {
                    'email': user.get('email', ''),
                    'username': user.get('username', ''),
                    'friendly_name': user.get('friendly_name', ''),
                    'user_id': user.get('user_id')
                }
    return user_dict

def get_stat_headers(title):
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

def fetch_tautulli_data_for_email(tautulli_base_url, tautulli_api_key, date_range, server_name, items_count=10):
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

        recent_data = fetch_recently_added_using_plex_sdk(tautulli_base_url, tautulli_api_key, items_count)
        data['recent_data'] = recent_data
                
        print(f"Fetched Tautulli data: {len(data['stats'])} stats, {len(data['graph_data'])} graphs, {len(data['recent_data'])} recent sections")
        
    except Exception as e:
        print(f"Error fetching Tautulli data: {e}")
        traceback.print_exc()
    
    return data

def fetch_recent_data_for_index(tautulli_base_url, tautulli_api_key, count):
    return fetch_recently_added_using_plex_sdk(tautulli_base_url, tautulli_api_key, int(count))

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
        
        is_local_static = (
            image_url.startswith('/static/') or 
            image_url.startswith('/static\\') or
            'static/img/' in image_url or
            'static/uploads/' in image_url
        )
        
        if is_local_static:
            full_url = urljoin(base_url or "http://127.0.0.1:6397", image_url)
            print(f"Local static file, fetching directly: {full_url}")
        elif image_url.startswith('/library/') or image_url.startswith('/photo/'):
            full_url = urljoin(base_url or "http://127.0.0.1:6397", f"/proxy-art{image_url}")
            print(f"Plex image, using proxy: {full_url}")
        elif image_url.startswith('http'):
            parsed = urlparse(image_url)
            
            if '/library/' in parsed.path or '/photo/' in parsed.path or '/composite/' in parsed.path:
                path = parsed.path
                query = parsed.query
                
                if query:
                    params = parse_qs(query)
                    if 'X-Plex-Token' in params:
                        del params['X-Plex-Token']
                    
                    if params:
                        query_str = urlencode(params, doseq=True)
                        path = f"{path}?{query_str}"
                
                full_url = urljoin(base_url or "http://127.0.0.1:6397", f"/proxy-art{path}")
                print(f"Full Plex URL, using proxy: {full_url}")
            else:
                full_url = image_url
                print(f"External URL, fetching directly: {full_url}")
        else:
            full_url = urljoin(base_url or "http://127.0.0.1:6397", image_url)
            print(f"Default case, fetching: {full_url}")
        
        print(f"Final URL to fetch: {full_url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
        }
        
        response = safe_get(full_url, timeout=15, headers=headers)
        print(f"Response status: {response.status_code}")
        print(f"Response content length: {len(response.content)}")
        
        response.raise_for_status()
        
        if len(response.content) < 100:
            print(f"Warning: Response content too small ({len(response.content)} bytes), likely not a valid image")
            return None
        
        content_type = response.headers.get('Content-Type')
        print(f"Content-Type: {content_type}")
        
        if not content_type or not content_type.startswith('image/'):
            print(f"Warning: Invalid content type: {content_type}")
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
        
    except requests.exceptions.Timeout as e:
        print(f"Timeout fetching image {image_url}: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Request error fetching image {image_url}: {e}")
        return None
    except Exception as e:
        print(f"Error processing image {image_url}: {e}")
        traceback.print_exc()
        return None

def fetch_and_attach_blurred_image(image_url, msg_root, cid_name, base_url=""):
    try:
        if image_url.startswith('/'):
            full_url = urljoin(base_url or "http://127.0.0.1:6397", image_url)
        else:
            full_url = image_url
        
        response = safe_get(full_url, timeout=10)
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

def truncate_text(text, max_chars=28):
    if len(text) <= max_chars:
        return text
    return text[:max_chars-3] + '...'

def build_stats_html_with_cid_background(stat_data, msg_root, theme_colors, base_url="", date_range=""):
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
        f'<th style="padding: 12px; background-color: rgba(52, 58, 64, 0.9); color: white; font-weight: bold; border: none; font-family: \'IBM Plex Sans\', \'Segoe UI\', Helvetica, Arial, sans-serif; font-size: 14px; text-align: left;">{h}</th>' 
        for h in headers
    ])
    
    rows_html = ""
    for row in rows:
        cells = get_stat_cells(title, row)
        cells_html = "".join([
            f'<td style="padding: 12px; background-color: rgba(255, 255, 255, 0.5); color: #333; border-bottom: 1px solid rgba(222, 226, 230, 0.8); font-family: \'IBM Plex Sans\', \'Segoe UI\', Helvetica, Arial, sans-serif; font-size: 14px;">{cell}</td>' 
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
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
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
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
        margin: 0;
        position: relative;
        z-index: 2;
    """
    
    table_style = """
        width: 100%;
        border-collapse: collapse;
        position: relative;
        z-index: 2;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """

    if date_range == "":
        date_range = get_cache_info('stats')['params']['time_range']
    
    return f"""
        <div style="{container_style}">
            {overlay}
            <div style="position: relative; z-index: 1;">
                <div style="{header_style}">{title} - Last {date_range} days</div>
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

def build_recently_added_html_with_cids(recent_data, msg_root, theme_colors, library_filter=None, base_url="", max_items=None):
    if not recent_data:
        return f"""
        <div style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
            <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">No recently added items available.</p>
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

    if max_items and len(items) > max_items:
        items = items[:max_items]
    
    if not items:
        return f"""
        <div style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
            <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">No recently added items found{f' for {library_filter}' if library_filter else ''}.</p>
        </div>
        """
    
    items_html = ""
    items_per_row = 5
    
    for i in range(0, len(items), items_per_row):
        row_items = items[i:i + items_per_row]
        row_html = '<tr class="recently-added-row">'
        
        for j, item in enumerate(row_items):
            full_title = item.get('title', 'Unknown')
            title = truncate_text(full_title, 23)
            year = item.get('year', '')
            if not year and (item.get('media_type') or item.get('type', '')).lower() == 'album':
                year = item.get('grandparent_title') or item.get('parent_title') or ''
            library = item.get('library_name', '')
            added_date = ""
            duration = ""

            item_type = (item.get('media_type') or item.get('type') or '').lower()
            if item_type in ['episode', 'season']:
                summary = (
                    item.get('grandparent_tagline') or 
                    item.get('grandparent_summary') or 
                    item.get('parent_summary') or 
                    item.get('tagline') or 
                    item.get('summary', '')
                )
            else:
                summary = item.get('tagline') or item.get('summary', '')
            
            poster_cid = None
            if item_type in ['episode', 'season']:
                poster_candidates = [
                    item.get('grandparent_thumb'),
                    item.get('parent_thumb'), 
                    item.get('thumb'),
                    item.get('art')
                ]
            else:
                poster_candidates = [
                    item.get('thumb'),
                    item.get('art'),
                    item.get('parent_thumb'),
                    item.get('grandparent_thumb')
                ]

            for candidate in poster_candidates:
                if candidate:
                    poster_url = f"/proxy-art{candidate}" if not candidate.startswith('/proxy-art') else candidate
                    poster_cid = fetch_and_attach_image(
                        poster_url, 
                        msg_root, 
                        f"recent-{i}-{j}", 
                        base_url
                    )
                    if poster_cid:
                        break
                        
            if item.get('updated_at'):
                try:
                    timestamp = item['updated_at']
                    if isinstance(timestamp, str) and timestamp.isdigit():
                        timestamp = int(timestamp)
                    
                    if isinstance(timestamp, (int, float)):
                        dt = datetime.fromtimestamp(timestamp)
                    else:
                        dt = datetime.fromisoformat(str(timestamp))

                    now = datetime.now()
                    if dt.tzinfo:
                        now = datetime.now(timezone.utc)
                        dt = dt.replace(tzinfo=timezone.utc)
                    
                    diff_days = (now - dt).days
                    
                    if diff_days < 0:
                        added_date = f"in {abs(diff_days)} days"
                    elif diff_days == 0:
                        added_date = "today"
                    elif diff_days == 1:
                        added_date = "yesterday"
                    else:
                        added_date = f"{diff_days} days ago"

                except Exception as e:
                    if item.get('originally_available_at'):
                        try:
                            timestamp = item['originally_available_at']
                            if isinstance(timestamp, str) and timestamp.isdigit():
                                timestamp = int(timestamp)
                            
                            if isinstance(timestamp, (int, float)):
                                dt = datetime.fromtimestamp(timestamp)
                            else:
                                dt = datetime.fromisoformat(str(timestamp))

                            now = datetime.now()
                            if dt.tzinfo:
                                now = datetime.now(timezone.utc)
                                dt = dt.replace(tzinfo=timezone.utc)
                            
                            diff_days = (now - dt).days
                            
                            if diff_days < 0:
                                added_date = f"in {abs(diff_days)} days"
                            elif diff_days == 0:
                                added_date = "today"
                            elif diff_days == 1:
                                added_date = "yesterday"
                            else:
                                added_date = f"{diff_days} days ago"

                        except Exception as e2:
                            added_date = ""
            
            if item_type == 'album':
                duration = item.get('duration') or item.get('grandparent_title') or item.get('parent_title') or 'Audio'
            else:
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
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
            """

            plex_url = item.get('plex_url', '')

            if poster_cid:
                poster_bg_url = f"cid:{poster_cid}"
                
                card_html = f"""
                    <div class="recently-added-card" style="
                        background-color: {theme_colors['card_bg']};
                        border-radius: 12px;
                        overflow: hidden;
                        border: 1px solid {theme_colors['border']};
                        width: 100%;
                        max-width: 124px;
                        margin: 0 auto;
                        box-shadow: 0 6px 18px rgba(0, 0, 0, 0.6);
                    ">
                        <div class="card-poster-wrapper" style="position: relative; display: block; text-align: right;">
                            <div class="card-poster" style="
                                background-image: url('{poster_bg_url}');
                            ">
                                {f'''
                                <div class="card-poster-badge"
                                    style="position: absolute; display: inline-block; bottom: 1px; right: 1px; max-width: fit-content; text-align: right; margin-left: auto;">
                                    {added_date}
                                </div>
                                ''' if added_date else ''}
                            </div>
                        </div>
                        
                        <div class="card-content" style="
                            padding: 6px;
                            background-color: {theme_colors['card_bg']};
                            color: {theme_colors['text']};
                            min-height: 135px;
                        ">
                            <div style="
                                font-weight: bold;
                                font-size: 14px;
                                color: {theme_colors['text']};
                                margin-bottom: 1px;
                                line-height: 1.2;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                word-wrap: break-word;
                                overflow-wrap: break-word;
                            ">{title}</div>
                            
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['muted_text']};
                                margin-bottom: 2px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{truncate_text(' • '.join(filter(None, [str(year) if year else '', duration])), 36)}</div>
                            
                            {f'''
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['text']};
                                opacity: 0.8;
                                line-height: 1.3;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                word-wrap: break-word;
                                overflow-wrap: break-word;
                            ">{summary[:84]}{'...' if len(summary) > 84 else ''}</div>
                            ''' if summary else ''}
                        </div>
                    </div>
                """

                if plex_url:
                    card_html = f'''
                        <a href="{plex_url}" 
                        style="text-decoration: none; color: inherit; display: block;" 
                        target="_blank"
                        title="Open in Plex">
                            {card_html}
                        </a>
                    '''
                else:
                    card_html = card_html
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
                        height: 320px;
                    ">
                        <div style="display: table-cell; vertical-align: middle;">
                            <div style="
                                font-weight: bold;
                                font-size: 14px;
                                color: {theme_colors['text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{title}</div>
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['muted_text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{' • '.join(filter(None, [str(year) if year else '', duration, library, f'Added {added_date}' if added_date else '']))}</div>
                            {f'''
                            <div style="
                                font-size: 11px;
                                color: {theme_colors['text']};
                                opacity: 0.8;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{summary[:100]}{'...' if len(summary) > 100 else ''}</div>
                            ''' if summary else ''}
                        </div>
                    </div>
                """

                if plex_url:
                    card_html = f'''
                        <a href="{plex_url}" 
                        style="text-decoration: none; color: inherit; display: block;" 
                        target="_blank"
                        title="Open in Plex">
                            {card_html}
                        </a>
                    '''
                else:
                    card_html = card_html
            
            row_html += f'<td class="recently-added-cell" style="{cell_style}">{card_html}</td>'
        
        while len(row_items) < items_per_row:
            row_html += f'<td class="recently-added-cell" style="width: 20%; padding: 8px;"></td>'
            row_items.append(None)
        
        row_html += "</tr>"
        items_html += row_html
    
    container_style = f"""
        background-color: {theme_colors['card_bg']};
        padding-bottom: 10px;
        border-radius: 8px;
        margin: 20px 0;
        border: 1px solid {theme_colors['border']};
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
        overflow: hidden;
        max-width: 100%;
    """
    
    title_style = f"""
        text-align: center;
        color: {theme_colors['text']};
        margin: 0 0 10px 0;
        font-size: 24px;
        font-weight: bold;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    table_style = """
        width: 100%;
        border-collapse: collapse;
        margin: 0;
        padding: 0;
        table-layout: fixed;
    """
    
    return f"""
        <div style="{container_style}">
            <h2 style="{title_style}">Recently Added{f' - {library_filter}' if library_filter else ''}</h2>
            <table class="recently-added-table" style="{table_style}">
                {items_html}
            </table>
        </div>
    """

def build_recommendations_html_with_cids(recs_data, msg_root, theme_colors, user_emails=None, base_url="", display_preference='email', users_full_data=None):
    if not recs_data:
        return ""
    
    html_sections = []
    
    for user_id, user_recs in recs_data.items():
        if user_emails and str(user_id) not in [str(k) for k in user_emails.keys()]:
            continue

        if users_full_data:
            display_name = get_user_display_name(user_id, users_full_data, display_preference)
        elif user_emails:
            user_email_value = user_emails.get(str(user_id), str(user_id))
            display_name = user_email_value
        else:
            display_name = str(user_id)
        
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
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
            """
            
            user_title_style = f"""
                text-align: center;
                color: {theme_colors['text']};
                margin: 0 0 20px 0;
                font-size: 24px;
                font-weight: bold;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
            """
            
            user_section = f"""
                <div style="{container_style}" data-recs-user="{user_id}">
                    <h2 style="{user_title_style}">Recommendations for {display_name}</h2>
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
            overview = item.get('overview', '')[:100] + "..." if item.get('overview') else ""
            runtime = item.get('runtime', '')

            if is_unavailable:
                href = item.get('href', '#')
                link_title = "Request on Overseerr"
            else:
                if item.get('plex_url'):
                    href = item['plex_url']
                    link_title = "Open in Plex"
                elif item.get('rating_key') and item.get('machine_id'):
                    href = build_plex_web_link(item['rating_key'], item['machine_id'])
                    link_title = "Open in Plex"
                else:
                    search_query = quote_plus(title_text)
                    href = f"https://app.plex.tv/desktop#!/search?query={search_query}"
                    link_title = "Search in Plex"
            
            vote_text = f"★ {vote:.1f}" if isinstance(vote, (int, float)) and vote > 0 else ""
            
            cell_style = f"""
                width: 20%;
                padding: 6px;
                vertical-align: top;
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
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
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
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
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
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
                                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                    margin-top: 132px;
                                ">{title_text}</div>
                                {f'''
                                <div style="
                                    font-size: 10px;
                                    color: rgba(255, 255, 255, 0.8);
                                    margin-top: 2px;
                                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
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
                            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            border-top: 1px solid {theme_colors['border']};
                        ">
                            {overview[:80]}{'...' if len(overview) > 80 else ''}
                        </div>
                        ''' if overview else ''}
                    </div>
                """
                
                card_html = f'<a href="{href}" style="text-decoration: none; color: inherit; display: block;" target="_blank" title="{link_title}">{card_content}</a>'
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
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{title_text}</div>
                            <div style="
                                font-size: 10px;
                                color: {theme_colors['muted_text']};
                                margin-bottom: 8px;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            ">{' • '.join(filter(None, [str(year) if year else '', vote_text, runtime, 'Unavailable' if is_unavailable else '']))}</div>
                            {f'''
                            <div style="
                                font-size: 10px;
                                color: {theme_colors['text']};
                                opacity: 0.8;
                                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
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
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
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

def build_individual_item_card_html(item, theme_colors, msg_root, base_url=""):
    item_title = item.get('title', 'Unknown Title')
    year = item.get('year')
    item_type = item.get('type', 'unknown')
    
    display_title = item_title
    if year:
        display_title += f" ({year})"
    
    type_icons = {
        'movie': '🎬',
        'show': '📺', 
        'album': '💿',
        'track': '🎵',
        'artist': '🎤'
    }
    type_icon = type_icons.get(item_type, '📄')
    
    subtitle = ""
    if item.get('parentTitle') and item_type in ['album', 'track']:
        subtitle = item['parentTitle']
    elif item.get('grandparentTitle') and item_type == 'track':
        subtitle = item['grandparentTitle']
    elif item_type == 'show':
        season_count = item.get('childCount', 0)
        episode_count = item.get('leafCount', 0)
        if season_count > 0:
            subtitle = f"{season_count} season{'s' if season_count != 1 else ''}"
        elif episode_count > 0:
            subtitle = f"{episode_count} episode{'s' if episode_count != 1 else ''}"
    
    poster_cid = None
    poster_url = item.get('thumb', '')
    if poster_url:
        print(f"Attempting to fetch thumb image: {poster_url}")
        if poster_url.startswith('http'):
            poster_cid = fetch_and_attach_image(poster_url, msg_root, f"collection_{item.get('key', 'unknown')}_thumb", base_url)
        else:
            full_poster_url = f"/proxy-art{poster_url if poster_url.startswith('/') else '/' + poster_url}"
            poster_cid = fetch_and_attach_image(full_poster_url, msg_root, f"collection_{item.get('key', 'unknown')}_thumb", base_url)
        print(f"Thumb CID result: {poster_cid}")
    
    if not poster_cid:
        print("No thumb CID, trying art URL...")
        art_url = item.get('art', '')
        if art_url:
            print(f"Attempting to fetch art image: {art_url}")
            if art_url.startswith('http'):
                poster_cid = fetch_and_attach_image(art_url, msg_root, f"collection_{item.get('key', 'unknown')}_art", base_url)
            else:
                full_art_url = f"/proxy-art{art_url if art_url.startswith('/') else '/' + art_url}"
                poster_cid = fetch_and_attach_image(full_art_url, msg_root, f"collection_{item.get('key', 'unknown')}_art", base_url)
            print(f"Art CID result: {poster_cid}")
    
    if poster_cid:
        return f"""
        <table cellpadding="0" cellspacing="0" border="0" style="
            background-color: {theme_colors['card_bg']};
            border-radius: 12px;
            width: 120px;
            margin: 0;
        ">
            <tr>
                <td style="
                    background-image: url('cid:{poster_cid}');
                    background-size: cover;
                    background-position: center;
                    background-repeat: no-repeat;
                    height: 180px;
                    background-color: #f8f9fa;
                    border-radius: 12px;
                    position: relative;
                    vertical-align: top;
                ">
                    <table cellpadding="0" cellspacing="0" border="0" width="100%">
                        <tr>
                            <td style="text-align: right;">
                                <div style="
                                    background-color: rgba(0, 0, 0, 0.8);
                                    color: white;
                                    padding: 4px 6px;
                                    border-radius: 4px;
                                    font-size: 10px;
                                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                    line-height: 1;
                                    display: inline-block;
                                    margin: 6px;
                                ">
                                    {type_icon}
                                </div>
                            </td>
                        </tr>
                        <tr>
                            <td style="height: 148px; vertical-align: bottom;">
                                <div style="
                                    background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent);
                                    border-radius: 0 0 11px 11px;
                                    padding: 6px;
                                ">
                                    <div style="
                                        font-weight: bold;
                                        font-size: 11px;
                                        color: white;
                                        line-height: 1.2;
                                        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                    ">{display_title}</div>
                                    {f'''<div style="
                                        font-size: 9px;
                                        color: #ccc;
                                        line-height: 1.2;
                                        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                        margin-top: 2px;
                                    ">{subtitle}</div>''' if subtitle else ''}
                                </div>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
        """
    else:
        return f"""
        <table cellpadding="0" cellspacing="0" border="0" style="
            background-color: {theme_colors['card_bg']};
            border-radius: 12px;
            border: 1px solid {theme_colors['border']};
            width: 120px;
            height: 180px;
            margin: 0;
        ">
            <tr>
                <td style="
                    text-align: center;
                    vertical-align: middle;
                    padding: 12px;
                    color: {theme_colors['text']};
                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                ">
                    <div style="
                        font-size: 11px;
                        margin-bottom: 8px;
                    ">{type_icon}</div>
                    <div style="
                        font-weight: bold;
                        font-size: 14px;
                        line-height: 1.2;
                        margin-bottom: 8px;
                        padding: 2px;
                    ">{display_title}</div>
                    {f'''<div style="
                        font-size: 9px;
                        color: {theme_colors['muted_text']};
                        line-height: 1.2;
                    ">{subtitle}</div>''' if subtitle else ''}
                </td>
            </tr>
        </table>
        """

def build_collection_card_html(collection, theme_colors, msg_root, base_url=""):
    poster_cid = None
    poster_url = collection.get('thumb', '')
    if poster_url:
        print(f"Attempting to fetch thumb image: {poster_url}")
        if poster_url.startswith('http'):
            poster_cid = fetch_and_attach_image(poster_url, msg_root, f"collection_{collection.get('key', 'unknown')}_thumb", base_url)
        else:
            full_poster_url = f"/proxy-art{poster_url if poster_url.startswith('/') else '/' + poster_url}"
            poster_cid = fetch_and_attach_image(full_poster_url, msg_root, f"collection_{collection.get('key', 'unknown')}_thumb", base_url)
        print(f"Thumb CID result: {poster_cid}")
    
    if not poster_cid:
        print("No thumb CID, trying art URL...")
        art_url = collection.get('art', '')
        if art_url:
            print(f"Attempting to fetch art image: {art_url}")
            if art_url.startswith('http'):
                poster_cid = fetch_and_attach_image(art_url, msg_root, f"collection_{collection.get('key', 'unknown')}_art", base_url)
            else:
                full_art_url = f"/proxy-art{art_url if art_url.startswith('/') else '/' + art_url}"
                poster_cid = fetch_and_attach_image(full_art_url, msg_root, f"collection_{collection.get('key', 'unknown')}_art", base_url)
            print(f"Art CID result: {poster_cid}")
    
    collection_title = collection.get('title', 'Unknown Collection')
    count = collection.get('childCount', 0)
    subtype = collection.get('subtype', 'unknown')
    summary = collection.get('summary', '')
    type_icon = '📽️' if subtype == 'movie' else '📺' if subtype == 'show' else '🎧'
    
    if poster_cid:
        poster_bg_url = f"cid:{poster_cid}"
        print(f"Final poster src for {collection_title}: {poster_bg_url}")
        
        return f"""
            <table cellpadding="0" cellspacing="0" border="0" style="
                background-color: {theme_colors['card_bg']};
                border-radius: 12px;
                width: 120px;
                margin: 0;
            ">
                <tr>
                    <td style="
                        background-image: url('{poster_bg_url}');
                        background-size: cover;
                        background-position: center;
                        background-repeat: no-repeat;
                        height: 180px;
                        background-color: #f8f9fa;
                        border-radius: 12px;
                        position: relative;
                        vertical-align: top;
                    ">
                        <table cellpadding="0" cellspacing="0" border="0" width="100%">
                            <tr>
                                <td style="text-align: right;">
                                    <div style="
                                        background-color: rgba(0, 0, 0, 0.8);
                                        color: white;
                                        padding: 4px 6px;
                                        border-radius: 4px;
                                        font-size: 10px;
                                        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                        line-height: 1;
                                        display: inline-block;
                                        margin: 6px;
                                    ">
                                        {type_icon} {count}
                                    </div>
                                </td>
                            </tr>
                            <tr>
                                <td style="height: 148px; vertical-align: bottom;">
                                    <div style="
                                        background: linear-gradient(to top, rgba(0, 0, 0, 0.8), transparent);
                                        border-radius: 0 0 11px 11px;
                                        padding: 6px;
                                    ">
                                        <div style="
                                            font-weight: bold;
                                            font-size: 12px;
                                            color: white;
                                            line-height: 1.2;
                                            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                                        ">{collection_title}</div>
                                    </div>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        """
    else:
        print(f"No valid image data for {collection_title}, using placeholder")
        return f"""
            <table cellpadding="0" cellspacing="0" border="0" style="
                background-color: {theme_colors['card_bg']};
                border-radius: 12px;
                border: 1px solid {theme_colors['border']};
                width: 120px;
                height: 180px;
                margin: 0;
            ">
                <tr>
                    <td style="
                        text-align: center;
                        vertical-align: middle;
                        padding: 12px;
                    ">
                        <div style="
                            font-weight: bold;
                            font-size: 14px;
                            color: {theme_colors['text']};
                            margin-bottom: 8px;
                            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                            padding: 2px;
                        ">{collection_title}</div>
                        <div style="
                            font-size: 11px;
                            color: {theme_colors['muted_text']};
                            font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                        ">{type_icon} {count} items</div>
                    </td>
                </tr>
            </table>
        """

def build_collections_html_with_cids(all_collections, msg_root, theme_colors, base_url="", custom_title=None, expanded_collections=None, group_index=0):
    if not all_collections:
        return f"""
        <div style="background-color: {theme_colors['card_bg']}; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid {theme_colors['border']}; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">
            <p style="text-align: center; color: {theme_colors['muted_text']}; padding: 20px; margin: 0; font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;">No collections available.</p>
        </div>
        """
    
    expanded_collections = expanded_collections or {}
    all_items_to_display = []
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT plex_url, plex_token FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    
    plex_settings = {}
    if row and row[0] and row[1]:
        plex_settings = {
            'plex_url': row[0],
            'plex_token': row[1]
        }

    for collection_index, collection in enumerate(all_collections):
        collection_id = f"{group_index}-{collection_index}-{collection.get('key')}"

        if collection_id in expanded_collections and plex_settings:
            print(f"Collection {collection_id} is expanded, fetching individual items...")
            individual_items = get_collection_items_for_email(collection.get('key'), plex_settings)
            
            for item in individual_items:
                item['is_individual_item'] = True
                item['original_collection'] = collection.get('title', 'Unknown Collection')
                all_items_to_display.append(item)
        else:
            collection['is_individual_item'] = False
            all_items_to_display.append(collection)
    
    items_html = ""
    items_per_row = 5
    
    for i in range(0, len(all_items_to_display), items_per_row):
        row_items = all_items_to_display[i:i + items_per_row]
        is_partial_row = len(row_items) < items_per_row
        
        if is_partial_row:
            items_count = len(row_items)
            
            row_html = f'<tr><td colspan="{items_per_row}" style="text-align: center; padding: 8px;">'
            row_html += '<table cellpadding="0" cellspacing="0" border="0" style="margin: 0 auto; border-collapse: separate;">'
            row_html += '<tr>'
            
            for j, item in enumerate(row_items):
                if items_count == 1:
                    cell_spacing = "0"
                elif items_count == 2:
                    cell_spacing = "60px" if j == 0 else "0"
                elif items_count == 3:
                    cell_spacing = "40px" if j < 2 else "0"
                elif items_count == 4:
                    cell_spacing = "20px" if j < 3 else "0"
                else:
                    cell_spacing = "8px" if j < items_count - 1 else "0"

                if item.get('is_individual_item'):
                    card_html = build_individual_item_card_html(item, theme_colors, msg_root, base_url)
                else:
                    card_html = build_collection_card_html(item, theme_colors, msg_root, base_url)
                
                row_html += f'<td style="vertical-align: top; padding-right: {cell_spacing};">{card_html}</td>'
            
            row_html += '</tr></table></td></tr>'
            items_html += row_html
        else:
            row_html = "<tr style='text-align: center;'>"
            
            for j, item in enumerate(row_items):
                cell_style = f"""
                    width: 20%;
                    padding: 8px;
                    vertical-align: top;
                    font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
                """

                if item.get('is_individual_item'):
                    card_html = build_individual_item_card_html(item, theme_colors, msg_root, base_url)
                else:
                    card_html = build_collection_card_html(item, theme_colors, msg_root, base_url)
                
                row_html += f'<td style="{cell_style}">{card_html}</td>'
            
            row_html += "</tr>"
            items_html += row_html
    
    container_style = f"""
        background-color: {theme_colors['card_bg']};
        border-radius: 8px;
        margin: 20px 0;
        border: 1px solid {theme_colors['border']};
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    title_style = f"""
        text-align: center;
        color: {theme_colors['text']};
        margin: 0 0 20px 0;
        font-size: 24px;
        font-weight: bold;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    table_style = """
        width: 100%;
        border-collapse: collapse;
        margin: 0;
        padding: 0;
    """

    display_title = custom_title if custom_title else "Collections"
    
    return f"""
        <div style="{container_style}">
            <h2 style="{title_style}">{display_title}</h2>
            <table cellpadding="0" cellspacing="0" border="0" style="{table_style}">
                {items_html}
            </table>
        </div>
    """

def attach_logo_image(msg_root, logo_filename, custom_logo_filename, base_url=""):
    if logo_filename == 'custom':
        logo_url = f"/static/uploads/logos/{custom_logo_filename}"
    else:
        logo_url = f"/static/img/{logo_filename}"
    return fetch_and_attach_image(logo_url, msg_root, "logo", base_url)

def build_email_html_with_all_cids(template_data, tautulli_data, msg_root, display_preference, users_data, recommendations_data=None, user_dict=None, base_url="", target_user_key=None, is_scheduled=False, items_count=None, date_range="", expanded_collections=None):
    selected_items = json.loads(template_data.get('selected_items', '[]'))
    email_text = template_data.get('email_text', '')
    subject = template_data.get('subject', '')
    server_name = tautulli_data.get('settings', {}).get('server_name', 'Plex Server')
    logo_filename = tautulli_data.get('settings', {}).get('logo_filename')
    custom_logo_filename = tautulli_data.get('settings', {}).get('custom_logo_filename')
    logo_width = tautulli_data.get('settings', {}).get('logo_width')
    expanded_collections = expanded_collections or {}
    
    theme_colors = get_email_theme_colors()

    if logo_filename == '' or logo_filename is None:
        if theme_colors['email_theme'] == 'custom':
            pass
        else:
            logo_filename = 'Asset_94x.png'

    if logo_width == '' or logo_width is None:
        if theme_colors['email_theme'] == 'custom':
            pass
        else:
            logo_width = 80
    
    logo_src = ""
    if logo_filename != '' and logo_filename is not None and logo_width != '' and logo_width is not None:
        logo_cid = attach_logo_image(msg_root, logo_filename, custom_logo_filename, base_url)
        if logo_filename == 'custom' and custom_logo_filename:
            logo_src = f"cid:{logo_cid}" if logo_cid else f"/static/uploads/logos/{custom_logo_filename}"
        else:
            logo_src = f"cid:{logo_cid}" if logo_cid else f"/static/img/{logo_filename}"
    
    content_html = ""
    
    if email_text.strip():
        content_html += build_text_block_html(email_text, 'textblock', theme_colors)
    
    for group_index, item in enumerate(selected_items):
        item_type = item.get('type', '')
        
        if item_type in ['textblock', 'titleblock', 'headerblock']:
            content = item.get('content', '').strip()
            if content:
                content_html += build_text_block_html(content, item_type, theme_colors)
        
        elif item_type == 'stat':
            stat_index = int(item['id'].split('-')[1])
            if stat_index < len(tautulli_data.get('stats', [])):
                stat_data = tautulli_data['stats'][stat_index]
                content_html += build_stats_html_with_cid_background(stat_data, msg_root, theme_colors, base_url, date_range)
        
        elif item_type == 'graph':
            content_html += build_graph_html_with_frontend_image(item, msg_root)
        
        elif item_type == 'recently added':
            library_filter = item.get('raLibrary')
            recent_data = tautulli_data.get('recent_data', [])

            max_items = items_count
            if max_items is None:
                cache_info = get_cache_info('recent_data')
                if cache_info.get('params'):
                    try:
                        max_items = int(cache_info['params'].get('count', 10))
                    except (TypeError, ValueError):
                        max_items = 10

            content_html += build_recently_added_html_with_cids(recent_data, msg_root, theme_colors, library_filter, base_url, max_items)
        
        elif item_type == 'recommendations':
            if recommendations_data:
                if target_user_key:
                    if item.get('userKey') == str(target_user_key):
                        filtered_recommendations = {target_user_key: recommendations_data.get(target_user_key, {})}
                        filtered_user_dict = {target_user_key: user_dict.get(target_user_key, target_user_key)} if user_dict else {target_user_key: target_user_key}
                        content_html += build_recommendations_html_with_cids(filtered_recommendations, msg_root, theme_colors, filtered_user_dict, base_url, display_preference, users_data)
                else:
                    content_html += build_recommendations_html_with_cids(recommendations_data, msg_root, theme_colors, user_dict, base_url, display_preference, users_data)
        
        elif item_type == 'collection_group':
            group_title = item.get('title', 'Collections')
            group_collections = item.get('collections', [])
            if group_collections:
                content_html += build_collections_html_with_cids(group_collections, msg_root, theme_colors, base_url, group_title, expanded_collections, group_index)

    return build_complete_email_html_with_cid_logo(content_html, server_name, subject, logo_src, logo_width, is_scheduled)

def build_complete_email_html_with_cid_logo(content_html, server_name, subject, logo_src, logo_width, is_scheduled=False):
    theme_colors = get_email_theme_colors()
    
    css = build_email_css_from_theme(theme_colors, logo_width)
    
    body_style = f"""
        margin: 0;
        padding: 0;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
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
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    header_style = f"""
        background: linear-gradient(135deg, {theme_colors['accent']} 0%, {theme_colors['primary']} 100%);
        color: white;
        padding: 10px 20px;
        text-align: center;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
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
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
        color: white;
    """
    
    content_style = f"""
        padding: 10px 15px;
        color: {theme_colors['text']};
        background-color: {theme_colors['card_bg']};
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    footer_style = f"""
        background-color: {theme_colors['secondary']};
        padding: 20px;
        text-align: center;
        border-top: 3px solid {theme_colors['primary']};
        color: {theme_colors['muted_text']};
        font-size: 12px;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    footer_link_style = f"""
        color: {theme_colors['accent']};
        text-decoration: none;
    """

    logo_html = ""
    if logo_src != "" and logo_src is not None and logo_width != "" and logo_width is not None:
        logo_html = f'<img src="{logo_src}" alt="{server_name}" class="email-logo" style="{logo_style}">'
    
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
                            {logo_html}
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

def send_standard_email_with_cids(to_emails, subject, selected_items, from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, settings, from_name, expanded_collections=None):
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
            None,
            None,
            base_url,
            None,
            False,
            None,
            "",
            expanded_collections
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

def send_recommendations_email_with_cids(to_emails, subject, user_dict, selected_items, from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, settings, from_name, expanded_collections=None):
    try:
        rec_user_keys = set()
        for item in selected_items:
            if item.get('type') == 'recommendations' and item.get('userKey'):
                rec_user_keys.add(item['userKey'])
        
        if not rec_user_keys:
            return send_standard_email_with_cids(
                to_emails, subject, selected_items, from_email, alias_email, 
                reply_to_email, password, smtp_username, smtp_server, smtp_port,
                smtp_protocol, settings, from_name, expanded_collections
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
                smtp_server, smtp_port, smtp_protocol, settings, from_name, expanded_collections
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

def send_single_user_email_with_cids(recipients, subject, selected_items, user_key, recommendations_data, from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, settings, from_name, expanded_collections=None):
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

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT recipient_display_name, tautulli_url, tautulli_api FROM settings WHERE id = 1")
        settings_row = cursor.fetchone()
        conn.close()
        
        display_preference = settings_row[0] if settings_row and settings_row[0] else 'email'
        tautulli_url = settings_row[1] if settings_row else None
        tautulli_api = settings_row[2] if settings_row else None
        
        users_full_data = None
        if tautulli_url and tautulli_api:
            users_data, _ = run_tautulli_command(tautulli_url.rstrip('/'), tautulli_api, 'get_users', 'Users', None)
            if users_data:
                users_full_data = users_data

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
            display_preference,
            users_full_data,
            recommendations_data,
            user_dict,
            base_url,
            target_user_key=user_key,
            is_scheduled=False,
            items_count=None,
            date_range="",
            expanded_collections=expanded_collections
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
        schedule_cursor.execute("SELECT date_range, items_count FROM email_schedules WHERE id = ?", (schedule_id,))
        schedule_result = schedule_cursor.fetchone()
        schedule_conn.close()

        display_name_conn = sqlite3.connect(DB_PATH)
        display_name_cursor = display_name_conn.cursor()
        display_name_cursor.execute("SELECT recipient_display_name FROM settings WHERE id = 1")
        display_pref_row = display_name_cursor.fetchone()
        display_preference = display_pref_row[0] if display_pref_row else 'email'
        display_name_conn.close()
        
        date_range = schedule_result[0] if schedule_result else 7
        items_count = schedule_result[1] if schedule_result else 10

        if email_list_id == 0 or email_list_id == 'ALL':
            settings_conn = sqlite3.connect(DB_PATH)
            settings_cursor = settings_conn.cursor()
            settings_cursor.execute("SELECT tautulli_url, tautulli_api FROM settings WHERE id = 1")
            settings_row = settings_cursor.fetchone()
            settings_conn.close()
            
            if settings_row and settings_row[0] and settings_row[1]:
                tautulli_url = settings_row[0].rstrip('/')
                tautulli_api = settings_row[1]
                users_data, _ = run_tautulli_command(tautulli_url, tautulli_api, 'get_users', 'Users', None)
                
                if users_data:
                    to_emails_list = [
                        u['email'] for u in users_data
                        if u.get('email') and u.get('email').strip() and u.get('is_active')
                    ]
                else:
                    print("No users found for ALL list")
                    return False
            else:
                print("Tautulli not configured for ALL list")
                return False
        else:
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
        templates_cursor.execute("SELECT name, subject, email_text, selected_items, expanded_collections FROM email_templates WHERE id = ?", (template_id,))
        template_result = templates_cursor.fetchone()
        templates_conn.close()
        
        if not template_result:
            print(f"Template {template_id} not found")
            return False
        
        template_name, subject, email_text, selected_items_json, expanded_collections_json = template_result
        selected_items = json.loads(selected_items_json) if selected_items_json else []
        expanded_collections = json.loads(expanded_collections_json) if expanded_collections_json else {}
        
        settings_conn = sqlite3.connect(DB_PATH)
        settings_cursor = settings_conn.cursor()
        settings_cursor.execute("SELECT from_email, alias_email, reply_to_email, password, smtp_server, smtp_port, smtp_protocol, server_name, tautulli_url, tautulli_api, logo_filename, logo_width, custom_logo_filename, from_name FROM settings WHERE id = 1")
        settings_result = settings_cursor.fetchone()
        settings_conn.close()
        
        if not settings_result:
            print("SMTP settings not found in database")
            return False
        
        from_email, alias_email, reply_to_email, encrypted_password, smtp_server, smtp_port, smtp_protocol, server_name, tautulli_base_url, tautulli_api_key, logo_filename, logo_width, custom_logo_filename, from_name = settings_result
        
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

        has_recs = any(item.get('type') == 'recommendations' for item in selected_items)

        users_data, _ = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_users', 'Users', None)
        user_dict = {}
        if users_data:
            user_dict = {
                u['user_id']: u['email']
                for u in users_data
                if u.get('email') != None and u.get('email') != '' and u.get('is_active')
            }
        
        if has_recs:
            print("Template contains recommendations, splitting emails by user...")
            
            rec_user_keys = set()
            for item in selected_items:
                if item.get('type') == 'recommendations' and item.get('userKey'):
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
                    from_email, alias_email, reply_to_email, encrypted_password, smtp_server,
                    smtp_port, smtp_protocol, server_name, tautulli_base_url, tautulli_api_key,
                    date_range, items_count, template_name, logo_filename, logo_width, custom_logo_filename,
                    from_name, display_preference, users_data, expanded_collections
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
                to_emails_list, subject, selected_items, from_email, alias_email, reply_to_email,
                encrypted_password, smtp_server, smtp_port, smtp_protocol, server_name, tautulli_base_url,
                tautulli_api_key, date_range, items_count, template_name, logo_filename, logo_width,
                custom_logo_filename, from_name, display_preference, users_data, expanded_collections
            )
        
    except Exception as e:
        print(f"Error in send_scheduled_email_with_cids: {e}")
        traceback.print_exc()
        return False

def send_scheduled_user_email_with_cids(recipients, subject, selected_items, user_key, recommendations_data, from_email, alias_email, reply_to_email, encrypted_password, smtp_server, smtp_port, smtp_protocol, server_name, tautulli_base_url, tautulli_api_key, date_range, items_count, template_name, logo_filename, logo_width, custom_logo_filename, from_name, display_preference, users_data, expanded_collections):
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
        tautulli_data = fetch_tautulli_data_for_email(tautulli_base_url, tautulli_api_key, date_range, server_name, items_count)
        tautulli_data["settings"]["logo_filename"] = logo_filename
        tautulli_data["settings"]["logo_width"] = logo_width
        tautulli_data["settings"]["custom_logo_filename"] = custom_logo_filename
        
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
            display_preference,
            users_data,
            recommendations_data,
            user_dict,
            base_url,
            target_user_key=user_key,
            is_scheduled=True,
            items_count=items_count,
            date_range=date_range,
            expanded_collections=expanded_collections
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

def send_scheduled_single_email_with_cids(to_emails_list, subject, selected_items, from_email, alias_email, reply_to_email, encrypted_password, smtp_server, smtp_port, smtp_protocol, server_name, tautulli_base_url, tautulli_api_key, date_range, items_count, template_name, logo_filename, logo_width, custom_logo_filename, from_name, display_preference, users_data, expanded_collections, email_text=""):
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
        tautulli_data = fetch_tautulli_data_for_email(tautulli_base_url, tautulli_api_key, date_range, server_name, items_count)
        tautulli_data["settings"]["logo_filename"] = logo_filename
        tautulli_data["settings"]["logo_width"] = logo_width
        tautulli_data["settings"]["custom_logo_filename"] = custom_logo_filename
        
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
            display_preference,
            users_data,
            None,
            None,
            base_url,
            None,
            True,
            items_count,
            date_range,
            expanded_collections
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
                font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
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
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    placeholder_title_style = """
        color: #6c757d;
        margin: 0 0 10px 0;
        font-size: 18px;
        font-weight: bold;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    placeholder_text_style = """
        color: #6c757d;
        margin: 0;
        font-size: 14px;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
    """
    
    placeholder_subtext_style = """
        color: #6c757d;
        margin: 5px 0 0;
        font-size: 12px;
        font-style: italic;
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
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
        font-family: 'IBM Plex Sans', 'Segoe UI', Helvetica, Arial, sans-serif;
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

@app.after_request
def set_security_headers(resp: Response):
    try:
        resp.headers.setdefault('X-Frame-Options', 'DENY')
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('Referrer-Policy', 'no-referrer')
        # If running behind HTTPS, HSTS can be enabled by the operator
        # resp.headers.setdefault('Strict-Transport-Security', 'max-age=63072000; includeSubDomains; preload')
        return resp
    except Exception:
        return resp

@app.route('/', methods=['GET', 'POST'])
@requires_auth
def index():
    stats = None
    users = None
    user_dict = {}
    users_full_data = None
    graph_commands = [
        { 'command' : 'get_concurrent_streams_by_stream_type', 'name' : 'Stream Type' },
        { 'command' : 'get_plays_by_date', 'name' : 'Plays by Date' },
        { 'command' : 'get_plays_by_dayofweek', 'name' : 'Plays by Day' },
        { 'command' : 'get_plays_by_hourofday', 'name' : 'Plays by Hour' },
        { 'command' : 'get_plays_by_source_resolution', 'name' : 'Plays by Source Res' },
        { 'command' : 'get_plays_by_stream_resolution', 'name' : 'Plays by Stream Res' },
        { 'command' : 'get_plays_by_stream_type', 'name' : 'Plays by Stream Type' },
        { 'command' : 'get_plays_by_top_10_platforms', 'name' : 'Plays by Top Platforms' },
        { 'command' : 'get_plays_by_top_10_users', 'name' : 'Plays by Top Users' },
        { 'command' : 'get_plays_per_month', 'name' : 'Plays per Month' },
        { 'command' : 'get_stream_type_by_top_10_platforms', 'name' : 'Stream Type by Top Platforms' },
        { 'command' : 'get_stream_type_by_top_10_users', 'name' : 'Stream Type by Top Users' }
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

    username = ""
    if session.get('username'):
        username = session.get('username')

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        from_email = cursor.execute("SELECT from_email FROM settings WHERE id = 1").fetchone()[0]
        server_name = cursor.execute("SELECT server_name FROM settings WHERE id = 1").fetchone()[0]
        tautulli_url = cursor.execute("SELECT tautulli_url FROM settings WHERE id = 1").fetchone()[0]
        tautulli_api = cursor.execute("SELECT tautulli_api FROM settings WHERE id = 1").fetchone()[0]
        logo_filename = cursor.execute("SELECT logo_filename FROM settings WHERE id = 1").fetchone()[0]
        logo_width = cursor.execute("SELECT logo_width FROM settings WHERE id = 1").fetchone()[0]
        email_theme = cursor.execute("SELECT email_theme FROM settings WHERE id = 1").fetchone()[0]
        custom_logo_filename = cursor.execute("SELECT custom_logo_filename FROM settings WHERE id = 1").fetchone()[0]
        recipient_display_name = cursor.execute("SELECT recipient_display_name FROM settings WHERE id = 1").fetchone()[0]
    except:
        from_email = cursor.execute("SELECT from_email FROM settings WHERE id = 1").fetchone()
        server_name = cursor.execute("SELECT server_name FROM settings WHERE id = 1").fetchone()
        tautulli_url = cursor.execute("SELECT tautulli_url FROM settings WHERE id = 1").fetchone()
        tautulli_api = cursor.execute("SELECT tautulli_api FROM settings WHERE id = 1").fetchone()
        logo_filename = cursor.execute("SELECT logo_filename FROM settings WHERE id = 1").fetchone()
        logo_width = cursor.execute("SELECT logo_width FROM settings WHERE id = 1").fetchone()
        email_theme = cursor.execute("SELECT email_theme FROM settings WHERE id = 1").fetchone()
        custom_logo_filename = cursor.execute("SELECT custom_logo_filename FROM settings WHERE id = 1").fetchone()
        recipient_display_name = cursor.execute("SELECT recipient_display_name FROM settings WHERE id = 1").fetchone()

    settings = {
        "from_email": from_email or "",
        "server_name": server_name or "",
        "tautulli_url": tautulli_url or "",
        "tautulli_api": decrypt(tautulli_api),
        "email_theme": email_theme or "",
        "custom_logo_filename": custom_logo_filename or "",
        "recipient_display_name": recipient_display_name or "email"
    }
    if logo_filename == '' or logo_filename is None:
        if email_theme == 'custom':
            settings['logo_filename'] = ''
        else:
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
        if email_theme == 'custom':
            settings['logo_width'] = 0
        else:
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
            users_full_data = users
            for user in users:
                if user['email'] != None and user['is_active']:
                    user_dict[user['user_id']] = user['email']

    if request.method == 'POST':
        token = request.form.get("csrf_token").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        if settings['server_name'] == "":
            return render_template('index.html', error='Please enter tautulli info on settings page',
                                    stats=stats, user_dict=user_dict, graph_data=graph_data,
                                    graph_commands=graph_commands, alert=alert, settings=settings,
                                    username=username)
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
            
            recent_data = fetch_recent_data_for_index(tautulli_base_url, tautulli_api_key, count)
            set_cached_data('recent_data', recent_data, cache_params)
            
            user_dict = {}
            users_full_data = None
            if users:
                users_full_data = users
                for user in users:
                    if user['email'] != None and user['is_active']:
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

    if not cache_info['graph_data'] or 'params' not in cache_info['graph_data']:
        if not cache_info['graph_data']:
            cache_info['graph_data'] = {}
        cache_info['graph_data']['params'] = {
            'time_range': 30
        }

    theme_settings = get_theme_settings()

    if alert == None:
        alert = request.args.get('alert')

    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    return render_template('index.html',
                           stats=stats, user_dict=user_dict, users_full_data=users_full_data,
                           graph_data=graph_data, graph_commands=graph_commands, recent_data=recent_data,
                           libs=libs, error=error, alert=alert, settings=settings, email_lists=email_lists,
                           cache_info=cache_info, recommendations_json=recommendations_json,
                           filtered_users=filtered_users, theme_settings=theme_settings,
                           nonce=secrets.token_urlsafe(16), csrf_token=session["csrf_token"], username=username
                        )

@app.route('/login', methods=['GET', 'POST'])
def login():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT login_toggle FROM settings WHERE id = 1")
    login_toggle = cursor.fetchone()
    conn.close()

    alert = request.args.get('alert')
    if login_toggle[0] != 'enabled':
        return redirect(url_for('index', alert=alert))

    if request.method == 'POST':
        token = request.form.get("csrf_token").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if check_credentials(username, password):
            session['authenticated'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid credentials')
        
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)

    return render_template('login.html', alert=alert, csrf_token=session["csrf_token"])

@app.route('/logout')
@requires_auth
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/proxy-art/<path:art_path>')
@requires_auth
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

    if '/composite/' in art_path:
        print(f"proxy-art: Detected composite image: {art_path}")
        
        composite_url = f"/{art_path}"
        if '?' in composite_url:
            composite_url += f"&X-Plex-Token={decrypt(plex_token)}"
        else:
            composite_url += f"?X-Plex-Token={decrypt(plex_token)}"
        
        encoded_composite_url = quote(composite_url, safe='')
        
        full_url = (
            f"{plex_url}/photo/:/transcode"
            f"?width=360&height=540&minSize=1&upscale=1"
            f"&url={encoded_composite_url}"
            f"&X-Plex-Token={decrypt(plex_token)}"
        )
    else:
        full_url = f"{plex_url}/{art_path}"
        if '?' in full_url:
            full_url += f"&X-Plex-Token={decrypt(plex_token)}"
        else:
            full_url += f"?X-Plex-Token={decrypt(plex_token)}"
    
    print(f"proxy-art: Fetching {full_url}")
    
    try:
        headers = {
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
        }
        
        r = safe_get(full_url, stream=True, timeout=15, headers=headers)
        r.raise_for_status()
        
        content_type = r.headers.get('Content-Type', 'image/jpeg')
        print(f"proxy-art: Success - Content-Type: {content_type}, Size: {r.headers.get('Content-Length', 'unknown')}")
        
        return Response(r.content, content_type=content_type, headers={
            'Cache-Control': 'public, max-age=86400'
        })
    except Exception as e:
        print(f"proxy-art: Error fetching {full_url}: {e}")
        return Response("Image not found", status=404)

@app.get("/proxy-img")
@requires_auth
def proxy_img():
    url = request.args.get("u", "")
    if not url.startswith(("http://","https://")):
        return Response(status=400)
    r = safe_get(url, timeout=15)
    ct = r.headers.get("Content-Type", "image/jpeg")
    return Response(r.content, headers={"Content-Type": ct, "Cache-Control": "public, max-age=86400"})

@app.route('/fetch_collections/<collection_type>', methods=['GET'])
@requires_auth
def fetch_collections(collection_type):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT plex_url, plex_token FROM settings WHERE id = 1")
        row = cursor.fetchone()
        conn.close()

        if not row or not row[0] or not row[1]:
            return jsonify({"status": "error", "message": "Plex connection not configured"})

        plex_url = row[0].rstrip('/')
        plex_token = row[1]

        sections_url = f"{plex_url}/library/sections"
        
        sections_response = safe_get(
            sections_url,
            headers={"X-Plex-Token": decrypt(plex_token), "Accept": "application/json"},
            timeout = 10
        )
        if sections_response.status_code != 200:
            return jsonify({"status": "error", "message": "Failed to fetch library sections"})

        sections_data = sections_response.json()
        collections = []

        target_type = collection_type
        
        for section in sections_data.get("MediaContainer", {}).get("Directory", []):
            if section.get("type") == target_type:
                section_id = section.get("key")
                section_title = section.get("title", "Unknown Library")
                
                collections_url = f"{plex_url}/library/sections/{section_id}/collections"
                collections_response = safe_get(collections_url, headers={"X-Plex-Token": decrypt(plex_token), "Accept": "application/json"}, timeout=10)
                
                if collections_response.status_code == 200:
                    collections_data = collections_response.json()
                    
                    for collection in collections_data.get("MediaContainer", {}).get("Metadata", []):
                        thumb = collection.get("thumb", "")
                        if thumb and not thumb.startswith("http"):
                            thumb = f"{plex_url}{thumb}?X-Plex-Token={decrypt(plex_token)}"
                        
                        art = collection.get("art", "")
                        if art and not art.startswith("http"):
                            art = f"{plex_url}{art}?X-Plex-Token={decrypt(plex_token)}"
                        
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

@app.route('/get_collection_items', methods=['POST'])
@requires_auth
def get_collection_items():
    require_csrf_for_json()
    try:
        data = request.get_json()
        collection_key = data.get('collection_key')
        collection_type = data.get('collection_type')
        
        if not collection_key:
            return jsonify({
                'status': 'error',
                'message': 'Collection key is required'
            }), 400
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT plex_url, plex_token FROM settings WHERE id = 1")
        row = cursor.fetchone()
        conn.close()

        if not row or not row[0] or not row[1]:
            return jsonify({"status": "error", "message": "Plex connection not configured"})

        plex_url = row[0].rstrip('/')
        plex_token = row[1]
        
        collection_items_url = f"{plex_url}/library/collections/{collection_key}/children"
        
        headers = {
            'X-Plex-Token': decrypt(plex_token),
            'Accept': 'application/json',
            **plex_headers
        }
        
        response = safe_get(collection_items_url, headers=headers, timeout=30)
        
        if response.status_code == 404:
            return jsonify({
                'status': 'error',
                'message': 'Collection not found'
            }), 404
        elif response.status_code != 200:
            return jsonify({
                'status': 'error',
                'message': f'Plex API error: {response.status_code}'
            }), 500
        
        plex_data = response.json()
        
        items = []
        if 'MediaContainer' in plex_data and 'Metadata' in plex_data['MediaContainer']:
            for item in plex_data['MediaContainer']['Metadata']:
                item_info = {
                    'title': item.get('title', 'Unknown Title'),
                    'key': item.get('key'),
                    'type': item.get('type'),
                    'year': item.get('year'),
                    'tagline': item.get('tagline'),
                    'summary': item.get('summary'),
                    'rating': item.get('rating'),
                    'duration': item.get('duration'),
                    'addedAt': item.get('addedAt'),
                    'thumb': item.get('thumb')
                }
                
                if item.get('type') == 'movie':
                    item_info['name'] = item_info['title']
                elif item.get('type') == 'show':
                    item_info['name'] = item_info['title']
                    if 'leafCount' in item:
                        item_info['episode_count'] = item['leafCount']
                    if 'childCount' in item:
                        item_info['season_count'] = item['childCount']
                elif item.get('type') == 'album':
                    item_info['name'] = item_info['title']
                    if 'parentTitle' in item:
                        item_info['artist'] = item['parentTitle']
                elif item.get('type') == 'track':
                    item_info['name'] = item_info['title']
                    if 'grandparentTitle' in item:
                        item_info['artist'] = item['grandparentTitle']
                    if 'parentTitle' in item:
                        item_info['album'] = item['parentTitle']
                
                items.append(item_info)
        
        items.sort(key=lambda x: x.get('title', '').lower())
        
        return jsonify({
            'status': 'success',
            'items': items,
            'total_count': len(items),
            'collection_key': collection_key,
            'collection_type': collection_type
        })
        
    except requests.RequestException as e:
        print(f"Error fetching collection items from Plex: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to connect to Plex: {str(e)}'
        }), 500
    except Exception as e:
        print(f"Error in get_collection_items: {e}")
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }), 500

@app.route('/pull_recommendations', methods=['POST'])
@requires_auth
def pull_recommendations():
    require_csrf_for_json()
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
@requires_auth
def send_email():
    require_csrf_for_json()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
        from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, server_name, logo_filename, logo_width, from_name, custom_logo_filename
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
            "logo_filename": row[9],
            "logo_width": row[10],
            "from_name": row[11] or "",
            "custom_logo_filename": row[12] or ""
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
    expanded_collections = data.get('expanded_collections', {})
    from_name = settings['from_name']

    has_recommendations = any(item.get('type') == 'recommendations' for item in selected_items)

    if has_recommendations and user_dict:
        return send_recommendations_email_with_cids(
            to_emails, subject, user_dict, selected_items,
            from_email, alias_email, reply_to_email, password, smtp_username, 
            smtp_server, smtp_port, smtp_protocol, settings, from_name, expanded_collections
        )
    else:
        return send_standard_email_with_cids(
            to_emails, subject, selected_items,
            from_email, alias_email, reply_to_email, password, smtp_username,
            smtp_server, smtp_port, smtp_protocol, settings, from_name, expanded_collections
        )

@app.route('/settings', methods=['GET', 'POST'])
@requires_auth
def settings():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    alert = request.args.get('alert')

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

    preset_logo_name_to_file = {
        "newsletterr_blue_small": "Asset_54x.png",
        "newsletterr_orange_small": "Asset_46x.png",
        "newsletterr_blue_banner": "Asset_94x.png",
        "newsletterr_orange_banner": "Asset_45x.png"
    }

    if request.method == "POST":
        token = request.form.get("csrf_token").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        cursor.execute("SELECT custom_logo_filename FROM settings WHERE id = 1")
        db_custom_logo = cursor.fetchone()
        existing_custom_logo = db_custom_logo[0] if db_custom_logo and db_custom_logo[0] else ""

        cursor.execute("SELECT login_toggle, nl_username, nl_password FROM settings WHERE id = 1")
        db_login_info = cursor.fetchone()
        existing_login_toggle = db_login_info[0] if db_login_info and db_login_info[0] else ""
        existing_nl_username = db_login_info[1] if db_login_info and db_login_info[1] else ""
        existing_nl_password = db_login_info[2] if db_login_info and db_login_info[2] else ""

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
        recipient_display_name = request.form.get("recipient_display_name", "email")
        logo_filename = request.form.get("logo_filename")
        logo_width = request.form.get("logo_width")
        email_theme = request.form.get("email_theme", "newsletterr_blue")
        from_name = request.form.get("from_name")
        custom_logo_filename = request.form.get("custom_logo_filename", "")
        login_toggle = request.form.get("login_toggle")
        nl_username = request.form.get("nl_username")
        nl_password = encrypt(request.form.get("nl_password"))

        if not custom_logo_filename and existing_custom_logo:
            custom_logo_filename = existing_custom_logo

        if logo_filename == 'custom':
            pass
        elif logo_filename in preset_logo_name_to_file:
            logo_filename = preset_logo_name_to_file[logo_filename]
        elif logo_filename == 'none':
            logo_filename = ""

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
                tautulli_api, conjurr_url, recipient_display_name, logo_filename, logo_width, email_theme, primary_color, secondary_color, accent_color, background_color,
                text_color, from_name, custom_logo_filename, login_toggle, nl_username, nl_password)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE
            SET from_email = excluded.from_email, alias_email = excluded.alias_email, reply_to_email = excluded.reply_to_email, password = excluded.password,
                smtp_username = excluded.smtp_username, smtp_server = excluded.smtp_server, smtp_port = excluded.smtp_port, smtp_protocol = excluded.smtp_protocol,
                server_name = excluded.server_name, plex_url = excluded.plex_url, tautulli_url = excluded.tautulli_url, tautulli_api = excluded.tautulli_api,
                conjurr_url = excluded.conjurr_url, recipient_display_name = excluded.recipient_display_name, logo_filename = excluded.logo_filename, logo_width = excluded.logo_width,
                email_theme = excluded.email_theme, primary_color = excluded.primary_color, secondary_color = excluded.secondary_color, accent_color = excluded.accent_color,
                background_color = excluded.background_color, text_color = excluded.text_color, from_name = excluded.from_name, custom_logo_filename = excluded.custom_logo_filename,
                login_toggle = excluded.login_toggle, nl_username = excluded.nl_username, nl_password = excluded.nl_password
        """, (from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, server_name, plex_url, tautulli_url, tautulli_api,
              conjurr_url, recipient_display_name, logo_filename, logo_width, email_theme, primary_color, secondary_color, accent_color, background_color, text_color, from_name,
              custom_logo_filename, login_toggle, nl_username, nl_password))
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
            "recipient_display_name": recipient_display_name,
            "logo_filename": logo_filename,
            "logo_width": logo_width,
            "email_theme": email_theme,
            "primary_color": primary_color,
            "secondary_color": secondary_color,
            "accent_color": accent_color,
            "background_color": background_color,
            "text_color": text_color,
            "from_name": from_name,
            "custom_logo_filename": custom_logo_filename,
            "login_toggle": login_toggle,
            "nl_username": nl_username,
            "nl_password": decrypt(nl_password)
        }

        if login_toggle == 'disabled':
            session.pop('username', None)

        if existing_nl_username != nl_username:
            session.pop('username', None)
            session.pop('authenticated', None)
            return redirect(url_for('login', alert="Settings saved successfully!"))
        
        if decrypt(existing_nl_password) != decrypt(nl_password):
            session.pop('username', None)
            session.pop('authenticated', None)
            return redirect(url_for('login', alert="Settings saved successfully!"))

        if existing_login_toggle != login_toggle:
            session.pop('username', None)
            session.pop('authenticated', None)
            return redirect(url_for('login', alert="Settings saved successfully!"))

        return redirect(url_for('settings', alert="Settings saved successfully!", settings=settings))

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
        recipient_display_name = cursor.execute("SELECT recipient_display_name FROM settings WHERE id = 1").fetchone()[0]
        logo_filename = cursor.execute("SELECT logo_filename FROM settings WHERE id = 1").fetchone()[0]
        logo_width = cursor.execute("SELECT logo_width FROM settings WHERE id = 1").fetchone()[0]
        email_theme = cursor.execute("SELECT email_theme FROM settings WHERE id = 1").fetchone()[0]
        primary_color = cursor.execute("SELECT primary_color FROM settings WHERE id = 1").fetchone()[0]
        secondary_color = cursor.execute("SELECT secondary_color FROM settings WHERE id = 1").fetchone()[0]
        accent_color = cursor.execute("SELECT accent_color FROM settings WHERE id = 1").fetchone()[0]
        background_color = cursor.execute("SELECT background_color FROM settings WHERE id = 1").fetchone()[0]
        text_color = cursor.execute("SELECT text_color FROM settings WHERE id = 1").fetchone()[0]
        from_name = cursor.execute("SELECT from_name FROM settings WHERE id = 1").fetchone()[0]
        custom_logo_filename = cursor.execute("SELECT custom_logo_filename FROM settings WHERE id = 1").fetchone()[0]
        login_toggle = cursor.execute("SELECT login_toggle FROM settings WHERE id = 1").fetchone()[0]
        nl_username = cursor.execute("SELECT nl_username FROM settings WHERE id = 1").fetchone()[0]
        nl_password = cursor.execute("SELECT nl_password FROM settings WHERE id = 1").fetchone()[0]
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
        recipient_display_name = cursor.execute("SELECT recipient_display_name FROM settings WHERE id = 1").fetchone()
        logo_filename = cursor.execute("SELECT logo_filename FROM settings WHERE id = 1").fetchone()
        logo_width = cursor.execute("SELECT logo_width FROM settings WHERE id = 1").fetchone()
        email_theme = cursor.execute("SELECT email_theme FROM settings WHERE id = 1").fetchone()
        primary_color = cursor.execute("SELECT primary_color FROM settings WHERE id = 1").fetchone()
        secondary_color = cursor.execute("SELECT secondary_color FROM settings WHERE id = 1").fetchone()
        accent_color = cursor.execute("SELECT accent_color FROM settings WHERE id = 1").fetchone()
        background_color = cursor.execute("SELECT background_color FROM settings WHERE id = 1").fetchone()
        text_color = cursor.execute("SELECT text_color FROM settings WHERE id = 1").fetchone()
        from_name = cursor.execute("SELECT from_name FROM settings WHERE id = 1").fetchone()
        custom_logo_filename = cursor.execute("SELECT custom_logo_filename FROM settings WHERE id = 1").fetchone()
        login_toggle = cursor.execute("SELECT login_toggle FROM settings WHERE id = 1").fetchone()
        nl_username = cursor.execute("SELECT nl_username FROM settings WHERE id = 1").fetchone()
        nl_password = cursor.execute("SELECT nl_password FROM settings WHERE id = 1").fetchone()

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
        "recipient_display_name": recipient_display_name or "email",
        "logo_filename": logo_filename or "",
        "email_theme": email_theme or "newsletterr_blue",
        "primary_color": primary_color or "#8acbd4",
        "secondary_color": secondary_color or "#222222",
        "accent_color": accent_color or "#62a1a4",
        "background_color": background_color or "#333333",
        "text_color": text_color or "#62a1a4",
        "from_name": from_name or "",
        "custom_logo_filename": custom_logo_filename or "",
        "login_toggle": login_toggle or "disabled",
        "nl_username": nl_username or ""
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
    if nl_password == '' or nl_password is None:
        settings["nl_password"] = ""
    else:
        settings["nl_password"] = decrypt(nl_password)
    
    conn.close()

    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    return render_template('settings.html', settings=settings, alert=alert, nonce=secrets.token_urlsafe(16), csrf_token=session["csrf_token"])

@app.route('/upload-logo', methods=['POST'])
@requires_auth
def upload_logo():
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        token = request.form.get('csrf_token')
        if not token or token != session.get('csrf_token'):
            abort(400)

    try:
        if 'logo' not in request.files:
            return jsonify({"status": "error", "message": "No file uploaded"}), 400

        file = request.files['logo']

        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400

        allowed_extensions = {'png', 'jpg', 'jpeg', 'webp'}
        if not file.filename.lower().endswith(tuple('.' + ext for ext in allowed_extensions)):
            return jsonify({"status": "error", "message": "Invalid file type. Only PNG, JPG, JPEG, and WebP are allowed"}), 400

        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)

        if file_size > 2 * 1024 * 1024:
            return jsonify({"status": "error", "message": "File too large. Maximum size is 2MB"}), 400

        timestamp = int(time.time())
        file_extension = file.filename.rsplit('.', 1)[1].lower()
        new_filename = f"logo_{timestamp}.{file_extension}"

        upload_dir = os.path.join(app.static_folder, 'uploads', 'logos')
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, new_filename)
        file.save(file_path)

        with Image.open(file_path) as img:
            width, height = img.size

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO settings (id, logo_filename, custom_logo_filename) 
            VALUES (1, 'custom', ?) 
            ON CONFLICT (id) DO UPDATE 
            SET logo_filename = 'custom', custom_logo_filename = excluded.custom_logo_filename
        """, (new_filename,))
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success", 
            "message": "Logo uploaded successfully",
            "filename": new_filename,
            "width": width,
            "height": height
        })

    except Exception as e:
        print(f"Error uploading logo: {e}")
        return jsonify({"status": "error", "message": f"Upload failed: {str(e)}"}), 500

@app.route('/delete-logo', methods=['POST'])
@requires_auth
def delete_logo():
    require_csrf_for_json()
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT custom_logo_filename FROM settings WHERE id = 1")
        result = cursor.fetchone()
        current_logo = result[0] if result else None

        if current_logo:
            logo_path = os.path.join(app.static_folder, 'uploads', 'logos', current_logo)
            if os.path.exists(logo_path):
                os.remove(logo_path)

            cursor.execute("""
                UPDATE settings 
                SET logo_filename = 'none', logo_width = 80, custom_logo_filename = ''
                WHERE id = 1
            """)
            conn.commit()
            conn.close()

            return jsonify({
                "status": "success", 
                "message": "Logo removed"
            })
        else:
            conn.close()
            return jsonify({
                "status": "info", 
                "message": "No logo set"
            })

    except Exception as e:
        print(f"Error deleting logo: {e}")
        return jsonify({"status": "error", "message": f"Delete failed: {str(e)}"}), 500

@app.post('/api/plex/pin')
@requires_auth
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
@requires_auth
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
@requires_auth
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
    params = {
        "includeHttps": "1"
    }
    
    response = safe_get(url, headers=headers, params=params)
    data = response.json()
    
    def select_best_connection(connections):
        https_connections = [connection for connection in connections if connection.get('protocol') == 'https']
        
        if https_connections:
            local_https = [connection for connection in https_connections if connection.get('local')]
            if local_https:
                return local_https[0]['uri']
            
            return https_connections[0]['uri']
        
        return connections[0]['uri'] if connections else None

    server = data[0]
    best_url = select_best_connection(server['connections'])
    
    if not best_url:
        return jsonify({"connected": False, "error": "No suitable connection found"})

    cursor.execute("""
        INSERT INTO settings (id, server_name, plex_url)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET server_name = excluded.server_name, plex_url = excluded.plex_url
    """, (server['name'], best_url))
    conn.commit()
    conn.close()

    if response.status_code == 200:
        return jsonify({"connected": True})
    return jsonify({"connected": False})

@app.route('/about', methods=['GET'])
@requires_auth
def about():
    return render_template('about.html')

@app.route('/email_history', methods=['GET'])
@requires_auth
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
        
        if not session.get("csrf_token"):
            session["csrf_token"] = secrets.token_urlsafe(32)
        
        return render_template('email_history.html', emails=email_list, csrf_token=session["csrf_token"])
    except Exception as e:
        print(f"Error loading email history: {e}")
        return render_template('email_history.html', emails=[])

@app.route('/email_history/clear', methods=['POST'])
@requires_auth
def clear_email_history():
    require_csrf_for_json()
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
@requires_auth
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
@requires_auth
def scheduling():
    try:
        schedules = get_email_schedules()
        email_lists = get_saved_email_lists()
        
        templates_conn = sqlite3.connect(DB_PATH)
        templates_cursor = templates_conn.cursor()
        templates_cursor.execute("SELECT id, name FROM email_templates ORDER BY name")
        templates = [{'id': row[0], 'name': row[1]} for row in templates_cursor.fetchall()]
        templates_conn.close()

        if not session.get("csrf_token"):
            session["csrf_token"] = secrets.token_urlsafe(32)
        
        return render_template('scheduling.html', schedules=schedules, email_lists=email_lists, templates=templates, csrf_token=session["csrf_token"])
    except Exception as e:
        print(f"Error loading scheduling page: {e}")
        return render_template('scheduling.html', schedules=[], email_lists=[], templates=[])

@app.route('/scheduling/create', methods=['POST'])
@requires_auth
def create_schedule():
    require_csrf_for_json()
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email_list_id = data.get('email_list_id')
        template_id = int(data.get('template_id'))
        frequency = data.get('frequency')
        start_date = data.get('start_date')
        send_time = data.get('send_time', '09:00')
        date_range = int(data.get('date_range', 7))
        items_count = int(data.get('items_count', 10))
        
        if not all([name, email_list_id, template_id, frequency, start_date]):
            return jsonify({"status": "error", "message": "All fields are required"}), 400
        
        if email_list_id == 'ALL':
            list_id = 'ALL'
        else:
            try:
                list_id = int(email_list_id)
            except (ValueError, TypeError):
                return jsonify({"status": "error", "message": "Invalid email list ID"}), 400
        
        success = create_email_schedule(name, list_id, template_id, frequency, start_date, send_time, date_range, items_count)
        if success:
            return jsonify({"status": "success", "message": f"Schedule '{name}' created successfully"})
        else:
            return jsonify({"status": "error", "message": "Failed to create schedule"}), 500
    except Exception as e:
        print(f"Error creating schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>', methods=['PUT'])
@requires_auth
def update_schedule(schedule_id):
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email_list_id = data.get('email_list_id')
        template_id = int(data.get('template_id'))
        frequency = data.get('frequency')
        start_date = data.get('start_date')
        send_time = data.get('send_time', '09:00')
        date_range = int(data.get('date_range', 7))
        items_count = int(data.get('items_count', 10))
        
        if not all([name, email_list_id, template_id, frequency, start_date]):
            return jsonify({"status": "error", "message": "All fields are required"}), 400
        
        if email_list_id == 'ALL':
            list_id = 'ALL'
        else:
            try:
                list_id = int(email_list_id)
            except (ValueError, TypeError):
                return jsonify({"status": "error", "message": "Invalid email list ID"}), 400
        
        success = update_email_schedule(schedule_id, name, list_id, template_id, frequency, start_date, send_time, date_range, items_count)
        if success:
            return jsonify({"status": "success", "message": f"Schedule '{name}' updated successfully"})
        else:
            return jsonify({"status": "error", "message": "Failed to update schedule"}), 500
    except Exception as e:
        print(f"Error updating schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>', methods=['DELETE'])
@requires_auth
def delete_schedule(schedule_id):
    try:
        delete_email_schedule(schedule_id)
        return jsonify({"status": "success", "message": "Schedule deleted successfully"})
    except Exception as e:
        print(f"Error deleting schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>/send-now', methods=['POST'])
@requires_auth
def send_schedule_now(schedule_id):
    require_csrf_for_json()
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
@requires_auth
def toggle_schedule(schedule_id):
    require_csrf_for_json()
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
@requires_auth
def preview_schedule(schedule_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT template_id, date_range, email_list_id, items_count
            FROM email_schedules 
            WHERE id = ?
        """, (schedule_id,))
        schedule_result = cursor.fetchone()
        conn.close()
        
        if not schedule_result:
            return jsonify({"status": "error", "message": "Schedule not found"}), 404
        
        template_id, date_range, email_list_id, items_count = schedule_result
        date_range = date_range or 7
        items_count = items_count or 10
        
        templates_conn = sqlite3.connect(DB_PATH)
        templates_cursor = templates_conn.cursor()
        templates_cursor.execute("SELECT name, subject, email_text, selected_items, expanded_collections FROM email_templates WHERE id = ?", (template_id,))
        template_result = templates_cursor.fetchone()
        templates_conn.close()
        
        if not template_result:
            return jsonify({"status": "error", "message": "Template not found"}), 404
        
        template_name, subject, email_text, selected_items_json, expanded_collections_json = template_result
        
        try:
            selected_items = json.loads(selected_items_json) if selected_items_json else []
        except:
            selected_items = []

        try:
            expanded_collections = json.loads(expanded_collections_json) if expanded_collections_json else []
        except:
            expanded_collections = {}

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
        users_full_data = None
        if settings.get('tautulli_url') and settings.get('tautulli_api'):
            try:
                users_data, _ = run_tautulli_command(settings['tautulli_url'].rstrip('/'), settings['tautulli_api'], 'get_users', 'Users', None)
                users_full_data = users_data
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
            settings['server_name'],
            items_count
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
            "items_count": items_count,
            "settings": settings,
            "stats": tautulli_data.get('stats', []),
            "graph_data": tautulli_data.get('graph_data', []),
            "recent_data": tautulli_data.get('recent_data', []),
            "graph_commands": tautulli_data.get('graph_commands', []),
            "recent_commands": [{'command': 'movie'}, {'command': 'show'}],
            "recommendations": recommendations_data or {},
            "user_dict": user_dict,
            "users_full_data": users_full_data,
            "expanded_collections": expanded_collections
        })
        
    except Exception as e:
        print(f"Error generating preview: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>/preview-page', methods=['GET'])
@requires_auth
def preview_schedule_page(schedule_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT date_range FROM email_schedules WHERE id = ?", (schedule_id,))
        schedule_result = cursor.fetchone()
        
        date_range = schedule_result[0] if schedule_result else 7
    except:
        date_range = 7

    cursor.execute("SELECT logo_filename, logo_width, tautulli_url, tautulli_api, custom_logo_filename, recipient_display_name FROM settings WHERE id = 1")
    settings_row = cursor.fetchone()
    logo_filename = settings_row[0] if settings_row else 'Asset_94x.png'
    logo_width = settings_row[1] if settings_row else 80
    tautulli_url = settings_row[2] if settings_row else ''
    tautulli_api = settings_row[3] if settings_row else ''
    custom_logo_filename = settings_row[4] if settings_row else ''
    recipient_display_name = settings_row[5] if settings_row else 'email'

    settings = {
        "logo_filename": logo_filename,
        "logo_width": logo_width,
        "custom_logo_filename": custom_logo_filename,
        "recipient_display_name": recipient_display_name
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
@requires_auth
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
            
            if current_date < start_date:
                if frequency == 'weekly':
                    weeks_to_skip = (start_date - current_date).days // 7
                    current_date += timedelta(weeks=weeks_to_skip)
                    
                    target_weekday = schedule_start.weekday()
                    days_ahead = (target_weekday - current_date.weekday()) % 7
                    current_date += timedelta(days=days_ahead)
                    
                    if current_date < start_date:
                        current_date += timedelta(days=7)

                elif frequency == 'biweekly':
                    weeks_to_skip = ((start_date - current_date).days // 14) * 2
                    current_date += timedelta(weeks=weeks_to_skip)
                    
                    target_weekday = schedule_start.weekday()
                    days_ahead = (target_weekday - current_date.weekday()) % 7
                    current_date += timedelta(days=days_ahead)
                    
                    if current_date < start_date:
                        current_date += timedelta(days=14)
                
                elif frequency in ['monthly', 'bimonthly_interval', 'quarterly', 'biannually', 'yearly']:
                    target_day = schedule_start.day
                    target_month = schedule_start.month
                    
                    if frequency == 'monthly':
                        current_date = datetime(year, month, min(target_day, calendar.monthrange(year, month)[1]))

                    elif frequency == 'bimonthly_interval':
                        months_diff = (year - schedule_start.year) * 12 + (month - target_month)
                        cycle_position = months_diff % 2
                        if cycle_position == 0:
                            current_date = datetime(year, month, min(target_day, calendar.monthrange(year, month)[1]))
                        else:
                            continue

                    elif frequency == 'quarterly':
                        months_diff = (year - schedule_start.year) * 12 + (month - target_month)
                        cycle_position = months_diff % 3
                        if cycle_position == 0:
                            current_date = datetime(year, month, min(target_day, calendar.monthrange(year, month)[1]))
                        else:
                            continue

                    elif frequency == 'biannually':
                        months_diff = (year - schedule_start.year) * 12 + (month - target_month)
                        cycle_position = months_diff % 6
                        if cycle_position == 0:
                            current_date = datetime(year, month, min(target_day, calendar.monthrange(year, month)[1]))
                        else:
                            continue

                    elif frequency == 'yearly':
                        if month == target_month:
                            if target_month == 2 and target_day == 29 and not calendar.isleap(year):
                                actual_day = 28
                            else:
                                actual_day = min(target_day, calendar.monthrange(year, month)[1])
                            current_date = datetime(year, month, actual_day)
                        else:
                            continue
                            
                elif frequency == 'bimonthly':
                    if schedule_start.day <= 15:
                        target_days = [1, 15]
                    else:
                        target_days = [15, 1]
                    current_date = datetime(year, month, 1)
            
            iteration_count = 0
            max_iterations = 50

            while current_date <= end_date and iteration_count < max_iterations:
                iteration_count += 1

                if current_date >= start_date and current_date >= schedule_start:
                    if frequency == 'bimonthly':
                        if schedule_start.day <= 15:
                            target_days = [1, 15]
                        else:
                            target_days = [15, 1]
                        
                        for target_day in target_days:
                            if target_day >= current_date.day:
                                target_date = current_date.replace(day=target_day)
                                if start_date <= target_date <= end_date:
                                    date_key = target_date.strftime('%Y-%m-%d')
                                    if date_key not in calendar_data:
                                        calendar_data[date_key] = []
                                    
                                    calendar_data[date_key].append({
                                        'id': schedule_id,
                                        'name': name,
                                        'time': send_time or '09:00',
                                        'frequency': frequency,
                                        'template_id': template_id
                                    })
                        break
                    else:
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

                elif frequency == 'biweekly':
                    current_date += timedelta(days=14)

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

                elif frequency == 'bimonthly_interval':
                    target_day = schedule_start.day
                    next_month = current_date.month + 2
                    next_year = current_date.year
                    while next_month > 12:
                        next_month -= 12
                        next_year += 1
                    
                    last_day_of_month = calendar.monthrange(next_year, next_month)[1]
                    actual_day = min(target_day, last_day_of_month)
                    current_date = current_date.replace(year=next_year, month=next_month, day=actual_day)

                elif frequency == 'quarterly':
                    target_day = schedule_start.day
                    next_month = current_date.month + 3
                    next_year = current_date.year
                    while next_month > 12:
                        next_month -= 12
                        next_year += 1
                    
                    last_day_of_month = calendar.monthrange(next_year, next_month)[1]
                    actual_day = min(target_day, last_day_of_month)
                    current_date = current_date.replace(year=next_year, month=next_month, day=actual_day)

                elif frequency == 'biannually':
                    target_day = schedule_start.day
                    next_month = current_date.month + 6
                    next_year = current_date.year
                    while next_month > 12:
                        next_month -= 12
                        next_year += 1
                    
                    last_day_of_month = calendar.monthrange(next_year, next_month)[1]
                    actual_day = min(target_day, last_day_of_month)
                    current_date = current_date.replace(year=next_year, month=next_month, day=actual_day)

                elif frequency == 'yearly':
                    target_day = schedule_start.day
                    target_month = schedule_start.month
                    next_year = current_date.year + 1
                    
                    if target_month == 2 and target_day == 29 and not calendar.isleap(next_year):
                        actual_day = 28
                    else:
                        last_day_of_month = calendar.monthrange(next_year, target_month)[1]
                        actual_day = min(target_day, last_day_of_month)
                    
                    current_date = datetime(next_year, target_month, actual_day)

                elif frequency == 'bimonthly':
                    break
                
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
@requires_auth
def clear_cache_route():
    require_csrf_for_json()
    clear_cache()
    return jsonify({"status": "success", "message": "Cache cleared successfully"})

@app.route('/cache_status', methods=['GET'])
@requires_auth
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
@requires_auth
def get_email_lists():
    try:
        lists = get_saved_email_lists()
        return jsonify({"status": "success", "lists": lists})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/email_lists', methods=['POST'])
@requires_auth
def save_email_list_route():
    require_csrf_for_json()
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
            return jsonify({"status": "error", "message": f"Error saving '{name}'"}), 400
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/email_lists/<int:list_id>', methods=['DELETE'])
@requires_auth
def delete_email_list_route(list_id):
    try:
        delete_email_list(list_id)
        return jsonify({"status": "success", "message": "List deleted successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/email_templates', methods=['GET'])
@requires_auth
def get_email_templates():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, selected_items, email_text, subject, expanded_collections FROM email_templates ORDER BY name")
        templates = cursor.fetchall()
        conn.close()
        
        template_list = []
        for template in templates:
            template_list.append({
                'id': template[0],
                'name': template[1],
                'selected_items': template[2],
                'email_text': template[3],
                'subject': template[4],
                'expanded_collections': template[5] or '{}'
            })
        
        return jsonify(template_list)
    except Exception as e:
        print(f"Error getting templates: {e}")
        return jsonify([])

@app.route('/email_templates', methods=['POST'])
@requires_auth
def save_email_template():
    require_csrf_for_json()
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        selected_items = data.get('selected_items', '[]')
        email_text = data.get('email_text', '')
        subject = data.get('subject', '')
        expanded_collections = data.get('expanded_collections', '{}')
        
        if not name:
            return jsonify({"status": "error", "message": "Template name is required"}), 400
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM email_templates WHERE name = ?", (name,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE email_templates 
                SET selected_items = ?, email_text = ?, subject = ?, expanded_collections = ?, updated_at = CURRENT_TIMESTAMP
                WHERE name = ?
            """, (selected_items, email_text, subject, expanded_collections, name))
            message = "Template updated successfully"
        else:
            cursor.execute("""
                INSERT INTO email_templates (name, selected_items, email_text, subject, expanded_collections)
                VALUES (?, ?, ?, ?, ?)
            """, (name, selected_items, email_text, subject, expanded_collections))
            message = "Template saved successfully"
        
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "message": message})
    except Exception as e:
        print(f"Error saving template: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/email_templates/<int:template_id>', methods=['DELETE'])
@requires_auth
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
    app.jinja_env.globals["version"] = "v2025.2"
    app.jinja_env.globals["publish_date"] = "December 31, 2025"

    app.jinja_env.globals["get_cache_status"] = get_global_cache_status

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
    
    if getattr(sys, 'frozen', False):
        ROOT = Path(sys.executable).parent
    else:
        ROOT = Path(__file__).resolve().parent

    ENV_DIR = ROOT / "env"
    ENV_FILE = ENV_DIR / ".env"
    os.makedirs(ENV_DIR, exist_ok = True)
    if os.path.exists(ROOT / ".env"):
        shutil.move(ROOT / ".env", ROOT / "env" / ".env")
    
    if not ENV_FILE.exists():
        ENV_FILE.touch()
        try:
            ENV_FILE.chmod(0o600)
        except Exception:
            pass

    load_dotenv(ENV_FILE)
    
    DATA_IMG_RE = re.compile(
        r'^data:(image/(png|jpeg|jpg|gif|webp));base64,([A-Za-z0-9+/=]+)$',
        re.IGNORECASE
    )
    _WORKERS_STARTED = False
    _WORKERS_LOCK = threading.Lock()
    _RENDER_LOCK = threading.Lock()

    DATA_KEY = ensure_data_key()
    fernet = Fernet(DATA_KEY)
    if not app.secret_key:
        app.secret_key = secrets.token_hex(16) + DATA_KEY[:16]

    os.makedirs("database", exist_ok=True)
    
    migrate_data_from_separate_dbs()
    init_db(DB_PATH)
    migrate_schema("logo_filename TEXT")
    migrate_schema("logo_width INTEGER")
    migrate_schema("recipient_display_name TEXT DEFAULT 'email'")
    migrate_ra_recs_to_recently_added_recommendations()
    migrate_email_templates_for_expanded_collections()

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" and not app.debug:
        start_background_workers()

    app.run(host="0.0.0.0", port=6397, debug=True)
