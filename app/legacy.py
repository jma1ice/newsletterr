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

from app import config, state
from app.crypto import encrypt, decrypt
from app.scheduler import start_background_workers, background_scheduler, refresh_daily_cache
from app.hooks import inject_update_info, refresh_hsts_setting, set_security_headers
from app.emails.images import fetch_and_attach_image, fetch_and_attach_blurred_image, fetch_and_attach_small_thumbnail, truncate_text
from app.emails.blocks import build_graph_html_with_frontend_image, build_text_block_html, build_separator_html, build_image_html_with_cid, build_emoji_html
from app.emails.fetchers import fetch_tautulli_data_for_email, fetch_recent_data_for_index, get_current_tautulli_data_for_email, get_recommendations_for_users, get_droppedneedle_wrapped_for_users, get_droppedneedle_server_stats_cached
from app.emails.builders import get_user_display_name, build_enhanced_user_dict, get_stat_headers, get_stat_cells, build_stats_html_with_cid_background, build_recently_added_html_with_cids, build_recommendations_html_with_cids, _wrapped_ranked_list_html, build_droppedneedle_wrapped_html_with_cids, build_droppedneedle_server_stats_html_with_cids, build_recommendations_section_with_cids, build_individual_item_card_html, build_collection_card_html, build_collections_html_with_cids
from app.emails.assemble import convert_html_to_plain_text, attach_logo_image, build_email_html_with_all_cids, build_complete_email_html_with_cid_logo
from app.emails.send import group_recipients_by_user, send_standard_email_with_cids, send_recommendations_email_with_cids, send_single_user_email_with_cids
from app.render import capture_chart_images_via_headless
from app.emails.scheduled import send_scheduled_email, send_scheduled_email_with_cids, send_scheduled_user_email_with_cids, send_scheduled_single_email_with_cids
from app.clients.tautulli import run_tautulli_command
from app.clients.plex import get_plex_client_identifier, get_plex_headers, get_plex_machine_id, build_plex_web_link, search_plex_for_rating_key, fetch_tv_shows_from_plex_sdk, fetch_movies_from_plex_sdk, fetch_albums_from_plex_sdk, fetch_recently_added_using_plex_sdk, get_collection_items_for_email
from app.clients.conjurr import run_conjurr_command
from app.clients.droppedneedle import fetch_droppedneedle_users, run_droppedneedle_command, fetch_droppedneedle_server_stats
from app.clients.github import _norm, _check_github_latest, _ensure_recent_check, _background_update_checker
from app.cache import get_global_cache_status, can_use_cached_data_for_preview, is_cache_valid, get_cached_data, set_cached_data, get_cache_info, clear_cache, gkak
from app.db import init_db, migrate_data_from_separate_dbs, migrate_schema, migrate_musicseerr_to_droppedneedle, migrate_ra_recs_to_recently_added_recommendations, migrate_email_templates_for_expanded_collections, migrate_email_templates_for_header_title, migrate_email_templates_for_custom_html
from app.security import require_csrf_for_json, sanitize_html_input, escape_html_output, requires_auth, check_credentials, safe_get, sanitize_html
from app.theme import get_theme_settings, get_email_theme_colors, build_email_css_from_theme
from app.store import get_saved_email_lists, save_email_list, delete_email_list, get_email_schedules, calculate_next_send, create_email_schedule, update_email_schedule, delete_email_schedule, toggle_schedule_status, update_schedule_last_sent

app = Flask(__name__, template_folder = str(config.ASSET_ROOT / 'templates'), static_folder = str(config.ASSET_ROOT / 'static'))


@app.route('/', methods=['GET'])
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
        return redirect(url_for('settings'))
    
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    conn = sqlite3.connect(config.DB_PATH)
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

@app.route('/pull_stats', methods=['POST'])
@requires_auth
def pull_stats():
    require_csrf_for_json()
    data = request.get_json()
    time_range = str(data.get('time_range', 30))
    count = str(data.get('count', 10))

    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT tautulli_url, tautulli_api, server_name, stats_type, recently_added_mode, recently_added_sort FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Please enter tautulli info on settings page"}), 500

    tautulli_base_url = row[0].rstrip('/')
    tautulli_api_key = decrypt(row[1])
    stats_type = row[3] or 'plays'
    recently_added_mode = row[4] or 'items'
    recently_added_sort = row[5] or 'date'

    cache_params = {
        'time_range': time_range,
        'count': count,
        'url': tautulli_base_url,
        'timestamp': time.time()
    }

    stats, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_home_stats', 'Stats', None, time_range, stats_type=stats_type)
    set_cached_data('stats', stats, cache_params)

    users, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, 'get_users', 'Users', error)
    set_cached_data('users', users, cache_params)

    graph_data = []
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
    for command in graph_commands:
        try:
            gd, error = run_tautulli_command(tautulli_base_url, tautulli_api_key, command["command"], command["name"], error, time_range, y_axis=stats_type)
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

    recent_data = fetch_recent_data_for_index(tautulli_base_url, tautulli_api_key, count, recently_added_mode=recently_added_mode, recently_added_sort=recently_added_sort)
    set_cached_data('recent_data', recent_data, cache_params)

    user_dict = {}
    users_full_data = None
    if users:
        users_full_data = users
        for user in users:
            if user['email'] != None and user['is_active']:
                user_dict[user['user_id']] = user['email']

    return jsonify({
        "success": True,
        "alert": f"Fresh data loaded! Stats/graphs for {time_range} days, and recently added {'within last ' + count + ' days' if recently_added_mode == 'days' else count + ' items'}.",
        "stats": stats or [],
        "graph_data": graph_data,
        "graph_commands": graph_commands,
        "recent_data": recent_data,
        "user_dict": user_dict,
        "users_full_data": users_full_data,
        "cache_info": {
            "stats": get_cache_info('stats'),
            "users": get_cache_info('users'),
            "graph_data": get_cache_info('graph_data'),
            "recent_data": get_cache_info('recent_data'),
            "recommendations_json": get_cache_info('recommendations_json'),
            "filtered_users": get_cache_info('filtered_users'),
        },
        "time_range": time_range,
        "count": count,
        "error": error
    })

@app.route('/proxy-art/<path:art_path>')
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
        conn = sqlite3.connect(config.DB_PATH)
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
            headers = get_plex_headers({'X-Plex-Token': decrypt(plex_token)}),
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
                collections_response = safe_get(collections_url, headers=get_plex_headers({'X-Plex-Token': decrypt(plex_token)}), timeout=10)
                
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
        
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT plex_url, plex_token FROM settings WHERE id = 1")
        row = cursor.fetchone()
        conn.close()

        if not row or not row[0] or not row[1]:
            return jsonify({"status": "error", "message": "Plex connection not configured"})

        plex_url = row[0].rstrip('/')
        plex_token = row[1]
        
        collection_items_url = f"{plex_url}/library/collections/{collection_key}/children"
        
        headers = get_plex_headers({'X-Plex-Token': decrypt(plex_token)})
        
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

    conn = sqlite3.connect(config.DB_PATH)
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
                                    libs=libs, settings=settings, theme_settings=get_theme_settings())
        else:
            conjurr_base_url = conjurr_settings['conjurr_url']
            recommendations_json, error = run_conjurr_command(conjurr_base_url, filtered_users, error)
            if error:
                alert = None
            else:
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
                            recommendations_json=recommendations_json, filtered_users=filtered_users, alert=alert,
                            error=error, theme_settings=theme_settings)

@app.route('/pull_droppedneedle_stats', methods=['POST'])
@requires_auth
def pull_droppedneedle_stats():
    require_csrf_for_json()
    droppedneedle_wrapped_json = {}
    droppedneedle_server_json = None
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

    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT droppedneedle_url, droppedneedle_api_key FROM settings WHERE id = 1")
    row = cursor.fetchone()
    conn.close()

    droppedneedle_url = (row[0] or "").strip() if row else ""
    droppedneedle_api_key = decrypt(row[1]) if row and row[1] else ""

    filtered_users = {k: v for k, v in user_dict.items() if v in to_emails}

    if droppedneedle_url == "" or droppedneedle_api_key == "":
        return render_template('index.html', error='Please enter DroppedNeedle URL and API key on settings page',
                                stats=stats, user_dict=user_dict, graph_data=graph_data,
                                graph_commands=graph_commands, recent_data=recent_data,
                                libs=libs, settings=settings, theme_settings=get_theme_settings())

    droppedneedle_wrapped_json, error = run_droppedneedle_command(droppedneedle_url, droppedneedle_api_key, filtered_users, error)
    droppedneedle_server_json, server_error = fetch_droppedneedle_server_stats(droppedneedle_url, droppedneedle_api_key)
    if server_error:
        error = (error + ", " if error else "") + server_error

    if error:
        alert = None
    else:
        alert = "DroppedNeedle stats pulled!"

    cache_params = {'timestamp': time.time()}
    set_cached_data('droppedneedle_filtered_users', filtered_users, cache_params)
    set_cached_data('droppedneedle_wrapped_json', droppedneedle_wrapped_json, cache_params)
    set_cached_data('droppedneedle_server_json', droppedneedle_server_json, cache_params)

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
                            droppedneedle_wrapped_json=droppedneedle_wrapped_json, droppedneedle_server_json=droppedneedle_server_json,
                            alert=alert, error=error, theme_settings=theme_settings)

@app.route('/send_email', methods=['POST'])
@requires_auth
def send_email():
    require_csrf_for_json()
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
        from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, server_name, logo_filename, logo_width, from_name, custom_logo_filename, send_mode, poster_max_height
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
            "custom_logo_filename": row[12] or "",
            "send_mode": row[13] or "bcc",
            "poster_max_height": int(row[14] or 0)
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
    email_header_title = data.get('email_header_title')
    user_dict = data.get('user_dict', {})
    selected_items = data.get('selected_items', [])
    expanded_collections = data.get('expanded_collections', {})
    from_name = settings['from_name']
    custom_html = data.get('custom_html', '')

    has_recommendations = any(item.get('type') == 'recommendations' for item in selected_items)
    has_droppedneedle_wrapped = any(item.get('type') == 'droppedneedle_wrapped' for item in selected_items)

    send_mode = settings.get('send_mode', 'bcc')

    if (has_recommendations or has_droppedneedle_wrapped) and user_dict:
        return send_recommendations_email_with_cids(
            to_emails, subject, email_header_title, user_dict, selected_items,
            from_email, alias_email, reply_to_email, password, smtp_username,
            smtp_server, smtp_port, smtp_protocol, settings, from_name, custom_html,
            expanded_collections, send_mode=send_mode
        )
    else:
        return send_standard_email_with_cids(
            to_emails, subject, email_header_title, selected_items,
            from_email, alias_email, reply_to_email, password, smtp_username,
            smtp_server, smtp_port, smtp_protocol, settings, from_name, custom_html,
            expanded_collections, send_mode=send_mode
        )

@app.route('/settings', methods=['GET', 'POST'])
@requires_auth
def settings():
    conn = sqlite3.connect(config.DB_PATH)
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

        try:
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
            droppedneedle_url = request.form.get("droppedneedle_url")
            droppedneedle_api_key = encrypt(request.form.get("droppedneedle_api_key"))
            recipient_display_name = request.form.get("recipient_display_name", "email")
            logo_filename = request.form.get("logo_filename")
            logo_width = request.form.get("logo_width")
            email_theme = request.form.get("email_theme", "newsletterr_blue")
            from_name = request.form.get("from_name")
            custom_logo_filename = request.form.get("custom_logo_filename", "")
            login_toggle = request.form.get("login_toggle")
            nl_username = request.form.get("nl_username")
            nl_password = encrypt(request.form.get("nl_password"))
            default_intro_text = request.form.get("default_intro_text", "")
            default_outro_text = request.form.get("default_outro_text", "")
            hsts_enabled = request.form.get("hsts_enabled", "disabled")
            scheduled_subject_prefix = request.form.get("scheduled_subject_prefix", "enabled")
            logo_position = request.form.get("logo_position", "center")
            hide_stat_play_counts = request.form.get("hide_stat_play_counts", "disabled")
            hide_graph_play_counts = request.form.get("hide_graph_play_counts", "disabled")
            stats_type = request.form.get("stats_type", "plays")
            recently_added_mode = request.form.get("recently_added_mode", "items")
            recently_added_sort = request.form.get("recently_added_sort", "date")
            ra_grid_columns = request.form.get("ra_grid_columns", "5")
            recs_grid_columns = request.form.get("recs_grid_columns", "5")
            stat_cover_art = request.form.get("stat_cover_art", "disabled")
            send_mode = request.form.get("send_mode", "bcc")
            poster_max_height = request.form.get("poster_max_height", "")

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
                    tautulli_api, conjurr_url, droppedneedle_url, droppedneedle_api_key, recipient_display_name, logo_filename, logo_width, email_theme, primary_color, secondary_color, accent_color, background_color,
                    text_color, from_name, custom_logo_filename, login_toggle, nl_username, nl_password, default_intro_text, default_outro_text, hsts_enabled, scheduled_subject_prefix, logo_position, hide_stat_play_counts, hide_graph_play_counts, stats_type, recently_added_mode, recently_added_sort, ra_grid_columns, recs_grid_columns, stat_cover_art, send_mode, poster_max_height)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE
                SET from_email = excluded.from_email, alias_email = excluded.alias_email, reply_to_email = excluded.reply_to_email, password = excluded.password,
                    smtp_username = excluded.smtp_username, smtp_server = excluded.smtp_server, smtp_port = excluded.smtp_port, smtp_protocol = excluded.smtp_protocol,
                    server_name = excluded.server_name, plex_url = excluded.plex_url, tautulli_url = excluded.tautulli_url, tautulli_api = excluded.tautulli_api,
                    conjurr_url = excluded.conjurr_url, droppedneedle_url = excluded.droppedneedle_url, droppedneedle_api_key = excluded.droppedneedle_api_key, recipient_display_name = excluded.recipient_display_name, logo_filename = excluded.logo_filename, logo_width = excluded.logo_width,
                    email_theme = excluded.email_theme, primary_color = excluded.primary_color, secondary_color = excluded.secondary_color, accent_color = excluded.accent_color,
                    background_color = excluded.background_color, text_color = excluded.text_color, from_name = excluded.from_name, custom_logo_filename = excluded.custom_logo_filename,
                    login_toggle = excluded.login_toggle, nl_username = excluded.nl_username, nl_password = excluded.nl_password,
                    default_intro_text = excluded.default_intro_text, default_outro_text = excluded.default_outro_text,
                    hsts_enabled = excluded.hsts_enabled, scheduled_subject_prefix = excluded.scheduled_subject_prefix, logo_position = excluded.logo_position,
                    hide_stat_play_counts = excluded.hide_stat_play_counts, hide_graph_play_counts = excluded.hide_graph_play_counts,
                    stats_type = excluded.stats_type, recently_added_mode = excluded.recently_added_mode, recently_added_sort = excluded.recently_added_sort,
                    ra_grid_columns = excluded.ra_grid_columns, recs_grid_columns = excluded.recs_grid_columns,
                    stat_cover_art = excluded.stat_cover_art,
                    send_mode = excluded.send_mode,
                    poster_max_height = excluded.poster_max_height
            """, (from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, server_name, plex_url, tautulli_url, tautulli_api,
                  conjurr_url, droppedneedle_url, droppedneedle_api_key, recipient_display_name, logo_filename, logo_width, email_theme, primary_color, secondary_color, accent_color, background_color, text_color, from_name,
                  custom_logo_filename, login_toggle, nl_username, nl_password, default_intro_text, default_outro_text, hsts_enabled, scheduled_subject_prefix, logo_position,
                  hide_stat_play_counts, hide_graph_play_counts, stats_type, recently_added_mode, recently_added_sort, ra_grid_columns, recs_grid_columns, stat_cover_art, send_mode, poster_max_height))
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
                "droppedneedle_url": droppedneedle_url,
                "droppedneedle_api_key": decrypt(droppedneedle_api_key),
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
                "nl_password": decrypt(nl_password),
                "default_intro_text": default_intro_text,
                "default_outro_text": default_outro_text,
                "hsts_enabled": hsts_enabled,
                "scheduled_subject_prefix": scheduled_subject_prefix,
                "logo_position": logo_position,
                "hide_stat_play_counts": hide_stat_play_counts,
                "hide_graph_play_counts": hide_graph_play_counts,
                "stats_type": stats_type,
                "recently_added_mode": recently_added_mode,
                "recently_added_sort": recently_added_sort,
                "ra_grid_columns": ra_grid_columns,
                "recs_grid_columns": recs_grid_columns,
                "stat_cover_art": stat_cover_art,
                "send_mode": send_mode,
                "poster_max_height": poster_max_height,
            }

            refresh_hsts_setting()

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

        except Exception as e:
            try:
                cursor.execute("SELECT plex_token FROM settings WHERE id = 1")
                plex_token = cursor.fetchone()[0]
                conn.close()
            except Exception:
                pass
            error_settings = {
                "from_email": request.form.get("from_email", ""),
                "alias_email": request.form.get("alias_email", ""),
                "reply_to_email": request.form.get("reply_to_email", ""),
                "password": request.form.get("password", ""),
                "smtp_username": request.form.get("smtp_username", ""),
                "smtp_server": request.form.get("smtp_server", ""),
                "smtp_port": request.form.get("smtp_port", ""),
                "smtp_protocol": request.form.get("smtp_protocol", "SSL"),
                "server_name": request.form.get("server_name", ""),
                "plex_url": request.form.get("plex_url", ""),
                "plex_token": plex_token,
                "tautulli_url": request.form.get("tautulli_url", ""),
                "tautulli_api": request.form.get("tautulli_api", ""),
                "conjurr_url": request.form.get("conjurr_url", ""),
                "droppedneedle_url": request.form.get("droppedneedle_url", ""),
                "droppedneedle_api_key": request.form.get("droppedneedle_api_key", ""),
                "recipient_display_name": request.form.get("recipient_display_name", "email"),
                "logo_filename": request.form.get("logo_filename", ""),
                "logo_width": request.form.get("logo_width", ""),
                "email_theme": request.form.get("email_theme", "newsletterr_blue"),
                "primary_color": request.form.get("primary_color", "#8acbd4"),
                "secondary_color": request.form.get("secondary_color", "#222222"),
                "accent_color": request.form.get("accent_color", "#62a1a4"),
                "background_color": request.form.get("background_color", "#333333"),
                "text_color": request.form.get("text_color", "#62a1a4"),
                "from_name": request.form.get("from_name", ""),
                "custom_logo_filename": request.form.get("custom_logo_filename", ""),
                "login_toggle": request.form.get("login_toggle", "disabled"),
                "nl_username": request.form.get("nl_username", ""),
                "nl_password": request.form.get("nl_password", ""),
                "default_intro_text": request.form.get("default_intro_text", ""),
                "default_outro_text": request.form.get("default_outro_text", ""),
                "hsts_enabled": request.form.get("hsts_enabled", "disabled"),
                "scheduled_subject_prefix": request.form.get("scheduled_subject_prefix", "enabled"),
                "logo_position": request.form.get("logo_position", "center"),
                "hide_stat_play_counts": request.form.get("hide_stat_play_counts", "disabled"),
                "hide_graph_play_counts": request.form.get("hide_graph_play_counts", "disabled"),
                "stats_type": request.form.get("stats_type", "plays"),
                "recently_added_mode": request.form.get("recently_added_mode", "items"),
                "recently_added_sort": request.form.get("recently_added_sort", "date"),
                "ra_grid_columns": request.form.get("ra_grid_columns", "5"),
                "recs_grid_columns": request.form.get("recs_grid_columns", "5"),
                "stat_cover_art": request.form.get("stat_cover_art", "disabled"),
                "send_mode": request.form.get("send_mode", "bcc"),
                "poster_max_height": request.form.get("poster_max_height", ""),
            }
            if not session.get("csrf_token"):
                session["csrf_token"] = secrets.token_urlsafe(32)
            return render_template('settings.html', settings=error_settings, error=f"Error saving settings: {str(e)}", nonce=secrets.token_urlsafe(16), csrf_token=session["csrf_token"])

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
        droppedneedle_url = cursor.execute("SELECT droppedneedle_url FROM settings WHERE id = 1").fetchone()[0]
        droppedneedle_api_key = cursor.execute("SELECT droppedneedle_api_key FROM settings WHERE id = 1").fetchone()[0]
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
        default_intro_text = cursor.execute("SELECT default_intro_text FROM settings WHERE id = 1").fetchone()[0]
        default_outro_text = cursor.execute("SELECT default_outro_text FROM settings WHERE id = 1").fetchone()[0]
        hsts_enabled = cursor.execute("SELECT hsts_enabled FROM settings WHERE id = 1").fetchone()[0]
        scheduled_subject_prefix = cursor.execute("SELECT scheduled_subject_prefix FROM settings WHERE id = 1").fetchone()[0]
        logo_position = cursor.execute("SELECT logo_position FROM settings WHERE id = 1").fetchone()[0]
        hide_stat_play_counts = cursor.execute("SELECT hide_stat_play_counts FROM settings WHERE id = 1").fetchone()[0]
        hide_graph_play_counts = cursor.execute("SELECT hide_graph_play_counts FROM settings WHERE id = 1").fetchone()[0]
        stats_type = cursor.execute("SELECT stats_type FROM settings WHERE id = 1").fetchone()[0]
        recently_added_mode = cursor.execute("SELECT recently_added_mode FROM settings WHERE id = 1").fetchone()[0]
        recently_added_sort = cursor.execute("SELECT recently_added_sort FROM settings WHERE id = 1").fetchone()[0]
        ra_grid_columns = cursor.execute("SELECT ra_grid_columns FROM settings WHERE id = 1").fetchone()[0]
        recs_grid_columns = cursor.execute("SELECT recs_grid_columns FROM settings WHERE id = 1").fetchone()[0]
        stat_cover_art = cursor.execute("SELECT stat_cover_art FROM settings WHERE id = 1").fetchone()[0]
        send_mode = cursor.execute("SELECT send_mode FROM settings WHERE id = 1").fetchone()[0]
        poster_max_height = cursor.execute("SELECT poster_max_height FROM settings WHERE id = 1").fetchone()[0]
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
        droppedneedle_url = cursor.execute("SELECT droppedneedle_url FROM settings WHERE id = 1").fetchone()
        droppedneedle_api_key = cursor.execute("SELECT droppedneedle_api_key FROM settings WHERE id = 1").fetchone()
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
        default_intro_text = cursor.execute("SELECT default_intro_text FROM settings WHERE id = 1").fetchone()
        default_outro_text = cursor.execute("SELECT default_outro_text FROM settings WHERE id = 1").fetchone()
        hsts_enabled = cursor.execute("SELECT hsts_enabled FROM settings WHERE id = 1").fetchone()
        scheduled_subject_prefix = cursor.execute("SELECT scheduled_subject_prefix FROM settings WHERE id = 1").fetchone()
        logo_position = cursor.execute("SELECT logo_position FROM settings WHERE id = 1").fetchone()
        hide_stat_play_counts = cursor.execute("SELECT hide_stat_play_counts FROM settings WHERE id = 1").fetchone()
        hide_graph_play_counts = cursor.execute("SELECT hide_graph_play_counts FROM settings WHERE id = 1").fetchone()
        stats_type = cursor.execute("SELECT stats_type FROM settings WHERE id = 1").fetchone()
        recently_added_mode = cursor.execute("SELECT recently_added_mode FROM settings WHERE id = 1").fetchone()
        recently_added_sort = cursor.execute("SELECT recently_added_sort FROM settings WHERE id = 1").fetchone()
        ra_grid_columns = cursor.execute("SELECT ra_grid_columns FROM settings WHERE id = 1").fetchone()
        recs_grid_columns = cursor.execute("SELECT recs_grid_columns FROM settings WHERE id = 1").fetchone()
        stat_cover_art = cursor.execute("SELECT stat_cover_art FROM settings WHERE id = 1").fetchone()
        send_mode = cursor.execute("SELECT send_mode FROM settings WHERE id = 1").fetchone()
        poster_max_height = cursor.execute("SELECT poster_max_height FROM settings WHERE id = 1").fetchone()

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
        "droppedneedle_url": droppedneedle_url or "",
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
        "nl_username": nl_username or "",
        "default_intro_text": default_intro_text or "",
        "default_outro_text": default_outro_text or "",
        "hsts_enabled": hsts_enabled or "disabled",
        "scheduled_subject_prefix": scheduled_subject_prefix or "enabled",
        "logo_position": logo_position or "center",
        "hide_stat_play_counts": hide_stat_play_counts or "disabled",
        "hide_graph_play_counts": hide_graph_play_counts or "disabled",
        "stats_type": stats_type or "plays",
        "recently_added_mode": recently_added_mode or "items",
        "recently_added_sort": recently_added_sort or "date",
        "ra_grid_columns": ra_grid_columns or "5",
        "recs_grid_columns": recs_grid_columns or "5",
        "stat_cover_art": stat_cover_art or "disabled",
        "send_mode": send_mode or "bcc",
        "poster_max_height": poster_max_height or "",
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

        conn = sqlite3.connect(config.DB_PATH)
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
        conn = sqlite3.connect(config.DB_PATH)
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

@app.route('/upload/media', methods=['POST'])
@requires_auth
def upload_media():
    if request.content_type and request.content_type.startswith('multipart/form-data'):
        token = request.form.get('csrf_token')
        if not token or token != session.get('csrf_token'):
            abort(400)
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file uploaded"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400

        allowed_extensions = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in allowed_extensions:
            return jsonify({"status": "error", "message": "Invalid file type. PNG, JPG, JPEG, WebP and GIF only"}), 400

        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        if file_size > 10 * 1024 * 1024:
            return jsonify({"status": "error", "message": "File too large. Maximum size is 10MB"}), 400

        timestamp = int(time.time())
        new_filename = f"media_{timestamp}_{secrets.token_hex(4)}.{ext}"

        upload_dir = os.path.join(app.static_folder, 'uploads', 'media')
        os.makedirs(upload_dir, exist_ok=True)

        file.save(os.path.join(upload_dir, new_filename))

        return jsonify({
            "status": "success",
            "filename": new_filename,
            "url": f"/static/uploads/media/{new_filename}"
        })
    except Exception as e:
        print(f"Error uploading media: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/test/tautulli', methods=['POST'])
@requires_auth
def test_tautulli():
    data = request.get_json()
    url = (data.get('url') or '').rstrip('/')
    api_key = (data.get('api_key') or '').strip()
    if not url:
        return jsonify({'status': 'error', 'message': 'Tautulli URL is required'})
    if not api_key:
        return jsonify({'status': 'error', 'message': 'Tautulli API key is required'})
    try:
        r = requests.get(f"{url}/api/v2", params={'apikey': api_key, 'cmd': 'arnold'}, timeout=10)
        resp = r.json()
        if resp.get('response', {}).get('result') == 'success':
            return jsonify({'status': 'ok', 'message': 'Connected to Tautulli'})
        msg = resp.get('response', {}).get('message') or 'Unexpected response, check your API key'
        return jsonify({'status': 'error', 'message': msg})
    except requests.exceptions.ConnectionError:
        return jsonify({'status': 'error', 'message': 'Tautulli is unreachable at that URL'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/test/conjurr', methods=['POST'])
@requires_auth
def test_conjurr():
    data = request.get_json()
    url = (data.get('url') or '').rstrip('/')
    if not url:
        return jsonify({'status': 'error', 'message': 'Conjurr URL is required'})
    try:
        r = requests.get(f"{url}/", timeout=10, allow_redirects=True)
        if urlparse(r.url).path.rstrip('/') == '/settings':
            return jsonify({'status': 'warning', 'message': 'Conjurr is reachable but not configured, complete setup in Conjurr settings'})
        return jsonify({'status': 'ok', 'message': 'Connected to Conjurr'})
    except requests.exceptions.ConnectionError:
        return jsonify({'status': 'error', 'message': 'Conjurr is unreachable at that URL'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/test/droppedneedle', methods=['POST'])
@requires_auth
def test_droppedneedle():
    data = request.get_json()
    url = (data.get('url') or '').rstrip('/')
    api_key = data.get('api_key') or ''
    if not url:
        return jsonify({'status': 'error', 'message': 'DroppedNeedle URL is required'})
    if not api_key:
        return jsonify({'status': 'error', 'message': 'DroppedNeedle Wrapped API key is required'})
    try:
        r = safe_get(f"{url}/api/v1/wrapped/users", timeout=10, headers={'X-Wrapped-Api-Key': api_key})
        if r.status_code == 401:
            return jsonify({'status': 'error', 'message': 'DroppedNeedle rejected the API key'})
        r.raise_for_status()
        return jsonify({'status': 'ok', 'message': 'Connected to DroppedNeedle'})
    except requests.exceptions.ConnectionError:
        return jsonify({'status': 'error', 'message': 'DroppedNeedle is unreachable at that URL'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/api/gif/search', methods=['GET'])
@requires_auth
def gif_search():
    query = request.args.get('q', '').strip()
    page = max(1, int(request.args.get('page', 1)))
    per_page = min(max(8, int(request.args.get('per_page', 24))), 50)

    if not query:
        return jsonify({"results": []}), 200

    ak = gkak()
    if not ak:
        return jsonify({"error": "GIF search not configured"}), 503
    
    customer_id = get_plex_client_identifier()

    try:
        url = f"https://api.klipy.com/api/v1/{ak}/gifs/search"
        resp = safe_get(
            url,
            params={
                "q": query,
                "page": page,
                "per_page": per_page,
                "customer_id": customer_id,
                "content_filter": "off",
                "locale": "us",
                "format_filter": "gif,webp"
            },
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for item in data.get('data', {}).get('data', []):
            hd = item.get('file', {}).get('hd', {})
            gif = hd.get('gif', {})
            webp = hd.get('webp', {})
            results.append({
                'id': item.get('id'),
                'title': item.get('title', ''),
                'url': webp.get('url', '') or gif.get('url', ''),
                'width': webp.get('width', '') or gif.get('width', 0),
                'height': webp.get('height', '') or gif.get('height', 0),
            })

        return jsonify({
            "results": results,
            "page": page,
            "per_page": per_page
        })
    except Exception as e:
        print(f"GIF search error: {e}")
        return jsonify({"error": "GIF search failed"}), 500

@app.post('/api/plex/pin')
@requires_auth
def plex_create_pin():
    with PlexAPI() as plex_api:
        res = plex_api.plex.get_pin(request={
            "client_id": state.plex_headers["X-Plex-Client-Identifier"],
            "client_name": "newsletterr",
            "device_nickname": "newsletterr",
            "client_version": f"{app.jinja_env.globals['version']}",
            "platform": "Flask",
        })
    
    assert res.auth_pin_container is not None

    auth_url = (
        "https://plex.tv/link?"
        f"clientID={quote_plus(state.plex_headers['X-Plex-Client-Identifier'])}"
        f"&code={quote_plus(res.auth_pin_container.code)}"
    )
    return jsonify({"pin_id": res.auth_pin_container.id, "code": res.auth_pin_container.code, "auth_url": auth_url, "expires_in": res.auth_pin_container.expires_in})

@app.get('/api/plex/pin/<int:pin_id>')
@requires_auth
def plex_poll_pin(pin_id: int):
    with PlexAPI() as plex_api:
        res = plex_api.plex.get_token_by_pin_id(request={
            "pin_id": pin_id,
            "client_id": state.plex_headers["X-Plex-Client-Identifier"],
            "client_name": "newsletterr",
            "device_nickname": "newsletterr",
            "client_version": f"{app.jinja_env.globals['version']}",
            "platform": "Flask",
        })
    
    assert res.auth_pin_container is not None

    token = res.auth_pin_container.auth_token
    if token:
        conn = sqlite3.connect(config.DB_PATH)
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
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT plex_token FROM settings WHERE id = 1")
    row = cursor.fetchone()
    token = row[0]

    url = "https://plex.tv/api/v2/resources"
    headers = get_plex_headers({"X-Plex-Token": decrypt(token)})
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
        conn = sqlite3.connect(config.DB_PATH)
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
        conn = sqlite3.connect(config.DB_PATH)
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
        conn = sqlite3.connect(config.DB_PATH)
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
        
        templates_conn = sqlite3.connect(config.DB_PATH)
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
        conn = sqlite3.connect(config.DB_PATH)
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
            
            update_conn = sqlite3.connect(config.DB_PATH)
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
        conn = sqlite3.connect(config.DB_PATH)
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
        
        templates_conn = sqlite3.connect(config.DB_PATH)
        templates_cursor = templates_conn.cursor()
        templates_cursor.execute("SELECT name, subject, email_text, selected_items, expanded_collections, email_header_title, custom_html FROM email_templates WHERE id = ?", (template_id,))
        template_result = templates_cursor.fetchone()
        templates_conn.close()
        
        if not template_result:
            return jsonify({"status": "error", "message": "Template not found"}), 404
        
        template_name, subject, email_text, selected_items_json, expanded_collections_json, email_header_title, custom_html = template_result
        email_header_title = email_header_title or ''
        custom_html = custom_html or ''
        
        try:
            selected_items = json.loads(selected_items_json) if selected_items_json else []
        except:
            selected_items = []

        try:
            expanded_collections = json.loads(expanded_collections_json) if expanded_collections_json else []
        except:
            expanded_collections = {}

        email_lists_conn = sqlite3.connect(config.DB_PATH)
        email_lists_cursor = email_lists_conn.cursor()
        email_lists_cursor.execute("SELECT emails FROM email_lists WHERE id = ?", (email_list_id,))
        email_list_result = email_lists_cursor.fetchone()
        email_lists_conn.close()
        
        if not email_list_result:
            return jsonify({"status": "error", "message": "Email list not found"}), 404
        
        to_emails = email_list_result[0]
        to_emails_list = [email.strip() for email in to_emails.split(",")]
        
        settings_conn = sqlite3.connect(config.DB_PATH)
        settings_cursor = settings_conn.cursor()
        settings_cursor.execute("SELECT server_name, tautulli_url, tautulli_api, logo_filename, logo_width, custom_logo_filename, logo_position, default_intro_text, default_outro_text, hide_stat_play_counts, hide_graph_play_counts, stats_type, recently_added_mode, recently_added_sort, ra_grid_columns, recs_grid_columns, stat_cover_art, poster_max_height FROM settings WHERE id = 1")
        settings_row = settings_cursor.fetchone()
        settings_conn.close()

        if settings_row:
            settings = {
                "server_name": settings_row[0],
                "tautulli_url": settings_row[1],
                "tautulli_api": settings_row[2],
                "logo_filename": settings_row[3],
                "logo_width": settings_row[4],
                "custom_logo_filename": settings_row[5] or '',
                "logo_position": settings_row[6] or 'center',
                "default_intro_text": settings_row[7] or '',
                "default_outro_text": settings_row[8] or '',
                "hide_stat_play_counts": settings_row[9] or 'disabled',
                "hide_graph_play_counts": settings_row[10] or 'disabled',
                "stats_type": settings_row[11] or 'plays',
                "recently_added_mode": settings_row[12] or 'items',
                "recently_added_sort": settings_row[13] or 'date',
                "ra_grid_columns": settings_row[14] or '5',
                "recs_grid_columns": settings_row[15] or '5',
                "stat_cover_art": settings_row[16] or 'disabled',
                "poster_max_height": int(settings_row[17] or 0) if settings_row[17] else 0,
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
            items_count,
            stats_type=settings.get('stats_type', 'plays'),
            recently_added_mode=settings.get('recently_added_mode', 'items'),
            recently_added_sort=settings.get('recently_added_sort', 'date')
        ) if settings.get('tautulli_url') and settings.get('tautulli_api') else {
            'settings': settings,
            'stats': [],
            'graph_data': [],
            'recent_data': [],
            'graph_commands': []
        }
        tautulli_data["settings"]["logo_filename"] = settings["logo_filename"]
        tautulli_data["settings"]["logo_width"] = settings["logo_width"]
        tautulli_data["settings"]["logo_position"] = settings.get("logo_position", "center")
        tautulli_data["settings"]["default_intro_text"] = settings.get("default_intro_text", "")
        tautulli_data["settings"]["default_outro_text"] = settings.get("default_outro_text", "")
        tautulli_data["settings"]["hide_stat_play_counts"] = settings.get("hide_stat_play_counts", "disabled")
        tautulli_data["settings"]["hide_graph_play_counts"] = settings.get("hide_graph_play_counts", "disabled")
        tautulli_data["settings"]["stats_type"] = settings.get("stats_type", "plays")
        tautulli_data["settings"]["recently_added_mode"] = settings.get("recently_added_mode", "items")
        tautulli_data["settings"]["recently_added_sort"] = settings.get("recently_added_sort", "date")
        tautulli_data["settings"]["ra_grid_columns"] = int(settings.get("ra_grid_columns") or 5)
        tautulli_data["settings"]["recs_grid_columns"] = int(settings.get("recs_grid_columns") or 5)
        tautulli_data["settings"]["stat_cover_art"] = settings.get("stat_cover_art", "disabled")
        tautulli_data["settings"]["poster_max_height"] = settings.get("poster_max_height", 0)

        recommendations_data = None
        has_recs = any(item.get('type') == 'recs' for item in selected_items)
        
        if has_recs:
            try:
                conn = sqlite3.connect(config.DB_PATH)
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
            "expanded_collections": expanded_collections,
            "email_header_title": email_header_title,
            "custom_html": custom_html
        })
        
    except Exception as e:
        print(f"Error generating preview: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/scheduling/<int:schedule_id>/preview-page', methods=['GET'])
@requires_auth
def preview_schedule_page(schedule_id):
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT date_range FROM email_schedules WHERE id = ?", (schedule_id,))
        schedule_result = cursor.fetchone()
        
        date_range = schedule_result[0] if schedule_result else 7
    except:
        date_range = 7

    cursor.execute("SELECT logo_filename, logo_width, tautulli_url, tautulli_api, custom_logo_filename, recipient_display_name, hide_graph_play_counts, stats_type, recently_added_mode, recently_added_sort, ra_grid_columns, recs_grid_columns, stat_cover_art, poster_max_height, logo_position FROM settings WHERE id = 1")
    settings_row = cursor.fetchone()
    logo_filename = settings_row[0] if settings_row else 'Asset_94x.png'
    logo_width = settings_row[1] if settings_row else 80
    tautulli_url = settings_row[2] if settings_row else ''
    tautulli_api = settings_row[3] if settings_row else ''
    custom_logo_filename = settings_row[4] if settings_row else ''
    recipient_display_name = settings_row[5] if settings_row else 'email'
    hide_graph_play_counts = settings_row[6] if settings_row else 'disabled'
    stats_type = settings_row[7] if settings_row else 'plays'
    recently_added_mode = settings_row[8] if settings_row else 'items'
    recently_added_sort = settings_row[9] if settings_row else 'date'
    ra_grid_columns = settings_row[10] if settings_row else '5'
    recs_grid_columns = settings_row[11] if settings_row else '5'
    stat_cover_art = settings_row[12] if settings_row else 'disabled'
    poster_max_height = int(settings_row[13] or 0) if settings_row and settings_row[13] else 0
    logo_position = settings_row[14] if settings_row else 'center'

    settings = {
        "logo_filename": logo_filename,
        "logo_width": logo_width,
        "custom_logo_filename": custom_logo_filename,
        "recipient_display_name": recipient_display_name,
        "hide_graph_play_counts": hide_graph_play_counts or 'disabled',
        "stats_type": stats_type or 'plays',
        "recently_added_mode": recently_added_mode or 'items',
        "recently_added_sort": recently_added_sort or 'date',
        "ra_grid_columns": ra_grid_columns or '5',
        "recs_grid_columns": recs_grid_columns or '5',
        "stat_cover_art": stat_cover_art or 'disabled',
        "poster_max_height": poster_max_height,
        "logo_position": logo_position or 'center',
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
        
        conn = sqlite3.connect(config.DB_PATH)
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
    for key in state.cache_storage:
        status[key] = {
            'has_data': state.cache_storage[key]['data'] is not None,
            'is_valid': is_cache_valid(key),
            'age_seconds': int(time.time() - state.cache_storage[key]['timestamp']) if state.cache_storage[key]['timestamp'] > 0 else 0
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
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, selected_items, email_text, subject, expanded_collections, email_header_title, custom_html FROM email_templates ORDER BY name")
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
                'expanded_collections': template[5] or '{}',
                'email_header_title': template[6] or '',
                'custom_html': template[7] or ''
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
        email_header_title = data.get('email_header_title', '')
        custom_html = data.get('custom_html', '')
        
        if not name:
            return jsonify({"status": "error", "message": "Template name is required"}), 400
        
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM email_templates WHERE name = ?", (name,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("""
                UPDATE email_templates 
                SET selected_items = ?, email_text = ?, subject = ?, expanded_collections = ?, email_header_title = ?, custom_html = ?, updated_at = CURRENT_TIMESTAMP
                WHERE name = ?
            """, (selected_items, email_text, subject, expanded_collections, email_header_title, custom_html, name))
            message = "Template updated successfully"
        else:
            cursor.execute("""
                INSERT INTO email_templates (name, selected_items, email_text, subject, expanded_collections, email_header_title, custom_html)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, selected_items, email_text, subject, expanded_collections, email_header_title, custom_html))
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
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM email_templates WHERE id = ?", (template_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "message": "Template deleted successfully"})
    except Exception as e:
        print(f"Error deleting template: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

