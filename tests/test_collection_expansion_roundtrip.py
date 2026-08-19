"""collection expansion state must survive a template save/load."""
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

CONVERSION_FUNCS = (
    "collectionExpansionKey",
    "stableGroupIdFor",
    "eachGroupCollection",
    "convertExpandedCollectionsForBackend",
    "convertExpandedCollectionsFromBackend",
)


def _run(script, items, expanded=None):
    source = BUILDER_JS.read_text(encoding="utf-8")
    parts = ["const COLLECTION_KEY_SEP = '::';",
             "let selectedItems = JSON.parse(process.env.ITEMS);",
             "const window = { expandedCollections: JSON.parse(process.env.EXPANDED) };"]
    parts += [_extract_js_function(source, name) for name in CONVERSION_FUNCS]
    parts.append(script)
    result = subprocess.run(
        ["node", "-e", "\n".join(parts)],
        capture_output=True, text=True, timeout=30,
        env={**os.environ,
             "ITEMS": json.dumps(items),
             "EXPANDED": json.dumps(expanded or {})},
    )
    if result.returncode != 0:
        raise AssertionError(f"node failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _group(group_id, *collection_keys):
    return {
        "id": group_id,
        "type": "collection_group",
        "title": "Group",
        "collections": [{"key": k, "title": k, "type": "movie"} for k in collection_keys],
    }


ITEMS = [
    {"id": "text-block-1", "type": "textblock"},
    _group("collection-group-1", "101", "202"),
    _group("collection-group-2", "303"),
]

# What the UI holds while the user has two collections expanded.
UI_STATE = {
    "collection-group-1::202": {"a": {"title": "A"}},
    "collection-group-2::303": {"b": {"title": "B"}},
}


def test_save_emits_the_positional_format_the_renderer_recomputes():
    out = _run("console.log(JSON.stringify(convertExpandedCollectionsForBackend()));",
               ITEMS, UI_STATE)
    # group at array index 1, its second collection; group at index 2, first.
    assert out == {
        "1-1-202": {"a": {"title": "A"}},
        "2-0-303": {"b": {"title": "B"}},
    }


def test_load_restores_ui_keys_from_the_stored_format():
    """The bug: loadTemplate assigned the stored dict raw, so no key matched."""
    stored = {"1-1-202": {"a": {"title": "A"}}, "2-0-303": {"b": {"title": "B"}}}
    out = _run(
        f"console.log(JSON.stringify(convertExpandedCollectionsFromBackend({json.dumps(stored)})));",
        ITEMS,
        {},
    )
    assert out == UI_STATE


def test_round_trip_is_lossless():
    stored = _run("console.log(JSON.stringify(convertExpandedCollectionsForBackend()));",
                  ITEMS, UI_STATE)
    back = _run(
        f"console.log(JSON.stringify(convertExpandedCollectionsFromBackend({json.dumps(stored)})));",
        ITEMS,
        {},
    )
    assert back == UI_STATE


def test_load_also_accepts_keys_saved_in_the_old_ui_format():
    """Templates written before the key scheme changed must still open."""
    legacy = {"collection-group-1-1-202": {"a": {"title": "A"}}}
    out = _run(
        f"console.log(JSON.stringify(convertExpandedCollectionsFromBackend({json.dumps(legacy)})));",
        ITEMS,
        {},
    )
    assert out == {"collection-group-1::202": {"a": {"title": "A"}}}


def test_ui_key_survives_reordering_within_a_group():
    """The old index-bearing key orphaned state whenever a collection moved.

    Same group, same collection, different position: the UI key is unchanged
    and the emitted positional key follows the new position.
    """
    reordered = [
        {"id": "text-block-1", "type": "textblock"},
        _group("collection-group-1", "202", "101"),   # 202 moved to the front
        _group("collection-group-2", "303"),
    ]
    out = _run("console.log(JSON.stringify(convertExpandedCollectionsForBackend()));",
               reordered, UI_STATE)
    assert out == {
        "1-0-202": {"a": {"title": "A"}},   # was 1-1-202 before the move
        "2-0-303": {"b": {"title": "B"}},
    }


def test_renderer_looks_up_exactly_what_the_save_emits():
    """Guards the JS/Python seam: app/emails/builders/collections.py rebuilds
    the id from the live list, so the two formats must not drift apart."""
    collections_py = (REPO_ROOT / "app/emails/builders/collections.py").read_text(encoding="utf-8")
    assert 'f"{group_index}-{collection_index}-{collection_key}"' in collections_py

    saved = _run("console.log(JSON.stringify(convertExpandedCollectionsForBackend()));",
                 ITEMS, UI_STATE)
    # group_index 1, collection_index 1, key 202 -> the renderer's f-string
    group_index, collection_index, collection_key = 1, 1, "202"
    assert f"{group_index}-{collection_index}-{collection_key}" in saved
