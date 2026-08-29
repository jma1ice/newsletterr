"""Regression guards for grouped Recently Added library snap-ins."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.js_helpers import _extract_js_function

REPO_ROOT = Path(__file__).resolve().parent.parent
RECENT_JS = REPO_ROOT / "static/js/app/02-recently-added.js"
BUILDER_JS = REPO_ROOT / "static/js/app/07-email-builder.js"
BUILDER_CSS = REPO_ROOT / "static/css/pages/builder.css"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the JS parity tests"
)


def _hero_choices(payload, libraries):
    source = RECENT_JS.read_text(encoding="utf-8")
    program = "\n".join([
        f"const recentPayload = {json.dumps(payload)};",
        "const flatten = arr => arr.flatMap(x => x?.recently_added || []);",
        _extract_js_function(source, "raLibraryNames"),
        _extract_js_function(source, "raAddedValue"),
        _extract_js_function(source, "raDedupeKey"),
        _extract_js_function(source, "raItemsForLibraries"),
        f"console.log(JSON.stringify(raItemsForLibraries({json.dumps(libraries)})));",
    ])
    result = subprocess.run(
        ["node", "-e", program], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_grouped_hero_choices_are_merged_deduped_and_sorted():
    payload = [
        {"recently_added": [
            {"title": "Old", "rating_key": "1", "guid": "plex://old", "library_name": "Movies", "added_at": "100"},
            {"title": "Shared", "rating_key": "2", "guid": "plex://shared", "library_name": "Movies", "added_at": "200"},
        ]},
        {"recently_added": [
            {"title": "Newest", "rating_key": "3", "guid": "plex://new", "library_name": "Requested Movies", "added_at": "400"},
            {"title": "Shared", "rating_key": "4", "guid": "plex://shared", "library_name": "Requested Movies", "added_at": "300"},
        ]},
    ]

    choices = _hero_choices(payload, ["Movies", "Requested Movies"])

    assert [choice["title"] for choice in choices] == ["Newest", "Shared", "Old"]
    assert choices[1]["key"] == "4"


def test_builder_stores_grouped_libraries_without_replacing_legacy_key():
    source = BUILDER_JS.read_text(encoding="utf-8")

    assert "extra.raLibraries = libraries" in source
    assert "item.raLibraries || item.raLibrary" in source
    assert "extra.raLibrary = btn.dataset.lib" in source


def test_combined_row_requires_two_checked_libraries():
    source = RECENT_JS.read_text(encoding="utf-8")
    css = BUILDER_CSS.read_text(encoding="utf-8")

    assert "Combined libraries" in source
    assert "querySelectorAll('.ra-group-library:checked').length < 2" in source
    assert 'class="snapin-row ra-group-row' in source
    assert ".ra-group-row .ra-library-options" in css
    assert "flex: 1 0 100%" in css
