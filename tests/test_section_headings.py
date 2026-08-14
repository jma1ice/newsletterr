"""per-item section heading override and hide."""
import re
from pathlib import Path

import pytest

from app.emails import headings
from app.emails.builders import layouts
from app.emails.builders.calendar_view import section_container_html
from app.emails.builders.card_grid import build_calendar_grid_html

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDER_JS = REPO_ROOT / "static/js/app/07-email-builder.js"

THEME = {
    'card_bg': '#111', 'border': '#222', 'text': '#eee', 'muted_text': '#999',
    'primary': '#07a', 'accent': '#0cf', 'email_theme': 'dark',
}

LAYOUTS = ('legacy', 'classic', 'editorial', 'digest', 'spotlight')


# --------------------------------------------------------------- the carrier

def test_stamp_returns_the_same_object_when_nothing_is_overridden():
    """Identity, not equality: the no-override path must not even copy."""
    assert headings.stamp(THEME) is THEME
    assert headings.stamp(THEME, '', False) is THEME
    assert headings.stamp(THEME, '   ') is THEME
    assert headings.stamp(THEME, None, None) is THEME


def test_stamp_copies_rather_than_mutating_when_overriding():
    stamped = headings.stamp(THEME, 'Custom')
    assert stamped is not THEME
    assert 'heading_override' not in THEME
    assert stamped['card_bg'] == THEME['card_bg']


def test_resolve_prefers_the_override_then_the_default():
    assert headings.resolve(THEME, 'Default') == 'Default'
    assert headings.resolve(headings.stamp(THEME, 'Custom'), 'Default') == 'Custom'


def test_resolve_returns_empty_when_hidden():
    hidden = headings.stamp(THEME, '', True)
    assert headings.resolve(hidden, 'Default') == ''
    # hide wins even if a heading was also typed
    assert headings.resolve(headings.stamp(THEME, 'Custom', True), 'Default') == ''


def test_whitespace_only_heading_is_not_an_override():
    assert headings.resolve(headings.stamp(THEME, '   '), 'Default') == 'Default'


# ------------------------------------------------------------- layout chrome

@pytest.mark.parametrize("layout", LAYOUTS)
def test_shell_is_untouched_without_an_override(layout):
    plain = layouts._shell(layout, THEME, 'Coming Soon (TV)', '<p>body</p>')
    stamped = layouts._shell(layout, headings.stamp(THEME), 'Coming Soon (TV)', '<p>body</p>')
    assert plain == stamped


@pytest.mark.parametrize("layout", LAYOUTS)
def test_shell_renders_the_override(layout):
    html = layouts._shell(layout, headings.stamp(THEME, 'On The Way'), 'Coming Soon (TV)', '<p>body</p>')
    assert 'On The Way' in html
    assert 'Coming Soon (TV)' not in html


@pytest.mark.parametrize("layout", LAYOUTS)
def test_shell_hides_the_heading_but_keeps_the_body_and_chrome(layout):
    html = layouts._shell(layout, headings.stamp(THEME, '', True), 'Coming Soon (TV)', '<p>body</p>')
    assert 'Coming Soon (TV)' not in html
    assert '<p>body</p>' in html
    # the section is still a section: its card/border/spacing survive
    assert THEME['border'] in html or 'margin' in html


@pytest.mark.parametrize("layout", LAYOUTS)
def test_hidden_heading_leaves_no_empty_heading_element(layout):
    """An empty <h2>/<div> would still occupy vertical space in a mail client."""
    html = layouts._shell(layout, headings.stamp(THEME, '', True), 'Label', '<p>body</p>')
    assert not re.search(r"<(h2|h3)[^>]*>\s*</\1>", html)


@pytest.mark.parametrize("layout", LAYOUTS)
def test_override_is_escaped_in_every_layout(layout):
    html = layouts._shell(layout, headings.stamp(THEME, '<script>x</script>'), 'Label', '')
    assert '<script>' not in html
    assert '&lt;script&gt;' in html


# ------------------------------------------------------------ legacy chrome

def test_card_grid_title_override_and_hide():
    plain = build_calendar_grid_html(['<i></i>'], None, THEME, 'Coming Soon (TV)', '', 5)
    assert 'Coming Soon (TV)' in plain

    renamed = build_calendar_grid_html(
        ['<i></i>'], None, headings.stamp(THEME, 'On The Way'), 'Coming Soon (TV)', '', 5)
    assert 'On The Way' in renamed and 'Coming Soon (TV)' not in renamed

    hidden = build_calendar_grid_html(
        ['<i></i>'], None, headings.stamp(THEME, '', True), 'Coming Soon (TV)', '', 5)
    assert 'Coming Soon (TV)' not in hidden
    assert '<h2' not in hidden


def test_card_grid_escapes_a_user_supplied_title():
    """It interpolated the title raw before headings could be user input."""
    html = build_calendar_grid_html(
        ['<i></i>'], None, headings.stamp(THEME, '<img src=x onerror=alert(1)>'),
        'Coming Soon (TV)', '', 5)
    assert '<img src=x' not in html
    assert '&lt;img' in html


def test_section_container_override_and_hide():
    plain = section_container_html(THEME, 'Coming Soon (Movies)', '<p>x</p>')
    assert 'Coming Soon (Movies)' in plain

    hidden = section_container_html(headings.stamp(THEME, '', True), 'Coming Soon (Movies)', '<p>x</p>')
    assert 'Coming Soon (Movies)' not in hidden
    assert '<p>x</p>' in hidden
    assert '<h2' not in hidden


def test_legacy_chrome_is_untouched_without_an_override():
    assert (build_calendar_grid_html(['<i></i>'], None, THEME, 'T', '', 5)
            == build_calendar_grid_html(['<i></i>'], None, headings.stamp(THEME), 'T', '', 5))
    assert (section_container_html(THEME, 'T', '<p>x</p>')
            == section_container_html(headings.stamp(THEME), 'T', '<p>x</p>'))


# ------------------------------------------------------------------ builder

def test_builder_offers_the_control_for_heading_bearing_snapins():
    source = BUILDER_JS.read_text(encoding="utf-8")
    assert "function itemHeadingControls(" in source
    assert "HEADING_ITEM_TYPES" in source

    block = source.split("const HEADING_ITEM_TYPES")[1].split("]);")[0]
    for item_type in ('sonarr_coming_soon', 'radarr_coming_soon', 'recently added',
                      'most_watched', 'ombi_requests', 'seerr_requests', 'top_viewer'):
        assert f"'{item_type}'" in block, item_type

    # blocks that are their own content carry no section heading
    for item_type in ('textblock', 'titleblock', 'separator', 'image', 'gif'):
        assert f"'{item_type}'" not in block, item_type


def test_blank_heading_clears_the_key_instead_of_storing_empty():
    """A stored empty string would ride into every saved template."""
    source = BUILDER_JS.read_text(encoding="utf-8")
    start = source.index(".snapin-heading-input")
    body = source[start:start + 700]
    assert "delete selectedItems[index].heading" in body
