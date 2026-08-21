"""The spotlight layout: dark card stack, hero lead, and a link to the server."""
import re
import sqlite3
from email.mime.multipart import MIMEMultipart

import pytest

from app.emails.builders import layouts as layouts_mod

THEME = {
    'background': '#333333', 'text': '#62a1a4', 'primary': '#8acbd4',
    'secondary': '#222222', 'accent': '#62a1a4', 'card_bg': '#2d2d2d',
    'border': '#404040', 'muted_text': '#cccccc', 'email_theme': 'newsletterr_blue',
}
RECENT = [{'recently_added': [
    {'title': 'The Grand Voyage', 'rating_key': '1', 'year': '2024', 'thumb': '/t/1',
     'summary': 'A crew sails past the edge of the map.', 'added_at': '1750000000',
     'updated_at': '1750000000', 'duration': '6900000', 'media_type': 'movie',
     'type': 'movie', 'library_name': 'Movies', 'plex_url': 'https://plex/1', 'rating': '8.4'},
    {'title': 'Neon Harbor', 'rating_key': '2', 'year': '2023', 'thumb': '/t/2', 'summary': '',
     'added_at': '1749000000', 'updated_at': '1749000000', 'duration': '5400000',
     'media_type': 'movie', 'type': 'movie', 'library_name': 'Movies', 'plex_url': '', 'rating': '7.9'},
]}]
MOST_WATCHED = [{'most_watched': [
    {'title': 'Big Hit', 'year': '2024', 'play_count': 57, 'thumb': '/t/1', 'plex_url': ''},
    {'title': 'Only Once', 'year': '2023', 'play_count': 1, 'thumb': '', 'plex_url': ''},
]}]
MOVIE_STAT = {'stat_title': 'Most Watched Movies', 'rows': [
    {'title': 'Dune', 'year': '2021', 'total_plays': 42, 'thumb': '/t/1'},
]}


@pytest.fixture(autouse=True)
def _stub_image_fetches(monkeypatch):
    monkeypatch.setattr(layouts_mod, "fetch_and_attach_image", lambda *a, **k: "cid:img")
    monkeypatch.setattr(layouts_mod, "fetch_and_attach_small_thumbnail", lambda *a, **k: "cid:thumb")
    monkeypatch.setattr(layouts_mod, "email_icon_img", lambda *a, **k: "")


def theme():
    return layouts_mod.apply_theme('spotlight', THEME)


# --- chassis

def test_spotlight_overrides_the_theme_chassis_without_touching_the_accent():
    t = theme()
    assert t['background'] == '#0f0f0f' and t['card_bg'] == '#181818'
    # the user's accent and primary survive: the layout is themeable
    assert t['accent'] == THEME['accent'] and t['primary'] == THEME['primary']
    # and the source theme is not mutated
    assert THEME['background'] == '#333333'


@pytest.mark.parametrize("layout", ["legacy", "classic", "editorial", "digest"])
def test_other_layouts_keep_their_theme(layout):
    assert layouts_mod.apply_theme(layout, THEME) is THEME


def test_body_copy_is_neutral_rather_than_the_theme_text_color():
    """Accent is spent on kickers and metrics; paragraphs stay readable gray."""
    assert theme()['text'] == '#c9c9c9'


# --- sections

def test_recently_added_leads_with_a_hero_then_lists_the_rest():
    html = layouts_mod.render_recently_added('spotlight', RECENT, MIMEMultipart(), theme(), base_url="http://b")
    # hero: accent-bordered card carrying the newest title at display size
    assert f"border: 1px solid {theme()['accent']}" in html
    assert "font-size: 21px" in html and "The Grand Voyage" in html
    # the remainder follows in its own card
    assert "Also new this week" in html and "Neon Harbor" in html


def test_a_single_recent_item_renders_the_hero_alone():
    single = [{'recently_added': RECENT[0]['recently_added'][:1]}]
    html = layouts_mod.render_recently_added('spotlight', single, MIMEMultipart(), theme(), base_url="http://b")
    assert "The Grand Voyage" in html
    assert "Also new this week" not in html


def test_metrics_stack_as_a_number_over_its_unit():
    html = layouts_mod.render_most_watched('spotlight', MOST_WATCHED, MIMEMultipart(), theme(), base_url="http://b")
    assert ">57</div>" in html and ">plays</div>" in html
    # and the unit is singular for one play
    assert ">1</div>" in html and ">play</div>" in html


def test_the_metric_is_not_repeated_in_the_meta_line():
    html = layouts_mod.render_stats('spotlight', MOVIE_STAT, MIMEMultipart(), theme(), "http://b", "30")
    assert html.count("42") == 1


def test_titles_are_not_underlined_but_stay_linked():
    html = layouts_mod.render_recently_added('spotlight', RECENT, MIMEMultipart(), theme(), base_url="http://b")
    assert 'href="https://plex/1"' in html
    assert "text-decoration: underline" not in html


def test_sections_without_a_spotlight_treatment_still_get_its_card():
    """Coming soon has no bespoke spotlight markup; it must not fall through to
    the digest text rows."""
    from tests.test_golden_sends import RADARR_MOVIES_FIXTURE
    html = layouts_mod.render_radarr_coming_soon('spotlight', RADARR_MOVIES_FIXTURE, MIMEMultipart(), theme(), base_url="http://b")
    assert "border-radius: 10px" in html and theme()['card_bg'] in html


# --- shell

@pytest.fixture()
def shell(app, seeded_settings):
    from app import config
    from app.emails.assemble import build_complete_email_html_with_cid_logo

    def render(layout='spotlight', server_url='https://app.plex.tv/desktop', media_server='plex'):
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute(
            "UPDATE settings SET email_layout = ?, media_server_type = ?, plex_web_url = ?, jellyfin_web_url = ? WHERE id = 1",
            (layout, media_server, server_url if media_server == 'plex' else '',
             server_url if media_server == 'jellyfin' else ''),
        )
        conn.commit()
        conn.close()
        return build_complete_email_html_with_cid_logo(
            "<p>body</p>", "Test Server", "Subject", "This Week", "", "", layout=layout)

    return render


def test_shell_runs_a_narrower_column_than_the_other_layouts(shell):
    """The class rule carries !important, so the width must come from the CSS.

    No space before !important: Yahoo drops the declaration when whitespace
    precedes it, so the email CSS is written without one throughout.
    """
    assert "max-width: 640px!important" in shell()
    assert "max-width: 800px!important" in shell(layout='classic')


def test_shell_and_cards_share_the_spotlight_canvas(shell):
    html = shell()
    assert 'bgcolor="#0f0f0f"' in html or "background-color: #0f0f0f" in html


def test_call_to_action_links_to_the_configured_server(shell):
    html = shell()
    assert "Open Plex" in html and 'href="https://app.plex.tv/desktop"' in html


def test_call_to_action_follows_the_media_server_type(shell):
    html = shell(server_url="http://jelly.local", media_server="jellyfin")
    assert "Open Jellyfin" in html and 'href="http://jelly.local"' in html


def test_no_call_to_action_when_the_server_url_is_unknown(shell):
    """Jellyfin has no default web URL, so an unconfigured one hides the button
    rather than linking nowhere. (Plex always has app.plex.tv to fall back on.)"""
    html = shell(server_url="", media_server="jellyfin")
    assert "Open Jellyfin" not in html and "Open Plex" not in html
    # the footer itself survives
    assert "newsletterr" in html


def test_plex_falls_back_to_the_default_web_url(shell):
    html = shell(server_url="")
    assert "Open Plex" in html and "app.plex.tv" in html


def test_other_layouts_have_no_call_to_action(shell):
    assert "Open Plex" not in shell(layout='classic')


def test_header_background_setting_does_not_apply(shell):
    """Spotlight has no header band to color; the kicker sits on the canvas."""
    from app import config
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute("UPDATE settings SET email_header_bg = '#123456' WHERE id = 1")
    conn.commit()
    conn.close()
    assert "#123456" not in shell()


def test_layout_is_registered_and_accepted_by_settings(csrf_client):
    from tests.test_routes import SETTINGS_FORM
    from app import config

    assert layouts_mod.is_layout('spotlight')
    client, token = csrf_client
    client.post("/settings", data={**SETTINGS_FORM, "csrf_token": token, "email_layout": "spotlight"})
    conn = sqlite3.connect(config.DB_PATH)
    saved = conn.execute("SELECT email_layout FROM settings WHERE id = 1").fetchone()[0]
    conn.close()
    assert saved == "spotlight"
    assert 'value="spotlight"' in client.get("/settings").get_data(as_text=True)


def test_every_registered_layout_renders_every_section():
    """A new layout must not silently fall through to another layout's markup
    or crash on a section nobody restyled."""
    for layout in layouts_mod.LAYOUTS:
        t = layouts_mod.apply_theme(layout, THEME)
        assert layouts_mod.render_recently_added(layout, RECENT, MIMEMultipart(), t, base_url="http://b")
        assert layouts_mod.render_most_watched(layout, MOST_WATCHED, MIMEMultipart(), t, base_url="http://b")
        assert layouts_mod.render_stats(layout, MOVIE_STAT, MIMEMultipart(), t, "http://b", "30")


def test_spotlight_markup_stays_email_safe():
    html = layouts_mod.render_recently_added('spotlight', RECENT, MIMEMultipart(), theme(), base_url="http://b")
    html += layouts_mod.render_most_watched('spotlight', MOST_WATCHED, MIMEMultipart(), theme(), base_url="http://b")
    assert "display: flex" not in html and "display:flex" not in html
    assert "display: grid" not in html and "display:grid" not in html
    assert not re.search(r"position:\s*absolute", html)
