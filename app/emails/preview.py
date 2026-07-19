import json

from email.mime.multipart import MIMEMultipart

from app import config
from app.settings_store import get_settings
from app.cache import get_cached_data
from app.emails.assemble import build_email_html_with_all_cids
from app.emails.fetchers import (
    get_current_tautulli_data_for_email,
    get_droppedneedle_server_stats_cached,
    get_yearly_wrapped_cached,
    get_sonarr_coming_soon_cached,
    get_radarr_coming_soon_cached,
    get_ombi_requests_cached,
    get_seerr_requests_cached,
)

import logging

logger = logging.getLogger(__name__)

def render_preview_email(data):
    """Full email HTML for the given builder state, produced by the exact
    pipeline a manual send uses, but with preview_mode set on msg_root so the
    image helpers return browser URLs and nothing attaches (see
    app/emails/images.py). This is the single renderer behind the index
    preview, the pop-out, and the schedule preview; WYSIWYG holds by
    construction. Returns a plain string; the route wraps it in jsonify."""
    settings = get_settings(decrypt_secrets=False)
    tautulli_data = get_current_tautulli_data_for_email(settings)
    recommendations_data = get_cached_data('recommendations_json', strict=False)
    user_dict = get_cached_data('filtered_users', strict=False)
    users_data = get_cached_data('users', strict=False)
    droppedneedle_wrapped_data = get_cached_data('droppedneedle_wrapped_json', strict=False)
    droppedneedle_server_data = get_droppedneedle_server_stats_cached(use_cache=True)
    yearly_wrapped_data = get_yearly_wrapped_cached(use_cache=True)
    days_ahead = settings.get("coming_soon_days_ahead") or 14
    sonarr_coming_soon_data = get_sonarr_coming_soon_cached(use_cache=True, days_ahead=days_ahead)
    radarr_coming_soon_data = get_radarr_coming_soon_cached(use_cache=True, days_ahead=days_ahead)
    ombi_requests_data = get_ombi_requests_cached(use_cache=True)
    seerr_requests_data = get_seerr_requests_cached(use_cache=True)

    msg_root = MIMEMultipart('related')
    msg_root.preview_mode = True

    template_data = {
        'selected_items': json.dumps(data.get('selected_items') or []),
        'email_text': data.get('email_text', ''),
        'subject': data.get('subject', ''),
        'custom_html': data.get('custom_html', ''),
    }

    hosted_enabled = settings.get("hosted_enabled") == "enabled"
    hosted_base_url = (settings.get("hosted_base_url") or "").rstrip('/')
    hosted_links_enabled = settings.get("hosted_links_enabled") == "enabled"
    hosted_links_base_url = (settings.get("hosted_links_base_url") or "").rstrip('/')
    links_base_url = hosted_links_base_url if (hosted_links_enabled and hosted_links_base_url) else hosted_base_url
    # sends replace the placeholder per recipient; preview just needs the link
    unsub_placeholder = "preview" if (hosted_enabled and hosted_base_url) else None

    try:
        items_count = int(data.get('items_count')) if data.get('items_count') else None
    except (TypeError, ValueError):
        items_count = None

    email_html, _hosted_unused = build_email_html_with_all_cids(
        template_data,
        tautulli_data,
        msg_root,
        settings.get('recipient_display_name') or 'email',
        users_data,
        recommendations_data,
        user_dict,
        config.INTERNAL_BASE_URL,
        None,
        False,
        items_count,
        "",
        data.get('expanded_collections') or {},
        data.get('email_header_title') or '',
        droppedneedle_wrapped_data=droppedneedle_wrapped_data,
        droppedneedle_server_data=droppedneedle_server_data,
        yearly_wrapped_data=yearly_wrapped_data,
        sonarr_coming_soon_data=sonarr_coming_soon_data,
        radarr_coming_soon_data=radarr_coming_soon_data,
        ombi_requests_data=ombi_requests_data,
        seerr_requests_data=seerr_requests_data,
        unsubscribe_placeholder=unsub_placeholder,
        hosted_base_url=hosted_base_url,
        hosted_images_enabled=False,
        hosted_enabled=hosted_enabled,
        links_base_url=links_base_url,
    )
    return email_html
