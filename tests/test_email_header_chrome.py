"""Header chrome settings: the server-name line and the header background."""
import sqlite3

import pytest

LAYOUTS_WITH_NAME = ("classic", "editorial", "digest", "spotlight")
SERVER_NAME = "Test Server"
GRADIENT = "linear-gradient(135deg,"


@pytest.fixture()
def chrome_env(app, seeded_settings):
    """Sets the two chrome columns and returns a render helper."""
    from app import config
    from app.emails.assemble import build_complete_email_html_with_cid_logo

    def render(layout, show_server_name="disabled", header_bg=""):
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute(
            "UPDATE settings SET email_layout = ?, email_show_server_name = ?, email_header_bg = ? WHERE id = 1",
            (layout, show_server_name, header_bg),
        )
        conn.commit()
        conn.close()
        return build_complete_email_html_with_cid_logo(
            "<p>body</p>", SERVER_NAME, "Subject", "The Header", "", "", layout=layout
        )

    return render


@pytest.mark.parametrize("layout", LAYOUTS_WITH_NAME)
def test_server_name_is_hidden_by_default(chrome_env, layout):
    html = chrome_env(layout)
    assert SERVER_NAME not in html and SERVER_NAME.upper() not in html
    # the rest of the header survives
    assert "The Header" in html


@pytest.mark.parametrize("layout", LAYOUTS_WITH_NAME)
def test_server_name_can_be_shown(chrome_env, layout):
    html = chrome_env(layout, show_server_name="enabled")
    assert SERVER_NAME in html or SERVER_NAME.upper() in html


@pytest.mark.parametrize("stored", [None, ""])
def test_unset_column_means_hidden(chrome_env, stored):
    """Rows predating the column (NULL) fall through to the stored default."""
    assert chrome_env("classic", show_server_name=stored).count(SERVER_NAME) == 0


def test_showing_the_name_puts_the_slash_back_in_the_digest_title(chrome_env):
    hidden = chrome_env("digest")
    shown = chrome_env("digest", show_server_name="enabled")
    assert "/ The Header" in shown
    assert "/ The Header" not in hidden
    assert "The Header" in hidden


def test_legacy_header_never_printed_the_name_either_way(chrome_env):
    hidden = chrome_env("legacy")
    shown = chrome_env("legacy", show_server_name="enabled")
    assert SERVER_NAME not in shown and SERVER_NAME.upper() not in shown
    assert shown == hidden


@pytest.mark.parametrize("layout", ("legacy", "classic"))
def test_header_background_defaults_to_the_gradient(chrome_env, layout):
    assert GRADIENT in chrome_env(layout)


@pytest.mark.parametrize("layout", ("legacy", "classic", "editorial", "digest"))
def test_solid_header_background_replaces_the_default(chrome_env, layout):
    html = chrome_env(layout, header_bg="#123456")
    assert "#123456" in html
    if layout in ("legacy", "classic"):
        assert GRADIENT not in html


def test_editorial_and_digest_headers_use_the_chosen_color_over_card_bg(chrome_env):
    for layout in ("editorial", "digest"):
        default_html = chrome_env(layout)
        custom_html = chrome_env(layout, header_bg="#123456")
        assert "background-color: #2d2d2d" in default_html
        assert "background-color: #123456" in custom_html


@pytest.mark.parametrize("bad", ["red; } body { background: url(x)", "#zzzzzz", "#12345", "rgb(1,2,3)"])
def test_non_hex_header_background_is_ignored(chrome_env, bad):
    """The value lands in a style attribute, so only #rrggbb may pass."""
    html = chrome_env("classic", header_bg=bad)
    assert bad not in html
    assert GRADIENT in html


# --- settings form round trip

def test_settings_form_round_trips_the_chrome_fields(csrf_client):
    """Form -> DB -> rendered form, including the gradient/solid mode gate."""
    from tests.test_routes import SETTINGS_FORM
    from app import config

    client, token = csrf_client
    base = {**SETTINGS_FORM, "csrf_token": token}

    client.post("/settings", data={**base, "email_layout": "digest",
                                   "email_show_server_name": "enabled",
                                   "email_header_bg_mode": "solid",
                                   "email_header_bg": "#123456"})
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute(
        "SELECT email_show_server_name, email_header_bg FROM settings WHERE id = 1").fetchone()
    conn.close()
    assert row == ("enabled", "#123456")

    html = client.get("/settings").get_data(as_text=True)
    assert 'value="#123456"' in html

    # switching back to the gradient clears the stored color even though the
    # picker still submits its last value
    client.post("/settings", data={**base, "email_layout": "digest",
                                   "email_header_bg_mode": "gradient",
                                   "email_header_bg": "#123456"})
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute("SELECT email_show_server_name, email_header_bg FROM settings WHERE id = 1").fetchone()
    conn.close()
    # an absent select posts nothing, which means the default (hide)
    assert row == ("disabled", "")


# --- header eyebrow text and the stock auto text

@pytest.fixture()
def header_text_env(app, seeded_settings):
    """Sets the header-text columns and renders a layout."""
    from app import config
    from app.emails.assemble import build_complete_email_html_with_cid_logo

    def render(layout, title="The Header", eyebrow="", auto="disabled", show_name="disabled"):
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute(
            "UPDATE settings SET email_show_server_name = ?, email_eyebrow_text = ?, "
            "email_auto_header_text = ? WHERE id = 1",
            (show_name, eyebrow, auto),
        )
        conn.commit()
        conn.close()
        return build_complete_email_html_with_cid_logo(
            "<p>b</p>", SERVER_NAME, "Subject", title, "", "", layout=layout)

    return render


def test_auto_header_text_is_off_by_default(header_text_env):
    """A hidden server name used to substitute stock filler; now the line is
    simply left out unless the setting asks for it."""
    html = header_text_env("spotlight")
    assert SERVER_NAME not in html
    assert "Your server" not in html
    assert "The Header" in html


def test_auto_header_text_restores_the_stock_wording(header_text_env):
    assert "Your server" in header_text_env("spotlight", auto="enabled")
    assert "This week on the server" in header_text_env("spotlight", title="", auto="enabled")
    assert "Your server, this month" in header_text_env("editorial", title="", auto="enabled")


@pytest.mark.parametrize("layout", ("spotlight", "editorial"))
def test_blank_header_title_prints_nothing_when_auto_is_off(header_text_env, layout):
    html = header_text_env(layout, title="")
    assert "This week on the server" not in html
    assert "Your server" not in html


@pytest.mark.parametrize("layout", ("spotlight", "editorial"))
def test_custom_eyebrow_wins_over_the_name_and_the_auto_text(header_text_env, layout):
    html = header_text_env(layout, eyebrow="Fresh this week", auto="enabled", show_name="enabled")
    assert "Fresh this week" in html
    assert "Your server" not in html
    # the eyebrow replaces the name on that line, the name keeps its own slot
    # in editorial only
    assert (SERVER_NAME.upper() in html) if layout == "editorial" else (SERVER_NAME not in html)


def test_eyebrow_text_is_escaped(header_text_env):
    html = header_text_env("spotlight", eyebrow='<script>alert(1)</script>')
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_settings_form_round_trips_the_header_text_fields(csrf_client):
    from tests.test_routes import SETTINGS_FORM
    from app import config

    client, token = csrf_client
    base = {**SETTINGS_FORM, "csrf_token": token}

    client.post("/settings", data={**base, "email_eyebrow_text": "  Fresh this week  ",
                                   "email_auto_header_text": "enabled"})
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute(
        "SELECT email_eyebrow_text, email_auto_header_text FROM settings WHERE id = 1").fetchone()
    conn.close()
    assert row == ("Fresh this week", "enabled")

    # an absent select posts nothing, which means the default (off)
    client.post("/settings", data={**base, "email_eyebrow_text": ""})
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute(
        "SELECT email_eyebrow_text, email_auto_header_text FROM settings WHERE id = 1").fetchone()
    conn.close()
    assert row == ("", "disabled")
