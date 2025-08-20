import os, math, uuid, base64, smtplib, sqlite3, requests, time, threading, re
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv, set_key, find_dotenv
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.utils import make_msgid
from flask import Flask, render_template, request, jsonify, Response
from pathlib import Path
from plex_api_client import PlexAPI
from urllib.parse import quote_plus

app = Flask(__name__)
app.jinja_env.globals["version"] = "v0.8.7"
app.jinja_env.globals["publish_date"] = "August 19, 2025"

# Cache configuration
CACHE_DURATION = 300  # 5 minutes in seconds
cache_storage = {
    'stats': {'data': None, 'timestamp': 0},
    'users': {'data': None, 'timestamp': 0},
    'graph_data': {'data': None, 'timestamp': 0},
    'recent_data': {'data': None, 'timestamp': 0}
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
EMAIL_LISTS_DB_PATH = os.path.join("database", "email_lists.db")
EMAIL_TEMPLATES_DB_PATH = os.path.join("database", "email_templates.db")
EMAIL_HISTORY_DB_PATH = os.path.join("database", "email_history.db")
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

def is_cache_valid(cache_key):
    """Check if cache data is still valid"""
    cache_entry = cache_storage.get(cache_key)
    if cache_entry and cache_entry['data'] is not None:
        return time.time() - cache_entry['timestamp'] < CACHE_DURATION
    return False

def get_cached_data(cache_key):
    """Get cached data if valid"""
    if is_cache_valid(cache_key):
        return cache_storage[cache_key]['data']
    return None

def set_cached_data(cache_key, data):
    """Store data in cache with current timestamp"""
    cache_storage[cache_key] = {
        'data': data,
        'timestamp': time.time()
    }

def clear_cache(cache_key=None):
    """Clear specific cache or all cache if no key specified"""
    if cache_key:
        cache_storage[cache_key] = {'data': None, 'timestamp': 0}
    else:
        for key in cache_storage:
            cache_storage[key] = {'data': None, 'timestamp': 0}

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
    conn.commit()
    conn.close()

def init_email_lists_db(db_path):
    """Initialize the email lists database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_lists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            emails TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def init_email_templates_db(db_path):
    """Initialize the email templates database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
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
    conn.commit()
    conn.close()

def init_email_history_db(db_path):
    """Initialize the email history database"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS email_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            recipients TEXT NOT NULL,
            email_content TEXT,
            content_size_kb REAL,
            recipient_count INTEGER,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

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
    conn = sqlite3.connect(EMAIL_LISTS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, emails FROM email_lists ORDER BY name")
    lists = cursor.fetchall()
    conn.close()
    return [{'id': row[0], 'name': row[1], 'emails': row[2]} for row in lists]

def save_email_list(name, emails):
    """Save a new email list"""
    conn = sqlite3.connect(EMAIL_LISTS_DB_PATH)
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
    conn = sqlite3.connect(EMAIL_LISTS_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM email_lists WHERE id = ?", (list_id,))
    conn.commit()
    conn.close()

def apply_layout(body, graphs_html_block, stats_html_block, ra_html_block, recs_html_block, layout, subject, server_name):
    body = body.replace('\n', '<br>')
    body = body.replace('[GRAPHS]', graphs_html_block)
    body = body.replace('[STATS]', stats_html_block)
    body = body.replace('[RECENTLY_ADDED]', ra_html_block)
    body = body.replace('[RECOMENDATIONS]', recs_html_block)

    if subject.startswith(server_name):
        display_subject = subject[len(server_name):].lstrip()
    else:
        display_subject = subject

    if layout == "standard":
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
    elif layout == "recently_added":
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
                                                {ra_html_block}
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
    elif layout == "recommendations":
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
                                                <h1 class="footer-bar" style="margin-left: auto; margin-right: auto; width: 300px; border-top: 1px solid #E5A00D; margin-top: 5px;">Recommended For You</h1>
                                                {recs_html_block}
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
    else:
        return body

def run_tautulli_command(base_url, api_key, command, data_type, error, time_range='30'):
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
        # Check cache for stats
        stats = get_cached_data('stats')
        
        # Check cache for users
        users = get_cached_data('users')
        
        # Check cache for graph data
        graph_data = get_cached_data('graph_data') or []
        
        # Check cache for recent data
        recent_data = get_cached_data('recent_data') or []
        
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

            # Check cache first for stats
            if stats is None:
                stats, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', error, time_range)
                set_cached_data('stats', stats)
            
            # Check cache first for users
            if users is None:
                users, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_users', 'Users', error)
                set_cached_data('users', users)
            
            # Check cache first for graph data
            if not graph_data:
                graph_data = []
                for command in graph_commands:
                    gd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], error, time_range)
                    graph_data.append(gd)
                set_cached_data('graph_data', graph_data)
            
            # Check cache first for recent data
            if not recent_data:
                recent_data = []
                for command in recent_commands:
                    rd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_recently_added', command["command"], error, count)
                    recent_data.append(rd)
                set_cached_data('recent_data', recent_data)
            
            # Update user_dict with fresh users data
            user_dict = {}
            for user in users:
                if user['email'] != None and user['is_active']:
                    user_dict[user['user_id']] = user['email']
            
            # Update alert to show cache status
            cache_status = []
            if is_cache_valid('stats'): cache_status.append("stats")
            if is_cache_valid('users'): cache_status.append("users") 
            if is_cache_valid('graph_data'): cache_status.append("graphs")
            if is_cache_valid('recent_data'): cache_status.append("recent items")
            
            if cache_status:
                alert = f"Data loaded! Used cached: {', '.join(cache_status)}. Fresh data for {time_range} days, and {count} recently added items."
            else:
                alert = f"Users, graphs/stats for {time_range} days, and {count} recently added items pulled fresh!"

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
        
    return render_template('index.html',
                           stats=stats, user_dict=user_dict,
                           graph_data=graph_data, graph_commands=graph_commands,
                           recent_data=recent_data, libs=libs,
                           error=error, alert=alert, settings=settings,
                           email_lists=email_lists
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
                history_conn = sqlite3.connect(EMAIL_HISTORY_DB_PATH)
                history_cursor = history_conn.cursor()
                history_cursor.execute("""
                    INSERT INTO email_history (subject, recipients, email_content, content_size_kb, recipient_count)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    subject,
                    ', '.join(all_recipients),
                    email_content,
                    round(content_size_kb, 2),
                    len(all_recipients)
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
        conn = sqlite3.connect(EMAIL_HISTORY_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, subject, recipients, content_size_kb, recipient_count, sent_at 
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
                'sent_at': formatted_time
            })
        
        return render_template('email_history.html', emails=email_list)
    except Exception as e:
        print(f"Error loading email history: {e}")
        return render_template('email_history.html', emails=[])

@app.route('/email_history/recipients/<int:email_id>', methods=['GET'])
def get_email_recipients(email_id):
    """Get recipients for a specific email"""
    try:
        conn = sqlite3.connect(EMAIL_HISTORY_DB_PATH)
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
        conn = sqlite3.connect(EMAIL_TEMPLATES_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, selected_items, email_text, subject, layout FROM email_templates ORDER BY name")
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
                'layout': template[5]
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
        layout = data.get('layout', 'standard')
        
        if not name:
            return jsonify({"status": "error", "message": "Template name is required"}), 400
        
        conn = sqlite3.connect(EMAIL_TEMPLATES_DB_PATH)
        cursor = conn.cursor()
        
        # Check if template with this name already exists
        cursor.execute("SELECT id FROM email_templates WHERE name = ?", (name,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing template
            cursor.execute("""
                UPDATE email_templates 
                SET selected_items = ?, email_text = ?, subject = ?, layout = ?, updated_at = CURRENT_TIMESTAMP
                WHERE name = ?
            """, (selected_items, email_text, subject, layout, name))
            message = "Template updated successfully"
        else:
            # Create new template
            cursor.execute("""
                INSERT INTO email_templates (name, selected_items, email_text, subject, layout)
                VALUES (?, ?, ?, ?, ?)
            """, (name, selected_items, email_text, subject, layout))
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
        conn = sqlite3.connect(EMAIL_TEMPLATES_DB_PATH)
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
    init_db(DB_PATH)
    init_email_lists_db(EMAIL_LISTS_DB_PATH)
    init_email_templates_db(EMAIL_TEMPLATES_DB_PATH)
    init_email_history_db(EMAIL_HISTORY_DB_PATH)
    migrate_schema("conjurr_url TEXT")
    app.run(host="127.0.0.1", port=6397, debug=True)
