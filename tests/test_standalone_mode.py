"""standalone mode, the contacts table, and list import/export."""
import sqlite3

import pytest

from app import config
from app.contacts_import import contacts_to_csv, is_email, normalize_email, parse_contacts


# --- the 'none' value never falls through to Plex

def test_media_server_type_accepts_none():
    from app.clients.mediaserver import get_media_server_type, is_standalone

    assert get_media_server_type({'media_server_type': 'none'}) == 'none'
    assert is_standalone({'media_server_type': 'none'}) is True
    # anything unrecognized still means Plex, unchanged
    assert get_media_server_type({'media_server_type': 'nonsense'}) == 'plex'
    assert get_media_server_type({}) == 'plex'
    assert is_standalone({}) is False


def test_dispatchers_short_circuit_instead_of_calling_plex(monkeypatch):
    from app.clients import mediaserver

    def _boom(*a, **k):
        raise AssertionError("standalone mode must not reach a media server")

    monkeypatch.setattr(mediaserver, 'get_plex_machine_id', _boom)
    monkeypatch.setattr(mediaserver, 'build_plex_web_link', _boom)
    monkeypatch.setattr(mediaserver, 'fetch_recently_added_using_plex_sdk', _boom)
    monkeypatch.setattr(mediaserver, 'get_jellyfin_server_id', _boom)
    monkeypatch.setattr(mediaserver, 'fetch_recently_added_using_jellyfin', _boom)
    monkeypatch.setattr(mediaserver, 'fetch_jellyfin_libraries', _boom)

    none = {'media_server_type': 'none'}
    assert mediaserver.get_server_identity(none) is None
    assert mediaserver.build_media_web_link('123', None, none) == ''
    assert mediaserver.fetch_recently_added('', '', settings=none) == []
    assert mediaserver.fetch_media_libraries(none) == []


def test_service_flags_report_nothing_configured_in_standalone():
    """The single chokepoint that makes the builder degrade."""
    from app.settings_store import get_service_flags

    configured = {
        'tautulli_url': 'http://t', 'tautulli_api': 'k',
        'conjurr_url': 'http://c', 'ombi_url': 'http://o', 'ombi_api_key': 'k',
        'seerr_url': 'http://s', 'seerr_api_key': 'k',
    }
    assert get_service_flags(configured)['tautulli'] is True

    standalone = {**configured, 'media_server_type': 'none'}
    flags = get_service_flags(standalone)
    assert flags['standalone'] is True
    assert not any(flags[k] for k in flags if k != 'standalone')


def test_email_chrome_drops_the_server_link_in_standalone(app, monkeypatch):
    import app.theme as theme_mod

    monkeypatch.setattr(theme_mod, 'get_settings', lambda **kw: {
        'media_server_type': 'none', 'plex_web_url': 'https://app.plex.tv/desktop'})
    assert theme_mod.get_email_chrome_settings()['server_url'] == ''


def test_tautulli_bundle_is_empty_and_makes_no_calls(monkeypatch):
    import app.emails.fetchers as fetchers

    monkeypatch.setattr(fetchers, 'get_media_server_type', lambda *a, **k: 'none')
    monkeypatch.setattr(fetchers, 'run_tautulli_command', lambda *a, **k: pytest.fail("called Tautulli"))

    data = fetchers.fetch_tautulli_data_for_email('http://t', 'key', 30, 'Server')
    assert data['recent_data'] == [] and data['stats'] == [] and data['graph_data'] == []


# --- import parsing

def test_header_row_is_optional():
    with_header = parse_contacts("email,name\nada@example.com,Ada")
    assert with_header['contacts'] == [('ada@example.com', 'Ada')]

    # a row holding a real address is data, never a header
    without = parse_contacts("ada@example.com,Ada")
    assert without['contacts'] == [('ada@example.com', 'Ada')]


def test_one_address_per_line_is_enough():
    result = parse_contacts("ada@example.com\ngrace@example.com\n")
    assert result['contacts'] == [('ada@example.com', ''), ('grace@example.com', '')]


def test_tabs_semicolons_and_quotes_all_parse():
    result = parse_contacts('email\tname\nada@example.com\t"Lovelace, Ada"')
    assert result['contacts'] == [('ada@example.com', 'Lovelace, Ada')]
    assert parse_contacts("email;name\nada@example.com;Ada")['contacts'] == [('ada@example.com', 'Ada')]


def test_mail_client_angle_form_keeps_the_name():
    result = parse_contacts("Ada Lovelace <ada@example.com>")
    assert result['contacts'] == [('ada@example.com', 'Ada Lovelace')]


def test_addresses_are_lowercased_and_column_order_does_not_matter():
    result = parse_contacts("Ada,ADA@Example.COM")
    assert result['contacts'] == [('ada@example.com', 'Ada')]


def test_every_rejected_row_is_reported_not_dropped():
    result = parse_contacts("ada@example.com\nnot an address\n\nbroken@\n")
    assert result['contacts'] == [('ada@example.com', '')]
    assert [line for line, _ in result['invalid']] == [2, 3]
    assert 'not an address' in result['invalid'][0][1]


def test_duplicates_within_the_file_and_against_the_list():
    result = parse_contacts(
        "ada@example.com\nada@example.com\ngrace@example.com",
        existing=['GRACE@example.com'])
    assert result['contacts'] == [('ada@example.com', '')]
    assert sorted(result['duplicate']) == ['ada@example.com', 'grace@example.com']


def test_unsubscribed_addresses_never_come_back_through_import():
    result = parse_contacts("ada@example.com\ngone@example.com",
                            suppressed=['gone@example.com'])
    assert result['contacts'] == [('ada@example.com', '')]
    assert result['suppressed'] == ['gone@example.com']


def test_email_rule_matches_the_chip_input():
    assert is_email('a@b.co') and is_email(normalize_email('  A@B.CO '))
    for bad in ('a@b', 'a b@c.com', '@b.com', 'a@.com ', ''):
        assert not is_email(normalize_email(bad))


def test_export_round_trips_through_the_parser():
    csv_text = contacts_to_csv([
        {'email': 'ada@example.com', 'name': 'Ada'},
        {'email': 'grace@example.com', 'name': ''},
    ])
    assert parse_contacts(csv_text)['contacts'] == [
        ('ada@example.com', 'Ada'), ('grace@example.com', '')]


def test_empty_input_is_not_an_error():
    for empty in ('', '   ', '\n\n'):
        result = parse_contacts(empty)
        assert result == {'contacts': [], 'duplicate': [], 'suppressed': [], 'invalid': []}


# --- contacts storage

@pytest.fixture()
def a_list(app):
    from app.store import save_email_list
    save_email_list('Import Test', 'seed@example.com')
    conn = sqlite3.connect(config.DB_PATH)
    list_id = conn.execute("SELECT id FROM email_lists WHERE name = 'Import Test'").fetchone()[0]
    conn.close()
    yield list_id
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("DELETE FROM contacts WHERE list_id = ?", (list_id,))
    conn.execute("DELETE FROM email_lists WHERE id = ?", (list_id,))
    conn.commit()
    conn.close()


def test_contacts_keep_the_list_column_in_sync(a_list):
    """email_lists.emails stays the address of record for sends, so it is
    rewritten from the contact rows on every change."""
    from app.store import add_contacts, get_contacts, delete_contact

    added = add_contacts(a_list, [('ada@example.com', 'Ada'), ('grace@example.com', 'Grace')])
    assert added == 2

    conn = sqlite3.connect(config.DB_PATH)
    emails = conn.execute("SELECT emails FROM email_lists WHERE id = ?", (a_list,)).fetchone()[0]
    conn.close()
    assert emails == 'ada@example.com, grace@example.com'

    contacts = get_contacts(a_list)
    assert [c['name'] for c in contacts] == ['Ada', 'Grace']

    assert delete_contact(contacts[0]['id']) is True
    conn = sqlite3.connect(config.DB_PATH)
    emails = conn.execute("SELECT emails FROM email_lists WHERE id = ?", (a_list,)).fetchone()[0]
    conn.close()
    assert emails == 'grace@example.com'


def test_re_adding_an_existing_contact_is_not_an_error(a_list):
    from app.store import add_contacts, get_contacts

    add_contacts(a_list, [('ada@example.com', 'Ada')])
    assert add_contacts(a_list, [('ada@example.com', 'Ada')]) == 0
    assert len(get_contacts(a_list)) == 1


# --- routes

def test_import_route_reports_every_category(csrf_client, a_list):
    client, token = csrf_client
    resp = client.post(f"/email_lists/{a_list}/import",
                       json={"text": "ada@example.com\nada@example.com\nbroken@"},
                       headers={"X-CSRF-Token": token})
    body = resp.get_json()
    assert resp.status_code == 200
    assert body['added'] == 1
    assert body['duplicate'] == 1
    assert body['invalid_count'] == 1
    assert body['invalid'][0]['line'] == 3


def test_import_route_404s_for_an_unknown_list(csrf_client):
    client, token = csrf_client
    resp = client.post("/email_lists/999999/import", json={"text": "a@b.co"},
                       headers={"X-CSRF-Token": token})
    assert resp.status_code == 404


def test_export_route_returns_csv(csrf_client, a_list):
    from app.store import add_contacts

    client, token = csrf_client
    add_contacts(a_list, [('ada@example.com', 'Ada')])
    resp = client.get(f"/email_lists/{a_list}/export")
    assert resp.status_code == 200
    assert 'text/csv' in resp.headers['Content-Type']
    assert 'attachment' in resp.headers['Content-Disposition']
    assert b'ada@example.com' in resp.data


def test_import_requires_auth(anon_client, a_list):
    resp = anon_client.post(f"/email_lists/{a_list}/import", json={"text": "a@b.co"})
    assert resp.status_code in (302, 401, 403)


def test_index_renders_in_standalone_and_hides_the_pull_rail(csrf_client):
    """The builder has to survive with no media server: the pull rail is gone,
    and the page still renders rather than erroring on an absent Plex."""
    import sqlite3

    client, _token = csrf_client
    conn = sqlite3.connect(config.DB_PATH)
    previous = conn.execute(
        "SELECT media_server_type, from_email FROM settings WHERE id = 1").fetchone()
    # the index redirects to setup without a from_email, so give it one
    conn.execute(
        "UPDATE settings SET media_server_type = 'none', from_email = 'a@b.co' WHERE id = 1")
    conn.commit()
    conn.close()
    try:
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert 'id="getAllBtn"' not in body        # the whole pull rail is hidden
        assert 'pullComingSoonBtn' not in body
        assert '"standalone": true' in body        # the flag reaches window.APP
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("UPDATE settings SET media_server_type = ?, from_email = ? WHERE id = 1",
                     (previous[0] if previous else 'plex', previous[1] if previous else ''))
        conn.commit()
        conn.close()


def test_collections_route_answers_empty_in_standalone(csrf_client):
    import sqlite3

    client, _token = csrf_client
    conn = sqlite3.connect(config.DB_PATH)
    previous = conn.execute("SELECT media_server_type FROM settings WHERE id = 1").fetchone()
    conn.execute("UPDATE settings SET media_server_type = 'none' WHERE id = 1")
    conn.commit()
    conn.close()
    try:
        resp = client.get("/fetch_collections/movie")
        # an empty success, not an error the caller has to explain away
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "success", "collections": []}
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("UPDATE settings SET media_server_type = ? WHERE id = 1",
                     (previous[0] if previous else 'plex',))
        conn.commit()
        conn.close()


# --- importing your first list, with none saved yet
#
# The id-based import needs a saved list and saving a list needs recipients, so
# without a create-or-append route there is no way in on a fresh install. This
# is the exact state a standalone install starts in.

def test_import_creates_the_list_when_none_exists(csrf_client):
    from app.store import get_contacts, get_saved_email_lists

    client, token = csrf_client
    try:
        resp = client.post("/email_lists/import", headers={"X-CSRF-Token": token},
                           json={"name": "Subscribers",
                                 "text": "ada@example.com,Ada\ngrace@example.com,Grace"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['added'] == 2
        assert body['list_name'] == 'Subscribers'

        names = [lst['name'] for lst in get_saved_email_lists()]
        assert 'Subscribers' in names
        assert len(get_contacts(body['list_id'])) == 2
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM contacts")
        conn.execute("DELETE FROM email_lists WHERE name = 'Subscribers'")
        conn.commit()
        conn.close()


def test_importing_the_same_name_twice_appends(csrf_client):
    from app.store import get_contacts

    client, token = csrf_client
    try:
        first = client.post("/email_lists/import", headers={"X-CSRF-Token": token},
                            json={"name": "Subscribers", "text": "ada@example.com"})
        second = client.post("/email_lists/import", headers={"X-CSRF-Token": token},
                             json={"name": "Subscribers", "text": "grace@example.com"})
        list_id = second.get_json()['list_id']
        # the same list, appended to, not a duplicate
        assert first.get_json()['list_id'] == list_id
        assert second.get_json()['added'] == 1
        assert {c['email'] for c in get_contacts(list_id)} == {'ada@example.com', 'grace@example.com'}
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM contacts")
        conn.execute("DELETE FROM email_lists WHERE name = 'Subscribers'")
        conn.commit()
        conn.close()


def test_import_without_a_name_is_rejected(csrf_client):
    client, token = csrf_client
    resp = client.post("/email_lists/import", headers={"X-CSRF-Token": token},
                       json={"text": "ada@example.com"})
    assert resp.status_code == 400
    assert 'name' in resp.get_json()['message'].lower()


def test_the_new_list_import_keeps_the_address_column_in_sync(csrf_client):
    """A list created this way has to be sendable, which means email_lists.emails
    must hold the addresses, not just the contacts table."""
    client, token = csrf_client
    try:
        resp = client.post("/email_lists/import", headers={"X-CSRF-Token": token},
                           json={"name": "Subscribers", "text": "ada@example.com\ngrace@example.com"})
        list_id = resp.get_json()['list_id']
        conn = sqlite3.connect(config.DB_PATH)
        emails = conn.execute("SELECT emails FROM email_lists WHERE id = ?", (list_id,)).fetchone()[0]
        conn.close()
        assert emails == 'ada@example.com, grace@example.com'
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM contacts")
        conn.execute("DELETE FROM email_lists WHERE name = 'Subscribers'")
        conn.commit()
        conn.close()


def test_standalone_index_points_at_import_when_no_lists_exist(csrf_client):
    """The first-run state a standalone install actually starts in: no media
    server and no saved lists, where the way in has to be visible."""
    client, _token = csrf_client
    conn = sqlite3.connect(config.DB_PATH)
    previous = conn.execute(
        "SELECT media_server_type, from_email FROM settings WHERE id = 1").fetchone()
    # other tests leave lists behind in the shared temp DB, and the hint only
    # shows with none saved, so clear them and put them back afterwards
    saved_lists = conn.execute("SELECT id, name, emails FROM email_lists").fetchall()
    conn.execute("DELETE FROM email_lists")
    conn.execute(
        "UPDATE settings SET media_server_type = 'none', from_email = 'a@b.co' WHERE id = 1")
    conn.commit()
    conn.close()
    try:
        body = client.get("/").data.decode()
        assert 'choose Import' in body          # the way in is stated, not hidden
        # and the button no longer waits on a saved list existing first
        assert 'id="import_list_btn" type="button" class="btn btn-sm btn-secondary"' in body
        assert 'id="import_list_name"' in body  # naming a list to create
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("UPDATE settings SET media_server_type = ?, from_email = ? WHERE id = 1",
                     (previous[0] if previous else 'plex', previous[1] if previous else ''))
        for row in saved_lists:
            conn.execute("INSERT OR IGNORE INTO email_lists (id, name, emails) VALUES (?, ?, ?)", row)
        conn.commit()
        conn.close()
