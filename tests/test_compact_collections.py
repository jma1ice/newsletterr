"""The compact-density collections row builder."""
import pytest

THEME = {
    'card_bg': '#181818', 'border': '#2b2b2b', 'text': '#c9c9c9',
    'muted_text': '#8e8e8e', 'accent': '#62a1a4', 'primary': '#8acbd4',
}

COLLECTION = {'key': '1', 'title': 'Staff Picks', 'type': 'movie', 'childCount': 3}
EXPANDED_ITEM = {'title': 'A Film', 'year': 2026, 'is_individual_item': True,
                 'original_collection': 'Staff Picks'}


def _compact_theme():
    """A theme stamped compact for a layout whose natural density is expanded,
    so show_art() is false and the compact rows path is taken."""
    from app.emails import density
    return density.stamp(dict(THEME), 'classic', 'compact')


def test_compact_rows_render_without_error():
    from app.emails.builders.collections import _compact_collection_rows_html
    html = _compact_collection_rows_html([COLLECTION], THEME)
    assert 'Staff Picks' in html
    assert '3 items' in html
    assert 'font-family:' in html


def test_compact_rows_name_their_font():
    """The regression: the font stack local was removed with a docstring."""
    from app.emails.builders.collections import _compact_collection_rows_html
    html = _compact_collection_rows_html([COLLECTION], THEME)
    assert 'IBM Plex Sans' in html


def test_expanded_items_show_their_source_collection():
    from app.emails.builders.collections import _compact_collection_rows_html
    html = _compact_collection_rows_html([EXPANDED_ITEM], THEME)
    assert 'A Film' in html
    assert 'Staff Picks' in html


def test_singular_item_count():
    from app.emails.builders.collections import _compact_collection_rows_html
    html = _compact_collection_rows_html([dict(COLLECTION, childCount=1)], THEME)
    assert '1 item<' in html or '1 item ' in html
    assert '1 items' not in html


def test_last_row_has_no_bottom_border():
    from app.emails.builders.collections import _compact_collection_rows_html
    html = _compact_collection_rows_html([COLLECTION, dict(COLLECTION, key='2')], THEME)
    assert html.count('border-bottom') == 2      # two cells on the first row only


def test_a_collection_group_renders_end_to_end_at_compact_density(monkeypatch):
    """The path that would actually have 500'd: the whole snap-in, compact."""
    from email.mime.multipart import MIMEMultipart
    from app.emails.builders import collections as collections_mod

    monkeypatch.setattr(collections_mod, "get_settings", lambda **kw: {'id': 1})

    root = MIMEMultipart('related')
    root.preview_mode = True
    html = collections_mod.build_collections_html_with_cids(
        [COLLECTION], root, _compact_theme(), "", "My Group", {}, 0)

    assert 'My Group' in html
    assert 'Staff Picks' in html


def test_the_same_group_still_renders_at_expanded_density(monkeypatch):
    from email.mime.multipart import MIMEMultipart
    from app.emails import density
    from app.emails.builders import collections as collections_mod

    monkeypatch.setattr(collections_mod, "get_settings", lambda **kw: {'id': 1})

    root = MIMEMultipart('related')
    root.preview_mode = True
    html = collections_mod.build_collections_html_with_cids(
        [COLLECTION], root, density.stamp(dict(THEME), 'classic', 'expanded'),
        "", "My Group", {}, 0)

    assert 'Staff Picks' in html


@pytest.mark.parametrize("items", [[], None])
def test_empty_input_is_harmless(items):
    from app.emails.builders.collections import _compact_collection_rows_html
    assert _compact_collection_rows_html(items or [], THEME) == ""
