"""Email density: compact vs expanded, applied across every layout."""
from email.mime.multipart import MIMEMultipart

import pytest

from app.emails import density
from app.emails.builders import layouts as layouts_mod

THEME = {
    'background': '#333333', 'text': '#62a1a4', 'primary': '#8acbd4',
    'secondary': '#222222', 'accent': '#62a1a4', 'card_bg': '#2d2d2d',
    'border': '#404040', 'muted_text': '#cccccc', 'email_theme': 'newsletterr_blue',
}
RECENT = [{'recently_added': [
    {'title': 'The Grand Voyage', 'rating_key': '1', 'year': '2024', 'thumb': '/t/1',
     'summary': 'A crew sails past the edge of the map.', 'updated_at': '1750000000',
     'duration': '6900000', 'media_type': 'movie', 'type': 'movie',
     'library_name': 'Movies', 'plex_url': 'https://plex/1'},
    {'title': 'Neon Harbor', 'rating_key': '2', 'year': '2023', 'thumb': '/t/2',
     'summary': 'Rain, neon, and one honest cop.', 'updated_at': '1749000000',
     'duration': '5400000', 'media_type': 'movie', 'type': 'movie',
     'library_name': 'Movies', 'plex_url': ''},
]}]
MOVIE_STAT = {'stat_title': 'Most Watched Movies', 'rows': [
    {'title': 'Dune', 'year': '2021', 'total_plays': 42, 'thumb': '/t/1', 'art': '/a/1'},
]}

@pytest.fixture(autouse=True)
def _stub_image_fetches(monkeypatch):
    monkeypatch.setattr(layouts_mod, "fetch_and_attach_image", lambda *a, **k: "cid:img")
    monkeypatch.setattr(layouts_mod, "fetch_and_attach_small_thumbnail", lambda *a, **k: "cid:thumb")
    monkeypatch.setattr(layouts_mod, "fetch_and_attach_blurred_image", lambda *a, **k: "cid:bg")
    monkeypatch.setattr(layouts_mod, "email_icon_img", lambda *a, **k: "")

def theme_for(layout, value=""):
    return density.stamp(layouts_mod.apply_theme(layout, THEME), layout, value)

def msg():
    return MIMEMultipart('related')

# --- resolution

@pytest.mark.parametrize("layout,expected", [
    ('legacy', 'expanded'), ('classic', 'expanded'), ('spotlight', 'expanded'),
    ('editorial', 'compact'), ('digest', 'compact'),
])
def test_blank_resolves_to_the_layouts_own_density(layout, expected):
    assert density.resolve(layout, "") == expected
    assert density.resolve(layout, None) == expected
    assert density.resolve(layout, "nonsense") == expected

def test_explicit_values_win_for_every_layout():
    for layout in density.NATURAL:
        assert density.resolve(layout, 'compact') == 'compact'
        assert density.resolve(layout, 'expanded') == 'expanded'

def test_natural_density_is_never_the_variant():
    for layout, natural in density.NATURAL.items():
        assert not density.is_variant(theme_for(layout, natural), layout)
        assert not density.is_variant(theme_for(layout, ""), layout)
        other = 'compact' if natural == 'expanded' else 'expanded'
        assert density.is_variant(theme_for(layout, other), layout)

def test_layout_rides_on_the_theme_for_the_shared_builders():
    # recommendations/collections take a theme but no layout argument
    assert density.layout_of(theme_for('digest', 'expanded')) == 'digest'
    p3 = density.picker3(theme_for('digest', 'expanded'))
    assert p3('tight', 'natural', 'roomy') == 'roomy'
    p3 = density.picker3(theme_for('classic', 'compact'))
    assert p3('tight', 'natural', 'roomy') == 'tight'
    p3 = density.picker3(theme_for('classic', ''))
    assert p3('tight', 'natural', 'roomy') == 'natural'

# --- artwork

@pytest.mark.parametrize("layout", ['legacy', 'classic', 'spotlight'])
def test_compact_variant_drops_artwork(layout):
    assert not density.show_art(theme_for(layout, 'compact'), layout)
    assert density.show_art(theme_for(layout, ''), layout)

@pytest.mark.parametrize("layout", ['editorial', 'digest'])
def test_naturally_compact_layouts_keep_their_artwork(layout):
    # editorial/digest are compact by nature; compact is not their variant, so
    # nothing about them changes and their goldens hold
    assert density.show_art(theme_for(layout, 'compact'), layout)
    assert density.show_art(theme_for(layout, 'expanded'), layout)

def test_compact_grids_stack_into_one_column():
    assert density.columns(theme_for('classic', 'compact'), 'classic', 5) == 1
    assert density.columns(theme_for('classic', ''), 'classic', 5) == 5

# --- rendered output

def test_classic_compact_has_no_posters_and_reads_as_rows():
    natural = layouts_mod.render_recently_added('classic', RECENT, msg(), theme_for('classic', ''))
    compact = layouts_mod.render_recently_added('classic', RECENT, msg(), theme_for('classic', 'compact'))
    assert '<img' in natural
    assert '<img' not in compact
    assert 'The Grand Voyage' in compact and 'Neon Harbor' in compact

def test_spotlight_compact_drops_the_hero_poster_but_keeps_the_hero():
    compact = layouts_mod.render_recently_added('spotlight', RECENT, msg(), theme_for('spotlight', 'compact'))
    assert '<img' not in compact
    assert 'The Grand Voyage' in compact

def test_editorial_expanded_grows_the_poster():
    natural = layouts_mod.render_recently_added('editorial', RECENT, msg(), theme_for('editorial', ''))
    expanded = layouts_mod.render_recently_added('editorial', RECENT, msg(), theme_for('editorial', 'expanded'))
    assert 'width: 96px' in natural
    assert 'width: 132px' in expanded

def test_digest_expanded_grows_its_rows():
    natural = layouts_mod.render_stats('digest', MOVIE_STAT, msg(), theme_for('digest', ''))
    expanded = layouts_mod.render_stats('digest', MOVIE_STAT, msg(), theme_for('digest', 'expanded'))
    assert 'padding: 5px 0' in natural
    assert 'padding: 9px 0' in expanded

def test_classic_compact_drops_the_blurred_stat_background():
    natural = layouts_mod.render_stats('classic', MOVIE_STAT, msg(), theme_for('classic', ''))
    compact = layouts_mod.render_stats('classic', MOVIE_STAT, msg(), theme_for('classic', 'compact'))
    assert 'background-image' in natural
    assert 'background-image' not in compact

def test_editorial_rows_keep_a_space_between_title_and_meta():
    # minify_email_html() collapses whitespace sitting between two tags, so the
    # separator has to live inside the text node
    row = layouts_mod._dated_row(theme_for('editorial', ''), 'Jul 4', 'Some Show', 'S01E02')
    assert '</b><span' in row
    assert '> S01E02</span>' in row

# --- settings round trip

def test_settings_form_round_trips_the_density(csrf_client):
    """Form -> DB -> rendered form, and a blank column shows the layout's own
    density so the dropdown never lies about what the email renders as."""
    import sqlite3

    from tests.test_routes import SETTINGS_FORM
    from app import config

    client, token = csrf_client
    base = {**SETTINGS_FORM, "csrf_token": token}

    client.post("/settings", data={**base, "email_layout": "classic", "email_density": "compact"})
    conn = sqlite3.connect(config.DB_PATH)
    assert conn.execute("SELECT email_density FROM settings WHERE id = 1").fetchone()[0] == "compact"
    conn.close()

    # anything that is not a density stores blank, which means "natural"
    client.post("/settings", data={**base, "email_layout": "classic", "email_density": "roomy"})
    conn = sqlite3.connect(config.DB_PATH)
    assert conn.execute("SELECT email_density FROM settings WHERE id = 1").fetchone()[0] == ""

    conn.execute("UPDATE settings SET email_density = '', email_layout = 'digest' WHERE id = 1")
    conn.commit()
    conn.close()

    html = client.get("/settings").get_data(as_text=True)
    # digest is naturally compact, so the blank column renders as Compact
    assert '<option value="compact" selected>Compact</option>' in html.replace(' >', '>')
