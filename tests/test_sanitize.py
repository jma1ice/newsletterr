"""the HTML allowlist applied to rich text blocks."""
import pytest

from app.emails.sanitize import sanitize_html


# ------------------------------------------------------------- what survives

@pytest.mark.parametrize("html", [
    "<b>bold</b>",
    "<strong>bold</strong><em>italic</em><u>under</u>",
    "<p>a paragraph</p>",
    "<div>block</div>",
    "<span style=\"color: #ff0000\">red</span>",
    "<ul><li>one</li><li>two</li></ul>",
    "<h2>heading</h2>",
    "<blockquote>quoted</blockquote>",
    "<br>",
    "<table><tr><td>cell</td></tr></table>",
])
def test_ordinary_formatting_is_preserved(html):
    assert sanitize_html(html) == html


def test_the_builtin_html_link_block_still_works():
    """createTextBlock('html-link') emits exactly this."""
    html = '<a href="https://www.google.com" target="_blank">Click to go to Google</a>'
    out = sanitize_html(html)
    assert 'href="https://www.google.com"' in out
    assert 'target="_blank"' in out
    assert "Click to go to Google" in out


def test_plain_text_passes_through():
    assert sanitize_html("just some words") == "just some words"


def test_text_is_escaped_not_dropped():
    assert sanitize_html("5 < 6 & 7 > 2") == "5 &lt; 6 &amp; 7 &gt; 2"


def test_empty_input():
    assert sanitize_html("") == ""
    assert sanitize_html(None) == ""


# --------------------------------------------------------------- what cannot

def test_script_tags_go_with_their_contents():
    out = sanitize_html("before<script>alert(1)</script>after")
    assert "alert" not in out
    assert "script" not in out
    assert out == "beforeafter"


@pytest.mark.parametrize("tag", ["iframe", "object", "embed", "form", "svg", "noscript"])
def test_dangerous_containers_are_dropped_whole(tag):
    out = sanitize_html(f"a<{tag}>payload</{tag}>b")
    assert "payload" not in out
    assert tag not in out


def test_event_handlers_are_stripped():
    out = sanitize_html('<div onclick="steal()">text</div>')
    assert "onclick" not in out
    assert "steal" not in out
    assert "text" in out


def test_event_handlers_in_any_casing():
    out = sanitize_html('<div OnClIcK="x()" ONMOUSEOVER="y()">t</div>')
    assert "onclick" not in out.lower()
    assert "onmouseover" not in out.lower()


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "  javascript:alert(1)",
    "java\tscript:alert(1)",
    "java\nscript:alert(1)",
    "vbscript:msgbox(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
])
def test_dangerous_url_schemes_are_refused(url):
    out = sanitize_html(f'<a href="{url}">click</a>')
    assert "javascript" not in out.lower()
    assert "vbscript" not in out.lower()
    assert "data:text/html" not in out.lower()
    assert "click" in out          # the text survives, only the href goes


def test_img_onerror_payload():
    out = sanitize_html('<img src=x onerror=alert(1)>')
    assert "onerror" not in out
    assert "alert" not in out


def test_unknown_tags_are_unwrapped_keeping_their_text():
    assert sanitize_html("<marquee>hello</marquee>") == "hello"
    assert sanitize_html("<custom-el>text</custom-el>") == "text"


def test_comments_are_dropped():
    """Conditional comments are an email-client attack surface."""
    out = sanitize_html("a<!--[if IE]><script>x</script><![endif]-->b")
    assert "script" not in out
    assert "if IE" not in out


def test_style_tag_contents_never_leak_as_text():
    out = sanitize_html("<style>body{display:none}</style>visible")
    assert "display:none" not in out
    assert out == "visible"


# ------------------------------------------------------------- style filter

def test_allowed_style_properties_survive():
    out = sanitize_html('<span style="color: red; font-size: 18px">x</span>')
    assert "color: red" in out
    assert "font-size: 18px" in out


def test_disallowed_style_properties_are_dropped():
    out = sanitize_html('<div style="position: fixed; color: red">x</div>')
    assert "position" not in out
    assert "color: red" in out


@pytest.mark.parametrize("value", [
    "width: expression(alert(1))",
    "background-color: url(javascript:alert(1))",
    "color: red; behavior: url(x.htc)",
])
def test_style_values_that_execute_are_dropped(value):
    out = sanitize_html(f'<div style="{value}">x</div>')
    assert "expression" not in out.lower()
    assert "javascript" not in out.lower()
    assert "behavior" not in out.lower()


def test_style_attribute_disappears_when_nothing_survives():
    out = sanitize_html('<div style="position: absolute">x</div>')
    assert "style" not in out


# ------------------------------------------------------------------ mangling

def test_unbalanced_tags_are_closed():
    """An unclosed tag would otherwise swallow the rest of the email."""
    out = sanitize_html("<b>bold")
    assert out == "<b>bold</b>"


def test_stray_close_tags_are_ignored():
    assert sanitize_html("text</b>") == "text"


def test_nested_unbalanced_tags_close_in_order():
    out = sanitize_html("<div><b><i>x</div>")
    assert out.endswith("</i></b></div>")


def test_target_blank_gains_noopener():
    out = sanitize_html('<a href="https://x.example" target="_blank">x</a>')
    assert 'rel="noopener noreferrer"' in out


def test_existing_rel_is_not_overwritten():
    out = sanitize_html('<a href="https://x.example" target="_blank" rel="nofollow">x</a>')
    assert out.count("rel=") == 1
    assert 'rel="nofollow"' in out


def test_quotes_in_attribute_values_cannot_break_out():
    out = sanitize_html('<a href="https://x.example/&quot;onmouseover=alert(1)">x</a>')
    assert "onmouseover=alert" not in out.replace("&quot;", '"') or "&quot;" in out


def test_relative_and_root_urls_are_kept():
    assert 'href="/unsubscribe"' in sanitize_html('<a href="/unsubscribe">x</a>')
    assert 'src="images/a.png"' in sanitize_html('<img src="images/a.png">')


def test_cid_urls_are_kept():
    """Inline attachments are how every poster in this app is delivered."""
    assert 'src="cid:poster-1"' in sanitize_html('<img src="cid:poster-1">')


def test_malformed_input_does_not_raise():
    for junk in ("<<<>>>", "<a href=", "<<b>>x", "<!", "<a href='x", "&#x3c;script&#x3e;"):
        sanitize_html(junk)   # must not raise


# ------------------------- what the editor's own controls emit must survive

def test_link_underline_removal_survives():
    """Mail clients underline links by default; only an explicit inline
    text-decoration overrides that, so it must not be filtered out."""
    out = sanitize_html('<a href="https://x.example" style="text-decoration: none;">x</a>')
    assert "text-decoration: none" in out


def test_text_colour_survives_in_both_notations():
    for value in ("color: #ff3366", "color: rgb(255, 51, 102)"):
        out = sanitize_html(f'<span style="{value}">x</span>')
        assert value.split(': ')[1] in out, out


def test_a_coloured_link_keeps_both_href_and_colour():
    out = sanitize_html('<a href="https://x.example" style="color: rgb(255, 51, 102);">x</a>')
    assert 'href="https://x.example"' in out
    assert "color: rgb(255, 51, 102)" in out


def test_ordered_lists_and_their_layout_styles_survive():
    """The list normalization is what stops a centred block stranding the
    marker away from its text, so it has to reach the email intact."""
    out = sanitize_html(
        '<ol style="display: inline-block; text-align: left; margin: 0px; padding-left: 1.5em;">'
        '<li>one</li></ol>')
    assert "<ol" in out and "<li>one</li>" in out
    for prop in ("display: inline-block", "text-align: left", "padding-left: 1.5em"):
        assert prop in out, prop


# ------------------------------------------------- the text block that uses it

THEME = {'text': '#c9c9c9'}


def test_text_block_sanitizes_its_content():
    from app.emails.blocks import build_text_block_html
    html = build_text_block_html('<b>ok</b><script>alert(1)</script>', 'textblock', THEME)
    assert "<b>ok</b>" in html
    assert "alert" not in html


def test_text_block_without_options_is_unchanged():
    """The property the goldens rest on: no opts means no extra declarations."""
    from app.emails.blocks import build_text_block_html
    plain = build_text_block_html('hello', 'textblock', THEME)
    with_empty = build_text_block_html('hello', 'textblock', THEME, opts={})
    with_blanks = build_text_block_html(
        'hello', 'textblock', THEME,
        opts={'align': '', 'fontSize': '', 'fontFamily': ''})
    assert plain == with_empty == with_blanks


@pytest.mark.parametrize("block_type", ["textblock", "titleblock", "headerblock"])
def test_alignment_override(block_type):
    from app.emails.blocks import build_text_block_html
    html = build_text_block_html('hi', block_type, THEME, opts={'align': 'right'})
    # appended after the built-in declaration, so CSS later-wins
    assert html.rindex('text-align: right') > html.rindex('text-align: center')


def test_font_size_override_applies():
    from app.emails.blocks import build_text_block_html
    assert 'font-size: 24px' in build_text_block_html(
        'hi', 'textblock', THEME, opts={'fontSize': 24})


@pytest.mark.parametrize("bad", [0, 7, 200, -3, 'abc', None, '', 'NaN'])
def test_out_of_range_font_sizes_are_ignored(bad):
    """A plain text block carries no font-size of its own, so a rejected
    override must leave the declaration absent entirely."""
    from app.emails.blocks import build_text_block_html
    html = build_text_block_html('hi', 'textblock', THEME, opts={'fontSize': bad})
    assert 'font-size' not in html


def test_font_family_override_uses_a_known_stack():
    from app.emails.blocks import build_text_block_html, TEXT_BLOCK_FONTS
    html = build_text_block_html('hi', 'textblock', THEME, opts={'fontFamily': 'serif'})
    assert TEXT_BLOCK_FONTS['serif'] in html


def test_unknown_font_family_is_ignored():
    from app.emails.blocks import build_text_block_html
    html = build_text_block_html('hi', 'textblock', THEME, opts={'fontFamily': 'comic-sans'})
    assert 'comic-sans' not in html


def test_newlines_still_become_breaks():
    from app.emails.blocks import build_text_block_html
    html = build_text_block_html('one\ntwo', 'textblock', THEME)
    assert 'one<br>two' in html
