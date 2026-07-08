import secrets
import os, time

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, session, url_for
from PIL import Image

from app.db import db_connect
from app.settings_store import get_settings
from app.crypto import encrypt, decrypt
from app.hooks import refresh_hsts_setting
from app.security import require_csrf_for_json, requires_auth

import logging

logger = logging.getLogger(__name__)

bp = Blueprint('settings', __name__)

@bp.route('/settings', methods=['GET', 'POST'])
@requires_auth
def settings():
    conn = db_connect()
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
        token = request.form.get("csrf_token", "").strip()
        if not token or token != session.get("csrf_token"):
            abort(400)

        try:
            cursor.execute("SELECT custom_logo_filename FROM settings WHERE id = 1")
            db_custom_logo = cursor.fetchone()
            existing_custom_logo = db_custom_logo[0] if db_custom_logo and db_custom_logo[0] else ""

            cursor.execute("SELECT login_toggle, nl_username, nl_password, password, tautulli_api, droppedneedle_api_key FROM settings WHERE id = 1")
            db_login_info = cursor.fetchone()
            existing_login_toggle = db_login_info[0] if db_login_info and db_login_info[0] else ""
            existing_nl_username = db_login_info[1] if db_login_info and db_login_info[1] else ""
            existing_nl_password = db_login_info[2] if db_login_info and db_login_info[2] else ""
            existing_password = db_login_info[3] if db_login_info and db_login_info[3] else ""
            existing_tautulli_api = db_login_info[4] if db_login_info and db_login_info[4] else ""
            existing_droppedneedle_api_key = db_login_info[5] if db_login_info and db_login_info[5] else ""

            # secret fields are write-only: a blank submission keeps the stored
            # value rather than overwriting it with an empty string
            def _secret(form_name, existing):
                submitted = (request.form.get(form_name) or "").strip()
                return encrypt(submitted) if submitted else existing

            from_email = request.form.get("from_email")
            alias_email = request.form.get("alias_email")
            reply_to_email = request.form.get("reply_to_email")
            password = _secret("password", existing_password)
            smtp_username = request.form.get("smtp_username")
            smtp_server = request.form.get("smtp_server")
            smtp_port = int(request.form.get("smtp_port"))
            smtp_protocol = request.form.get("smtp_protocol")
            server_name = request.form.get("server_name")
            plex_url = request.form.get("plex_url")
            tautulli_url = request.form.get("tautulli_url")
            tautulli_api = _secret("tautulli_api", existing_tautulli_api)
            conjurr_url = request.form.get("conjurr_url")
            droppedneedle_url = request.form.get("droppedneedle_url")
            droppedneedle_api_key = _secret("droppedneedle_api_key", existing_droppedneedle_api_key)
            recipient_display_name = request.form.get("recipient_display_name", "email")
            logo_filename = request.form.get("logo_filename")
            logo_width = request.form.get("logo_width")
            email_theme = request.form.get("email_theme", "newsletterr_blue")
            from_name = request.form.get("from_name")
            custom_logo_filename = request.form.get("custom_logo_filename", "")
            login_toggle = request.form.get("login_toggle")
            nl_username = request.form.get("nl_username")
            nl_password = _secret("nl_password", existing_nl_password)
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
                return redirect(url_for('auth.login', alert="Settings saved successfully!"))

            if decrypt(existing_nl_password) != decrypt(nl_password):
                session.pop('username', None)
                session.pop('authenticated', None)
                return redirect(url_for('auth.login', alert="Settings saved successfully!"))

            if existing_login_toggle != login_toggle:
                session.pop('username', None)
                session.pop('authenticated', None)
                return redirect(url_for('auth.login', alert="Settings saved successfully!"))

            return redirect(url_for('settings.settings', alert="Settings saved successfully!", settings=settings))

        except Exception as e:
            try:
                cursor.execute("SELECT plex_token FROM settings WHERE id = 1")
                plex_token = cursor.fetchone()[0]
                conn.close()
            except Exception:
                logger.debug("suppressed exception; using fallback", exc_info=True)
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
            return render_template('settings.html', settings=error_settings, error=f"Error saving settings: {str(e)}", csrf_token=session["csrf_token"])

    s = get_settings(decrypt_secrets=False)
    from_email = s.get("from_email")
    alias_email = s.get("alias_email")
    reply_to_email = s.get("reply_to_email")
    password = s.get("password")
    smtp_username = s.get("smtp_username")
    smtp_server = s.get("smtp_server")
    smtp_port = s.get("smtp_port")
    smtp_protocol = s.get("smtp_protocol")
    server_name = s.get("server_name")
    plex_url = s.get("plex_url")
    plex_token = s.get("plex_token")
    tautulli_url = s.get("tautulli_url")
    tautulli_api = s.get("tautulli_api")
    conjurr_url = s.get("conjurr_url")
    droppedneedle_url = s.get("droppedneedle_url")
    droppedneedle_api_key = s.get("droppedneedle_api_key")
    recipient_display_name = s.get("recipient_display_name")
    logo_filename = s.get("logo_filename")
    logo_width = s.get("logo_width")
    email_theme = s.get("email_theme")
    primary_color = s.get("primary_color")
    secondary_color = s.get("secondary_color")
    accent_color = s.get("accent_color")
    background_color = s.get("background_color")
    text_color = s.get("text_color")
    from_name = s.get("from_name")
    custom_logo_filename = s.get("custom_logo_filename")
    login_toggle = s.get("login_toggle")
    nl_username = s.get("nl_username")
    nl_password = s.get("nl_password")
    default_intro_text = s.get("default_intro_text")
    default_outro_text = s.get("default_outro_text")
    hsts_enabled = s.get("hsts_enabled")
    scheduled_subject_prefix = s.get("scheduled_subject_prefix")
    logo_position = s.get("logo_position")
    hide_stat_play_counts = s.get("hide_stat_play_counts")
    hide_graph_play_counts = s.get("hide_graph_play_counts")
    stats_type = s.get("stats_type")
    recently_added_mode = s.get("recently_added_mode")
    recently_added_sort = s.get("recently_added_sort")
    ra_grid_columns = s.get("ra_grid_columns")
    recs_grid_columns = s.get("recs_grid_columns")
    stat_cover_art = s.get("stat_cover_art")
    send_mode = s.get("send_mode")
    poster_max_height = s.get("poster_max_height")

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
    # secrets are never sent to the browser; the form shows a placeholder and
    # a blank submission keeps the stored value (write-only fields)
    settings["password"] = ""
    settings["has_password"] = bool(password)
    settings["tautulli_api"] = ""
    settings["has_tautulli_api"] = bool(tautulli_api)
    settings["droppedneedle_api_key"] = ""
    settings["has_droppedneedle_api_key"] = bool(droppedneedle_api_key)
    settings["nl_password"] = ""
    settings["has_nl_password"] = bool(nl_password)
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

    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    return render_template('settings.html', settings=settings, alert=alert, csrf_token=session["csrf_token"])

@bp.route('/upload-logo', methods=['POST'])
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

        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'logos')
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, new_filename)
        file.save(file_path)

        with Image.open(file_path) as img:
            width, height = img.size

        conn = db_connect()
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
        logger.error(f"Error uploading logo: {e}")
        return jsonify({"status": "error", "message": f"Upload failed: {str(e)}"}), 500

@bp.route('/delete-logo', methods=['POST'])
@requires_auth
def delete_logo():
    require_csrf_for_json()
    try:
        conn = db_connect()
        cursor = conn.cursor()

        cursor.execute("SELECT custom_logo_filename FROM settings WHERE id = 1")
        result = cursor.fetchone()
        current_logo = result[0] if result else None

        if current_logo:
            logo_path = os.path.join(current_app.static_folder, 'uploads', 'logos', current_logo)
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
        logger.error(f"Error deleting logo: {e}")
        return jsonify({"status": "error", "message": f"Delete failed: {str(e)}"}), 500

@bp.route('/upload/media', methods=['POST'])
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

        upload_dir = os.path.join(current_app.static_folder, 'uploads', 'media')
        os.makedirs(upload_dir, exist_ok=True)

        file.save(os.path.join(upload_dir, new_filename))

        return jsonify({
            "status": "success",
            "filename": new_filename,
            "url": f"/static/uploads/media/{new_filename}"
        })
    except Exception as e:
        logger.error(f"Error uploading media: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
