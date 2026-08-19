"""linking Jellyfin users to email addresses."""
import sqlite3

import pytest

from app import config
from app.contacts_import import match_contacts_to_users


def _users(*pairs):
    return [{'user_id': uid, 'username': name, 'friendly_name': name, 'is_active': True}
            for uid, name in pairs]


# --- storage

@pytest.fixture(autouse=True)
def clean_mapping(app):
    yield
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("DELETE FROM media_user_emails")
    conn.commit()
    conn.close()


def test_set_and_read_back(app):
    from app.store import get_media_user_emails, set_media_user_email

    assert set_media_user_email('u1', 'Ada@Example.com') is True
    assert get_media_user_emails('jellyfin') == {'u1': 'ada@example.com'}
    # server type scopes the mapping, since ids are only unique within a server
    assert get_media_user_emails('plex') == {}


def test_blank_email_unlinks(app):
    from app.store import get_media_user_emails, set_media_user_email

    set_media_user_email('u1', 'ada@example.com')
    set_media_user_email('u1', '')
    assert get_media_user_emails('jellyfin') == {}


def test_relinking_overwrites_rather_than_duplicating(app):
    from app.store import get_media_user_emails, set_media_user_email

    set_media_user_email('u1', 'old@example.com')
    set_media_user_email('u1', 'new@example.com')
    assert get_media_user_emails('jellyfin') == {'u1': 'new@example.com'}


def test_blank_user_id_is_rejected(app):
    from app.store import set_media_user_email
    assert set_media_user_email('', 'a@b.co') is False
    assert set_media_user_email(None, 'a@b.co') is False


# --- auto-match on import

def test_exact_name_match_links():
    linked = match_contacts_to_users(
        [('ada@example.com', 'Ada'), ('grace@example.com', 'Grace')],
        _users(('u1', 'Ada'), ('u2', 'Grace')))
    assert linked == {'u1': 'ada@example.com', 'u2': 'grace@example.com'}


def test_matching_ignores_case_and_surrounding_space():
    linked = match_contacts_to_users([('ada@example.com', '  ADA  ')], _users(('u1', 'Ada')))
    assert linked == {'u1': 'ada@example.com'}


def test_no_fuzzy_matching():
    """A near miss silently mailing the wrong person is worse than no match."""
    for name in ('Adaa', 'Ad', 'Ada Lovelace', 'Ada.'):
        assert match_contacts_to_users([('x@example.com', name)], _users(('u1', 'Ada'))) == {}


def test_contacts_without_names_never_link():
    assert match_contacts_to_users([('ada@example.com', '')], _users(('u1', 'Ada'))) == {}
    assert match_contacts_to_users([('ada@example.com', '   ')], _users(('u1', 'Ada'))) == {}


def test_an_existing_link_is_never_overwritten():
    """It may be a manual correction, and a re-import must not undo it."""
    linked = match_contacts_to_users(
        [('new@example.com', 'Ada')], _users(('u1', 'Ada')),
        existing={'u1': 'manual@example.com'})
    assert linked == {}


def test_a_name_held_by_two_accounts_is_skipped():
    linked = match_contacts_to_users(
        [('ada@example.com', 'Ada')], _users(('u1', 'Ada'), ('u2', 'ada')))
    assert linked == {}


def test_two_contacts_claiming_one_account_is_skipped():
    linked = match_contacts_to_users(
        [('one@example.com', 'Ada'), ('two@example.com', 'Ada')], _users(('u1', 'Ada')))
    assert linked == {}


def test_unmatched_contacts_are_simply_left_alone():
    linked = match_contacts_to_users(
        [('ada@example.com', 'Ada'), ('nobody@example.com', 'Nobody')],
        _users(('u1', 'Ada')))
    assert linked == {'u1': 'ada@example.com'}


def test_empty_inputs_do_not_raise():
    assert match_contacts_to_users([], []) == {}
    assert match_contacts_to_users(None, None) == {}


# --- routes

def test_map_route_is_empty_off_jellyfin(csrf_client):
    client, _ = csrf_client
    resp = client.get("/media_user_emails")
    assert resp.status_code == 200
    # the default fixture install is Plex, so there is nothing to map
    assert resp.get_json() == {"status": "success", "users": []}


def test_saving_the_map_rejects_a_bad_address(csrf_client):
    client, token = csrf_client
    resp = client.post("/media_user_emails", json={"mapping": {"u1": "not-an-address"}},
                       headers={"X-CSRF-Token": token})
    assert resp.status_code == 400
    from app.store import get_media_user_emails
    assert get_media_user_emails('jellyfin') == {}   # nothing partially written


def test_saving_the_map_stores_and_unlinks(csrf_client):
    from app.store import get_media_user_emails

    client, token = csrf_client
    resp = client.post("/media_user_emails",
                       json={"mapping": {"u1": "Ada@Example.com", "u2": ""}},
                       headers={"X-CSRF-Token": token})
    assert resp.status_code == 200
    assert resp.get_json()["linked"] == 1
    assert get_media_user_emails('jellyfin') == {'u1': 'ada@example.com'}


def test_saving_a_non_object_mapping_is_rejected(csrf_client):
    client, token = csrf_client
    resp = client.post("/media_user_emails", json={"mapping": ["a@b.co"]},
                       headers={"X-CSRF-Token": token})
    assert resp.status_code == 400


def test_map_routes_require_auth(anon_client):
    assert anon_client.get("/media_user_emails").status_code in (302, 401, 403)
    assert anon_client.post("/media_user_emails", json={"mapping": {}}).status_code in (302, 400, 401, 403)


# --- end to end: the import that saves you typing every address twice

def test_import_auto_links_on_jellyfin(csrf_client, monkeypatch):
    from app.store import get_media_user_emails, save_email_list
    import app.blueprints.emails as emails_mod

    client, token = csrf_client
    conn = sqlite3.connect(config.DB_PATH)
    prev = conn.execute("SELECT media_server_type FROM settings WHERE id = 1").fetchone()[0]
    conn.execute("UPDATE settings SET media_server_type = 'jellyfin' WHERE id = 1")
    conn.commit()
    conn.close()

    monkeypatch.setattr(emails_mod, 'fetch_jellyfin_users',
                        lambda: _users(('u1', 'Ada'), ('u2', 'Grace')))
    try:
        save_email_list('JF Link Test', 'seed@example.com')
        conn = sqlite3.connect(config.DB_PATH)
        list_id = conn.execute("SELECT id FROM email_lists WHERE name = 'JF Link Test'").fetchone()[0]
        conn.close()

        resp = client.post(f"/email_lists/{list_id}/import", headers={"X-CSRF-Token": token},
                           json={"text": "email,name\nada@example.com,Ada\nnobody@example.com,Nobody"})
        body = resp.get_json()
        assert body['added'] == 2
        assert body['linked'] == 1          # Ada matched an account, Nobody did not
        assert get_media_user_emails('jellyfin') == {'u1': 'ada@example.com'}
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM contacts")
        conn.execute("DELETE FROM email_lists WHERE name = 'JF Link Test'")
        conn.execute("UPDATE settings SET media_server_type = ? WHERE id = 1", (prev,))
        conn.commit()
        conn.close()


def test_import_does_not_link_on_plex(csrf_client, monkeypatch):
    """Plex supplies its own addresses, so the auto-link has no business running."""
    from app.store import get_media_user_emails, save_email_list
    import app.blueprints.emails as emails_mod

    client, token = csrf_client
    monkeypatch.setattr(emails_mod, 'fetch_jellyfin_users',
                        lambda: pytest.fail("must not query Jellyfin on Plex"))
    try:
        save_email_list('Plex Link Test', 'seed@example.com')
        conn = sqlite3.connect(config.DB_PATH)
        list_id = conn.execute("SELECT id FROM email_lists WHERE name = 'Plex Link Test'").fetchone()[0]
        conn.close()

        resp = client.post(f"/email_lists/{list_id}/import", headers={"X-CSRF-Token": token},
                           json={"text": "ada@example.com,Ada"})
        assert resp.get_json()['linked'] == 0
        assert get_media_user_emails('jellyfin') == {}
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM contacts")
        conn.execute("DELETE FROM email_lists WHERE name = 'Plex Link Test'")
        conn.commit()
        conn.close()


def test_a_failing_auto_link_never_fails_the_import(csrf_client, monkeypatch):
    """The contacts are already saved by then; losing the link is the lesser
    failure and must not turn a good import into an error."""
    from app.store import save_email_list
    import app.blueprints.emails as emails_mod

    client, token = csrf_client
    conn = sqlite3.connect(config.DB_PATH)
    prev = conn.execute("SELECT media_server_type FROM settings WHERE id = 1").fetchone()[0]
    conn.execute("UPDATE settings SET media_server_type = 'jellyfin' WHERE id = 1")
    conn.commit()
    conn.close()

    def _boom():
        raise RuntimeError("jellyfin down")
    monkeypatch.setattr(emails_mod, 'fetch_jellyfin_users', _boom)
    try:
        save_email_list('JF Fail Test', 'seed@example.com')
        conn = sqlite3.connect(config.DB_PATH)
        list_id = conn.execute("SELECT id FROM email_lists WHERE name = 'JF Fail Test'").fetchone()[0]
        conn.close()

        resp = client.post(f"/email_lists/{list_id}/import", headers={"X-CSRF-Token": token},
                           json={"text": "ada@example.com,Ada"})
        assert resp.status_code == 200
        assert resp.get_json()['added'] == 1
        assert resp.get_json()['linked'] == 0
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM contacts")
        conn.execute("DELETE FROM email_lists WHERE name = 'JF Fail Test'")
        conn.execute("UPDATE settings SET media_server_type = ? WHERE id = 1", (prev,))
        conn.commit()
        conn.close()
