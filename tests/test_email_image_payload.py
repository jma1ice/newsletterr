"""How many bytes an embedded image costs.

tests/test_email_image_sizing.py covers how images are *displayed* (bounded by
width, never height); this file covers what actually goes on the wire.

`poster_max_height` is the one knob. The assembler stamps it on msg_root so it
reaches every attach helper, and blank means source resolution. It ships
non-blank because blank on a large library is what put 55 MB in a user's
weekly send (posters averaged 1.2 MB each and nothing capped them).
"""
import io
import sqlite3
from email.mime.multipart import MIMEMultipart

import pytest
from PIL import Image

from app.emails import images as images_mod
from app.emails.builders import layouts as layouts_mod
from app.emails.builders import coming_soon as coming_soon_mod
from app.emails.builders import ombi_requests as ombi_mod
from app.emails.builders import seerr_requests as seerr_mod

THEME = {
    'background': '#333333', 'text': '#62a1a4', 'primary': '#8acbd4',
    'secondary': '#222222', 'accent': '#62a1a4', 'card_bg': '#2d2d2d',
    'border': '#404040', 'muted_text': '#cccccc', 'email_theme': 'newsletterr_blue',
}
LAYOUTS = ("classic", "editorial", "digest", "spotlight")


def jpeg_bytes(w, h):
    """Noisy, so JPEG cannot compress it down to nothing and the byte counts
    below mean something."""
    import random
    img = Image.new('RGB', (w, h))
    px = img.load()
    rnd = random.Random(0)
    for y in range(0, h, 3):
        for x in range(0, w, 3):
            px[x, y] = (rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255))
    out = io.BytesIO()
    img.save(out, format='JPEG', quality=92)
    return out.getvalue()


def root(cap=None):
    msg = MIMEMultipart()
    if cap is not None:
        msg.poster_max_height = cap
    return msg


# --- the stamp

def test_an_unstamped_root_reads_as_no_cap():
    assert images_mod.size_cap(MIMEMultipart()) == 0


@pytest.mark.parametrize("stamped, expected", [
    (800, 800), ("600", 600), ("", 0), (0, 0), (None, 0), ("nonsense", 0), (-5, 0),
])
def test_the_stamp_is_read_defensively(stamped, expected):
    assert images_mod.size_cap(root(stamped)) == expected


def test_a_blank_setting_leaves_a_box_cap_unset():
    """Blank means source resolution, so a display box must not quietly
    reimpose a cap of its own."""
    assert images_mod.box_cap(root(""), 204) is None


def test_a_box_cap_takes_whichever_is_tighter():
    assert images_mod.box_cap(root(800), 204) == 204
    assert images_mod.box_cap(root(100), 204) == 100


# --- what reaches the message

@pytest.fixture()
def source_poster(monkeypatch):
    raw = jpeg_bytes(1500, 2250)

    class Response:
        status_code = 200
        content = raw
        headers = {'Content-Type': 'image/jpeg'}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(images_mod, "safe_get", lambda *a, **k: Response())
    return raw


def attached(msg):
    return msg.get_payload()[0].get_payload(decode=True)


def test_a_blank_setting_delivers_the_source_bytes(source_poster):
    msg = root("")
    images_mod.fetch_and_attach_image('http://host/p.jpg', msg, 'p')
    assert attached(msg) == source_poster


def test_the_setting_caps_an_image_with_no_other_sizing(source_poster):
    msg = root(800)
    images_mod.fetch_and_attach_image('http://host/p.jpg', msg, 'p')
    w, h = Image.open(io.BytesIO(attached(msg))).size
    assert h == 800
    assert w / h == pytest.approx(1500 / 2250, rel=0.01)  # aspect kept
    assert len(attached(msg)) < len(source_poster) / 4


def test_the_setting_shrinks_a_target_crop_rather_than_dropping_it(source_poster):
    """The crop is layout machinery: it gives a grid one aspect ratio. A cap
    tighter than the crop has to scale it, not disable it."""
    msg = root(60)
    images_mod.fetch_and_attach_image('http://host/p.jpg', msg, 'p', target=(200, 300))
    assert Image.open(io.BytesIO(attached(msg))).size == (40, 60)


def test_a_target_crop_survives_a_blank_setting(source_poster):
    msg = root("")
    images_mod.fetch_and_attach_image('http://host/p.jpg', msg, 'p', target=(200, 300))
    assert Image.open(io.BytesIO(attached(msg))).size == (200, 300)


def test_the_setting_wins_when_it_is_tighter_than_the_caller(source_poster):
    msg = root(50)
    images_mod.fetch_and_attach_image('http://host/p.jpg', msg, 'p', max_height=204)
    assert Image.open(io.BytesIO(attached(msg))).size[1] == 50


def test_the_setting_reaches_small_thumbnails(source_poster):
    msg = root(20)
    images_mod.fetch_and_attach_small_thumbnail('http://host/p.jpg', msg, 't', height=38)
    assert Image.open(io.BytesIO(attached(msg))).size[1] == 20


def test_the_setting_reaches_blurred_backdrops(source_poster):
    capped, uncapped = root(120), root("")
    images_mod.fetch_and_attach_blurred_image('http://host/p.jpg', capped, 'b')
    images_mod.fetch_and_attach_blurred_image('http://host/p.jpg', uncapped, 'b')
    assert Image.open(io.BytesIO(attached(capped))).size[1] == 120
    assert len(attached(capped)) < len(attached(uncapped))


def test_animated_images_are_never_re_encoded(monkeypatch):
    """A GIF flattened by PIL loses its animation, and the media block is
    where users drop them."""
    frames = [Image.new('P', (1600, 1600), c) for c in (1, 2)]
    buf = io.BytesIO()
    frames[0].save(buf, format='GIF', save_all=True, append_images=frames[1:])
    raw = buf.getvalue()

    class Response:
        status_code = 200
        content = raw
        headers = {'Content-Type': 'image/gif'}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(images_mod, "safe_get", lambda *a, **k: Response())
    msg = root(200)
    images_mod.fetch_and_attach_image('http://host/a.gif', msg, 'g')
    out = Image.open(io.BytesIO(attached(msg)))
    assert getattr(out, 'is_animated', False)
    assert out.size == (1600, 1600)


# --- every card-grid builder asks for a cap

@pytest.fixture()
def poster_calls(monkeypatch):
    calls = []

    def recorder(image_url, msg_root, cid_name, base_url="", max_height=None,
                 hosted_images_enabled=False, hosted_base_url="", target=None):
        calls.append({'cid': cid_name, 'max_height': max_height, 'target': target})
        return f"cid:{cid_name}"

    for mod in (layouts_mod, coming_soon_mod, ombi_mod, seerr_mod):
        monkeypatch.setattr(mod, "fetch_and_attach_image", recorder)
    monkeypatch.setattr(layouts_mod, "fetch_and_attach_small_thumbnail", lambda *a, **k: "cid:thumb")
    return calls


def assert_all_capped(calls):
    assert calls, "builder attached no artwork, so the test proves nothing"
    for call in calls:
        capped = (call['max_height'] or 0) > 0 or bool(call['target'])
        assert capped, f"{call['cid']} was attached at full resolution"


RECENT = [{'recently_added': [
    {'title': f'Movie {n}', 'rating_key': str(n), 'year': '2024', 'thumb': f'/t/{n}',
     'art': f'/a/{n}', 'summary': 's', 'added_at': '1750000000', 'duration': '3600000',
     'media_type': 'movie', 'type': 'movie', 'library_name': 'Movies', 'plex_url': '', 'rating': '8'}
    for n in range(12)]}]

SONARR = [{'title': 'Show', 'year': 2024, 'seasonNumber': 1, 'episodeNumber': 1,
           'airDateUtc': '2099-01-01T00:00:00Z', 'hasFile': False,
           'series': {'title': 'Show', 'year': 2024,
                      'images': [{'coverType': 'poster', 'remoteUrl': 'http://img/p.jpg'}]}}
          for _ in range(8)]

RADARR = [{'title': f'Film {n}', 'year': 2099, 'inCinemas': '2099-01-01T00:00:00Z', 'hasFile': False,
           'images': [{'coverType': 'poster', 'remoteUrl': 'http://img/p.jpg'}]}
          for n in range(8)]

SEERR = {'requests': [
    {'title': f'Req {n}', 'releaseDate': '2026-01-01', 'posterPath': '/p.jpg',
     'status': 1, 'mediaStatus': 3, 'requestedDate': '2026-01-01T00:00:00Z',
     'requestedBy': 'alice'}
    for n in range(8)]}


@pytest.mark.parametrize("layout", LAYOUTS)
def test_recently_added_cards_are_capped(layout, poster_calls):
    layouts_mod.render_recently_added(layout, RECENT, root(800), THEME,
                                      base_url="http://base", orientation="grid")
    assert_all_capped(poster_calls)


@pytest.mark.parametrize("layout", LAYOUTS)
def test_coming_soon_cards_are_capped(layout, poster_calls):
    layouts_mod.render_sonarr_coming_soon(layout, SONARR, root(800), THEME,
                                          base_url="http://base", view="grid")
    layouts_mod.render_radarr_coming_soon(layout, RADARR, root(800), THEME,
                                          base_url="http://base", view="grid")
    assert_all_capped(poster_calls)


@pytest.mark.parametrize("layout", sorted(layouts_mod._CARD_LAYOUTS))
def test_request_cards_are_capped(layout, poster_calls):
    # editorial and digest render requests as text rows, with no artwork to cap
    layouts_mod.render_requests(layout, 'seerr', SEERR, root(800), THEME, base_url="http://base")
    assert_all_capped(poster_calls)


def test_legacy_coming_soon_cards_are_capped(poster_calls):
    coming_soon_mod.build_sonarr_coming_soon_html_with_cids(SONARR, root(800), THEME, base_url="http://base")
    coming_soon_mod.build_radarr_coming_soon_html_with_cids(RADARR, root(800), THEME, base_url="http://base")
    assert_all_capped(poster_calls)


def test_legacy_seerr_cards_are_capped(poster_calls):
    seerr_mod.build_seerr_requests_html_with_cids(SEERR, root(800), THEME, base_url="http://base")
    assert_all_capped(poster_calls)


def test_card_caps_stand_down_when_the_setting_is_blank(poster_calls):
    """The user's escape hatch: clear the field, get source resolution."""
    layouts_mod.render_recently_added('classic', RECENT, root(""), THEME,
                                      base_url="http://base", orientation="grid")
    assert poster_calls
    assert all(not c['max_height'] and not c['target'] for c in poster_calls)


def test_the_cap_tracks_the_column_count():
    """Fewer columns means wider cards, so the cap has to grow with them."""
    from app.emails.builders.card_grid import poster_max_height_for
    assert poster_max_height_for(2) > poster_max_height_for(5)


# --- the setting ships non-blank

def test_the_assembler_stamps_the_setting_on_the_message():
    from app.emails.assemble import build_email_html_with_all_cids
    import inspect
    src = inspect.getsource(build_email_html_with_all_cids)
    assert "msg_root.poster_max_height = poster_max_height" in src


def test_the_default_is_not_blank():
    from app.settings_store import INT_COLUMNS
    assert INT_COLUMNS["poster_max_height"] > 0


def test_init_db_moves_a_blank_install_onto_the_default(tmp_path):
    """simmons777's install has the column blank, so the fix has to reach it
    without them touching settings."""
    from app.db import init_db
    db = str(tmp_path / "n.db")
    init_db(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO settings (id, poster_max_height) VALUES (1, '')")
    conn.commit()
    conn.close()

    init_db(db)

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT poster_max_height FROM settings WHERE id = 1").fetchone()[0] == '800'
    conn.close()


def test_a_chosen_value_survives_the_backfill(tmp_path):
    from app.db import init_db
    db = str(tmp_path / "n.db")
    init_db(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO settings (id, poster_max_height) VALUES (1, '300')")
    conn.commit()
    conn.close()

    init_db(db)

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT poster_max_height FROM settings WHERE id = 1").fetchone()[0] == '300'
    conn.close()
