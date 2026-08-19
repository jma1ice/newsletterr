# Media-server abstraction (NEWS-24): the operations the app actually uses,
# dispatched on the media_server_type setting ('plex' default, 'jellyfin',
# and 'none').
# The design rule: the Jellyfin side normalizes everything to the shapes the
# Plex path already produces, so builders, layouts, previews, and goldens
# never branch on server type; only pull-time code calls through here.
#
# 'none' is standalone mode: newsletterr as a plain mailing-list tool with no
# media server attached. Every dispatcher below has to name it explicitly,
# because the v2026.4.4 shape of these checks was "jellyfin or else Plex",
# which would send a standalone install straight into Plex code paths and out
# to a server that was never configured.
from app.settings_store import get_settings
from app.clients.plex import get_plex_machine_id, build_plex_web_link, fetch_recently_added_using_plex_sdk
from app.clients.jellyfin import (
    get_jellyfin_server_id,
    build_jellyfin_web_link,
    fetch_jellyfin_libraries,
    fetch_recently_added_using_jellyfin,
)

import logging

logger = logging.getLogger(__name__)

MEDIA_SERVER_TYPES = ('plex', 'jellyfin', 'emby', 'none')

JELLYFIN_LIKE = ('jellyfin', 'emby')

def is_jellyfin_like(settings=None):
    return get_media_server_type(settings) in JELLYFIN_LIKE

def media_user_scope(settings=None):
    server_type = get_media_server_type(settings)
    return server_type if server_type in JELLYFIN_LIKE else 'jellyfin'

def get_media_server_type(settings=None):
    s = settings or get_settings(decrypt_secrets=False)
    server_type = (s.get('media_server_type') or 'plex').strip().lower()
    return server_type if server_type in MEDIA_SERVER_TYPES else 'plex'

def is_standalone(settings=None):
    return get_media_server_type(settings) == 'none'

def get_server_identity(settings=None):
    """The stable id deep links are scoped to: the Plex machine identifier or
    the Jellyfin server Id. None when the active server is unreachable, and
    None in standalone mode, where there is nothing to identify."""
    server_type = get_media_server_type(settings)
    if server_type == 'none':
        return None
    if server_type in JELLYFIN_LIKE:
        return get_jellyfin_server_id()
    return get_plex_machine_id()

def build_media_web_link(item_key, identity, settings=None):
    """Deep link for an item on the active media server. `item_key` is a Plex
    rating key or a Jellyfin item id; `identity` comes from
    get_server_identity() so per-item calls stay network-free. Standalone mode
    has no server to link into, so it yields no link rather than a broken one."""
    s = settings or get_settings(decrypt_secrets=False)
    server_type = get_media_server_type(s)
    if server_type == 'none':
        return ''
    if server_type in JELLYFIN_LIKE:
        return build_jellyfin_web_link(item_key, identity, s.get('jellyfin_web_url'), s.get('jellyfin_url'), server_type)
    return build_plex_web_link(item_key, identity, s.get('plex_web_url'))

def artwork_proxy_prefix(settings=None):
    """Route prefix item thumb paths are served through; the Jellyfin proxy
    injects the auth header so no token ever reaches email HTML."""
    return '/proxy-jf-art' if is_jellyfin_like(settings) else '/proxy-art'

def fetch_recently_added(tautulli_base_url, tautulli_api_key, items_count=10, recently_added_mode="items", recently_added_sort="date", settings=None):
    """Recently added in the recent_data shape, from whichever media server
    is active. The Plex path rides Tautulli for library names (unchanged);
    the Jellyfin path needs no Tautulli at all; standalone has no source."""
    server_type = get_media_server_type(settings)
    if server_type == 'none':
        return []
    if server_type in JELLYFIN_LIKE:
        return fetch_recently_added_using_jellyfin(items_count, recently_added_mode, recently_added_sort)
    return fetch_recently_added_using_plex_sdk(tautulli_base_url, tautulli_api_key, int(items_count), recently_added_mode=recently_added_mode, recently_added_sort=recently_added_sort)

def fetch_media_libraries(settings=None):
    """Library list in the Tautulli get_library_names shape regardless of
    server type. The Plex path keeps its existing Tautulli-backed callers;
    this is the chokepoint pull code switches through."""
    server_type = get_media_server_type(settings)
    if server_type == 'none':
        return []
    if server_type in JELLYFIN_LIKE:
        return fetch_jellyfin_libraries()
    # Plex libraries flow through Tautulli (run_tautulli_command
    # 'get_library_names') at the call sites that own the Tautulli
    # credentials; nothing to dispatch here yet.
    return []
