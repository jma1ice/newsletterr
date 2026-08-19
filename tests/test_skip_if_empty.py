"""skip the send when the email would render nothing."""
import json
import sqlite3

from app import config
from app.emails.assemble import CHROME_ITEM_TYPES


# --- what counts as content

def test_authored_chrome_never_counts_as_content():
    """A template whose only survivors are an intro and a separator is exactly
    the quiet-week email this option exists to suppress."""
    for kind in ('textblock', 'titleblock', 'headerblock', 'separator', 'image', 'gif', 'emoji'):
        assert kind in CHROME_ITEM_TYPES


def test_data_backed_sections_are_not_chrome():
    for kind in ('recently added', 'most_watched', 'stat', 'graph', 'recommendations',
                 'yearly_wrapped', 'sonarr_coming_soon', 'ombi_requests', 'collection_group',
                 'droppedneedle_wrapped', 'recently_released'):
        assert kind not in CHROME_ITEM_TYPES


# --- the count that comes out of assembly

def _assemble(items, email_text="", custom_html=""):
    """Assemble a template and return (html, render_stats)."""
    from email.mime.multipart import MIMEMultipart
    from app.emails.assemble import build_email_html_with_all_cids

    template_data = {
        'selected_items': json.dumps(items),
        'email_text': email_text,
        'custom_html': custom_html,
        'subject': 'Test',
    }
    stats = {}
    build_email_html_with_all_cids(
        template_data, {'settings': {'server_name': 'Test'}}, MIMEMultipart('related'),
        'email', None, render_stats=stats,
    )
    return stats


def test_no_items_reports_no_content():
    assert _assemble([]) == {'content_items': 0}


def test_chrome_only_template_reports_no_content():
    """The load-bearing case: an intro paragraph and a separator render real
    HTML, but the email still has nothing to say."""
    items = [
        {'id': 'a', 'type': 'textblock', 'content': 'Here is this week of nothing.'},
        {'id': 'b', 'type': 'separator'},
    ]
    assert _assemble(items, email_text="Hello there")['content_items'] == 0


def test_data_section_with_no_data_reports_no_content():
    """The case that makes this feature non-trivial: recently added with nothing
    pulled does not render nothing, it renders a "No recently added items"
    card. Counting rendered-and-non-empty would call that content and the skip
    would never fire."""
    items = [{'id': 'a', 'type': 'recently added', 'raLibrary': ''}]
    assert _assemble(items)['content_items'] == 0


def test_empty_state_cards_are_marked_so_they_can_be_told_apart():
    from email.mime.multipart import MIMEMultipart
    from app.emails.assemble import item_rendered_content
    from app.emails.builders.card_grid import EMPTY_STATE_MARKER, empty_state_html
    from app.emails.builders.recently_added import build_recently_added_html_with_cids

    theme = {'card_bg': '#181818', 'border': '#2b2b2b', 'muted_text': '#8e8e8e',
             'text': '#c9c9c9', 'primary': '#8acbd4', 'accent': '#62a1a4'}
    assert EMPTY_STATE_MARKER in empty_state_html(theme, "No items.")

    # the two bespoke ones in recently added: no data at all, and data that
    # nothing matched after the library filter
    no_data = build_recently_added_html_with_cids(None, MIMEMultipart('related'), theme)
    assert EMPTY_STATE_MARKER in no_data
    filtered_out = build_recently_added_html_with_cids(
        [{'recently_added': [{'title': 'X', 'library_name': 'TV'}]}],
        MIMEMultipart('related'), theme, library_filter='Movies')
    assert EMPTY_STATE_MARKER in filtered_out

    # and the check reads them as no content
    assert item_rendered_content({'type': 'recently added'}, no_data) is False
    assert item_rendered_content({'type': 'recently added'}, filtered_out) is False


def test_a_real_section_is_not_mistaken_for_empty():
    from app.emails.assemble import item_rendered_content
    assert item_rendered_content({'type': 'recently added'}, '<div>A real card</div>') is True
    assert item_rendered_content({'type': 'textblock'}, '<div>Just chrome</div>') is False
    assert item_rendered_content({'type': 'recently added'}, '   ') is False


def test_a_section_that_renders_counts():
    """Collections render from the item itself rather than from a pull, so this
    is a section that produces output with no data fetched."""
    items = [{
        'id': 'a', 'type': 'collection_group', 'title': 'Staff Picks',
        'collections': [{'title': 'A Collection', 'ratingKey': '1', 'thumb': '', 'type': 'movie'}],
    }]
    assert _assemble(items)['content_items'] == 1


def test_custom_html_is_never_empty():
    """The body is the author's own writing, whatever the tokens resolved to.
    Counting only tokens would skip a hand-written email that says exactly what
    its author meant it to say."""
    stats = _assemble([], custom_html="<p>Hand written, no tokens at all.</p>")
    assert stats['content_items'] == 1


def test_blank_custom_html_still_reports_nothing():
    assert _assemble([], custom_html="   ")['content_items'] == 0


def test_render_stats_is_optional():
    """Callers that do not care keep the old two-tuple return and pass nothing."""
    from email.mime.multipart import MIMEMultipart
    from app.emails.assemble import build_email_html_with_all_cids

    html, hosted = build_email_html_with_all_cids(
        {'selected_items': '[]', 'email_text': 'hi', 'subject': 'S'},
        {'settings': {'server_name': 'Test'}}, MIMEMultipart('related'), 'email', None,
    )
    assert html and hosted is None


# --- schema and round trip

def test_schedule_stores_and_reads_back_the_flag(app):
    from app.store import create_email_schedule, get_email_schedules

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("INSERT OR IGNORE INTO email_lists (id, name, emails) VALUES (900, 'SkipEmpty', 'a@b.co')")
    conn.execute("INSERT OR IGNORE INTO email_templates (id, name, selected_items) VALUES (900, 'SkipEmptyTpl', '[]')")
    conn.commit()
    conn.close()
    try:
        create_email_schedule('Empty Test', 900, 900, 'weekly', '2026-09-01', skip_if_empty=1)
        row = next(s for s in get_email_schedules() if s['name'] == 'Empty Test')
        assert row['skip_if_empty'] is True
        # the NEWS-45 fields still read back correctly beside it, which is the
        # thing a column added mid-SELECT would silently break
        assert row['skip_if_no_new'] is False
        assert row['skip_min_items'] == 1
        assert row['email_list_name'] == 'SkipEmpty'
        assert row['template_name'] == 'SkipEmptyTpl'
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM email_schedules WHERE name = 'Empty Test'")
        conn.execute("DELETE FROM email_lists WHERE id = 900")
        conn.execute("DELETE FROM email_templates WHERE id = 900")
        conn.commit()
        conn.close()


def test_default_is_off_so_no_existing_schedule_changes(app):
    from app.store import create_email_schedule, get_email_schedules

    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("INSERT OR IGNORE INTO email_lists (id, name, emails) VALUES (901, 'DefOff', 'a@b.co')")
    conn.execute("INSERT OR IGNORE INTO email_templates (id, name, selected_items) VALUES (901, 'DefOffTpl', '[]')")
    conn.commit()
    conn.close()
    try:
        create_email_schedule('Default Off', 901, 901, 'weekly', '2026-09-01')
        row = next(s for s in get_email_schedules() if s['name'] == 'Default Off')
        assert row['skip_if_empty'] is False
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM email_schedules WHERE name = 'Default Off'")
        conn.execute("DELETE FROM email_lists WHERE id = 901")
        conn.execute("DELETE FROM email_templates WHERE id = 901")
        conn.commit()
        conn.close()


def test_route_accepts_the_flag(csrf_client):
    client, token = csrf_client
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("INSERT OR IGNORE INTO email_lists (id, name, emails) VALUES (902, 'RouteEmpty', 'a@b.co')")
    conn.execute("INSERT OR IGNORE INTO email_templates (id, name, selected_items) VALUES (902, 'RouteEmptyTpl', '[]')")
    conn.commit()
    conn.close()
    try:
        resp = client.post("/scheduling/create", headers={"X-CSRF-Token": token}, json={
            "name": "Route Empty", "email_list_id": 902, "template_id": 902,
            "frequency": "weekly", "start_date": "2026-09-01", "skip_if_empty": True,
        })
        assert resp.status_code == 200
        conn = sqlite3.connect(config.DB_PATH)
        stored = conn.execute(
            "SELECT skip_if_empty FROM email_schedules WHERE name = 'Route Empty'").fetchone()[0]
        conn.close()
        assert stored == 1
    finally:
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("DELETE FROM email_schedules WHERE name = 'Route Empty'")
        conn.execute("DELETE FROM email_lists WHERE id = 902")
        conn.execute("DELETE FROM email_templates WHERE id = 902")
        conn.commit()
        conn.close()
