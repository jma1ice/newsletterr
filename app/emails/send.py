import json, smtplib

from collections import defaultdict
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

from app import config
from app.clients.tautulli import run_tautulli_command
from app.db import db_connect
from app.store import filter_suppressed, record_email_history
from app.tokens import make_unsubscribe_placeholder, sign_unsubscribe_token
from app.emails.assemble import convert_html_to_plain_text, build_email_html_with_all_cids
from app.emails.fetchers import get_current_tautulli_data_for_email, get_recommendations_for_users, get_droppedneedle_wrapped_for_users, get_droppedneedle_server_stats_cached, get_yearly_wrapped_cached, get_sonarr_coming_soon_cached, get_radarr_coming_soon_cached

import logging

logger = logging.getLogger(__name__)

def group_recipients_by_user(to_emails_list, user_dict):
    email_to_user = { (v or '').strip().lower(): k for k, v in (user_dict or {}).items() if v }
    groups = defaultdict(list)
    for email in (to_emails_list or []):
        key = email_to_user.get((email or '').strip().lower())
        groups[key].append(email)
    return groups

def send_personalized_per_recipient(server, msg_root, from_addr, recipients, email_html, plain_text,
                                     unsub_placeholder, hosted_base_url, send_mode):
    """Sends msg_root once per recipient, swapping in that recipient's own
    signed unsubscribe token for the shared placeholder embedded in
    email_html/plain_text at build time."""
    image_parts = msg_root.get_payload()[1:]
    last_content = None
    for recipient in recipients:
        token = sign_unsubscribe_token(recipient)
        personalized_html = email_html.replace(unsub_placeholder, token)
        personalized_plain = plain_text.replace(unsub_placeholder, token)

        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(personalized_plain, 'plain', 'utf-8'))
        alt.attach(MIMEText(personalized_html, 'html', 'utf-8'))
        msg_root.set_payload([alt] + image_parts)

        if 'List-Unsubscribe' in msg_root:
            del msg_root['List-Unsubscribe']
        msg_root['List-Unsubscribe'] = f'<mailto:{from_addr}?subject=unsubscribe>, <{hosted_base_url}/u/{token}>'
        if 'List-Unsubscribe-Post' not in msg_root:
            msg_root['List-Unsubscribe-Post'] = 'List-Unsubscribe=One-Click'

        if send_mode == 'to':
            msg_root.replace_header('To', recipient)

        last_content = msg_root.as_string()
        server.sendmail(from_addr, [recipient], last_content)
    return last_content

@dataclass
class SendRequest:
    """Per-request data for a manual send; settings travel separately."""
    subject: str
    email_header_title: str
    selected_items: list
    custom_html: str = ''
    expanded_collections: dict = field(default_factory=dict)
    user_dict: dict = field(default_factory=dict)
    is_test: bool = False

def send_standard_email_with_cids(req, settings, to_emails):
    """Returns (payload, http_status), the route wraps it in jsonify."""
    try:
        to_emails, _suppressed = filter_suppressed(to_emails)
        if not to_emails:
            return {"error": "All recipients have unsubscribed"}, 400

        from_email = settings.get("from_email") or ""
        alias_email = settings.get("alias_email") or ""
        reply_to_email = settings.get("reply_to_email") or ""
        password = settings.get("password") or ""
        smtp_username = settings.get("smtp_username") or ""
        smtp_server = settings.get("smtp_server") or ""
        smtp_port = int(settings.get("smtp_port") or 587)
        smtp_protocol = settings.get("smtp_protocol") or "TLS"
        from_name = settings.get("from_name") or ""
        send_mode = settings.get("send_mode") or "bcc"
        subject = req.subject
        email_header_title = req.email_header_title
        selected_items = req.selected_items
        custom_html = req.custom_html
        expanded_collections = req.expanded_collections
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
        msg_root['Subject'] = subject
        if alias_email == '':
            if from_name == '':
                msg_root['From'] = from_email
            else:
                msg_root['From'] = formataddr((from_name, from_email))
            msg_root['To'] = from_email
        else:
            if from_name == '':
                msg_root['From'] = alias_email
            else:
                msg_root['From'] = formataddr((from_name, alias_email))
            msg_root['To'] = alias_email
        
        if reply_to_email != '':
            msg_root['Reply-To'] = reply_to_email

        msg_alternative = MIMEMultipart('alternative')
        msg_root.attach(msg_alternative)

        logger.info("Building email content...")
        tautulli_data = get_current_tautulli_data_for_email(settings)
        droppedneedle_server_data = get_droppedneedle_server_stats_cached(use_cache=True)
        yearly_wrapped_data = get_yearly_wrapped_cached(use_cache=True)
        sonarr_coming_soon_data = get_sonarr_coming_soon_cached(use_cache=True, days_ahead=settings.get("coming_soon_days_ahead") or 14)
        radarr_coming_soon_data = get_radarr_coming_soon_cached(use_cache=True, days_ahead=settings.get("coming_soon_days_ahead") or 14)

        template_data = {
            'selected_items': json.dumps(selected_items),
            'email_text': '',
            'subject': subject,
            'custom_html': custom_html
        }

        base_url = config.INTERNAL_BASE_URL

        hosted_enabled = settings.get("hosted_enabled") == "enabled"
        hosted_base_url = (settings.get("hosted_base_url") or "").rstrip('/')
        hosted_images_enabled = settings.get("hosted_images_enabled") == "enabled"
        use_personalized_send = hosted_enabled and bool(hosted_base_url)
        unsub_placeholder = make_unsubscribe_placeholder() if use_personalized_send else None
        build_hosted_variant = use_personalized_send and not req.is_test

        email_html, hosted_html = build_email_html_with_all_cids(
            template_data,
            tautulli_data,
            msg_root,
            None,
            None,
            None,
            None,
            base_url,
            None,
            False,
            None,
            "",
            expanded_collections,
            email_header_title,
            droppedneedle_server_data=droppedneedle_server_data,
            yearly_wrapped_data=yearly_wrapped_data,
            sonarr_coming_soon_data=sonarr_coming_soon_data,
            radarr_coming_soon_data=radarr_coming_soon_data,
            unsubscribe_placeholder=unsub_placeholder,
            hosted_base_url=hosted_base_url,
            hosted_images_enabled=hosted_images_enabled,
            build_hosted_variant=build_hosted_variant
        )

        plain_text = convert_html_to_plain_text(email_html)
        if not use_personalized_send:
            msg_alternative.attach(MIMEText(plain_text, 'plain', 'utf-8'))
            msg_alternative.attach(MIMEText(email_html, 'html', 'utf-8'))

        logger.info(f"Attempting SMTP connection...")

        if smtp_protocol == 'SSL':
            logger.info(f"Using SMTP_SSL on port {smtp_port}")
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, password)
        else:
            logger.info(f"Using SMTP with STARTTLS on port {smtp_port}")
            server = smtplib.SMTP(smtp_server, smtp_port)
            logger.info("Starting TLS...")
            server.starttls()
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, password)

        logger.info("SMTP connection established successfully")

        logger.info("Sending email...")

        from_addr = alias_email if alias_email else from_email
        if use_personalized_send:
            all_recipients = to_emails if send_mode == 'to' else [from_addr] + to_emails
            email_content = send_personalized_per_recipient(
                server, msg_root, from_addr, all_recipients, email_html, plain_text,
                unsub_placeholder, hosted_base_url, send_mode
            )
        elif send_mode == 'to':
            email_content = msg_root.as_string()
            for recipient in to_emails:
                msg_root.replace_header('To', recipient)
                server.sendmail(from_addr, [recipient], msg_root.as_string())
            all_recipients = to_emails
        else:
            email_content = msg_root.as_string()
            server.sendmail(from_addr, [from_addr] + to_emails, email_content)
            all_recipients = [from_addr] + to_emails

        content_size_kb = len((email_content or "").encode('utf-8')) / 1024
        content_size_mb = content_size_kb / 1024
        logger.info(f"Email size: {content_size_mb:.2f} MB")
        if content_size_mb > 25:
            logger.warning("WARNING: Email exceeds typical size limits")

        logger.info(f"Email sent successfully!")

        record_email_history(subject, ', '.join(all_recipients), email_content,
                             round(content_size_kb, 2), len(all_recipients), 'Manual', hosted_html=hosted_html)

        server.quit()
        return {"success": True, "sent_to": ', '.join(all_recipients), "size": content_size_kb}, 200
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP Connection Error: {e}")
        logger.warning("This often indicates wrong port/protocol combination")
        msg = f"SMTP connection error: {e}"
        record_email_history(req.subject, ', '.join(to_emails), '', 0, len(to_emails), 'Manual', status='failed', error=msg)
        return {"error": msg}, 500
    except smtplib.SMTPServerDisconnected as e:
        logger.warning(f"SMTP Server Disconnected: {e}")
        logger.warning("Server closed connection - likely protocol mismatch")
        msg = f"SMTP server disconnected: {e}"
        record_email_history(req.subject, ', '.join(to_emails), '', 0, len(to_emails), 'Manual', status='failed', error=msg)
        return {"error": msg}, 500
    except Exception as e:
        logger.error(f"SMTP send error: {e}")
        record_email_history(req.subject, ', '.join(to_emails), '', 0, len(to_emails), 'Manual', status='failed', error=str(e))
        return {"error": str(e)}, 500

def send_recommendations_email_with_cids(req, settings, to_emails):
    """Returns (payload, http_status), the route wraps it in jsonify."""
    try:
        to_emails, _suppressed = filter_suppressed(to_emails)
        if not to_emails:
            return {"error": "All recipients have unsubscribed"}, 400

        selected_items = req.selected_items
        user_dict = req.user_dict
        rec_user_keys = set()
        wrapped_user_keys = set()
        for item in selected_items:
            if item.get('type') == 'recommendations' and item.get('userKey'):
                rec_user_keys.add(item['userKey'])
            elif item.get('type') == 'droppedneedle_wrapped' and item.get('userKey'):
                wrapped_user_keys.add(item['userKey'])

        personalized_user_keys = rec_user_keys | wrapped_user_keys

        if not personalized_user_keys:
            return send_standard_email_with_cids(req, settings, to_emails)

        recommendations_data = get_recommendations_for_users(rec_user_keys, to_emails, user_dict, use_cache=True) if rec_user_keys else {}
        droppedneedle_wrapped_data = get_droppedneedle_wrapped_for_users(wrapped_user_keys, to_emails, user_dict, use_cache=True) if wrapped_user_keys else {}
        droppedneedle_server_data = get_droppedneedle_server_stats_cached(use_cache=True)
        yearly_wrapped_data = get_yearly_wrapped_cached(use_cache=True)
        sonarr_coming_soon_data = get_sonarr_coming_soon_cached(use_cache=True, days_ahead=settings.get("coming_soon_days_ahead") or 14)
        radarr_coming_soon_data = get_radarr_coming_soon_cached(use_cache=True, days_ahead=settings.get("coming_soon_days_ahead") or 14)

        if rec_user_keys and not recommendations_data:
            return {"error": "No recommendations data available. Please pull recommendations first."}, 400
        if wrapped_user_keys and not droppedneedle_wrapped_data:
            return {"error": "No DroppedNeedle wrapped data available. Please pull DroppedNeedle stats first."}, 400

        groups = group_recipients_by_user(to_emails, user_dict)

        total_sent = 0
        sent_info = []

        for user_key, recipients in groups.items():
            if user_key is None or user_key not in personalized_user_keys:
                logger.info(f"Skipping recipients without recommendations or wrapped stats: {recipients}")
                continue

            success = send_single_user_email_with_cids(
                req, settings, recipients, user_key,
                recommendations_data=recommendations_data,
                droppedneedle_wrapped_data=droppedneedle_wrapped_data,
                droppedneedle_server_data=droppedneedle_server_data,
                yearly_wrapped_data=yearly_wrapped_data,
                sonarr_coming_soon_data=sonarr_coming_soon_data,
                radarr_coming_soon_data=radarr_coming_soon_data,
            )

            if success:
                total_sent += len(recipients)
                sent_info.append(', '.join(recipients))

        if total_sent == 0:
            return {"error": "No recipients matched a recommendations or wrapped stats block. No emails sent."}, 400

        return {"success": True, "sent_groups": sent_info}, 200

    except Exception as e:
        logger.error("%s %s", "Error in send_recommendations_email_with_cids:", e)
        return {"error": str(e)}, 500

def send_single_user_email_with_cids(req, settings, recipients, user_key, recommendations_data=None, droppedneedle_wrapped_data=None, droppedneedle_server_data=None, yearly_wrapped_data=None, sonarr_coming_soon_data=None, radarr_coming_soon_data=None):
    try:
        from_email = settings.get("from_email") or ""
        alias_email = settings.get("alias_email") or ""
        reply_to_email = settings.get("reply_to_email") or ""
        password = settings.get("password") or ""
        smtp_username = settings.get("smtp_username") or ""
        smtp_server = settings.get("smtp_server") or ""
        smtp_port = int(settings.get("smtp_port") or 587)
        smtp_protocol = settings.get("smtp_protocol") or "TLS"
        from_name = settings.get("from_name") or ""
        send_mode = settings.get("send_mode") or "bcc"
        subject = req.subject
        email_header_title = req.email_header_title
        selected_items = req.selected_items
        custom_html = req.custom_html
        expanded_collections = req.expanded_collections
        logger.info(f"SMTP Config: {smtp_server}:{smtp_port} using {smtp_protocol}")

        if smtp_port == 465 and smtp_protocol == 'TLS':
            logger.warning("WARNING: Port 465 with TLS protocol detected!")
            logger.info("Port 465 requires SSL protocol. Consider changing to:")
            logger.info("- Port 587 with TLS, OR")
            logger.info("- Port 465 with SSL")
        
        if smtp_port == 587 and smtp_protocol == 'SSL':
            logger.warning("WARNING: Port 587 with SSL protocol detected!")
            logger.info("Port 587 typically uses TLS (STARTTLS)")

        display_preference = settings["recipient_display_name"]
        tautulli_url = settings.get("tautulli_url")
        tautulli_api = settings.get("tautulli_api")
        
        users_full_data = None
        if tautulli_url and tautulli_api:
            users_data, _ = run_tautulli_command(tautulli_url.rstrip('/'), tautulli_api, 'get_users', 'Users', None)
            if users_data:
                users_full_data = users_data

        msg_root = MIMEMultipart('related')
        msg_root['Subject'] = subject
        
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
        tautulli_data = get_current_tautulli_data_for_email(settings)
        
        template_data = {
            'selected_items': json.dumps(selected_items),
            'email_text': '',
            'subject': subject,
            'custom_html': custom_html
        }
        
        base_url = config.INTERNAL_BASE_URL

        hosted_enabled = settings.get("hosted_enabled") == "enabled"
        hosted_base_url = (settings.get("hosted_base_url") or "").rstrip('/')
        hosted_images_enabled = settings.get("hosted_images_enabled") == "enabled"
        use_personalized_send = hosted_enabled and bool(hosted_base_url)
        unsub_placeholder = make_unsubscribe_placeholder() if use_personalized_send else None

        user_dict = {user_key: recipients[0]} if recipients else {}

        # never build_hosted_variant here: this is a personalized per-user
        # send (recommendations/wrapped data), and the hosted newsletter page
        # is public/unauthenticated, must never receive one recipient's
        # personal data (see build_email_html_with_all_cids docstring)
        email_html, _hosted_html_unused = build_email_html_with_all_cids(
            template_data,
            tautulli_data,
            msg_root,
            display_preference,
            users_full_data,
            recommendations_data,
            user_dict,
            base_url,
            target_user_key=user_key,
            is_scheduled=False,
            items_count=None,
            date_range="",
            expanded_collections=expanded_collections,
            email_header_title=email_header_title,
            droppedneedle_wrapped_data=droppedneedle_wrapped_data,
            droppedneedle_server_data=droppedneedle_server_data,
            yearly_wrapped_data=yearly_wrapped_data,
            sonarr_coming_soon_data=sonarr_coming_soon_data,
            radarr_coming_soon_data=radarr_coming_soon_data,
            unsubscribe_placeholder=unsub_placeholder,
            hosted_base_url=hosted_base_url,
            hosted_images_enabled=hosted_images_enabled
        )

        plain_text = convert_html_to_plain_text(email_html)
        if not use_personalized_send:
            msg_alternative.attach(MIMEText(plain_text, 'plain', 'utf-8'))
            msg_alternative.attach(MIMEText(email_html, 'html', 'utf-8'))

        logger.info(f"Attempting SMTP connection...")

        if smtp_protocol == 'SSL':
            logger.info(f"Using SMTP_SSL on port {smtp_port}")
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, password)
        else:
            logger.info(f"Using SMTP with STARTTLS on port {smtp_port}")
            server = smtplib.SMTP(smtp_server, smtp_port)
            logger.info("Starting TLS...")
            server.starttls()
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, password)

        logger.info("SMTP connection established successfully")

        logger.info("Sending email...")

        from_addr = alias_email if alias_email else from_email
        if use_personalized_send:
            all_recipients = recipients if send_mode == 'to' else [from_addr] + recipients
            email_content = send_personalized_per_recipient(
                server, msg_root, from_addr, all_recipients, email_html, plain_text,
                unsub_placeholder, hosted_base_url, send_mode
            )
        elif send_mode == 'to':
            email_content = msg_root.as_string()
            for recipient in recipients:
                msg_root.replace_header('To', recipient)
                server.sendmail(from_addr, [recipient], msg_root.as_string())
            all_recipients = recipients
        else:
            email_content = msg_root.as_string()
            server.sendmail(from_addr, [from_addr] + recipients, email_content)
            all_recipients = [from_addr] + recipients

        content_size_kb = len((email_content or "").encode('utf-8')) / 1024
        content_size_mb = content_size_kb / 1024
        logger.info(f"Email size: {content_size_mb:.2f} MB")
        if content_size_mb > 25:
            logger.warning("WARNING: Email exceeds typical size limits")

        server.quit()
        logger.info(f"Email sent successfully!")

        record_email_history(subject, ', '.join(all_recipients), email_content,
                             round(content_size_kb, 2), len(all_recipients), 'Manual')

        return True
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP Connection Error: {e}")
        logger.warning("This often indicates wrong port/protocol combination")
        record_email_history(req.subject, ', '.join(recipients), '', 0, len(recipients), 'Manual', status='failed', error=f"SMTP connection error: {e}")
        return False
    except smtplib.SMTPServerDisconnected as e:
        logger.warning(f"SMTP Server Disconnected: {e}")
        logger.warning("Server closed connection - likely protocol mismatch")
        record_email_history(req.subject, ', '.join(recipients), '', 0, len(recipients), 'Manual', status='failed', error=f"SMTP server disconnected: {e}")
        return False
    except Exception as e:
        logger.error(f"Error sending single user email: {e}")
        record_email_history(req.subject, ', '.join(recipients), '', 0, len(recipients), 'Manual', status='failed', error=str(e))
        return False

def resend_email_from_history(email_id, settings):
    conn = db_connect()
    row = conn.execute(
        "SELECT subject, recipients, email_content, status, template_name FROM email_history WHERE id = ?",
        (email_id,)
    ).fetchone()
    conn.close()

    if not row:
        return False, "History entry not found"

    subject, recipients_str, email_content, status, template_name = row
    if status == 'failed':
        return False, "Cannot resend a failed send (no content was captured)"
    if not email_content:
        return False, "No stored content for this send (sent before resend support was added)"

    recipients = [r.strip() for r in (recipients_str or "").split(',') if r.strip()]
    if not recipients:
        return False, "No recipients stored for this send"

    from_email = settings.get("from_email") or ""
    alias_email = settings.get("alias_email") or ""
    password = settings.get("password") or ""
    smtp_username = settings.get("smtp_username") or ""
    smtp_server = settings.get("smtp_server") or ""
    smtp_port = int(settings.get("smtp_port") or 587)
    smtp_protocol = settings.get("smtp_protocol") or "TLS"
    from_addr = alias_email if alias_email else from_email

    try:
        if smtp_protocol == 'SSL':
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
        login_username = smtp_username if smtp_username else from_email
        server.login(login_username, password)

        server.sendmail(from_addr, recipients, email_content)
        server.quit()

        content_size_kb = len(email_content.encode('utf-8')) / 1024
        record_email_history(subject, ', '.join(recipients), email_content,
                             round(content_size_kb, 2), len(recipients), template_name or 'Manual')
        logger.info(f"Resent history entry {email_id} to {len(recipients)} recipients")
        return True, f"Resent to {len(recipients)} recipient{'s' if len(recipients) != 1 else ''}"
    except Exception as e:
        logger.error(f"Error resending history entry {email_id}: {e}")
        record_email_history(subject, ', '.join(recipients), '', 0, len(recipients), template_name or 'Manual', status='failed', error=str(e))
        return False, str(e)
