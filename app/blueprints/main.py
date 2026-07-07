import secrets
import sqlite3, time

from flask import Blueprint, Response, jsonify, redirect, render_template, request, session, url_for
from urllib.parse import quote

from app import config, state
from app.cache import is_cache_valid, get_cached_data, get_cache_info, clear_cache
from app.crypto import decrypt
from app.security import require_csrf_for_json, requires_auth, safe_get
from app.store import get_saved_email_lists
from app.theme import get_theme_settings

bp = Blueprint('main', __name__)

@bp.route('/', methods=['GET'])
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
    droppedneedle_wrapped_json = {}
    droppedneedle_server_json = None
    error = None
    alert = None

    username = ""
    if session.get('username'):
        username = session.get('username')

    conn = sqlite3.connect(config.DB_PATH)
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
        default_intro_text = cursor.execute("SELECT default_intro_text FROM settings WHERE id = 1").fetchone()[0]
        default_outro_text = cursor.execute("SELECT default_outro_text FROM settings WHERE id = 1").fetchone()[0]
        recently_added_mode = cursor.execute("SELECT recently_added_mode FROM settings WHERE id = 1").fetchone()[0]
        recently_added_sort = cursor.execute("SELECT recently_added_sort FROM settings WHERE id = 1").fetchone()[0]
        ra_grid_columns = cursor.execute("SELECT ra_grid_columns FROM settings WHERE id = 1").fetchone()[0]
        recs_grid_columns = cursor.execute("SELECT recs_grid_columns FROM settings WHERE id = 1").fetchone()[0]
        stat_cover_art = cursor.execute("SELECT stat_cover_art FROM settings WHERE id = 1").fetchone()[0]
        poster_max_height = cursor.execute("SELECT poster_max_height FROM settings WHERE id = 1").fetchone()[0]
        logo_position = cursor.execute("SELECT logo_position FROM settings WHERE id = 1").fetchone()[0]
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
        default_intro_text = cursor.execute("SELECT default_intro_text FROM settings WHERE id = 1").fetchone()
        default_outro_text = cursor.execute("SELECT default_outro_text FROM settings WHERE id = 1").fetchone()
        recently_added_mode = cursor.execute("SELECT recently_added_mode FROM settings WHERE id = 1").fetchone()
        recently_added_sort = cursor.execute("SELECT recently_added_sort FROM settings WHERE id = 1").fetchone()
        ra_grid_columns = cursor.execute("SELECT ra_grid_columns FROM settings WHERE id = 1").fetchone()
        recs_grid_columns = cursor.execute("SELECT recs_grid_columns FROM settings WHERE id = 1").fetchone()
        stat_cover_art = cursor.execute("SELECT stat_cover_art FROM settings WHERE id = 1").fetchone()
        poster_max_height = cursor.execute("SELECT poster_max_height FROM settings WHERE id = 1").fetchone()
        logo_position = cursor.execute("SELECT logo_position FROM settings WHERE id = 1").fetchone()

    settings = {
        "from_email": from_email or "",
        "server_name": server_name or "",
        "tautulli_url": tautulli_url or "",
        "tautulli_api": decrypt(tautulli_api),
        "email_theme": email_theme or "",
        "custom_logo_filename": custom_logo_filename or "",
        "recipient_display_name": recipient_display_name or "email",
        "default_intro_text": default_intro_text or "",
        "default_outro_text": default_outro_text or "",
        "recently_added_mode": recently_added_mode or "items",
        "recently_added_sort": recently_added_sort or "date",
        "ra_grid_columns": ra_grid_columns or "5",
        "recs_grid_columns": recs_grid_columns or "5",
        "stat_cover_art": stat_cover_art or "disabled",
        "poster_max_height": poster_max_height or "",
        "logo_position": logo_position or "center",
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
        return redirect(url_for('settings.settings'))
    
    conn.close()

    if settings['server_name'] != "":
        stats = get_cached_data('stats', strict=True) or get_cached_data('stats', strict=False)
        users = get_cached_data('users', strict=True) or get_cached_data('users', strict=False)
        graph_data = get_cached_data('graph_data', strict=True) or get_cached_data('graph_data', strict=False) or []
        recent_data = get_cached_data('recent_data', strict=True) or get_cached_data('recent_data', strict=False) or []
        recommendations_json = get_cached_data('recommendations_json', strict=True) or get_cached_data('recommendations_json', strict=False) or {}
        filtered_users = get_cached_data('filtered_users', strict=True) or get_cached_data('filtered_users', strict=False) or {}
        droppedneedle_wrapped_json = get_cached_data('droppedneedle_wrapped_json', strict=True) or get_cached_data('droppedneedle_wrapped_json', strict=False) or {}
        droppedneedle_server_json = get_cached_data('droppedneedle_server_json', strict=True) or get_cached_data('droppedneedle_server_json', strict=False)
        
        if users:
            users_full_data = users
            for user in users:
                if user['email'] != None and user['is_active']:
                    user_dict[user['user_id']] = user['email']

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
                           droppedneedle_wrapped_json=droppedneedle_wrapped_json, droppedneedle_server_json=droppedneedle_server_json,
                           nonce=secrets.token_urlsafe(16), csrf_token=session["csrf_token"], username=username
                        )

@bp.route('/proxy-art/<path:art_path>')
@requires_auth
def proxy_art(art_path):
    conn = sqlite3.connect(config.DB_PATH)
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

@bp.get("/proxy-img")
@requires_auth
def proxy_img():
    url = request.args.get("u", "")
    if not url.startswith(("http://","https://")):
        return Response(status=400)
    r = safe_get(url, timeout=15)
    ct = r.headers.get("Content-Type", "image/jpeg")
    return Response(r.content, headers={"Content-Type": ct, "Cache-Control": "public, max-age=86400"})

@bp.route('/about', methods=['GET'])
@requires_auth
def about():
    return render_template('about.html')

@bp.route('/clear_cache', methods=['POST'])
@requires_auth
def clear_cache_route():
    require_csrf_for_json()
    clear_cache()
    return jsonify({"status": "success", "message": "Cache cleared successfully"})

@bp.route('/cache_status', methods=['GET'])
@requires_auth
def cache_status():
    status = {}
    for key in state.cache_storage:
        status[key] = {
            'has_data': state.cache_storage[key]['data'] is not None,
            'is_valid': is_cache_valid(key),
            'age_seconds': int(time.time() - state.cache_storage[key]['timestamp']) if state.cache_storage[key]['timestamp'] > 0 else 0
        }
    return jsonify(status)
