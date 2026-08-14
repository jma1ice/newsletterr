"""Email images must be bounded by width, never by height alone."""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDERS = sorted((REPO_ROOT / "app/emails/builders").glob("*.py"))

THEME = {
    'card_bg': '#181818', 'border': '#2b2b2b', 'text': '#c9c9c9',
    'muted_text': '#8e8e8e', 'accent': '#62a1a4', 'primary': '#8acbd4',
    'secondary': '#222', 'background': '#0f0f0f',
}


def test_the_head_css_still_forces_height_auto():
    """The premise of everything below. If this rule ever goes away, the
    width-only sizing is no longer required and this file should be revisited.
    """
    theme = (REPO_ROOT / "app/theme.py").read_text(encoding="utf-8")
    assert re.search(r"img\s*\{\{[^}]*height:\s*auto\s*!important", theme, re.S)


@pytest.mark.parametrize("path", BUILDERS, ids=lambda p: p.name)
def test_no_builder_emits_an_image_with_auto_width(path):
    """`width:auto` on an <img> leaves it unbounded once the head CSS has
    forced the height to auto as well."""
    source = path.read_text(encoding="utf-8")
    for match in re.finditer(r"<img\b[^>]*>", source):
        tag = match.group(0)
        if re.search(r"width:\s*auto", tag):
            pytest.fail(f"{path.name}: image sized with width:auto -> {tag[:120]}")


def _wrapped_html(with_user=True):
    from email.mime.multipart import MIMEMultipart
    from app.emails.builders.stats import build_yearly_wrapped_html_with_cids

    root = MIMEMultipart('related')
    root.preview_mode = True
    stats = [
        {'stat_title': 'Most Watched Movies',
         'rows': [{'title': 'A Film', 'total_plays': 3, 'thumb': '/library/metadata/1/thumb'}]},
        {'stat_title': 'Most Active Users',
         'rows': [{'user': 'someone', 'total_plays': 9,
                   'user_thumb': 'https://plex.tv/users/x/avatar'}]},
    ]
    return build_yearly_wrapped_html_with_cids(
        stats, root, THEME, year=2026, base_url="", include_user_info=with_user)


def test_year_in_plex_poster_is_width_bounded():
    """Regression: the poster carried height:60px and width:auto, so nothing
    bounded it and it rendered full size."""
    html = _wrapped_html()
    posters = [tag for tag in re.findall(r"<img\b[^>]*>", html)
               if "border-radius:50%" not in tag and "email-icons" not in tag]
    assert posters, "no poster image rendered; fixture no longer exercises this"
    for tag in posters:
        assert re.search(r"width:\s*\d+px", tag), tag
        assert "width:auto" not in tag.replace(" ", ""), tag


def test_year_in_plex_avatar_keeps_its_square_sizing():
    """The round avatar always had a width and was never affected; it should
    not have been changed by the poster fix."""
    html = _wrapped_html()
    avatars = [tag for tag in re.findall(r"<img\b[^>]*>", html) if "border-radius:50%" in tag]
    assert avatars, "no avatar rendered; fixture no longer exercises this"
    for tag in avatars:
        assert "width:60px" in tag.replace(" ", "")
        assert "height:60px" in tag.replace(" ", "")


def test_wrapped_renders_nothing_extra_without_thumbnails():
    """The thumb-less path is what the goldens pin, so it must stay clean."""
    from email.mime.multipart import MIMEMultipart
    from app.emails.builders.stats import build_yearly_wrapped_html_with_cids

    root = MIMEMultipart('related')
    root.preview_mode = True
    stats = [{'stat_title': 'Most Watched Movies',
              'rows': [{'title': 'A Film', 'total_plays': 3}]}]
    html = build_yearly_wrapped_html_with_cids(stats, root, THEME, year=2026)
    assert "A Film" in html
    # no stray <img> and no empty gap where one would have been
    posters = [t for t in re.findall(r"<img\b[^>]*>", html) if "email-icons" not in t]
    assert posters == []
