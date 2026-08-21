import re
import secrets

from datetime import datetime, timezone
from flask import Blueprint, Response, jsonify, redirect, render_template, request, session, url_for

from app import dates
from app.db import db_connect
from app.settings_store import get_settings
from app.security import require_csrf_for_json, requires_auth, json_body
from app.store import get_saved_email_lists, save_email_list, delete_email_list, get_suppressed_emails, remove_suppressed, get_contacts, add_contacts, delete_contact, get_media_user_emails, set_media_user_emails, get_email_history_page
from app.contacts_import import contacts_to_csv, is_email, match_contacts_to_users, normalize_email, parse_contacts
from app.clients.jellyfin import fetch_jellyfin_users
from app.clients.mediaserver import get_media_server_type, is_jellyfin_like, media_user_scope
from app.emails.send import SendRequest, send_standard_email_with_cids, send_recommendations_email_with_cids, resend_email_from_history
from app.emails.preview import render_preview_email
from app.emails.pdf import render_html_to_pdf, render_history_email_to_pdf, pdf_filename

import logging

logger = logging.getLogger(__name__)

bp = Blueprint('emails', __name__)

@bp.route('/preview_email', methods=['POST'])
@requires_auth
def preview_email():
    require_csrf_for_json()
    data, err = json_body()
    if err:
        return err
    try:
        return jsonify({"html": render_preview_email(data)})
    except Exception as e:
        logger.exception("preview render failed")
        return jsonify({"error": f"Preview render failed: {e}"}), 500

@bp.route('/export_pdf', methods=['POST'])
@requires_auth
def export_pdf():
    # NEWS-9: same payload as /preview_email; the preview pipeline renders
    # (browser URLs) and weasyprint converts. Request-scoped, gthread-safe.
    require_csrf_for_json()
    data, err = json_body()
    if err:
        return err
    try:
        html = render_preview_email(data)
        pdf_bytes = render_html_to_pdf(html)
        filename = pdf_filename(data.get('subject'))
        return Response(pdf_bytes, mimetype='application/pdf',
                        headers={'Content-Disposition': f'attachment; filename="{filename}"'})
    except Exception as e:
        logger.exception("pdf export failed")
        return jsonify({"error": f"PDF export failed: {e}"}), 500

@bp.route('/email_history/<int:email_id>/pdf', methods=['GET'])
@requires_auth
def email_history_pdf(email_id):
    try:
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute("SELECT subject, email_content FROM email_history WHERE id = ?", (email_id,))
        row = cursor.fetchone()
        conn.close()
        if not row or not row[1]:
            return jsonify({"error": "No stored content for this email"}), 404
        subject, email_content = row
        pdf_bytes = render_history_email_to_pdf(email_content)
        return Response(pdf_bytes, mimetype='application/pdf',
                        headers={'Content-Disposition': f'attachment; filename="{pdf_filename(subject)}"'})
    except Exception as e:
        logger.exception("history pdf export failed")
        return jsonify({"error": f"PDF export failed: {e}"}), 500

@bp.route('/send_email', methods=['POST'])
@requires_auth
def send_email():
    require_csrf_for_json()
    settings = get_settings()
    if "id" not in settings:
        return jsonify({"error": "Please enter email info on settings page"}), 500

    data, err = json_body(["to_emails", "subject"])
    if err:
        return err
    to_emails = [e.strip() for e in str(data['to_emails']).split(",") if e.strip()]
    if not to_emails:
        return jsonify({"error": "At least one recipient is required"}), 400
    req = SendRequest(
        subject=data['subject'],
        email_header_title=data.get('email_header_title'),
        selected_items=data.get('selected_items', []),
        custom_html=data.get('custom_html', ''),
        expanded_collections=data.get('expanded_collections', {}),
        user_dict=data.get('user_dict', {}),
    )

    has_recommendations = any(item.get('type') == 'recommendations' for item in req.selected_items)
    has_droppedneedle_wrapped = any(item.get('type') == 'droppedneedle_wrapped' for item in req.selected_items)

    if (has_recommendations or has_droppedneedle_wrapped) and req.user_dict:
        payload, status = send_recommendations_email_with_cids(req, settings, to_emails)
    else:
        payload, status = send_standard_email_with_cids(req, settings, to_emails)
    return jsonify(payload), status

@bp.route('/send_test_email', methods=['POST'])
@requires_auth
def send_test_email():
    require_csrf_for_json()
    settings = get_settings()
    if "id" not in settings:
        return jsonify({"error": "Please enter email info on settings page"}), 500
    test_recipient = settings.get("from_email")
    if not test_recipient:
        return jsonify({"error": "Set a From address on the settings page first"}), 400

    data, err = json_body(["subject"])
    if err:
        return err
    req = SendRequest(
        subject=f"[TEST] {data['subject']}",
        email_header_title=data.get('email_header_title'),
        selected_items=data.get('selected_items', []),
        custom_html=data.get('custom_html', ''),
        expanded_collections=data.get('expanded_collections', {}),
        user_dict=data.get('user_dict', {}),
        is_test=True,
    )
    payload, status = send_standard_email_with_cids(req, settings, [test_recipient])
    if status == 200:
        payload["message"] = f"Test email sent to {test_recipient}"
    return jsonify(payload), status

@bp.route('/email_history', methods=['GET'])
@requires_auth
def email_history():
    try:
        try:
            page = max(1, int(request.args.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
        per_page = 50
        offset = (page - 1) * per_page

        emails, total = get_email_history_page(per_page, offset)

        _time_format = dates.resolve_time_format(get_settings(decrypt_secrets=False).get('time_format'))

        email_list = []
        for email in emails:
            try:
                utc_dt = datetime.fromisoformat(email[5].replace('Z', '+00:00'))
                local_dt = utc_dt.replace(tzinfo=timezone.utc).astimezone()
                # The date half stays ISO on purpose: this is a sortable log
                # column, so it follows the clock setting but not the date-order
                # one, the same way filenames and API parameters do.
                formatted_time = f"{dates.fmt_iso_date(local_dt)} {dates.fmt_time(local_dt, _time_format, seconds=True)}"
            except:
                logger.debug("suppressed exception; using fallback", exc_info=True)
                formatted_time = email[5]

            email_list.append({
                'id': email[0],
                'subject': email[1],
                'recipients': email[2],
                'content_size_kb': email[3],
                'recipient_count': email[4],
                'sent_at': formatted_time,
                'template_name': email[6] if email[6] else 'Manual',
                'status': email[7] or 'sent',
                'error': email[8],
            })

        if not session.get("csrf_token"):
            session["csrf_token"] = secrets.token_urlsafe(32)

        total_pages = max(1, (total + per_page - 1) // per_page)
        return render_template('email_history.html', emails=email_list,
                               page=page, total_pages=total_pages, total=total,
                               csrf_token=session["csrf_token"])
    except Exception as e:
        logger.error(f"Error loading email history: {e}")
        return render_template('email_history.html', emails=[], page=1, total_pages=1, total=0)

@bp.route('/email_history/clear', methods=['POST'])
@requires_auth
def clear_email_history():
    require_csrf_for_json()
    try:
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM email_history")
        conn.commit()
        conn.close()
        return redirect(url_for('emails.email_history'))
    except Exception as e:
        logger.error(f"Error clearing email history: {e}")
        return redirect(url_for('emails.email_history'))

@bp.route('/email_history/<int:email_id>/resend', methods=['POST'])
@requires_auth
def resend_email(email_id):
    require_csrf_for_json()
    settings = get_settings()
    if "id" not in settings:
        return jsonify({"status": "error", "message": "Please enter email info on settings page"}), 500

    success, message = resend_email_from_history(email_id, settings)
    return jsonify({"status": "ok" if success else "error", "message": message}), (200 if success else 500)

@bp.route('/email_history/recipients/<int:email_id>', methods=['GET'])
@requires_auth
def get_email_recipients(email_id):
    try:
        conn = db_connect()
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
        logger.error(f"Error getting recipients: {e}")
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
    require_csrf_for_json()
    try:
        delete_email_list(list_id)
        return jsonify({"status": "success", "message": "List deleted successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

MAX_IMPORT_BYTES = 2 * 1024 * 1024

def _import_payload():
    upload = request.files.get('file')
    require_csrf_for_json()
    if upload is not None:
        raw = upload.read(MAX_IMPORT_BYTES + 1)
        if len(raw) > MAX_IMPORT_BYTES:
            return None, (jsonify({"status": "error", "message": "File is too large (2 MB limit)"}), 413)
        text = raw.decode('utf-8', errors='replace')
    else:
        data = request.get_json(silent=True) or {}
        text = (data.get('text') or '')[:MAX_IMPORT_BYTES]

    if not text.strip():
        return None, (jsonify({"status": "error", "message": "Nothing to import"}), 400)
    return text, None

@bp.route('/email_lists/import', methods=['POST'])
@requires_auth
def import_into_new_email_list():
    try:
        name = ((request.form.get('name') if request.files.get('file') is not None
                 else (request.get_json(silent=True) or {}).get('name')) or '').strip()
        if not name:
            return jsonify({"status": "error", "message": "A list name is required"}), 400

        text, err = _import_payload()
        if err:
            return err

        conn = db_connect()
        row = conn.execute("SELECT id FROM email_lists WHERE name = ?", (name,)).fetchone()
        conn.close()
        if row:
            list_id = row[0]
        else:
            # created empty, then filled: add_contacts rewrites the address
            # column from the contact rows, so the two cannot drift
            save_email_list(name, '')
            conn = db_connect()
            created = conn.execute("SELECT id FROM email_lists WHERE name = ?", (name,)).fetchone()
            conn.close()
            if not created:
                return jsonify({"status": "error", "message": f"Could not create list '{name}'"}), 500
            list_id = created[0]

        payload = _run_import(list_id, text)
        payload['list_id'] = list_id
        payload['list_name'] = name
        return jsonify(payload)
    except Exception as e:
        logger.error(f"Error importing into a new list: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/email_lists/<int:list_id>/import', methods=['POST'])
@requires_auth
def import_email_list(list_id):
    try:
        conn = db_connect()
        row = conn.execute("SELECT id FROM email_lists WHERE id = ?", (list_id,)).fetchone()
        conn.close()
        if not row:
            return jsonify({"status": "error", "message": "List not found"}), 404

        text, err = _import_payload()
        if err:
            return err

        return jsonify(_run_import(list_id, text))
    except Exception as e:
        logger.error(f"Error importing contacts: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

def _run_import(list_id, text):
    existing = [c['email'] for c in get_contacts(list_id)]
    suppressed = [r['email'] for r in (get_suppressed_emails() or [])]

    result = parse_contacts(text, existing=existing, suppressed=suppressed)
    added = add_contacts(list_id, result['contacts']) if result['contacts'] else 0

    linked = 0
    if result['contacts'] and get_media_server_type() in ('jellyfin', 'emby'):
        try:
            # keyed by the active server: Jellyfin and Emby user ids are
            # unrelated, so a mapping made on one must not be read on the other
            scope = media_user_scope()
            mapping = match_contacts_to_users(
                result['contacts'], fetch_jellyfin_users(),
                existing=get_media_user_emails(scope))
            linked = set_media_user_emails(mapping, scope)
        except Exception:
            logger.warning("Jellyfin auto-link after import failed", exc_info=True)

    return {
        "status": "success",
        "added": added,
        "duplicate": len(result['duplicate']),
        "suppressed": len(result['suppressed']),
        "linked": linked,
        "invalid": [{"line": line, "text": text_} for line, text_ in result['invalid'][:20]],
        "invalid_count": len(result['invalid']),
    }

@bp.route('/email_lists/<int:list_id>/export', methods=['GET'])
@requires_auth
def export_email_list(list_id):
    try:
        conn = db_connect()
        row = conn.execute("SELECT name FROM email_lists WHERE id = ?", (list_id,)).fetchone()
        conn.close()
        if not row:
            return jsonify({"status": "error", "message": "List not found"}), 404

        safe_name = re.sub(r'[^A-Za-z0-9._-]+', '-', row[0] or 'list').strip('-') or 'list'
        return Response(
            contacts_to_csv(get_contacts(list_id)),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{safe_name}-contacts.csv"'},
        )
    except Exception as e:
        logger.error(f"Error exporting contacts: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/email_lists/<int:list_id>/contacts', methods=['GET'])
@requires_auth
def list_contacts(list_id):
    try:
        return jsonify({"status": "success", "contacts": get_contacts(list_id)})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/contacts/<int:contact_id>', methods=['DELETE'])
@requires_auth
def delete_contact_route(contact_id):
    require_csrf_for_json()
    try:
        if delete_contact(contact_id):
            return jsonify({"status": "success"})
        return jsonify({"status": "error", "message": "Contact not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/media_user_emails', methods=['GET'])
@requires_auth
def get_media_user_email_map():
    try:
        if not is_jellyfin_like():
            return jsonify({"status": "success", "users": []})
        mapped = get_media_user_emails(media_user_scope())
        users = [
            {
                'user_id': u['user_id'],
                'username': u.get('username') or u.get('friendly_name') or u['user_id'],
                'email': mapped.get(u['user_id'], ''),
                'is_active': u.get('is_active', True),
            }
            for u in (fetch_jellyfin_users() or [])
        ]
        return jsonify({"status": "success", "users": users})
    except Exception as e:
        logger.error(f"Error listing media user emails: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/media_user_emails', methods=['POST'])
@requires_auth
def save_media_user_email_map():
    require_csrf_for_json()
    try:
        data = request.get_json(silent=True) or {}
        mapping = data.get('mapping')
        if not isinstance(mapping, dict):
            return jsonify({"status": "error", "message": "Expected a mapping object"}), 400

        cleaned = {}
        for user_id, email in mapping.items():
            email = (email or '').strip()
            if email and not is_email(normalize_email(email)):
                return jsonify({"status": "error",
                                "message": f"'{email}' is not a valid email address"}), 400
            cleaned[str(user_id)] = normalize_email(email) if email else ''

        set_media_user_emails(cleaned, media_user_scope())
        return jsonify({"status": "success", "linked": sum(1 for v in cleaned.values() if v)})
    except Exception as e:
        logger.error(f"Error saving media user emails: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/suppressed_emails', methods=['GET'])
@requires_auth
def get_suppressed_emails_route():
    try:
        rows = get_suppressed_emails()
        return jsonify({"status": "success", "suppressed": rows})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/suppressed_emails/<int:entry_id>', methods=['DELETE'])
@requires_auth
def delete_suppressed_email_route(entry_id):
    require_csrf_for_json()
    try:
        remove_suppressed(entry_id)
        return jsonify({"status": "success", "message": "Recipient removed from suppression list"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/email_templates', methods=['GET'])
@requires_auth
def get_email_templates():
    try:
        conn = db_connect()
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
        logger.error(f"Error getting templates: {e}")
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
        
        conn = db_connect()
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
        logger.error(f"Error saving template: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/email_templates/<int:template_id>', methods=['DELETE'])
@requires_auth
def delete_email_template(template_id):
    require_csrf_for_json()
    try:
        conn = db_connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM email_templates WHERE id = ?", (template_id,))
        conn.commit()
        conn.close()
        
        return jsonify({"status": "success", "message": "Template deleted successfully"})
    except Exception as e:
        logger.error(f"Error deleting template: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
