"""NEWS-69: Emby as a media server type."""
import sqlite3
from unittest.mock import patch

import pytest

from app import config
from app.clients.jellyfin import build_jellyfin_web_link
from app.clients.mediaserver import (
    MEDIA_SERVER_TYPES,
    artwork_proxy_prefix,
    build_media_web_link,
    get_media_server_type,
    is_jellyfin_like,
)

EMBY = {'media_server_type': 'emby'}


# --- the type itself

def test_emby_is_a_recognized_type():
    assert 'emby' in MEDIA_SERVER_TYPES
    assert get_media_server_type(EMBY) == 'emby'
    assert is_jellyfin_like(EMBY) is True
    assert is_jellyfin_like({'media_server_type': 'jellyfin'}) is True
    assert is_jellyfin_like({'media_server_type': 'plex'}) is False
    assert is_jellyfin_like({'media_server_type': 'none'}) is False


def test_emby_uses_the_jellyfin_artwork_proxy():
    """Same image endpoints, so the same proxy that injects the auth header."""
    assert artwork_proxy_prefix(EMBY) == '/proxy-jf-art'


# --- the one real API difference

def test_emby_deep_links_use_its_own_web_route():
    """Jellyfin routes an item to #!/details, Emby to #!/item. This is the only
    endpoint difference between them that this app touches."""
    jellyfin = build_jellyfin_web_link('abc', 'srv', '', 'http://host:8096', 'jellyfin')
    emby = build_jellyfin_web_link('abc', 'srv', '', 'http://host:8096', 'emby')
    assert jellyfin.endswith('#!/details?id=abc&serverId=srv')
    assert emby.endswith('#!/item?id=abc&serverId=srv')


def test_an_unknown_flavor_falls_back_to_the_jellyfin_route():
    assert '#!/details' in build_jellyfin_web_link('abc', None, '', 'http://h', 'nonsense')


def test_the_media_link_dispatcher_passes_the_flavor_through():
    link = build_media_web_link('abc', 'srv', {
        'media_server_type': 'emby', 'jellyfin_url': 'http://host:8096', 'jellyfin_web_url': ''})
    assert '#!/item?id=abc' in link


# --- dispatch sites treat emby like jellyfin

def test_email_chrome_offers_the_server_link_on_emby(app, monkeypatch):
    import app.theme as theme_mod

    monkeypatch.setattr(theme_mod, 'get_settings', lambda **kw: {
        'media_server_type': 'emby', 'jellyfin_web_url': 'https://emby.example.com'})
    chrome = theme_mod.get_email_chrome_settings()
    assert chrome['server_url'] == 'https://emby.example.com'


def test_the_email_pull_takes_the_jellyfin_path_on_emby(monkeypatch):
    import app.emails.fetchers as fetchers

    monkeypatch.setattr(fetchers, 'get_media_server_type', lambda *a, **k: 'emby')
    monkeypatch.setattr(fetchers, 'run_tautulli_command',
                        lambda *a, **k: pytest.fail("Emby must not call Tautulli"))
    monkeypatch.setattr(fetchers, 'fetch_jellywatch_home_stats', lambda **k: [])
    monkeypatch.setattr(fetchers, 'fetch_jellyfin_library_counts', lambda: [])
    monkeypatch.setattr(fetchers, 'fetch_recently_added', lambda *a, **k: [])

    data = fetchers.fetch_tautulli_data_for_email('http://t', 'key', 30, 'Server')
    assert data['graph_data'] == []


def test_the_inactivity_filter_takes_the_jellyfin_path_on_emby():
    from app.emails import send as send_mod

    users = [{'user_id': 'u1', 'email': 'a@b.co', 'last_seen': ''}]
    with patch.object(send_mod, 'get_media_server_type', return_value='emby'), \
         patch('app.clients.jellyfin.fetch_jellyfin_users', return_value=users):
        kept, excluded = send_mod.filter_inactive(
            ['a@b.co'], {'media_server_type': 'emby', 'exclude_inactive_days': 30})
    assert excluded == ['a@b.co']


def test_playback_reporting_is_offered_on_emby(app):
    """The plugin is Emby-origin, so the graphs work covers it too."""
    from app.crypto import encrypt
    from app.clients import playback_reporting as pr

    conn = sqlite3.connect(config.DB_PATH)
    prev = conn.execute("SELECT media_server_type FROM settings WHERE id = 1").fetchone()[0]
    conn.execute("UPDATE settings SET media_server_type = 'emby', jellyfin_url = ?, "
                 "jellyfin_api_key = ?, playback_reporting_enabled = 'enabled' WHERE id = 1",
                 ("http://localhost:8096", encrypt("k")))
    conn.commit()
    conn.close()
    try:
        url, key = pr._connection()
        assert url == "http://localhost:8096"
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("UPDATE settings SET media_server_type = ?, playback_reporting_enabled = 'disabled' WHERE id = 1", (prev,))
        conn.commit()
        conn.close()


# --- the user-email mapping is per server

def test_the_mapping_scope_falls_back_rather_than_following_plex():
    """The mapping can be read or written while Plex is active but Jellyfin is
    still configured; keying that under 'plex' would save to a row nothing ever
    reads back."""
    from app.clients.mediaserver import media_user_scope

    assert media_user_scope({'media_server_type': 'jellyfin'}) == 'jellyfin'
    assert media_user_scope({'media_server_type': 'emby'}) == 'emby'
    assert media_user_scope({'media_server_type': 'plex'}) == 'jellyfin'
    assert media_user_scope({'media_server_type': 'none'}) == 'jellyfin'


def test_the_mapping_is_keyed_per_server_so_ids_cannot_collide(app):
    """Jellyfin and Emby user ids are unrelated. The same id on both must not
    resolve to the same person."""
    from app.store import get_media_user_emails, set_media_user_email

    try:
        set_media_user_email('shared-id', 'jf@example.com', 'jellyfin')
        set_media_user_email('shared-id', 'emby@example.com', 'emby')
        assert get_media_user_emails('jellyfin') == {'shared-id': 'jf@example.com'}
        assert get_media_user_emails('emby') == {'shared-id': 'emby@example.com'}
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM media_user_emails WHERE user_id = 'shared-id'")
        conn.commit()
        conn.close()


# --- the enumeration, which is the known way this breaks

def test_no_dispatch_still_reads_jellyfin_or_else_plex():
    """NEWS-48 established the failure mode: a branch comparing to 'jellyfin'
    alone sends an Emby install down a Plex path. Every such comparison in the
    app has to name Emby too, or ask is_jellyfin_like."""
    import re
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent
    offenders = []
    for path in (repo_root / 'app').rglob('*.py'):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"""==\s*['"]jellyfin['"]|!=\s*['"]jellyfin['"]""", line):
                offenders.append(f"{path.relative_to(repo_root)}:{number}: {line.strip()}")
    assert not offenders, "these compare to 'jellyfin' alone:\n" + "\n".join(offenders)
