"""Recommendations snap-in: per-user counts and the description toggle."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

# same brace-matching extractor the preview parity guards use
from tests.test_js_preview_parity import _extract_js_function

REPO_ROOT = Path(__file__).resolve().parent.parent
RECS_JS = REPO_ROOT / "static/js/app/09-recs-wrapped.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _counts(data):
    fn = _extract_js_function(RECS_JS.read_text(encoding="utf-8"), "recsCountsForUser")
    driver = f"""
{fn}
const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(recsCountsForUser(data)));
"""
    result = subprocess.run(["node", "-e", driver], input=json.dumps(data),
                            capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise AssertionError(f"node failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def test_counts_include_available_and_unavailable():
    out = _counts({
        "movie_posters": [{}] * 13, "movie_posters_unavailable": [{}] * 5,
        "show_posters": [{}] * 10, "show_posters_unavailable": [{}] * 8,
    })
    assert (out["movies"], out["shows"]) == (18, 18)
    assert out["label"] == "18 movies, 18 shows"
    assert "5 unavailable" in out["title"] and "8 unavailable" in out["title"]


def test_counts_singular_labels():
    out = _counts({"movie_posters": [{}], "show_posters": [{}]})
    assert out["label"] == "1 movie, 1 show"


def test_empty_payload_reads_as_no_recommendations():
    # the case that started this: conjurr answers 200 with nothing in it
    out = _counts({"movie_posters": [], "movie_posters_unavailable": [],
                   "show_posters": [], "show_posters_unavailable": []})
    assert (out["movies"], out["shows"]) == (0, 0)
    assert out["label"] == "no recommendations"
    assert "pull again" in out["title"]


def test_missing_keys_do_not_throw():
    assert _counts({})["label"] == "no recommendations"


def test_add_button_is_disabled_for_an_empty_user():
    source = RECS_JS.read_text(encoding="utf-8")
    rows = source.split("recs-add-btn", 1)[1]
    assert "isEmpty ? `disabled" in rows


# --- recs_show_description

RECS_ITEM = {
    "title": "Parasite", "year": 2019, "url": "", "vote": 8.5,
    "overview": "A poor family schemes their way into a wealthy household.",
}


def _render(show_description):
    from email.mime.multipart import MIMEMultipart
    from app.emails.builders.recommendations import build_recommendations_section_with_cids
    from app.theme import get_email_theme_colors

    msg_root = MIMEMultipart("related")
    msg_root.preview_mode = True
    return build_recommendations_section_with_cids(
        [RECS_ITEM], [], "Recommended Movies", msg_root, "recs-movies-1",
        get_email_theme_colors(), show_description=show_description,
    )


def test_descriptions_render_when_enabled(app, seeded_settings):
    with app.app_context():
        assert "schemes their way" in _render(True)


def test_descriptions_are_hidden_when_disabled(app, seeded_settings):
    with app.app_context():
        html = _render(False)
        assert "schemes their way" not in html
        assert "Parasite" in html  # only the overview goes away


def test_setting_reaches_the_renderer(app, seeded_settings):
    import sqlite3
    from app import config
    from app.cache import set_cached_data
    from app.emails.preview import render_preview_email

    set_cached_data("recommendations_json", {"7": {"movie_posters": [RECS_ITEM]}}, {"timestamp": 0})
    set_cached_data("filtered_users", {"7": "a@b.c"}, {"timestamp": 0})
    payload = {"subject": "s", "custom_html": "", "email_header_title": "",
               "selected_items": [{"id": "recs-user-a", "type": "recommendations", "userKey": "7"}],
               "expanded_collections": {}, "items_count": None}

    def _render_with(value):
        conn = sqlite3.connect(config.DB_PATH)
        conn.execute("UPDATE settings SET recs_show_description = ? WHERE id = 1", (value,))
        conn.commit()
        conn.close()
        with app.app_context():
            return render_preview_email(payload)

    try:
        assert "schemes their way" in _render_with("enabled")
        assert "schemes their way" not in _render_with("disabled")
    finally:
        _render_with("enabled")


def test_settings_form_round_trips_the_toggle(csrf_client):
    import sqlite3
    from app import config
    from tests.test_routes import SETTINGS_FORM

    client, token = csrf_client
    client.post("/settings", data={**SETTINGS_FORM, "csrf_token": token,
                                   "recs_show_description": "disabled"})
    conn = sqlite3.connect(config.DB_PATH)
    stored = conn.execute("SELECT recs_show_description FROM settings WHERE id = 1").fetchone()[0]
    conn.close()
    assert stored == "disabled"

    html = client.get("/settings").get_data(as_text=True)
    select = html.split('id="recs_show_description"', 1)[1].split("</select>", 1)[0]
    assert 'value="disabled" selected' in select.replace("  ", " ")
    assert 'value="enabled"  selected' not in select
