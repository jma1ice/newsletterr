import json, os, shutil, sqlite3, time

from app import config

import logging

logger = logging.getLogger(__name__)

def db_connect(row_factory=None):
    """Open a connection to the app database.

    WAL journaling plus a busy timeout let the scheduler thread and the
    gthread request workers write concurrently without "database is locked"
    errors. WAL is a persistent property of the file (set once, cheap to
    re-assert); busy_timeout is per-connection. Callers own closing.
    """
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA journal_mode=WAL")
    if row_factory is not None:
        conn.row_factory = row_factory
    return conn

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
            plex_web_url TEXT DEFAULT 'https://app.plex.tv/desktop',
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
            login_toggle TEXT DEFAULT "disabled",
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
            template_name TEXT,  -- Name of template used (NULL/Manual for legacy/manual sends)
            status TEXT DEFAULT 'sent',  -- 'sent' or 'failed'
            error TEXT  -- failure reason when status = 'failed'
        )
    """)

    try:
        cursor.execute("PRAGMA table_info(email_history)")
        cols = [r[1] for r in cursor.fetchall()]
        if 'template_name' not in cols:
            cursor.execute("ALTER TABLE email_history ADD COLUMN template_name TEXT")
        if 'status' not in cols:
            cursor.execute("ALTER TABLE email_history ADD COLUMN status TEXT DEFAULT 'sent'")
        if 'error' not in cols:
            cursor.execute("ALTER TABLE email_history ADD COLUMN error TEXT")
    except Exception as _e:
        logger.warning(f"Warning: could not ensure email_history columns exist: {_e}")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppressed_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL COLLATE NOCASE,
            unsubscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hosted_images (
            token TEXT PRIMARY KEY,
            content_type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

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
        logger.info("Adding send_time column to email_schedules table...")
        cursor.execute("ALTER TABLE email_schedules ADD COLUMN send_time TEXT DEFAULT '09:00'")
        conn.commit()
    
    if 'date_range' not in columns:
        logger.info("Adding date_range column to email_schedules table...")
        cursor.execute("ALTER TABLE email_schedules ADD COLUMN date_range INTEGER DEFAULT 7")
        conn.commit()

    if 'items_count' not in columns:
        logger.info("Adding items_count column to email_schedules table...")
        cursor.execute("ALTER TABLE email_schedules ADD COLUMN items_count INTEGER DEFAULT 10")
        conn.commit()
    
    cursor.execute("PRAGMA table_info(settings)")
    settings_columns = [column[1] for column in cursor.fetchall()]
    if 'smtp_username' not in settings_columns:
        logger.info("Adding smtp_username column to settings table...")
        cursor.execute("ALTER TABLE settings ADD COLUMN smtp_username TEXT")
        conn.commit()

    if 'smtp_protocol' not in settings_columns:
        logger.info("Adding smtp_protocol column to settings table...")
        cursor.execute("ALTER TABLE settings ADD COLUMN smtp_protocol TEXT")
        conn.commit()

    if 'reply_to_email' not in settings_columns:
        logger.info("Adding reply_to_email column to settings table...")
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
            logger.info(f"Adding {col_name} column to settings table...")
            cursor.execute(f'ALTER TABLE settings ADD COLUMN {col_name} {col_def}')
            conn.commit()

    if 'from_name' not in settings_columns:
        logger.info("Adding from_name column to settings table...")
        cursor.execute("ALTER TABLE settings ADD COLUMN from_name TEXT")
        conn.commit()

    login_columns = [
        ('login_toggle', 'TEXT DEFAULT "disabled"'),
        ('nl_username', 'TEXT'),
        ('nl_password', 'TEXT')
    ]
    for col_name, col_def in login_columns:
        if col_name not in settings_columns:
            logger.info(f"Adding {col_name} column to settings table...")
            cursor.execute(f'ALTER TABLE settings ADD COLUMN {col_name} {col_def}')
            conn.commit()

    cursor.execute("PRAGMA table_info(settings)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'custom_logo_filename' not in columns:
        logger.info("Adding custom_logo_filename column to settings table...")
        cursor.execute("ALTER TABLE settings ADD COLUMN custom_logo_filename TEXT")
        conn.commit()

    cursor.execute("PRAGMA table_info(settings)")
    columns = [column[1] for column in cursor.fetchall()]
    for col_name, col_def in [('default_intro_text', 'TEXT DEFAULT ""'), ('default_outro_text', 'TEXT DEFAULT ""'), ('hsts_enabled', 'TEXT DEFAULT "disabled"'), ('scheduled_subject_prefix', 'TEXT DEFAULT "enabled"'), ('logo_position', 'TEXT DEFAULT "center"'), ('hide_stat_play_counts', 'TEXT DEFAULT "disabled"'), ('hide_graph_play_counts', 'TEXT DEFAULT "disabled"'), ('stats_type', 'TEXT DEFAULT "plays"'), ('recently_added_mode', 'TEXT DEFAULT "items"'), ('recently_added_sort', 'TEXT DEFAULT "date"'), ('ra_grid_columns', 'TEXT DEFAULT "5"'), ('recs_grid_columns', 'TEXT DEFAULT "5"'), ('stat_cover_art', 'TEXT DEFAULT "disabled"'), ('send_mode', 'TEXT DEFAULT "bcc"'), ('poster_max_height', 'TEXT DEFAULT ""'), ('droppedneedle_url', 'TEXT DEFAULT ""'), ('droppedneedle_api_key', 'TEXT DEFAULT ""'), ('discord_webhook_url', 'TEXT DEFAULT ""'), ('sonarr_url', 'TEXT DEFAULT ""'), ('sonarr_api_key', 'TEXT DEFAULT ""'), ('radarr_url', 'TEXT DEFAULT ""'), ('radarr_api_key', 'TEXT DEFAULT ""'), ('coming_soon_days_ahead', 'TEXT DEFAULT "14"'), ('coming_soon_grid_columns', 'TEXT DEFAULT "5"'), ('hosted_enabled', 'TEXT DEFAULT "disabled"'), ('hosted_base_url', 'TEXT DEFAULT ""'), ('hosted_images_enabled', 'TEXT DEFAULT "disabled"'), ('ra_show_description', 'TEXT DEFAULT "enabled"'), ('collections_grid_columns', 'TEXT DEFAULT "5"'), ('exclude_inactive_days', 'TEXT DEFAULT "0"'), ('include_user_info', 'TEXT DEFAULT "enabled"'), ('email_size_warn_mb', 'TEXT DEFAULT "10"'), ('appearance_theme', 'TEXT DEFAULT "dark"'), ('pride_flag', 'TEXT DEFAULT "off"'), ('snapins_floating', 'TEXT DEFAULT "1"'), ('hosted_image_retention_days', 'TEXT DEFAULT "90"'), ('hosted_links_enabled', 'TEXT DEFAULT "disabled"'), ('hosted_links_base_url', 'TEXT DEFAULT ""')]:
        if col_name not in columns:
            logger.info(f"Adding {col_name} column to settings table...")
            cursor.execute(f'ALTER TABLE settings ADD COLUMN {col_name} {col_def}')
            conn.commit()

    conn.close()

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
    
    logger.info("Migrating data from separate database files to unified database...")
    
    unified_conn = db_connect()
    unified_cursor = unified_conn.cursor()
    
    try:
        email_lists_path = os.path.join("database", "email_lists.db")
        if os.path.exists(email_lists_path):
            logger.info("Migrating email lists...")
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
            logger.info("Migrating email templates...")
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
            logger.info("Migrating email history...")
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
            logger.info("Migrating email schedules...")
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
        logger.info("Data migration completed successfully!")
        
        backup_dir = os.path.join("database", "backup_" + str(int(time.time())))
        os.makedirs(backup_dir, exist_ok=True)
        
        for db_path in separate_dbs:
            if os.path.exists(db_path):
                backup_path = os.path.join(backup_dir, os.path.basename(db_path))
                shutil.move(db_path, backup_path)
                logger.info(f"Moved {db_path} to {backup_path}")
                
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        unified_conn.rollback()
    finally:
        unified_conn.close()

def migrate_schema(column_def):
    conn = db_connect()
    try:
        col_name = column_def.split()[0]
        cursor = conn.execute("PRAGMA table_info('settings')")
        has_column = any(row[1] == col_name for row in cursor.fetchall())
        if not has_column:
            conn.execute(f"ALTER TABLE settings ADD COLUMN {column_def}")
            conn.commit()
    finally:
        conn.close()

def migrate_musicseerr_to_droppedneedle():
    conn = db_connect()
    try:
        cursor = conn.execute("PRAGMA table_info('settings')")
        columns = [row[1] for row in cursor.fetchall()]
        for old_col, new_col in [('musicseerr_url', 'droppedneedle_url'), ('musicseerr_api_key', 'droppedneedle_api_key')]:
            if old_col in columns and new_col not in columns:
                conn.execute(f"ALTER TABLE settings RENAME COLUMN {old_col} TO {new_col}")
        conn.commit()

        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='email_templates'")
        if cursor.fetchone():
            cursor = conn.execute("SELECT id, selected_items FROM email_templates WHERE selected_items LIKE '%musicseerr%'")
            for template_id, selected_json in cursor.fetchall():
                try:
                    items = json.loads(selected_json)
                except json.JSONDecodeError:
                    continue
                changed = False
                for item in items:
                    if isinstance(item, dict) and item.get("type") in ("musicseerr_wrapped", "musicseerr_server_stats"):
                        item["type"] = item["type"].replace("musicseerr", "droppedneedle")
                        changed = True
                if changed:
                    conn.execute("UPDATE email_templates SET selected_items = ? WHERE id = ?", (json.dumps(items, ensure_ascii=False), template_id))
            conn.commit()
    except Exception as e:
        logger.exception(f"Error migrating musicseerr columns to droppedneedle: {e}")
    finally:
        conn.close()

def migrate_ra_recs_to_recently_added_recommendations():
    conn = db_connect()
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

    logger.info(f"Updated {updated} templates successfully.")

def migrate_email_templates_for_expanded_collections():
    try:
        conn = db_connect()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(email_templates)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'expanded_collections' not in columns:
            logger.info("Adding expanded_collections column to email_templates table...")
            cursor.execute("ALTER TABLE email_templates ADD COLUMN expanded_collections TEXT DEFAULT '{}'")
            conn.commit()
            logger.info("Successfully added expanded_collections column")
            
        conn.close()
        
    except Exception as e:
        logger.exception(f"Error migrating email_templates table: {e}")

def migrate_email_templates_for_header_title():
    try:
        conn = db_connect()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT server_name FROM settings WHERE id = 1")
            row = cursor.fetchone()
            server_name = row[0]
        except Exception:
            logger.debug("suppressed exception; using fallback", exc_info=True)
            server_name = "Server"

        cursor.execute("PRAGMA table_info(email_templates)")
        columns = [column[1] for column in cursor.fetchall()]

        if 'email_header_title' not in columns:
            logger.info("Adding email_header_title column to email_templates table...")
            cursor.execute("ALTER TABLE email_templates ADD COLUMN email_header_title TEXT")
            conn.commit()

            cursor.execute("UPDATE email_templates SET email_header_title = ? WHERE email_header_title IS NULL", (f"{server_name} Newsletter",))
            conn.commit()
            logger.info("Successfully added and backfilled email_header_title column")

        conn.close()
    except Exception as e:
        logger.exception(f"Error migrating email_templates for email_header_title: {e}")

def migrate_email_templates_for_custom_html():
    try:
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(email_templates)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'custom_html' not in columns:
            logger.info("Adding custom_html column to email_templates table...")
            cursor.execute("ALTER TABLE email_templates ADD COLUMN custom_html TEXT DEFAULT ''")
            conn.commit()
        conn.close()
    except Exception as e:
        logger.exception(f"Error migrating email_templates for custom_html: {e}")

def migrate_email_history_for_hosted_html():
    try:
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(email_history)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'hosted_html' not in columns:
            logger.info("Adding hosted_html column to email_history table...")
            cursor.execute("ALTER TABLE email_history ADD COLUMN hosted_html TEXT")
            conn.commit()
        conn.close()
    except Exception as e:
        logger.exception(f"Error migrating email_history for hosted_html: {e}")
