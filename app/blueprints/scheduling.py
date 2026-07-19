import secrets
import calendar, json

from datetime import datetime, timedelta
from flask import Blueprint, jsonify, render_template, request, session

from app.db import db_connect
from app.settings_store import get_settings
from app.cache import can_use_cached_data_for_preview, get_cached_data
from app.security import require_csrf_for_json, requires_auth, json_body
from app.store import get_saved_email_lists, get_email_schedules, create_email_schedule, update_email_schedule, delete_email_schedule, toggle_schedule_status
from app.theme import get_theme_settings
from app.clients.tautulli import run_tautulli_command
from app.clients.conjurr import run_conjurr_command
from app.emails.fetchers import fetch_tautulli_data_for_email
from app.emails.scheduled import send_scheduled_email

import logging

logger = logging.getLogger(__name__)

bp = Blueprint('scheduling', __name__)

@bp.route('/scheduling', methods=['GET'])
@requires_auth
def scheduling():
    try:
        schedules = get_email_schedules()
        email_lists = get_saved_email_lists()
        
        templates_conn = db_connect()
        templates_cursor = templates_conn.cursor()
        templates_cursor.execute("SELECT id, name FROM email_templates ORDER BY name")
        templates = [{'id': row[0], 'name': row[1]} for row in templates_cursor.fetchall()]
        templates_conn.close()

        if not session.get("csrf_token"):
            session["csrf_token"] = secrets.token_urlsafe(32)

        _s = get_settings(decrypt_secrets=False)
        recently_added_mode = (_s.get("recently_added_mode") or "items") if "id" in _s else "items"

        return render_template('scheduling.html', schedules=schedules, email_lists=email_lists, templates=templates, csrf_token=session["csrf_token"], recently_added_mode=recently_added_mode)
    except Exception as e:
        logger.error(f"Error loading scheduling page: {e}")
        return render_template('scheduling.html', schedules=[], email_lists=[], templates=[])

@bp.route('/scheduling/create', methods=['POST'])
@requires_auth
def create_schedule():
    require_csrf_for_json()
    data, err = json_body(["name", "email_list_id", "template_id", "frequency", "start_date"])
    if err:
        return err
    try:
        name = data.get('name', '').strip()
        email_list_id = data.get('email_list_id')
        template_id = int(data.get('template_id'))
        frequency = data.get('frequency')
        start_date = data.get('start_date')
        send_time = data.get('send_time', '09:00')
        date_range = int(data.get('date_range', 7))
        items_count = int(data.get('items_count', 10))

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
        logger.error(f"Error creating schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/scheduling/<int:schedule_id>', methods=['PUT'])
@requires_auth
def update_schedule(schedule_id):
    data, err = json_body(["name", "email_list_id", "template_id", "frequency", "start_date"])
    if err:
        return err
    try:
        name = data.get('name', '').strip()
        email_list_id = data.get('email_list_id')
        template_id = int(data.get('template_id'))
        frequency = data.get('frequency')
        start_date = data.get('start_date')
        send_time = data.get('send_time', '09:00')
        date_range = int(data.get('date_range', 7))
        items_count = int(data.get('items_count', 10))

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
        logger.error(f"Error updating schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/scheduling/<int:schedule_id>', methods=['DELETE'])
@requires_auth
def delete_schedule(schedule_id):
    require_csrf_for_json()
    try:
        delete_email_schedule(schedule_id)
        return jsonify({"status": "success", "message": "Schedule deleted successfully"})
    except Exception as e:
        logger.error(f"Error deleting schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/scheduling/<int:schedule_id>/send-now', methods=['POST'])
@requires_auth
def send_schedule_now(schedule_id):
    require_csrf_for_json()
    try:
        conn = db_connect()
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
        
        logger.info(f"Manual send triggered for schedule: {name}")
        success = send_scheduled_email(schedule_id, email_list_id, template_id)
        
        if success:
            current_time = datetime.now().isoformat()
            
            update_conn = db_connect()
            update_cursor = update_conn.cursor()
            update_cursor.execute("""
                UPDATE email_schedules 
                SET last_sent = ? 
                WHERE id = ?
            """, (current_time, schedule_id))
            update_conn.commit()
            update_conn.close()
            
            logger.info(f"Updated last_sent timestamp for schedule {name}")
            return jsonify({"status": "success", "message": f"Email '{name}' sent successfully"})
        else:
            return jsonify({"status": "error", "message": f"Failed to send email '{name}'. Check Email History for the reason."})
            
    except Exception as e:
        logger.error(f"Error in manual send: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/scheduling/<int:schedule_id>/toggle', methods=['POST'])
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
        logger.error(f"Error toggling schedule: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/scheduling/<int:schedule_id>/preview', methods=['GET'])
@requires_auth
def preview_schedule(schedule_id):
    try:
        conn = db_connect()
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
        
        templates_conn = db_connect()
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
            logger.debug("suppressed exception; using fallback", exc_info=True)
            selected_items = []

        try:
            expanded_collections = json.loads(expanded_collections_json) if expanded_collections_json else []
        except:
            logger.debug("suppressed exception; using fallback", exc_info=True)
            expanded_collections = {}

        email_lists_conn = db_connect()
        email_lists_cursor = email_lists_conn.cursor()
        email_lists_cursor.execute("SELECT emails FROM email_lists WHERE id = ?", (email_list_id,))
        email_list_result = email_lists_cursor.fetchone()
        email_lists_conn.close()
        
        if not email_list_result:
            return jsonify({"status": "error", "message": "Email list not found"}), 404
        
        to_emails = email_list_result[0]
        to_emails_list = [email.strip() for email in to_emails.split(",")]
        
        _s = get_settings(decrypt_secrets=False)
        settings_row = (_s.get("server_name"), _s.get("tautulli_url"), _s.get("tautulli_api"), _s.get("logo_filename"), _s.get("logo_width"), _s.get("custom_logo_filename"), _s.get("logo_position"), _s.get("default_intro_text"), _s.get("default_outro_text"), _s.get("hide_stat_play_counts"), _s.get("hide_graph_play_counts"), _s.get("stats_type"), _s.get("recently_added_mode"), _s.get("recently_added_sort"), _s.get("ra_grid_columns"), _s.get("recs_grid_columns"), _s.get("stat_cover_art"), _s.get("poster_max_height"), _s.get("collections_grid_columns"), _s.get("ra_show_description"), _s.get("include_user_info")) if "id" in _s else None

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
                "collections_grid_columns": settings_row[18] or '5',
                "ra_show_description": settings_row[19] or 'enabled',
                "include_user_info": settings_row[20] or 'enabled',
                "email_layout": _s.get("email_layout") or 'classic',
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
                logger.error(f"Error fetching user_dict for preview API: {e}")
        
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
        tautulli_data["settings"]["collections_grid_columns"] = int(settings.get("collections_grid_columns") or 5)
        tautulli_data["settings"]["ra_show_description"] = settings.get("ra_show_description", "enabled")
        tautulli_data["settings"]["include_user_info"] = settings.get("include_user_info", "enabled")
        tautulli_data["settings"]["email_layout"] = settings.get("email_layout", "classic")

        recommendations_data = None
        has_recs = any(item.get('type') == 'recommendations' for item in selected_items)
        
        if has_recs:
            try:
                _s = get_settings(decrypt_secrets=False)
                row = (_s.get("conjurr_url"),) if "id" in _s else None
                conjurr_url = (row[0] or "").strip() if row else ""

                if conjurr_url and user_dict:
                    filtered_users = {k: v for k, v in user_dict.items() if v in to_emails_list}
                    recommendations_data, _ = run_conjurr_command(conjurr_url, filtered_users, error=None)

            except Exception as e:
                logger.warning(f"preview_schedule: recommendations unavailable: {e}")
                recommendations_data = {}

        # Cache-only reads (no live fetch in the preview) for the remaining
        # block types, mirroring how stats/recommendations are sourced above.
        yearly_wrapped_data = get_cached_data('yearly_wrapped_json', strict=False) or []
        droppedneedle_wrapped_data = get_cached_data('droppedneedle_wrapped_json', strict=False) or {}
        droppedneedle_server_data = get_cached_data('droppedneedle_server_json', strict=False) or None
        sonarr_coming_soon_data = get_cached_data('sonarr_coming_soon_json', strict=False) or []
        radarr_coming_soon_data = get_cached_data('radarr_coming_soon_json', strict=False) or []
        ombi_requests_data = get_cached_data('ombi_requests_json', strict=False) or {}
        seerr_requests_data = get_cached_data('seerr_requests_json', strict=False) or {}

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
            "recommendations": recommendations_data or {},
            "yearly_wrapped": yearly_wrapped_data,
            "droppedneedle_wrapped": droppedneedle_wrapped_data,
            "droppedneedle_server": droppedneedle_server_data,
            "sonarr_coming_soon": sonarr_coming_soon_data,
            "radarr_coming_soon": radarr_coming_soon_data,
            "ombi_requests": ombi_requests_data,
            "seerr_requests": seerr_requests_data,
            "user_dict": user_dict,
            "users_full_data": users_full_data,
            "expanded_collections": expanded_collections,
            "email_header_title": email_header_title,
            "custom_html": custom_html
        })
        
    except Exception as e:
        logger.exception(f"Error generating preview: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/scheduling/<int:schedule_id>/preview-page', methods=['GET'])
@requires_auth
def preview_schedule_page(schedule_id):
    conn = db_connect()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT date_range FROM email_schedules WHERE id = ?", (schedule_id,))
        schedule_result = cursor.fetchone()
        
        date_range = schedule_result[0] if schedule_result else 7
    except:
        logger.debug("suppressed exception; using fallback", exc_info=True)
        date_range = 7

    _s = get_settings(decrypt_secrets=False)
    settings_row = (_s.get("logo_filename"), _s.get("logo_width"), _s.get("tautulli_url"), _s.get("tautulli_api"), _s.get("custom_logo_filename"), _s.get("recipient_display_name"), _s.get("hide_graph_play_counts"), _s.get("stats_type"), _s.get("recently_added_mode"), _s.get("recently_added_sort"), _s.get("ra_grid_columns"), _s.get("recs_grid_columns"), _s.get("stat_cover_art"), _s.get("poster_max_height"), _s.get("logo_position"), _s.get("collections_grid_columns"), _s.get("ra_show_description"), _s.get("include_user_info"), _s.get("hosted_enabled"), _s.get("hosted_base_url"), _s.get("hosted_links_enabled"), _s.get("hosted_links_base_url")) if "id" in _s else None
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
    collections_grid_columns = settings_row[15] if settings_row else '5'
    ra_show_description = settings_row[16] if settings_row else 'enabled'
    include_user_info = settings_row[17] if settings_row else 'enabled'
    hosted_enabled = settings_row[18] if settings_row else 'disabled'
    hosted_base_url = settings_row[19] if settings_row else ''
    hosted_links_enabled = settings_row[20] if settings_row else 'disabled'
    hosted_links_base_url = settings_row[21] if settings_row else ''

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
        "collections_grid_columns": collections_grid_columns or '5',
        "ra_show_description": ra_show_description or 'enabled',
        "include_user_info": include_user_info or 'enabled',
        "email_layout": _s.get("email_layout") or 'classic',
        "hosted_enabled": hosted_enabled or 'disabled',
        "hosted_base_url": hosted_base_url or '',
        "hosted_links_enabled": hosted_links_enabled or 'disabled',
        "hosted_links_base_url": hosted_links_base_url or '',
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
            logger.error(f"Error fetching user_dict for preview: {e}")
    
    can_use_cache, cache_reason = can_use_cached_data_for_preview(date_range)
    
    if can_use_cache:
        logger.info(f"Preview page using cached data: {cache_reason}")
        stats = get_cached_data('stats', strict=True) or get_cached_data('stats', strict=False) or []
        graph_data = get_cached_data('graph_data', strict=True) or get_cached_data('graph_data', strict=False) or []
        recent_data = get_cached_data('recent_data', strict=True) or get_cached_data('recent_data', strict=False) or []
        recommendations = (get_cached_data('recommendations', strict=True) or get_cached_data('recommendations', strict=False) or {})
    else:
        logger.info(f"Preview page using cached data (fallback): {cache_reason}")
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

@bp.route('/scheduling/calendar-data', methods=['GET'])
@requires_auth
def get_calendar_data():
    try:
        month = int(request.args.get('month', datetime.now().month))
        year = int(request.args.get('year', datetime.now().year))
    except (TypeError, ValueError):
        return jsonify({"error": "month and year must be integers"}), 400
    try:
        
        conn = db_connect()
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
                logger.debug("suppressed exception; using fallback", exc_info=True)
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
        logger.error(f"Error getting calendar data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
