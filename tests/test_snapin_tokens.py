# Snap-in tokens in custom HTML (NEWS-32): parser and expansion unit tests.
# The render callback is stubbed; end-to-end rendering is pinned by the
# custom HTML golden in test_golden_sends.py.

from app.emails.snapin_tokens import expand_snapin_tokens, synthesize_snapin_item

STATS = [
    {"stat_title": "Most Watched Movies", "rows": [{"title": "Dune"}]},
    {"stat_title": "Most Active Users", "rows": [{"user": "a"}]},
]

def _echo_render(item, group_index=0):
    return f"[{item['type']}|{item.get('raLibrary') or item.get('mwLibrary') or item.get('library') or item.get('id')}]"

def test_simple_token_expands():
    out = expand_snapin_tokens("<p>before</p>{{snapin:wrapped}}<p>after</p>", _echo_render)
    assert out == "<p>before</p>[yearly_wrapped|token-wrapped]<p>after</p>"

def test_token_with_library_arg():
    out = expand_snapin_tokens("{{snapin:recently_added:Movies}}", _echo_render)
    assert out == "[recently added|Movies]"

def test_recently_added_count_arg():
    item = synthesize_snapin_item("recently_added", ["TV Shows", "5"], [])
    assert item["raLibrary"] == "TV Shows"
    assert item["raCount"] == "5"

def test_library_names_with_spaces_and_whitespace():
    item = synthesize_snapin_item("most_watched", [" TV Shows "], [])
    # expand strips whitespace around args before synthesis
    out = expand_snapin_tokens("{{snapin:most_watched: TV Shows }}", _echo_render)
    assert out == "[most_watched|TV Shows]"

def test_stats_token_resolves_title_to_index():
    item = synthesize_snapin_item("stats", ["most watched movies"], STATS)
    assert item == {"id": "stat-0", "name": "Most Watched Movies", "type": "stat"}

def test_stats_token_unknown_title_is_none():
    assert synthesize_snapin_item("stats", ["No Such Stat"], STATS) is None

def test_unknown_name_renders_html_comment():
    out = expand_snapin_tokens("x {{snapin:grafs}} y", _echo_render)
    assert out == "x <!-- newsletterr: unknown snapin token {{snapin:grafs}} --> y"

def test_unknown_token_comment_cannot_break_out():
    # '--' inside the token must not terminate the comment early, so any
    # markup smuggled into an unknown token stays inert inside the comment
    out = expand_snapin_tokens("{{snapin:bad:--><script>x</script>}}", _echo_render)
    assert out.startswith("<!--")
    assert out.endswith("-->")
    assert out.count("-->") == 1

def test_random_pick_requires_library():
    assert synthesize_snapin_item("random_pick", [], []) is None
    item = synthesize_snapin_item("random_pick", ["Movies"], [])
    assert item["type"] == "random_pick"
    assert item["library"] == "Movies"

def test_multiple_tokens_and_untouched_html():
    html = "<h1>News</h1>{{snapin:coming_soon_tv}}<hr>{{snapin:requests_ombi}}"
    out = expand_snapin_tokens(html, _echo_render)
    assert out == "<h1>News</h1>[sonarr_coming_soon|token-coming_soon_tv]<hr>[ombi_requests|token-requests_ombi]"

def test_html_without_tokens_passes_through_unchanged():
    html = "<p>plain {{ not_a_token }} html</p>"
    assert expand_snapin_tokens(html, _echo_render) == html
