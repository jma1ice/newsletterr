import os, math, uuid, base64, smtplib, sqlite3, requests, time, threading
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv, set_key, find_dotenv
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify, Response
from pathlib import Path
from plex_api_client import PlexAPI
from urllib.parse import quote_plus

app = Flask(__name__)
app.jinja_env.globals["version"] = "v0.8.0"
app.jinja_env.globals["publish_date"] = "August 18, 2025"
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

load_dotenv(ENV_PATH)

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
                                                <h1 class="footer-bar" style="margin-left: auto; margin-right: auto; width: 250px; border-top: 1px solid #E5A00D; margin-top: 5px;">{display_subject}</h1>
                                                <p>
                                                    {body}
                                                </p>
                                                <div class="footer-bar" style="margin-left: auto; margin-right: auto; width: 250px; border-top: 1px solid #E5A00D; margin-top: 25px;">&nbsp;</div>
                                                <div class="content-block powered-by" style="padding-bottom: 10px; padding-top: 0;">Generated for Plex Media Server by newsletterr</div>
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
                                                <h1 class="footer-bar" style="margin-left: auto; margin-right: auto; width: 250px; border-top: 1px solid #E5A00D; margin-top: 5px;">{display_subject}</h1>
                                                {ra_html_block}
                                                <div class="footer-bar" style="margin-left: auto; margin-right: auto; width: 250px; border-top: 1px solid #E5A00D; margin-top: 25px;">&nbsp;</div>
                                                <div class="content-block powered-by" style="padding-bottom: 10px; padding-top: 0;">Generated for Plex Media Server by newsletterr</div>
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
                                                <h1 class="footer-bar" style="margin-left: auto; margin-right: auto; width: 250px; border-top: 1px solid #E5A00D; margin-top: 5px;">{display_subject}</h1>
                                                {recs_html_block}
                                                <div class="footer-bar" style="margin-left: auto; margin-right: auto; width: 250px; border-top: 1px solid #E5A00D; margin-top: 25px;">&nbsp;</div>
                                                <div class="content-block powered-by" style="padding-bottom: 10px; padding-top: 0;">Generated for Plex Media Server by newsletterr</div>
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
    except Exception:
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

            stats, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', error, time_range)
            users, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_users', 'Users', error)
            for command in graph_commands:
                gd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], error, time_range)
                graph_data.append(gd)
            for command in recent_commands:
                rd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_recently_added', command["command"], error, count)
                recent_data.append(rd)
            
            for user in users:
                if user['email'] != None and user['is_active']:
                    user_dict[user['user_id']] = user['email']
            
            alert = f"Users, graphs/stats for {time_range} days, and {count} recently added items pulled!"

    if graph_data == []:
        graph_data = [{},{}]

    if recent_data == []:
        recent_data = [{},{}]
        
    libs = ['movies', 'shows']
        
    return render_template('index.html',
                           stats=stats, user_dict=user_dict,
                           graph_data=graph_data, graph_commands=graph_commands,
                           recent_data=recent_data, libs=libs,
                           error=error, alert=alert, settings=settings
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
            "from_email": row[0],
            "alias_email": row[1],
            "password": row[2],
            "smtp_server": row[3],
            "smtp_port": int(row[4]),
            "server_name": row[5]
        }
    else:
        return jsonify({"error": "Please enter email info on settings page"}), 500

    data = request.get_json()

    graphs = data['graphs']
    stats = data['stats']
    recently_added = data['recently_added']
    recommendations = data['recommendations']
    from_email = settings['from_email']
    alias_email = settings['alias_email']
    password = settings['password']
    smtp_server = settings['smtp_server']
    smtp_port = int(settings['smtp_port'])
    server_name = settings['server_name']
    to_emails = data['to_emails'].split(", ")
    subject = data['subject']
    email_text = data['email_text']
    layout = data.get('layout', 'none')

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

    html_graphs = []
    for graph in graphs:
        cid = str(uuid.uuid4())

        html_graphs.append(f'<p><img src="cid:{cid}" style="max-width: 100%;"></p>')

        base64_data = graph['img'].split(',')[1]
        image_data = base64.b64decode(base64_data)

        image_part = MIMEImage(image_data, _subtype='png')
        image_part.add_header('Content-ID', f'<{cid}>')
        image_part.add_header('Content-Disposition', 'inline', filename=f'{cid}.png')
        msg_root.attach(image_part)
    graphs_html_block = ''.join(html_graphs)

    html_stats = []
    for stat in stats:
        cid = str(uuid.uuid4())

        html_stats.append(f'<p><img src="cid:{cid}" style="max-width: 100%;"></p>')

        base64_data = stat['img'].split(',')[1]
        image_data = base64.b64decode(base64_data)

        image_part = MIMEImage(image_data, _subtype='png')
        image_part.add_header('Content-ID', f'<{cid}>')
        image_part.add_header('Content-Disposition', 'inline', filename=f'{cid}.png')
        msg_root.attach(image_part)
    stats_html_block = ''.join(html_stats)

    html_ra = []
    for ra_image in recently_added:
        raw = base64.b64decode(ra_image.get('base64',''))
        subtype = (ra_image.get('mime','image/png').split('/',1)[-1]) or 'png'

        img = MIMEImage(raw, _subtype=subtype)
        cid = ra_image.get('cid','asset.png')
        html_ra.append(f'<p><img src="cid:{cid}" style="max-width: 100%;"></p>')
        img.add_header('Content-ID', f'<{cid}>')
        img.add_header('Content-Disposition', 'inline', filename=cid)
        msg_root.attach(img)
    ra_html_block = ''.join(html_ra)

    html_recs = []
    for rec in recommendations:
        raw = base64.b64decode(rec.get('base64',''))
        subtype = (rec.get('mime','image/png').split('/',1)[-1]) or 'png'

        img = MIMEImage(raw, _subtype=subtype)
        cid = rec.get('cid','asset.png')
        html_recs.append(f'<p><img src="cid:{cid}" style="max-width: 100%;"></p>')
        img.add_header('Content-ID', f'<{cid}>')
        img.add_header('Content-Disposition', 'inline', filename=cid)
        msg_root.attach(img)
    recs_html_block = ''.join(html_recs)

    html_content = apply_layout(email_text, graphs_html_block, stats_html_block, ra_html_block, recs_html_block, layout, subject, server_name)

    msg_alternative.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(from_email, decrypt(password))
            if alias_email == '':
                server.sendmail(from_email, [from_email] + to_emails, msg_root.as_string())
            else:
                server.sendmail(alias_email, [alias_email] + to_emails, msg_root.as_string())
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
            "from_email": row[0],
            "alias_email": row[1],
            "password": decrypt(row[2]),
            "smtp_server": row[3],
            "smtp_port": int(row[4]),
            "server_name": row[5],
            "plex_token": row[6],
            "tautulli_url": row[7],
            "tautulli_api": decrypt(row[8]),
            "conjurr_url": row[9]
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

if __name__ == '__main__':
    os.makedirs("database", exist_ok=True)
    init_db(DB_PATH)
    migrate_schema("conjurr_url TEXT")
    app.run(host="127.0.0.1", port=6397, debug=True)
