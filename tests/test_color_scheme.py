"""The email's declared color-scheme follows the theme it is actually painted in."""

import re
import sqlite3

import pytest

from app.theme import is_dark_background


DARK = "#333333"      # every shipped preset
LIGHT = "#f6f4ef"


def test_luminance_split_matches_the_shipped_presets():
    assert is_dark_background(DARK) is True
    assert is_dark_background("#0f0f0f") is True
    assert is_dark_background(LIGHT) is False
    assert is_dark_background("#ffffff") is False


def test_a_missing_or_bogus_background_is_treated_as_dark():
    # Every preset is dark, so that is the safer assumption when the value is
    # unusable, a light declaration on a dark email is the bug being fixed.
    for value in ("", None, "not-a-color", "#12345"):
        assert is_dark_background(value) is True


@pytest.fixture()
def render(app, seeded_settings):
    from app import config
    from app.emails.assemble import build_complete_email_html_with_cid_logo

    def _render(background):
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute(
            "UPDATE settings SET email_theme = 'custom', background_color = ? WHERE id = 1",
            (background,),
        )
        conn.commit()
        conn.close()
        return build_complete_email_html_with_cid_logo(
            "<p>body</p>", "Test Server", "Subject", "Header", "", "")

    return _render


def _meta(html, name):
    match = re.search(rf'<meta name="{name}" content="([^"]+)"', html)
    return match.group(1) if match else None


def test_dark_theme_declares_dark(render):
    html = render(DARK)
    assert _meta(html, "color-scheme") == "dark only"
    assert _meta(html, "supported-color-schemes") == "dark only"
    assert "color-scheme: dark!important" in html


def test_light_theme_declares_light(render):
    html = render(LIGHT)
    assert _meta(html, "color-scheme") == "light only"
    assert _meta(html, "supported-color-schemes") == "light only"
    assert "color-scheme: light!important" in html


def test_the_declaration_is_never_hardcoded_against_the_theme(render):
    """The regression this file exists for: a dark email claiming to be light."""
    dark_html = render(DARK)
    light_html = render(LIGHT)
    assert _meta(dark_html, "color-scheme") != _meta(light_html, "color-scheme")
