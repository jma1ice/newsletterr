"""Regression guards for text snap-in content surviving a page reload."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_js_preview_parity import _extract_js_function

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDER_JS = REPO_ROOT / "static/js/app/07-email-builder.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the JS parity tests"
)

# Minimal stand-in for the builder page. Textareas only exist for ids listed in
# `rendered`, which is how a freshly loaded page looks before the first render.
STUB_DOM = """
let selectedItems = JSON.parse(process.env.ITEMS);
const rendered = JSON.parse(process.env.RENDERED);
const document = {
    querySelector(sel) {
        const m = /data-textblock-id="([^"]+)"/.exec(sel);
        if (m && rendered[m[1]] !== undefined) {
            return { get value() { return rendered[m[1]]; },
                     set value(v) { rendered[m[1]] = v; } };
        }
        return null;
    },
};
"""


def _run(script, items, rendered=None):
    """Run the real accessors plus `script` under node, return its JSON stdout."""
    source = BUILDER_JS.read_text(encoding="utf-8")
    driver = "\n".join([
        STUB_DOM,
        _extract_js_function(source, "getTextBlockContent"),
        _extract_js_function(source, "setTextBlockContent"),
        _extract_js_function(source, "getTextBlockDisplayName"),
        script,
    ])
    result = subprocess.run(
        ["node", "-e", driver],
        capture_output=True, text=True, timeout=30,
        env={**os.environ,
             "ITEMS": json.dumps(items),
             "RENDERED": json.dumps(rendered or {})},
    )
    if result.returncode != 0:
        raise AssertionError(f"node failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def test_content_survives_when_the_editor_is_not_rendered_yet():
    """A restored draft or template has no textareas yet: read item.content."""
    items = [{"id": "text-block-1", "type": "textblock", "name": "What's the deal?",
              "content": "What's the deal?"}]
    got = _run(
        "process.stdout.write(JSON.stringify(getTextBlockContent('text-block-1')))",
        items,
    )
    assert got == "What's the deal?"


def test_rendered_editor_wins_over_stale_item_content():
    """While the block is on screen the textarea is the live value."""
    items = [{"id": "text-block-1", "type": "textblock", "content": "old"}]
    got = _run(
        "process.stdout.write(JSON.stringify(getTextBlockContent('text-block-1')))",
        items, rendered={"text-block-1": "typed since"},
    )
    assert got == "typed since"


def test_set_records_content_on_the_item_without_a_textarea():
    """Template load sets content before the editors exist; it must stick."""
    items = [{"id": "intro-block-1", "type": "textblock", "name": "New text block"}]
    got = _run(
        "setTextBlockContent('intro-block-1', 'Welcome to the server');"
        "process.stdout.write(JSON.stringify(selectedItems[0]))",
        items,
    )
    assert got["content"] == "Welcome to the server"
    assert got["name"] == "Welcome to the server"


def test_set_syncs_both_the_textarea_and_the_item():
    items = [{"id": "text-block-2", "type": "textblock", "content": "before"}]
    got = _run(
        "setTextBlockContent('text-block-2', 'after');"
        "process.stdout.write(JSON.stringify("
        "  [selectedItems[0].content, getTextBlockContent('text-block-2')]))",
        items, rendered={"text-block-2": "before"},
    )
    assert got == ["after", "after"]


def test_unknown_block_id_is_empty_not_undefined():
    got = _run(
        "process.stdout.write(JSON.stringify(getTextBlockContent('text-block-9')))",
        [],
    )
    assert got == ""
