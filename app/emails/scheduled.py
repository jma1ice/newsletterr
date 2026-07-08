import json, os, smtplib

from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from app.db import db_connect
from app.settings_store import get_settings
from app.render import capture_chart_images_via_headless
from app.clients.tautulli import run_tautulli_command
from app.clients.conjurr import run_conjurr_command
from app.clients.droppedneedle import run_droppedneedle_command, fetch_droppedneedle_server_stats
from app.emails.assemble import convert_html_to_plain_text, build_email_html_with_all_cids
from app.emails.fetchers import fetch_tautulli_data_for_email
from app.emails.send import group_recipients_by_user

import logging

logger = logging.getLogger(__name__)

@dataclass
class ScheduleContext:
    """Per-run data for one scheduled send; settings travel separately."""
    schedule_id: int
    template_name: str
    subject: str
    email_header_title: str
    custom_html: str
    selected_items: list
    expanded_collections: dict
    date_range: int
    items_count: int
    use_prefix: bool
    users_data: list = None
    recommendations_data: dict = field(default_factory=dict)
    droppedneedle_wrapped_data: dict = field(default_factory=dict)
    droppedneedle_server_data: dict = None
    email_text: str = ""

def send_scheduled_email(schedule_id, email_list_id, template_id):
    return send_scheduled_email_with_cids(schedule_id, email_list_id, template_id)

def send_scheduled_email_with_cids(schedule_id, email_list_id, template_id):
    try:
        schedule_conn = db_connect()
        schedule_cursor = schedule_conn.cursor()
        schedule_cursor.execute("SELECT date_range, items_count FROM email_schedules WHERE id = ?", (schedule_id,))
        schedule_result = schedule_cursor.fetchone()
        schedule_conn.close()

        # decrypted settings; downstream decrypt() calls in clients pass
        # plaintext through unchanged (InvalidToken passthrough)
        s = get_settings()

        date_range = schedule_result[0] if schedule_result else 7
        items_count = schedule_result[1] if schedule_result else 10

        if email_list_id == 0 or email_list_id == 'ALL':
            if s.get("tautulli_url") and s.get("tautulli_api"):
                tautulli_url = s["tautulli_url"].rstrip('/')
                tautulli_api = s["tautulli_api"]
                users_data, _ = run_tautulli_command(tautulli_url, tautulli_api, 'get_users', 'Users', None)
                
                if users_data:
                    to_emails_list = [
                        u['email'] for u in users_data
                        if u.get('email') and u.get('email').strip() and u.get('is_active')
                    ]
                else:
                    logger.info("No users found for ALL list")
                    return False
            else:
                logger.info("Tautulli not configured for ALL list")
                return False
        else:
            email_lists_conn = db_connect()
            email_lists_cursor = email_lists_conn.cursor()
            email_lists_cursor.execute("SELECT emails FROM email_lists WHERE id = ?", (email_list_id,))
            email_list_result = email_lists_cursor.fetchone()
            email_lists_conn.close()
            
            if not email_list_result:
                logger.error(f"Email list {email_list_id} not found")
                return False
            
            to_emails = email_list_result[0]
            to_emails_list = [email.strip() for email in to_emails.split(",")]
        
        templates_conn = db_connect()
        templates_cursor = templates_conn.cursor()
        templates_cursor.execute("SELECT name, subject, email_text, selected_items, expanded_collections, email_header_title, custom_html FROM email_templates WHERE id = ?", (template_id,))
        template_result = templates_cursor.fetchone()
        templates_conn.close()
        
        if not template_result:
            logger.error(f"Template {template_id} not found")
            return False
        
        template_name, subject, email_text, selected_items_json, expanded_collections_json, email_header_title, custom_html = template_result
        selected_items = json.loads(selected_items_json) if selected_items_json else []
        expanded_collections = json.loads(expanded_collections_json) if expanded_collections_json else {}
        email_header_title = email_header_title or ''
        custom_html = custom_html or ''
        
        if "id" not in s:
            logger.error("SMTP settings not found in database")
            return False

        public_base = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:6397")
        theme = 'dark'
        
        logger.info("Capturing chart images...")
        try:
            chart_images = capture_chart_images_via_headless(schedule_id, public_base, theme)
        except Exception:
            # environments without playwright browsers (release binaries)
            # still send the email, just without rendered chart images
            logger.warning("Chart capture unavailable; sending without chart images", exc_info=True)
            chart_images = {}
        logger.info(f"Captured {len(chart_images)} chart images")
        
        for item in selected_items:
            if item.get('type') == 'graph' and item.get('id') in chart_images:
                chart_data = chart_images[item['id']]
                item['chartImage'] = chart_data.get('dataUrl', '')
                item['chartSVG'] = chart_data.get('svg', '')

        has_recs = any(item.get('type') == 'recommendations' for item in selected_items)
        has_wrapped = any(item.get('type') == 'droppedneedle_wrapped' for item in selected_items)

        users_data, _ = run_tautulli_command(s.get("tautulli_url"), s.get("tautulli_api"), 'get_users', 'Users', None)
        user_dict = {}
        if users_data:
            user_dict = {
                u['user_id']: u['email']
                for u in users_data
                if u.get('email') != None and u.get('email') != '' and u.get('is_active')
            }

        droppedneedle_url = (s.get("droppedneedle_url") or "").strip()
        droppedneedle_api_key = s.get("droppedneedle_api_key") or ""
        droppedneedle_server_data, _ = fetch_droppedneedle_server_stats(droppedneedle_url, droppedneedle_api_key) if (droppedneedle_url and droppedneedle_api_key) else (None, None)

        ctx = ScheduleContext(
            schedule_id=schedule_id,
            template_name=template_name,
            subject=subject,
            email_header_title=email_header_title,
            custom_html=custom_html,
            selected_items=selected_items,
            expanded_collections=expanded_collections,
            date_range=date_range,
            items_count=items_count,
            use_prefix=s["scheduled_subject_prefix"] == 'enabled',
            users_data=users_data,
            droppedneedle_server_data=droppedneedle_server_data,
        )

        if has_recs or has_wrapped:
            logger.info("Template contains recommendations or DroppedNeedle wrapped stats, splitting emails by user...")

            rec_user_keys = set()
            wrapped_user_keys = set()
            for item in selected_items:
                if item.get('type') == 'recommendations' and item.get('userKey'):
                    rec_user_keys.add(item['userKey'])
                elif item.get('type') == 'droppedneedle_wrapped' and item.get('userKey'):
                    wrapped_user_keys.add(item['userKey'])

            personalized_user_keys = rec_user_keys | wrapped_user_keys
            if not personalized_user_keys:
                logger.info("No recommendation or wrapped user keys found in template")
                return False

            recommendations_data = {}
            if rec_user_keys:
                if not s.get("conjurr_url"):
                    logger.info("Conjurr URL not configured")
                    return False

                conjurr_url = s["conjurr_url"].strip()
                filtered_rec_users = {k: v for k, v in user_dict.items() if str(k) in rec_user_keys and v in to_emails_list}

                if not filtered_rec_users:
                    logger.info("No users found matching recommendation blocks and email recipients")
                    return False

                recommendations_data, _ = run_conjurr_command(conjurr_url, filtered_rec_users, None)
                if not recommendations_data:
                    logger.error("Failed to fetch recommendations data")
                    return False

            droppedneedle_wrapped_data = {}
            if wrapped_user_keys:
                if not (droppedneedle_url and droppedneedle_api_key):
                    logger.info("DroppedNeedle URL/API key not configured")
                    return False

                filtered_wrapped_users = {k: v for k, v in user_dict.items() if str(k) in wrapped_user_keys and v in to_emails_list}

                if not filtered_wrapped_users:
                    logger.info("No users found matching DroppedNeedle wrapped blocks and email recipients")
                    return False

                droppedneedle_wrapped_data, _ = run_droppedneedle_command(droppedneedle_url, droppedneedle_api_key, filtered_wrapped_users, None)
                if not droppedneedle_wrapped_data:
                    logger.error("Failed to fetch DroppedNeedle wrapped data")
                    return False

            groups = group_recipients_by_user(to_emails_list, user_dict)

            ctx.recommendations_data = recommendations_data
            ctx.droppedneedle_wrapped_data = droppedneedle_wrapped_data

            total_sent = 0
            sent_info = []

            for user_key, recipients in groups.items():
                if user_key is None or str(user_key) not in personalized_user_keys:
                    logger.info(f"Skipping recipients without recommendations or wrapped stats: {recipients}")
                    continue

                success = send_scheduled_user_email_with_cids(ctx, s, recipients, user_key)

                if success:
                    total_sent += len(recipients)
                    sent_info.append(', '.join(recipients))
                    logger.info(f"Successfully sent scheduled email to user {user_key}: {recipients}")
                else:
                    logger.error(f"Failed to send scheduled email to user {user_key}: {recipients}")

            if total_sent == 0:
                logger.info("No emails were sent successfully")
                return False

            logger.info(f"Scheduled email sent successfully to {total_sent} total recipients across {len(sent_info)} user groups")
            return True

        else:
            logger.info("Template has no recommendations or wrapped stats, sending single email to all recipients...")
            return send_scheduled_single_email_with_cids(ctx, s, to_emails_list)

    except Exception as e:
        logger.exception(f"Error in send_scheduled_email_with_cids: {e}")
        return False

def send_scheduled_user_email_with_cids(ctx, settings, recipients, user_key):
    try:
        from_email = settings.get("from_email")
        alias_email = settings.get("alias_email")
        reply_to_email = settings.get("reply_to_email")
        password = settings.get("password")
        smtp_username = settings.get("smtp_username")
        smtp_server = settings.get("smtp_server")
        smtp_port = settings.get("smtp_port")
        smtp_protocol = settings.get("smtp_protocol")
        server_name = settings.get("server_name")
        tautulli_base_url = settings.get("tautulli_url")
        tautulli_api_key = settings.get("tautulli_api")
        logo_filename = settings.get("logo_filename")
        logo_width = settings.get("logo_width")
        custom_logo_filename = settings.get("custom_logo_filename")
        from_name = settings.get("from_name") or ''
        display_preference = settings["recipient_display_name"]
        logo_position = settings["logo_position"]
        default_intro_text = settings["default_intro_text"]
        default_outro_text = settings["default_outro_text"]
        hide_stat_play_counts = settings["hide_stat_play_counts"]
        hide_graph_play_counts = settings["hide_graph_play_counts"]
        stats_type = settings["stats_type"]
        recently_added_mode = settings["recently_added_mode"]
        recently_added_sort = settings["recently_added_sort"]
        ra_grid_columns = settings["ra_grid_columns"]
        recs_grid_columns = settings["recs_grid_columns"]
        stat_cover_art = settings["stat_cover_art"]
        send_mode = settings["send_mode"]
        poster_max_height = settings["poster_max_height"]
        subject = ctx.subject
        email_header_title = ctx.email_header_title
        custom_html = ctx.custom_html
        selected_items = ctx.selected_items
        expanded_collections = ctx.expanded_collections
        date_range = ctx.date_range
        items_count = ctx.items_count
        template_name = ctx.template_name
        use_prefix = ctx.use_prefix
        users_data = ctx.users_data
        recommendations_data = ctx.recommendations_data
        droppedneedle_wrapped_data = ctx.droppedneedle_wrapped_data
        droppedneedle_server_data = ctx.droppedneedle_server_data
        logger.info(f"SMTP Config: {smtp_server}:{smtp_port} using {smtp_protocol}")

        if smtp_port == 465 and smtp_protocol == 'TLS':
            logger.warning("WARNING: Port 465 with TLS protocol detected!")
            logger.info("Port 465 requires SSL protocol. Consider changing to:")
            logger.info("- Port 587 with TLS, OR")
            logger.info("- Port 465 with SSL")
        
        if smtp_port == 587 and smtp_protocol == 'SSL':
            logger.warning("WARNING: Port 587 with SSL protocol detected!")
            logger.info("Port 587 typically uses TLS (STARTTLS)")

        msg_root = MIMEMultipart('related')
        msg_root['Subject'] = f"[SCHEDULED] {subject}" if use_prefix else subject
        
        if alias_email:
            if from_name == '':
                msg_root['From'] = alias_email
            else:
                msg_root['From'] = formataddr((from_name, alias_email))
            msg_root['To'] = alias_email
        else:
            if from_name == '':
                msg_root['From'] = from_email
            else:
                msg_root['From'] = formataddr((from_name, from_email))
            msg_root['To'] = from_email
        
        if reply_to_email:
            msg_root['Reply-To'] = reply_to_email

        msg_alternative = MIMEMultipart('alternative')
        msg_root.attach(msg_alternative)

        logger.info("Building email content...")
        tautulli_data = fetch_tautulli_data_for_email(tautulli_base_url, tautulli_api_key, date_range, server_name, items_count, stats_type=stats_type, recently_added_mode=recently_added_mode, recently_added_sort=recently_added_sort)
        tautulli_data["settings"]["logo_filename"] = logo_filename
        tautulli_data["settings"]["logo_width"] = logo_width
        tautulli_data["settings"]["custom_logo_filename"] = custom_logo_filename
        tautulli_data["settings"]["logo_position"] = logo_position
        tautulli_data["settings"]["default_intro_text"] = default_intro_text
        tautulli_data["settings"]["default_outro_text"] = default_outro_text
        tautulli_data["settings"]["hide_stat_play_counts"] = hide_stat_play_counts
        tautulli_data["settings"]["hide_graph_play_counts"] = hide_graph_play_counts
        tautulli_data["settings"]["stats_type"] = stats_type
        tautulli_data["settings"]["recently_added_mode"] = recently_added_mode
        tautulli_data["settings"]["recently_added_sort"] = recently_added_sort
        tautulli_data["settings"]["ra_grid_columns"] = ra_grid_columns
        tautulli_data["settings"]["recs_grid_columns"] = recs_grid_columns
        tautulli_data["settings"]["stat_cover_art"] = stat_cover_art
        tautulli_data["settings"]["poster_max_height"] = poster_max_height

        template_data = {
            'selected_items': json.dumps(selected_items),
            'email_text': '',
            'subject': subject,
            'custom_html': custom_html
        }

        base_url = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:6397")

        user_dict = {user_key: recipients[0]} if recipients else {}
        
        email_html = build_email_html_with_all_cids(
            template_data, 
            tautulli_data, 
            msg_root,
            display_preference,
            users_data,
            recommendations_data,
            user_dict,
            base_url,
            target_user_key=user_key,
            is_scheduled=True,
            items_count=items_count,
            date_range=date_range,
            expanded_collections=expanded_collections,
            email_header_title=email_header_title,
            droppedneedle_wrapped_data=droppedneedle_wrapped_data,
            droppedneedle_server_data=droppedneedle_server_data
        )

        plain_text = convert_html_to_plain_text(email_html)
        msg_alternative.attach(MIMEText(plain_text, 'plain', 'utf-8'))
        msg_alternative.attach(MIMEText(email_html, 'html', 'utf-8'))

        logger.info(f"Attempting SMTP connection...")

        if smtp_protocol == 'SSL':
            logger.info(f"Using SMTP_SSL on port {smtp_port}")
            server = smtplib.SMTP_SSL(smtp_server, int(smtp_port))
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, password)
        else:
            logger.info(f"Using SMTP with STARTTLS on port {smtp_port}")
            server = smtplib.SMTP(smtp_server, int(smtp_port))
            logger.info("Starting TLS...")
            server.starttls()
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, password)
        
        logger.info("SMTP connection established successfully")
        
        email_content = msg_root.as_string()

        content_size_kb = len(email_content.encode('utf-8')) / 1024
        content_size_mb = len(email_content.encode('utf-8')) / (1024 * 1024)
        logger.info(f"Email size: {content_size_mb:.2f} MB")
        if content_size_mb > 25:
            logger.warning("WARNING: Email exceeds typical size limits")

        logger.info("Sending email...")

        from_addr = alias_email if alias_email else from_email
        if send_mode == 'to':
            for recipient in recipients:
                msg_root.replace_header('To', recipient)
                server.sendmail(from_addr, [recipient], msg_root.as_string())
            all_recipients = recipients
        else:
            server.sendmail(from_addr, [from_addr] + recipients, email_content)
            all_recipients = [from_addr] + recipients

        server.quit()
        logger.info(f"Email sent successfully!")

        try:
            history_conn = db_connect()
            history_cursor = history_conn.cursor()
            history_cursor.execute('''INSERT INTO email_history (subject, recipients, email_content, content_size_kb, recipient_count, template_name)
                            VALUES (?, ?, ?, ?, ?, ?)''',
                            (f"[SCHEDULED] {subject}", ', '.join(all_recipients), email_content[:1000], content_size_kb, len(all_recipients), template_name))
            history_conn.commit()
            history_conn.close()
        except Exception as log_err:
            logger.error(f"Error logging scheduled email history: {log_err}")

        return True
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP Connection Error: {e}")
        logger.warning("This often indicates wrong port/protocol combination")
        return False
    except smtplib.SMTPServerDisconnected as e:
        logger.warning(f"SMTP Server Disconnected: {e}")
        logger.warning("Server closed connection - likely protocol mismatch")
        return False
    except Exception as e:
        logger.exception(f"Error sending scheduled user email: {e}")
        return False

def send_scheduled_single_email_with_cids(ctx, settings, to_emails_list):
    try:
        from_email = settings.get("from_email")
        alias_email = settings.get("alias_email")
        reply_to_email = settings.get("reply_to_email")
        password = settings.get("password")
        smtp_username = settings.get("smtp_username")
        smtp_server = settings.get("smtp_server")
        smtp_port = settings.get("smtp_port")
        smtp_protocol = settings.get("smtp_protocol")
        server_name = settings.get("server_name")
        tautulli_base_url = settings.get("tautulli_url")
        tautulli_api_key = settings.get("tautulli_api")
        logo_filename = settings.get("logo_filename")
        logo_width = settings.get("logo_width")
        custom_logo_filename = settings.get("custom_logo_filename")
        from_name = settings.get("from_name") or ''
        display_preference = settings["recipient_display_name"]
        logo_position = settings["logo_position"]
        default_intro_text = settings["default_intro_text"]
        default_outro_text = settings["default_outro_text"]
        hide_stat_play_counts = settings["hide_stat_play_counts"]
        hide_graph_play_counts = settings["hide_graph_play_counts"]
        stats_type = settings["stats_type"]
        recently_added_mode = settings["recently_added_mode"]
        recently_added_sort = settings["recently_added_sort"]
        ra_grid_columns = settings["ra_grid_columns"]
        recs_grid_columns = settings["recs_grid_columns"]
        stat_cover_art = settings["stat_cover_art"]
        send_mode = settings["send_mode"]
        poster_max_height = settings["poster_max_height"]
        subject = ctx.subject
        email_header_title = ctx.email_header_title
        custom_html = ctx.custom_html
        selected_items = ctx.selected_items
        expanded_collections = ctx.expanded_collections
        date_range = ctx.date_range
        items_count = ctx.items_count
        template_name = ctx.template_name
        use_prefix = ctx.use_prefix
        users_data = ctx.users_data
        droppedneedle_server_data = ctx.droppedneedle_server_data
        email_text = ctx.email_text
        logger.info(f"SMTP Config: {smtp_server}:{smtp_port} using {smtp_protocol}")

        if smtp_port == 465 and smtp_protocol == 'TLS':
            logger.warning("WARNING: Port 465 with TLS protocol detected!")
            logger.info("Port 465 requires SSL protocol. Consider changing to:")
            logger.info("- Port 587 with TLS, OR")
            logger.info("- Port 465 with SSL")
        
        if smtp_port == 587 and smtp_protocol == 'SSL':
            logger.warning("WARNING: Port 587 with SSL protocol detected!")
            logger.info("Port 587 typically uses TLS (STARTTLS)")

        msg_root = MIMEMultipart('related')
        msg_root['Subject'] = f"[SCHEDULED] {subject}" if use_prefix else subject
        
        if alias_email:
            if from_name == '':
                msg_root['From'] = alias_email
            else:
                msg_root['From'] = formataddr((from_name, alias_email))
            msg_root['To'] = alias_email
        else:
            if from_name == '':
                msg_root['From'] = from_email
            else:
                msg_root['From'] = formataddr((from_name, from_email))
            msg_root['To'] = from_email

        if reply_to_email:
            msg_root['Reply-To'] = reply_to_email
        
        msg_alternative = MIMEMultipart('alternative')
        msg_root.attach(msg_alternative)

        logger.info("Building email content...")
        tautulli_data = fetch_tautulli_data_for_email(tautulli_base_url, tautulli_api_key, date_range, server_name, items_count, stats_type=stats_type, recently_added_mode=recently_added_mode, recently_added_sort=recently_added_sort)
        tautulli_data["settings"]["logo_filename"] = logo_filename
        tautulli_data["settings"]["logo_width"] = logo_width
        tautulli_data["settings"]["custom_logo_filename"] = custom_logo_filename
        tautulli_data["settings"]["logo_position"] = logo_position
        tautulli_data["settings"]["default_intro_text"] = default_intro_text
        tautulli_data["settings"]["default_outro_text"] = default_outro_text
        tautulli_data["settings"]["hide_stat_play_counts"] = hide_stat_play_counts
        tautulli_data["settings"]["hide_graph_play_counts"] = hide_graph_play_counts
        tautulli_data["settings"]["stats_type"] = stats_type
        tautulli_data["settings"]["recently_added_mode"] = recently_added_mode
        tautulli_data["settings"]["recently_added_sort"] = recently_added_sort
        tautulli_data["settings"]["ra_grid_columns"] = ra_grid_columns
        tautulli_data["settings"]["recs_grid_columns"] = recs_grid_columns
        tautulli_data["settings"]["stat_cover_art"] = stat_cover_art
        tautulli_data["settings"]["poster_max_height"] = poster_max_height

        template_data = {
            'selected_items': json.dumps(selected_items),
            'email_text': email_text,
            'subject': subject,
            'custom_html': custom_html
        }

        base_url = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:6397")
        
        email_html = build_email_html_with_all_cids(
            template_data, 
            tautulli_data, 
            msg_root,
            display_preference,
            users_data,
            None,
            None,
            base_url,
            None,
            True,
            items_count,
            date_range,
            expanded_collections,
            email_header_title=email_header_title,
            droppedneedle_server_data=droppedneedle_server_data
        )

        plain_text = convert_html_to_plain_text(email_html)
        msg_alternative.attach(MIMEText(plain_text, 'plain', 'utf-8'))
        msg_alternative.attach(MIMEText(email_html, 'html', 'utf-8'))

        logger.info(f"Attempting SMTP connection...")

        if smtp_protocol == 'SSL':
            logger.info(f"Using SMTP_SSL on port {smtp_port}")
            server = smtplib.SMTP_SSL(smtp_server, int(smtp_port))
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, password)
        else:
            logger.info(f"Using SMTP with STARTTLS on port {smtp_port}")
            server = smtplib.SMTP(smtp_server, int(smtp_port))
            logger.info("Starting TLS...")
            server.starttls()
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, password)
        
        logger.info("SMTP connection established successfully")
        
        email_content = msg_root.as_string()

        content_size_kb = len(email_content.encode('utf-8')) / 1024
        content_size_mb = len(email_content.encode('utf-8')) / (1024 * 1024)
        logger.info(f"Email size: {content_size_mb:.2f} MB")
        if content_size_mb > 25:
            logger.warning("WARNING: Email exceeds typical size limits")

        logger.info("Sending email...")

        from_addr = alias_email if alias_email else from_email
        if send_mode == 'to':
            for recipient in to_emails_list:
                msg_root.replace_header('To', recipient)
                server.sendmail(from_addr, [recipient], msg_root.as_string())
            all_recipients = to_emails_list
        else:
            server.sendmail(from_addr, [from_addr] + to_emails_list, email_content)
            all_recipients = [from_addr] + to_emails_list

        server.quit()
        logger.info(f"Email sent successfully!")

        try:
            history_conn = db_connect()
            history_cursor = history_conn.cursor()
            history_cursor.execute('''INSERT INTO email_history (subject, recipients, email_content, content_size_kb, recipient_count, template_name)
                            VALUES (?, ?, ?, ?, ?, ?)''',
                            (f"[SCHEDULED] {subject}", ', '.join(all_recipients), email_content[:1000], content_size_kb, len(all_recipients), template_name))
            history_conn.commit()
            history_conn.close()
        except Exception as log_err:
            logger.error(f"Error logging scheduled email history: {log_err}")
        
        logger.info(f"Scheduled email sent successfully to {len(all_recipients)} recipients")
        return True
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP Connection Error: {e}")
        logger.warning("This often indicates wrong port/protocol combination")
        return False
    except smtplib.SMTPServerDisconnected as e:
        logger.warning(f"SMTP Server Disconnected: {e}")
        logger.warning("Server closed connection - likely protocol mismatch")
        return False
    except Exception as e:
        logger.exception(f"Error in send_scheduled_single_email_with_cids: {e}")
        return False
