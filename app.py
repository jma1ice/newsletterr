import os
import math
import uuid
import base64
import smtplib
import sqlite3
import requests
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify, Response, send_file

app = Flask(__name__)
app.jinja_env.globals["version"] = "v0.6.3"
app.jinja_env.globals["publish_date"] = "August 7, 2025"

DB_PATH = os.path.join("database", "data.db")

@app.route('/favicon.ico')
def favicon():
    return send_file('favicon.ico', mimetype='image/x-icon')

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
            tautulli_api TEXT
        )
    """)
    conn.commit()
    conn.close()

def apply_layout(body, graphs_html_block, stats_html_block, layout, subject, server_name):
    body = body.replace('\n', '<br>')
    body = body.replace('[GRAPHS]', graphs_html_block)
    body = body.replace('[STATS]', stats_html_block)

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
                        <td class="container" style="font-family: 'IBM Plex Sans', Helvetica, Arial, sans-serif; font-size: 14px; vertical-align: top; display: block; max-width: 1042px; padding: 10px; width: 1042px; margin: 0 auto !important;">
                            <div class="content" style="box-sizing: border-box; display: block; margin: 0 auto; max-width: 1037px; padding: 10px;"><span class="preheader" style="color: transparent; display: none; height: 0; max-height: 0; max-width: 0; opacity: 0; overflow: hidden; mso-hide: all; visibility: hidden; width: 0;">{server_name} Newsletter</span>
                                <table class="main" style="border-collapse: separate; mso-table-lspace: 0pt; mso-table-rspace: 0pt; width: 100%; background: #282A2D; border-radius: 3px; color: #ffffff;" border="0" cellspacing="0" cellpadding="3">
                                    <tbody>
                                        <tr>
                                            <td class="wrapper" style="font-family: 'IBM Plex Sans', Helvetica, Arial, sans-serif; font-size: 14px; vertical-align: top; box-sizing: border-box; padding: 5px; overflow: auto;">
                                                <div class="header" style="width: 50%; height: 10px; text-align: center;"><img class="header-img" style="border: none; -ms-interpolation-mode: bicubic; max-width: 9%; width: 492px; height: 20px; margin-left: -35px;" src="https://d15k2d11r6t6rl.cloudfront.net/public/users/Integrators/669d5713-9b6a-46bb-bd7e-c542cff6dd6a/3bef3c50f13f4320a9e31b8be79c6ad2/Plex%20Logo%20Update%202022/plex-logo-heavy-stroke.png" width="492" height="90" /></div>
                                                <div class="server-name" style="font-size: 25px; text-align: center; margin-bottom: 0;">{server_name} Newsletter</div>
                                            </td>
                                        </tr>
                                        <tr>
                                            <td class="footer" style="font-family: 'IBM Plex Sans', Helvetica, Arial, sans-serif; font-size: 12px; vertical-align: top; clear: both; margin-top: 0; text-align: center; width: 100%;">
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
    else:
        return body

def run_tautulli_command(base_url, api_key, command, data_type, error, time_range='30'):
    if command == 'get_users':
        api_url = f"{base_url}/api/v2?apikey={api_key}&cmd={command}"
    else:
        if command == 'get_plays_per_month':
            month_range = str(math.ceil(int(time_range) / 30))
            api_url = f"{base_url}/api/v2?apikey={api_key}&cmd={command}&time_range={month_range}"
        else:
            api_url = f"{base_url}/api/v2?apikey={api_key}&cmd={command}&time_range={time_range}"

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

@app.route('/', methods=['GET', 'POST'])
def index():
    stats = None
    users = None
    user_emails = []
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
    graph_data = []
    error = None
    alert = None

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
        from_email, alias_email, password, smtp_server, smtp_port, server_name, plex_url, plex_token, tautulli_url, tautulli_api
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
            "server_name": row[5],
            "plex_url": row[6],
            "plex_token": row[7],
            "tautulli_url": row[8],
            "tautulli_api": row[9]
        }
    else:
        settings = {
            "from_email": ""
        }

    if request.method == 'POST':
        if settings['from_email'] == "":
            return render_template('index.html', error='Please enter tautulli info on settings page',
                                    stats=stats, user_emails=user_emails, graph_data=graph_data,
                                    graph_commands=graph_commands, alert=alert, settings=settings)
        else:
            time_range = request.form.get("days_to_pull")
            base_url = settings['tautulli_url'].rstrip('/')
            api_key = settings['tautulli_api']

            stats, error = run_tautulli_command(base_url, api_key, 'get_home_stats', 'Stats', error, time_range)
            users, error = run_tautulli_command(base_url, api_key, 'get_users', 'Users', error)
            for command in graph_commands:
                gd, error = run_tautulli_command(base_url, api_key, command["command"], command["name"], error, time_range)
                graph_data.append(gd)
            
            for user in users:
                if user['email'] != None and user['is_active']:
                    user_emails.append(user['email'])
            
            alert = f"Users and graphs/stats for {time_range} days pulled successfully!"

    if graph_data == []:
        graph_data = [{},{}]
        
    return render_template('index.html',
                           stats=stats, user_emails=user_emails,
                           graph_data=graph_data, graph_commands=graph_commands,
                           error=error, alert=alert, settings=settings
                        )

@app.route('/proxy-art/<path:art_path>')
def proxy_art(art_path):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
        from_email, alias_email, password, smtp_server, smtp_port, server_name, plex_url, plex_token, tautulli_url, tautulli_api
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
            "server_name": row[5],
            "plex_url": row[6],
            "plex_token": row[7],
            "tautulli_url": row[8],
            "tautulli_api": row[9]
        }
    else:
        settings = {
            "from_email": ""
        }

    plex_token = settings['plex_token']
    plex_url = settings['plex_url'].rstrip('/')

    full_url = f"{plex_url}/{art_path}?X-Plex-Token={plex_token}"
    r = requests.get(full_url, stream=True)
    return Response(r.content, content_type=r.headers['Content-Type'])

@app.route('/send_email', methods=['POST'])
def send_email():
    alert = None
    error = None

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
        from_email, alias_email, password, smtp_server, smtp_port, server_name, tautulli_url, tautulli_api
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
            "server_name": row[5],
            "tautulli_url": row[6],
            "tautulli_api": row[7]
        }
    else:
        return jsonify({"error": "Please enter email info on settings page"}), 500

    data = request.get_json()

    graphs = data['graphs']
    stats = data['stats']
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

    html_content = apply_layout(email_text, graphs_html_block, stats_html_block, layout, subject, server_name)

    msg_alternative.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(from_email, password)
            if alias_email == '':
                server.sendmail(from_email, [from_email] + to_emails, msg_root.as_string())
            else:
                server.sendmail(alias_email, [alias_email] + to_emails, msg_root.as_string())
            #alert = "Email sent!"
        return jsonify({"success": True})
    except Exception as e:
        #error = f"Error: {str(e)}"
        return jsonify({"error": str(e)}), 500
    #return render_template('index.html', alert=alert, error=error)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if request.method == "POST":
        from_email = request.form.get("from_email")
        alias_email = request.form.get("alias_email")
        password = request.form.get("password")
        smtp_server = request.form.get("smtp_server")
        smtp_port = int(request.form.get("smtp_port"))
        server_name = request.form.get("server_name")
        plex_url = request.form.get("plex_url")
        plex_token = request.form.get("plex_token")
        tautulli_url = request.form.get("tautulli_url")
        tautulli_api = request.form.get("tautulli_api")

        cursor.execute("""
            REPLACE INTO settings
            (id, from_email, alias_email, password, smtp_server, smtp_port, server_name, plex_url, plex_token, tautulli_url, tautulli_api)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (from_email, alias_email, password, smtp_server, smtp_port, server_name, plex_url, plex_token, tautulli_url, tautulli_api))
        conn.commit()
        conn.close()

        settings = {
            "from_email": from_email,
            "alias_email": alias_email,
            "password": password,
            "smtp_server": smtp_server,
            "smtp_port": smtp_port,
            "server_name": server_name,
            "plex_url": plex_url,
            "plex_token": plex_token,
            "tautulli_url": tautulli_url,
            "tautulli_api": tautulli_api
        }

        return render_template('settings.html', alert="Settings saved successfully!", settings=settings)

    cursor.execute("""
        SELECT
        from_email, alias_email, password, smtp_server, smtp_port, server_name, plex_url, plex_token, tautulli_url, tautulli_api
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
            "server_name": row[5],
            "plex_url": row[6],
            "plex_token": row[7],
            "tautulli_url": row[8],
            "tautulli_api": row[9]
        }
    else:
        settings = {
            "from_email": ""
        }

    return render_template('settings.html', settings=settings)

@app.route('/about', methods=['GET'])
def about():
    return render_template('about.html')

if __name__ == '__main__':
    os.makedirs("database", exist_ok=True)
    init_db(DB_PATH)
    app.run(host="127.0.0.1", port=6397, debug=True)
