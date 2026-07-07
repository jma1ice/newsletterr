import json, os, smtplib, sqlite3

from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from flask import jsonify

from app import config
from app.settings_store import get_settings
from app.crypto import decrypt
from app.clients.tautulli import run_tautulli_command
from app.emails.assemble import convert_html_to_plain_text, build_email_html_with_all_cids
from app.emails.fetchers import get_current_tautulli_data_for_email, get_recommendations_for_users, get_droppedneedle_wrapped_for_users, get_droppedneedle_server_stats_cached

def group_recipients_by_user(to_emails_list, user_dict):
    email_to_user = { (v or '').strip().lower(): k for k, v in (user_dict or {}).items() if v }
    groups = defaultdict(list)
    for email in (to_emails_list or []):
        key = email_to_user.get((email or '').strip().lower())
        groups[key].append(email)
    return groups

def send_standard_email_with_cids(to_emails, subject, email_header_title, selected_items, from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, settings, from_name, custom_html, expanded_collections=None, send_mode='bcc'):
    try:
        print(f"SMTP Config: {smtp_server}:{smtp_port} using {smtp_protocol}")

        if smtp_port == 465 and smtp_protocol == 'TLS':
            print("WARNING: Port 465 with TLS protocol detected!")
            print("Port 465 requires SSL protocol. Consider changing to:")
            print("- Port 587 with TLS, OR")
            print("- Port 465 with SSL")
        
        if smtp_port == 587 and smtp_protocol == 'SSL':
            print("WARNING: Port 587 with SSL protocol detected!")
            print("Port 587 typically uses TLS (STARTTLS)")

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

        print("Building email content...")
        tautulli_data = get_current_tautulli_data_for_email(settings)
        droppedneedle_server_data = get_droppedneedle_server_stats_cached(use_cache=True)

        template_data = {
            'selected_items': json.dumps(selected_items),
            'email_text': '',
            'subject': subject,
            'custom_html': custom_html
        }

        base_url = os.environ.get("PUBLIC_BASE_URL", "http://127.0.0.1:6397")

        email_html = build_email_html_with_all_cids(
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
            droppedneedle_server_data=droppedneedle_server_data
        )

        plain_text = convert_html_to_plain_text(email_html)
        msg_alternative.attach(MIMEText(plain_text, 'plain', 'utf-8'))
        msg_alternative.attach(MIMEText(email_html, 'html', 'utf-8'))

        print(f"Attempting SMTP connection...")

        if smtp_protocol == 'SSL':
            print(f"Using SMTP_SSL on port {smtp_port}")
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, decrypt(password))
        else:
            print(f"Using SMTP with STARTTLS on port {smtp_port}")
            server = smtplib.SMTP(smtp_server, smtp_port)
            print("Starting TLS...")
            server.starttls()
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, decrypt(password))

        print("SMTP connection established successfully")
            
        email_content = msg_root.as_string()

        content_size_kb = len(email_content.encode('utf-8')) / 1024
        content_size_mb = len(email_content.encode('utf-8')) / (1024 * 1024)
        print(f"Email size: {content_size_mb:.2f} MB")
        if content_size_mb > 25:
            print("WARNING: Email exceeds typical size limits")

        print("Sending email...")

        from_addr = alias_email if alias_email else from_email
        if send_mode == 'to':
            for recipient in to_emails:
                msg_root.replace_header('To', recipient)
                server.sendmail(from_addr, [recipient], msg_root.as_string())
            all_recipients = to_emails
        else:
            server.sendmail(from_addr, [from_addr] + to_emails, email_content)
            all_recipients = [from_addr] + to_emails

        print(f"Email sent successfully!")

        try:
            history_conn = sqlite3.connect(config.DB_PATH)
            history_cursor = history_conn.cursor()
            history_cursor.execute("""
                INSERT INTO email_history (subject, recipients, email_content, content_size_kb, recipient_count, template_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                subject,
                ', '.join(all_recipients),
                email_content[:1000],
                round(content_size_kb, 2),
                len(all_recipients),
                'Manual'
            ))
            history_conn.commit()
            history_conn.close()
        except Exception as history_error:
            print(f"Error saving email history: {history_error}")

        server.quit()
        return jsonify({"success": True, "sent_to": ', '.join(all_recipients), "size": content_size_kb})
    except smtplib.SMTPConnectError as e:
        print(f"SMTP Connection Error: {e}")
        print("This often indicates wrong port/protocol combination")
        return False
    except smtplib.SMTPServerDisconnected as e:
        print(f"SMTP Server Disconnected: {e}")
        print("Server closed connection - likely protocol mismatch")
        return False
    except Exception as e:
        print("SMTP send error:", e)
        return jsonify({"error": str(e)}), 500

def send_recommendations_email_with_cids(to_emails, subject, email_header_title, user_dict, selected_items, from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, settings, from_name, custom_html, expanded_collections=None, send_mode='bcc'):
    try:
        rec_user_keys = set()
        wrapped_user_keys = set()
        for item in selected_items:
            if item.get('type') == 'recommendations' and item.get('userKey'):
                rec_user_keys.add(item['userKey'])
            elif item.get('type') == 'droppedneedle_wrapped' and item.get('userKey'):
                wrapped_user_keys.add(item['userKey'])

        personalized_user_keys = rec_user_keys | wrapped_user_keys

        if not personalized_user_keys:
            return send_standard_email_with_cids(
                to_emails, subject, email_header_title, selected_items, from_email, alias_email,
                reply_to_email, password, smtp_username, smtp_server, smtp_port,
                smtp_protocol, settings, from_name, custom_html, expanded_collections, send_mode=send_mode
            )

        recommendations_data = get_recommendations_for_users(rec_user_keys, to_emails, user_dict, use_cache=True) if rec_user_keys else {}
        droppedneedle_wrapped_data = get_droppedneedle_wrapped_for_users(wrapped_user_keys, to_emails, user_dict, use_cache=True) if wrapped_user_keys else {}
        droppedneedle_server_data = get_droppedneedle_server_stats_cached(use_cache=True)

        if rec_user_keys and not recommendations_data:
            return jsonify({"error": "No recommendations data available. Please pull recommendations first."}), 400
        if wrapped_user_keys and not droppedneedle_wrapped_data:
            return jsonify({"error": "No DroppedNeedle wrapped data available. Please pull DroppedNeedle stats first."}), 400

        groups = group_recipients_by_user(to_emails, user_dict)

        total_sent = 0
        sent_info = []

        for user_key, recipients in groups.items():
            if user_key is None or user_key not in personalized_user_keys:
                print("Skipping recipients without recommendations or wrapped stats:", recipients)
                continue

            success = send_single_user_email_with_cids(
                recipients, subject, email_header_title, selected_items, user_key, recommendations_data,
                from_email, alias_email, reply_to_email, password, smtp_username,
                smtp_server, smtp_port, smtp_protocol, settings, from_name, custom_html, expanded_collections,
                send_mode=send_mode, droppedneedle_wrapped_data=droppedneedle_wrapped_data, droppedneedle_server_data=droppedneedle_server_data
            )

            if success:
                total_sent += len(recipients)
                sent_info.append(', '.join(recipients))

        if total_sent == 0:
            return jsonify({"error": "No recipients matched a recommendations or wrapped stats block. No emails sent."}), 400

        return jsonify({"success": True, "sent_groups": sent_info})

    except Exception as e:
        print("Error in send_recommendations_email_with_cids:", e)
        return jsonify({"error": str(e)}), 500

def send_single_user_email_with_cids(recipients, subject, email_header_title, selected_items, user_key, recommendations_data, from_email, alias_email, reply_to_email, password, smtp_username, smtp_server, smtp_port, smtp_protocol, settings, from_name, custom_html, expanded_collections=None, send_mode='bcc', droppedneedle_wrapped_data=None, droppedneedle_server_data=None):
    try:
        print(f"SMTP Config: {smtp_server}:{smtp_port} using {smtp_protocol}")

        if smtp_port == 465 and smtp_protocol == 'TLS':
            print("WARNING: Port 465 with TLS protocol detected!")
            print("Port 465 requires SSL protocol. Consider changing to:")
            print("- Port 587 with TLS, OR")
            print("- Port 465 with SSL")
        
        if smtp_port == 587 and smtp_protocol == 'SSL':
            print("WARNING: Port 587 with SSL protocol detected!")
            print("Port 587 typically uses TLS (STARTTLS)")

        _s = get_settings(decrypt_secrets=False)
        settings_row = (_s.get("recipient_display_name"), _s.get("tautulli_url"), _s.get("tautulli_api")) if "id" in _s else None
        
        display_preference = settings_row[0] if settings_row and settings_row[0] else 'email'
        tautulli_url = settings_row[1] if settings_row else None
        tautulli_api = settings_row[2] if settings_row else None
        
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

        print("Building email content...")
        tautulli_data = get_current_tautulli_data_for_email(settings)
        
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
            droppedneedle_server_data=droppedneedle_server_data
        )

        plain_text = convert_html_to_plain_text(email_html)
        msg_alternative.attach(MIMEText(plain_text, 'plain', 'utf-8'))
        msg_alternative.attach(MIMEText(email_html, 'html', 'utf-8'))

        print(f"Attempting SMTP connection...")

        if smtp_protocol == 'SSL':
            print(f"Using SMTP_SSL on port {smtp_port}")
            server = smtplib.SMTP_SSL(smtp_server, smtp_port)
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, decrypt(password))
        else:
            print(f"Using SMTP with STARTTLS on port {smtp_port}")
            server = smtplib.SMTP(smtp_server, smtp_port)
            print("Starting TLS...")
            server.starttls()
            login_username = smtp_username if smtp_username else from_email
            server.login(login_username, decrypt(password))

        print("SMTP connection established successfully")
            
        email_content = msg_root.as_string()

        content_size_kb = len(email_content.encode('utf-8')) / 1024
        content_size_mb = len(email_content.encode('utf-8')) / (1024 * 1024)
        print(f"Email size: {content_size_mb:.2f} MB")
        if content_size_mb > 25:
            print("WARNING: Email exceeds typical size limits")
        
        print("Sending email...")

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
        print(f"Email sent successfully!")

        try:
            history_conn = sqlite3.connect(config.DB_PATH)
            history_cursor = history_conn.cursor()
            history_cursor.execute("""
                INSERT INTO email_history (subject, recipients, email_content, content_size_kb, recipient_count, template_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                subject,
                ', '.join(all_recipients),
                email_content[:1000],
                round(content_size_kb, 2),
                len(all_recipients),
                'Manual'
            ))
            history_conn.commit()
            history_conn.close()
        except Exception as history_error:
            print(f"Error saving email history: {history_error}")
        
        return True
    except smtplib.SMTPConnectError as e:
        print(f"SMTP Connection Error: {e}")
        print("This often indicates wrong port/protocol combination")
        return False
    except smtplib.SMTPServerDisconnected as e:
        print(f"SMTP Server Disconnected: {e}")
        print("Server closed connection - likely protocol mismatch")
        return False
    except Exception as e:
        print(f"Error sending single user email: {e}")
        return False
