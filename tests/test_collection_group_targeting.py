"""choosing which collection group an Add lands in, and moving a
collection between groups afterwards.

The move has to carry expansion state with it: the maps are keyed by group id
plus collection key, so a move that only splices the arrays would leave an
expanded collection looking collapsed in its new home.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.js_helpers import _extract_js_function

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDER_JS = REPO_ROOT / "static/js/app/07-email-builder.js"
COLLECTIONS_JS = REPO_ROOT / "static/js/app/17-collections.js"
SNAPINS_HTML = REPO_ROOT / "templates/partials/_snapins.html"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the JS parity tests"
)


def _run(script, items, expanded=None, collapsed=None):
    builder = BUILDER_JS.read_text(encoding="utf-8")
    collections = COLLECTIONS_JS.read_text(encoding="utf-8")
    driver = "\n".join([
        "const COLLECTION_KEY_SEP = '::';",
        "let selectedItems = JSON.parse(process.env.ITEMS);",
        "const window = {",
        "  expandedCollections: JSON.parse(process.env.EXPANDED),",
        "  collapsedCollectionsUI: JSON.parse(process.env.COLLAPSED),",
        "};",
        # the move calls back into the renderer and the preview; neither is
        # under test here.
        "function updateSelectedItemsDisplay() {}",
        _extract_js_function(builder, "collectionExpansionKey"),
        _extract_js_function(collections, "collectionGroups"),
        _extract_js_function(collections, "moveCollectionToGroup"),
        script,
    ])
    result = subprocess.run(
        ["node", "-e", driver],
        capture_output=True, text=True, timeout=30,
        env={**os.environ,
             "ITEMS": json.dumps(items),
             "EXPANDED": json.dumps(expanded or {}),
             "COLLAPSED": json.dumps(collapsed or {})},
    )
    if result.returncode != 0:
        raise AssertionError(f"node failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _group(group_id, title, *keys):
    return {
        "id": group_id, "type": "collection_group", "title": title,
        "collections": [{"key": k, "title": f"C{k}", "type": "movie"} for k in keys],
    }


ITEMS = [_group("collection-group-1", "First", "101", "202"),
         _group("collection-group-2", "Second", "303")]

REPORT = """
console.log(JSON.stringify({
    moved: moved,
    groups: selectedItems.map(g => ({ id: g.id, keys: g.collections.map(c => c.key) })),
    expanded: Object.keys(window.expandedCollections),
    collapsed: Object.keys(window.collapsedCollectionsUI),
}));
"""


def test_move_relocates_the_collection():
    out = _run(
        "const moved = moveCollectionToGroup('collection-group-1', 1, 'collection-group-2');" + REPORT,
        ITEMS,
    )
    assert out["moved"] is True
    assert out["groups"] == [
        {"id": "collection-group-1", "keys": ["101"]},
        {"id": "collection-group-2", "keys": ["303", "202"]},
    ]


def test_move_carries_expansion_state_to_the_new_group():
    out = _run(
        "const moved = moveCollectionToGroup('collection-group-1', 1, 'collection-group-2');" + REPORT,
        ITEMS,
        expanded={"collection-group-1::202": {"x": {"title": "X"}}},
        collapsed={"collection-group-1::202": True},
    )
    assert out["expanded"] == ["collection-group-2::202"]
    assert out["collapsed"] == ["collection-group-2::202"]


def test_move_into_a_group_that_already_has_it_is_refused():
    """Both sides must be left untouched, or the collection is lost."""
    items = [_group("collection-group-1", "First", "101"),
             _group("collection-group-2", "Second", "101")]
    out = _run(
        "const moved = moveCollectionToGroup('collection-group-1', 0, 'collection-group-2');" + REPORT,
        items,
        expanded={"collection-group-1::101": {"x": {"title": "X"}}},
    )
    assert out["moved"] is False
    assert out["groups"] == [
        {"id": "collection-group-1", "keys": ["101"]},
        {"id": "collection-group-2", "keys": ["101"]},
    ]
    assert out["expanded"] == ["collection-group-1::101"]


def test_move_to_the_same_group_is_a_no_op():
    out = _run(
        "const moved = moveCollectionToGroup('collection-group-1', 0, 'collection-group-1');" + REPORT,
        ITEMS,
    )
    assert out["moved"] is True
    assert out["groups"][0]["keys"] == ["101", "202"]


def test_move_with_an_unknown_group_is_refused():
    out = _run(
        "const moved = moveCollectionToGroup('collection-group-1', 0, 'collection-group-9');" + REPORT,
        ITEMS,
    )
    assert out["moved"] is False
    assert out["groups"][0]["keys"] == ["101", "202"]


def test_add_no_longer_hardcodes_the_last_group():
    """The reported bug: Add always targeted the last group in the list."""
    source = COLLECTIONS_JS.read_text(encoding="utf-8")
    start = source.index("function addCollectionItem(")
    body = source[start:source.index("\n}", start)]
    assert "targetCollectionGroup()" in body
    assert "for (let i = selectedItems.length - 1" not in body


def test_destination_picker_exists_and_hides_when_there_is_no_choice():
    html = SNAPINS_HTML.read_text(encoding="utf-8")
    assert 'id="collection-target-group"' in html

    row = re.search(r'<div id="collection-target-row"[^>]*>', html)
    assert row, "destination picker row is gone"
    # Ships hidden: one group is the common case and there is nothing to pick.
    assert "d-none" in row.group(0), row.group(0)

    source = COLLECTIONS_JS.read_text(encoding="utf-8")
    start = source.index("function refreshCollectionTargetOptions(")
    body = source[start:source.index("\n}", start)]
    assert "groups.length < 2" in body, "picker no longer hides itself with one group"
