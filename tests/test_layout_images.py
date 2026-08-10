"""Image parity between the legacy builders and the classic/editorial/digest layouts."""
import re
from email.mime.multipart import MIMEMultipart

import pytest

from app.emails.builders import layouts as layouts_mod
from app.emails.builders import stats as stats_mod

LAYOUTS = ("classic", "editorial", "digest", "spotlight")

THEME = {
    'background': '#333333', 'text': '#62a1a4', 'primary': '#8acbd4',
    'secondary': '#222222', 'accent': '#62a1a4', 'card_bg': '#2d2d2d',
    'border': '#404040', 'muted_text': '#cccccc', 'email_theme': 'newsletterr_blue',
}

MOVIE_STAT = {
    'stat_id': 'top_movies', 'stat_title': 'Most Watched Movies',
    'rows': [
        {'title': 'Dune', 'year': '2021', 'total_plays': 42, 'thumb': '/library/metadata/1/thumb'},
        {'title': 'Arrival', 'year': '2016', 'total_plays': 30, 'thumb': '/library/metadata/2/thumb'},
    ],
}
PLATFORM_STAT = {
    'stat_id': 'top_platforms', 'stat_title': 'Most Active Platforms',
    'rows': [{'platform': 'Roku', 'total_plays': 12, 'thumb': '/library/metadata/9/thumb'}],
}
USER_STAT = {
    'stat_id': 'top_users', 'stat_title': 'Most Active Users',
    'rows': [
        {'user': 'alice', 'total_plays': 20, 'user_thumb': 'http://plex.tv/alice.png'},
        {'user': 'bob', 'total_plays': 10, 'user_thumb': 'http://plex.tv/bob.png'},
    ],
}
WRAPPED = [
    {'stat_title': 'Most Watched Movies', 'rows': [{'title': 'Dune', 'total_plays': 42, 'thumb': '/t/1'}]},
    {'stat_title': 'Most Watched TV Shows', 'rows': [{'title': 'Severance', 'total_plays': 30, 'thumb': '/t/2'}]},
    {'stat_title': 'Most Active Users', 'rows': [{'user': 'alice', 'user_thumb': 'http://plex.tv/alice.png'}]},
]


@pytest.fixture(autouse=True)
def _stub_image_fetches(monkeypatch):
    for mod in (layouts_mod, stats_mod):
        monkeypatch.setattr(mod, "fetch_and_attach_small_thumbnail", lambda *a, **k: "cid:thumb")
        if hasattr(mod, "fetch_and_attach_image"):
            monkeypatch.setattr(mod, "fetch_and_attach_image", lambda *a, **k: "cid:img")
        if hasattr(mod, "fetch_and_attach_blurred_image"):
            monkeypatch.setattr(mod, "fetch_and_attach_blurred_image", lambda *a, **k: "cid:bg")
        if hasattr(mod, "email_icon_img"):
            monkeypatch.setattr(mod, "email_icon_img", lambda *a, **k: '<img src="cid:icon">')


def imgs(html):
    """<img> tags, minus the monochrome section icons."""
    return [tag for tag in re.findall(r"<img [^>]*>", html or "") if 'cid:icon' not in tag]


def render(layout, stat, **kw):
    return layouts_mod.render_stats(layout, stat, MIMEMultipart(), THEME, "http://base", "30", **kw)


@pytest.mark.parametrize("layout", LAYOUTS)
def test_cover_art_reaches_the_layouts_when_enabled(layout):
    """Legacy attaches a thumbnail per row; the layouts must match it."""
    legacy = stats_mod.build_stats_html_with_cid_background(
        MOVIE_STAT, MIMEMultipart(), THEME, "http://base", "30", show_cover_art=True)
    assert len(imgs(render(layout, MOVIE_STAT, show_cover_art=True))) == len(imgs(legacy)) == 2


@pytest.mark.parametrize("layout", LAYOUTS)
def test_cover_art_stays_off_when_the_setting_is_off(layout):
    assert imgs(render(layout, MOVIE_STAT, show_cover_art=False)) == []


@pytest.mark.parametrize("layout", LAYOUTS)
def test_cover_art_skips_stats_that_have_no_artwork(layout):
    """Platforms/libraries carry a thumb field but no art worth showing."""
    assert imgs(render(layout, PLATFORM_STAT, show_cover_art=True)) == []


@pytest.mark.parametrize("layout", LAYOUTS)
def test_user_avatars_render_without_the_cover_art_setting(layout):
    """Legacy shows avatars whenever the user has one; cover art is unrelated."""
    tags = imgs(render(layout, USER_STAT, show_cover_art=False))
    assert len(tags) == 2
    assert all("border-radius: 50%" in tag for tag in tags)


@pytest.mark.parametrize("layout", LAYOUTS)
def test_user_avatars_follow_the_user_info_toggle(layout):
    assert render(layout, USER_STAT, include_user_info=False) == ""


@pytest.mark.parametrize("layout", ("classic", "editorial", "spotlight"))
def test_wrapped_highlights_carry_artwork(layout):
    """One image per highlight, matching legacy wrapped."""
    legacy = stats_mod.build_yearly_wrapped_html_with_cids(
        WRAPPED, MIMEMultipart(), THEME, base_url="http://base")
    html = layouts_mod.render_wrapped(layout, WRAPPED, MIMEMultipart(), THEME, base_url="http://base")
    assert len(imgs(html)) == len(imgs(legacy)) == 3
    # the top user is a round avatar, the titles are posters
    assert sum("border-radius: 50%" in tag for tag in imgs(html)) == 1


def test_digest_wrapped_tiles_stay_text_only():
    """The digest tiles are too small for artwork; posters live in its
    recently-added strip instead."""
    html = layouts_mod.render_wrapped("digest", WRAPPED, MIMEMultipart(), THEME, base_url="http://base")
    assert imgs(html) == []
    assert "Dune" in html


@pytest.mark.parametrize("layout", LAYOUTS)
def test_missing_artwork_never_emits_a_broken_image(layout):
    bare = {'stat_title': 'Most Watched Movies', 'rows': [{'title': 'No Art', 'total_plays': 1}]}
    assert imgs(render(layout, bare, show_cover_art=True)) == []


@pytest.mark.parametrize("layout", LAYOUTS)
def test_posters_are_sized_by_width_never_height(layout):
    """The email head CSS sets img { height: auto !important }, so a poster
    given a CSS height renders at its natural size and blows out the row."""
    tags = imgs(render(layout, MOVIE_STAT, show_cover_art=True))
    assert tags
    for tag in tags:
        assert re.search(r"width: \d+px", tag), tag
        assert "height: auto" in tag, tag
        assert re.search(r'width="\d+"', tag), tag  # attribute too, for Outlook


@pytest.mark.parametrize("layout", ("classic", "editorial", "spotlight"))
def test_wrapped_posters_are_sized_by_width_too(layout):
    html = layouts_mod.render_wrapped(layout, WRAPPED, MIMEMultipart(), THEME, base_url="http://base")
    posters = [tag for tag in imgs(html) if "border-radius: 50%" not in tag]
    assert posters
    for tag in posters:
        assert re.search(r"width: \d+px", tag) and "height: auto" in tag, tag


# --- blurred backdrop (classic only, mirroring the legacy stat card)

ART_STAT = {
    'stat_title': 'Most Watched Movies',
    'rows': [
        {'title': 'Dune', 'total_plays': 42, 'thumb': '/t/1', 'art': '/library/metadata/1/art'},
        {'title': 'Arrival', 'total_plays': 30, 'thumb': '/t/2'},
    ],
}


def test_classic_stat_card_gets_the_blurred_backdrop():
    html = render('classic', ART_STAT)
    assert "background-image: url('cid:bg')" in html
    # solid color stays underneath for clients that drop background images
    assert "background-color: #2d2d2d" in html
    # and the contents sit on a scrim so the text stays legible
    assert "rgba(28, 28, 28, 0.74)" in html


def test_backdrop_is_independent_of_the_cover_art_setting():
    """Legacy shows the backdrop either way; only row thumbs are gated."""
    for cover in (True, False):
        assert "background-image" in render('classic', ART_STAT, show_cover_art=cover)


@pytest.mark.parametrize("layout", ("editorial", "digest", "spotlight"))
def test_other_layouts_have_no_backdrop(layout):
    assert "background-image" not in render(layout, ART_STAT)


def test_no_backdrop_and_no_scrim_without_artwork():
    html = render('classic', MOVIE_STAT)  # rows carry thumbs but no art
    assert "background-image" not in html
    assert "rgba(28, 28, 28" not in html


def test_backdrop_does_not_leak_into_other_classic_sections():
    """_shell is shared; only the stat card passes a backdrop."""
    recent = [{'recently_added': [
        {'title': 'A Movie', 'rating_key': '1', 'year': '2024', 'thumb': '/t/1', 'art': '/a/1',
         'summary': 's', 'added_at': '1750000000', 'duration': '3600000', 'media_type': 'movie',
         'type': 'movie', 'library_name': 'Movies', 'plex_url': '', 'rating': '8'},
    ]}]
    html = layouts_mod.render_recently_added('classic', recent, MIMEMultipart(), THEME, base_url="http://base")
    assert "background-image" not in html
