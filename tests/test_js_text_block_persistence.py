"""Regression guards for text snap-in content surviving a page reload."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.js_helpers import _extract_js_function

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDER_JS = REPO_ROOT / "static/js/app/07-email-builder.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the JS parity tests"
)

# Minimal stand-in for the builder page. Editors only exist for ids listed in
# `rendered`, which is how a freshly loaded page looks before the first render.
# The editor is a contenteditable div, so the stub is a DIV whose
# innerHTML carries the content; the TEXTAREA branch is still exercised by
# test_textarea_editors_are_still_read_by_value below.
STUB_DOM = """
let selectedItems = JSON.parse(process.env.ITEMS);
const rendered = JSON.parse(process.env.RENDERED);
const asTextarea = process.env.AS_TEXTAREA === '1';
const CSS = { escape: (s) => String(s) };
const document = {
    querySelector(sel) {
        const m = /data-textblock-id="([^"]+)"/.exec(sel);
        if (m && rendered[m[1]] !== undefined) {
            return {
                tagName: asTextarea ? 'TEXTAREA' : 'DIV',
                get value() { return rendered[m[1]]; },
                set value(v) { rendered[m[1]] = v; },
                get innerHTML() { return rendered[m[1]]; },
                set innerHTML(v) { rendered[m[1]] = v; },
            };
        }
        return null;
    },
    createElement() {
        // textBlockPlainText's scratch node; the stub only needs enough of it
        // for the plain-text paths these tests exercise.
        return {
            innerHTML: '',
            textContent: '',
            querySelectorAll() { return []; },
        };
    },
};
"""


def _run(script, items, rendered=None, as_textarea=False):
    """Run the real accessors plus `script` under node, return its JSON stdout."""
    source = BUILDER_JS.read_text(encoding="utf-8")
    driver = "\n".join([
        STUB_DOM,
        _extract_js_function(source, "textBlockSurface"),
        _extract_js_function(source, "getTextBlockContent"),
        _extract_js_function(source, "setTextBlockContent"),
        _extract_js_function(source, "textBlockPlainText"),
        _extract_js_function(source, "getTextBlockDisplayName"),
        script,
    ])
    result = subprocess.run(
        ["node", "-e", driver],
        capture_output=True, text=True, timeout=30,
        env={**os.environ,
             "ITEMS": json.dumps(items),
             "RENDERED": json.dumps(rendered or {}),
             "AS_TEXTAREA": "1" if as_textarea else "0"},
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


def test_rich_content_round_trips_through_the_surface():
    items = [{"id": "text-block-1", "type": "textblock", "content": "plain"}]
    got = _run(
        "setTextBlockContent('text-block-1', '<b>bold</b> and <i>italic</i>');"
        "process.stdout.write(JSON.stringify("
        "  [selectedItems[0].content, getTextBlockContent('text-block-1')]))",
        items, rendered={"text-block-1": "plain"},
    )
    assert got == ["<b>bold</b> and <i>italic</i>"] * 2


def test_the_editors_own_font_size_is_stripped_from_content():
    """Regression guard, structural.

    With styleWithCSS on, applying an alignment re-wrapped the text in spans
    carrying the builder editor's `font-size: 0.9rem`, which would then have
    overridden the block's real size in the email. Two defenses: commands emit
    tags rather than CSS, and any inline font-size is stripped on read. The
    behavioral check runs in the browser (scratchpad check_phase7.py), since
    both defenses need a real contenteditable to exercise.
    """
    rich = (REPO_ROOT / "static/js/app/38-rich-text.js").read_text(encoding="utf-8")

    # Formatting commands emit tags, not CSS. styleWithCSS is switched on for
    # exactly one thing (the color swatch, which needs a style) and switched
    # straight back off, so `true` must never outnumber `false`.
    assert "styleWithCSS', false, false" in rich, "commands emit CSS again"
    assert rich.count("styleWithCSS', false, true") <= rich.count("styleWithCSS', false, false")

    assert "function stripEditorArtifacts(" in rich
    assert "removeProperty(prop)" in rich, "artifact stripping is gone"
    props = rich.split("ARTIFACT_PROPS = [")[1].split("]")[0]
    for prop in ("font-size", "font-family"):
        assert prop in props, f"{prop} is no longer stripped"

    builder = BUILDER_JS.read_text(encoding="utf-8")
    start = builder.index("function getTextBlockContent(")
    body = builder[start:builder.index("\nfunction ", start + 1)]
    assert "stripEditorArtifacts" in body, "content is read without stripping artifacts"


def test_textarea_editors_are_still_read_by_value():
    """The TEXTAREA branch stays for anything still rendering one."""
    items = [{"id": "text-block-1", "type": "textblock", "content": "old"}]
    got = _run(
        "process.stdout.write(JSON.stringify(getTextBlockContent('text-block-1')))",
        items, rendered={"text-block-1": "typed"}, as_textarea=True,
    )
    assert got == "typed"
