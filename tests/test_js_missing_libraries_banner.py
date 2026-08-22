"""The stale-library banner, driven through the real renderMissingLibraries."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.js_helpers import _extract_js_function

REPO_ROOT = Path(__file__).resolve().parent.parent
ALERTS_JS = REPO_ROOT / "static/js/app/00-alerts.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the JS parity tests"
)

# Stand-in for the two banner nodes. textContent and innerHTML are tracked
# separately so a renderer that switched to markup is visible to the test.
STUB_DOM = """
const nodes = {
    missing_libraries_p: { style: { display: 'none' } },
    missing_libraries_text: { textContent: '', innerHTML: '' },
};
const document = { getElementById: (id) => nodes[id] || null };
"""

def _render(libraries):
    source = ALERTS_JS.read_text()
    script = (
        STUB_DOM
        + _extract_js_function(source, "renderMissingLibraries")
        + f"\nrenderMissingLibraries({json.dumps(libraries)});"
        + "\nconsole.log(JSON.stringify({"
        + "  display: nodes.missing_libraries_p.style.display,"
        + "  text: nodes.missing_libraries_text.textContent,"
        + "  html: nodes.missing_libraries_text.innerHTML,"
        + "}));"
    )
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)

def test_banner_stays_hidden_when_nothing_is_missing():
    assert _render([])["display"] == "none"

def test_banner_stays_hidden_when_the_key_is_absent():
    # Older cached responses and the Jellyfin path send no list at all.
    assert _render(None)["display"] == "none"

def test_banner_lists_every_missing_library_by_name():
    out = _render([
        {"section_id": "20", "name": "Deleted Movies", "type": "movie"},
        {"section_id": "5", "name": "Old Music", "type": "artist"},
    ])
    assert out["display"] == ""
    assert "Deleted Movies, Old Music" in out["text"]
    assert "2 libraries are" in out["text"]
    assert "Tautulli" in out["text"]

def test_single_library_reads_as_singular():
    out = _render([{"section_id": "20", "name": "Deleted Movies", "type": "movie"}])
    assert "1 library is" in out["text"]

def test_a_library_without_a_name_falls_back_to_its_section_id():
    out = _render([{"section_id": "20"}])
    assert "Section 20" in out["text"]

def test_library_names_are_written_as_text_not_markup():
    hostile = '<img src=x onerror="alert(1)">'
    out = _render([{"section_id": "20", "name": hostile, "type": "movie"}])
    # Present verbatim in textContent, and nothing was written as innerHTML.
    assert hostile in out["text"]
    assert out["html"] == ""
