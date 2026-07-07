import secrets
import sqlite3

from datetime import datetime, timezone
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app import config
from app.settings_store import get_settings
from app.security import require_csrf_for_json, requires_auth
from app.store import get_saved_email_lists, save_email_list, delete_email_list
from app.emails.send import send_standard_email_with_cids, send_recommendations_email_with_cids

bp = Blueprint('emails', __name__)

@bp.route('/send_email', methods=['POST'])
@requires_auth
def send_email():
    require_csrf_for_json()
    _s = get_settings(decrypt_secrets=False)
    row = (_s.get("from_email"), _s.get("alias_email"), _s.get("reply_to_email"), _s.get("password"), _s.get("smtp_username"), _s.get("smtp_server"), _s.get("smtp_port"), _s.get("smtp_protocol"), _s.get("server_name"), _s.get("logo_filename"), _s.get("logo_width"), _s.get("from_name"), _s.get("custom_logo_filename"), _s.get("send_mode"), _s.get("poster_max_height")) if "id" in _s else None

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

@bp.route('/email_history', methods=['GET'])
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

@bp.route('/email_history/clear', methods=['POST'])
@requires_auth
def clear_email_history():
    require_csrf_for_json()
    try:
        conn = sqlite3.connect(config.DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM email_history")
        conn.commit()
        conn.close()
        return redirect(url_for('emails.email_history'))
    except Exception as e:
        print(f"Error clearing email history: {e}")
        return redirect(url_for('emails.email_history'))

@bp.route('/email_history/recipients/<int:email_id>', methods=['GET'])
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

@bp.route('/email_lists', methods=['GET'])
@requires_auth
def get_email_lists():
    try:
        lists = get_saved_email_lists()
        return jsonify({"status": "success", "lists": lists})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/email_lists', methods=['POST'])
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

@bp.route('/email_lists/<int:list_id>', methods=['DELETE'])
@requires_auth
def delete_email_list_route(list_id):
    try:
        delete_email_list(list_id)
        return jsonify({"status": "success", "message": "List deleted successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/email_templates', methods=['GET'])
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

@bp.route('/email_templates', methods=['POST'])
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

@bp.route('/email_templates/<int:template_id>', methods=['DELETE'])
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
