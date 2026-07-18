"""Parity guards for the hand-synced JS preview mirrors.

The email builders in app/emails/ render what actually gets sent. The preview
functions in static/js/app/ and templates/schedule_preview.html re-implement
that same filtering in JS so the on-screen preview is WYSIWYG. Nothing keeps
the two in sync except discipline.

These tests run the real JS out of the real source files through node and
assert it agrees with the Python it mirrors.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.emails.builders.ombi_requests import filter_ombi_pending

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every source file that defines its own copy of the Ombi preview filter.
OMBI_FILTER_SOURCES = [
    "static/js/app/04-stats-graphs.js",
    "templates/schedule_preview.html",
]

def _extract_js_function(source, name):
    """Return the source text of `function <name>(...) { ... }`, brace-matched.

    Skips braces inside strings, template literals and comments so a function
    body containing `${...}` or `{` in a string does not truncate the match.
    """
    start = source.find(f"function {name}")
    if start == -1:
        raise AssertionError(f"function {name} not found")

    depth = 0
    started = False
    i = start
    in_single = in_double = in_template = False
    in_line_comment = in_block_comment = False

    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
        elif in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 1
        elif in_single or in_double or in_template:
            if ch == "\\":
                i += 1
            elif in_single and ch == "'":
                in_single = False
            elif in_double and ch == '"':
                in_double = False
            elif in_template and ch == "`":
                in_template = False
        elif ch == "/" and nxt == "/":
            in_line_comment = True
            i += 1
        elif ch == "/" and nxt == "*":
            in_block_comment = True
            i += 1
        elif ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch == "`":
            in_template = True
        elif ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                return source[start:i + 1]
        i += 1

    raise AssertionError(f"unbalanced braces extracting {name}")

def _run_js_filter(func_src, payload):
    """Run the extracted _filterOmbiPending over `payload` under node and
    return its entries projected onto the fields Python also produces."""
    driver = func_src + """
const payload = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = _filterOmbiPending(payload).map(e => [
    e.title ?? null,
    e.year ?? null,
    e.poster ?? null,
    !!e.approved,
    e.requestedDate ?? null,
]);
process.stdout.write(JSON.stringify(out));
"""
    result = subprocess.run(
        ["node", "-e", driver], input=json.dumps(payload),
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise AssertionError(f"node failed: {result.stderr.strip()}")
    return [tuple(row) for row in json.loads(result.stdout)]

def _python_filter(payload):
    return [
        (e["title"], e["year"], e["poster"], bool(e["approved"]), e["requested_date"])
        for e in filter_ombi_pending(payload)
    ]

def _movie(title, requested, approved=False, available=False, denied=False):
    return {
        "title": title, "releaseDate": "2025-06-01", "posterPath": f"/{title}.jpg",
        "approved": approved, "available": available, "denied": denied,
        "requestedDate": requested,
    }

def _season(requested, approved=False, available=False, denied=False):
    return {
        "approved": approved, "available": available, "denied": denied,
        "requestedDate": requested,
    }

def _show(title, seasons):
    return {
        "title": title, "releaseDate": "2024-01-01", "posterPath": f"/{title}.jpg",
        "childRequests": seasons,
    }

# Each case is exercised against Python and against every JS mirror. The names
# describe the request state, not the expected output, so a case stays valid
# if the shared filtering rule is ever deliberately changed.
PAYLOAD_CASES = [
    ("empty", {"movies": [], "tv": []}),
    ("none_payload", None),
    ("missing_keys", {}),
    # Movies: only unresolved ones survive.
    ("movie_pending", {"movies": [_movie("Pending", "2026-07-10T00:00:00Z")], "tv": []}),
    ("movie_approved", {"movies": [_movie("Approved", "2026-07-11T00:00:00Z", approved=True)], "tv": []}),
    ("movie_available", {"movies": [_movie("Available", "2026-07-01T00:00:00Z", approved=True, available=True)], "tv": []}),
    ("movie_denied", {"movies": [_movie("Denied", "2026-07-02T00:00:00Z", denied=True)], "tv": []}),
    ("movie_missing_fields", {"movies": [{"title": "Bare"}], "tv": []}),
    # TV: a show survives only while some season is still pending.
    ("tv_all_pending", {"movies": [], "tv": [_show("AllPending", [_season("2026-07-09T00:00:00Z")])]}),
    ("tv_all_pending_approved", {"movies": [], "tv": [_show("PendingApproved", [_season("2026-07-08T00:00:00Z", approved=True)])]}),
    ("tv_all_available", {"movies": [], "tv": [_show("Done", [_season("2026-07-01T00:00:00Z", approved=True, available=True)])]}),
    ("tv_all_denied", {"movies": [], "tv": [_show("Rejected", [_season("2026-07-02T00:00:00Z", denied=True)])]}),
    # The regression this test exists for: resolved, but not uniformly.
    ("tv_mixed_available_and_denied", {"movies": [], "tv": [_show("MixedResolved", [
        _season("2026-07-01T00:00:00Z", approved=True, available=True),
        _season("2026-07-05T00:00:00Z", denied=True),
    ])]}),
    # One season landed, another is still outstanding, so the show stays and
    # its approved flag must reflect the pending season, not the finished one.
    ("tv_partially_pending", {"movies": [], "tv": [_show("Partial", [
        _season("2026-07-01T00:00:00Z", approved=True, available=True),
        _season("2026-07-05T00:00:00Z"),
    ])]}),
    ("tv_no_children", {"movies": [], "tv": [_show("Empty", [])]}),
    ("tv_missing_children_key", {"movies": [], "tv": [{"title": "NoKey"}]}),
    # Mixed payload: checks the combined most-recent-first ordering.
    ("sorting_across_types", {
        "movies": [
            _movie("OldMovie", "2026-01-01T00:00:00Z"),
            _movie("NewMovie", "2026-12-01T00:00:00Z", approved=True),
        ],
        "tv": [
            _show("MidShow", [_season("2026-06-01T00:00:00Z")]),
            _show("NewestShow", [_season("2026-12-15T00:00:00Z", approved=True)]),
        ],
    }),
    ("undated_requests", {
        "movies": [_movie("NoDate", None)],
        "tv": [_show("NoDateShow", [_season(None)])],
    }),
]

@pytest.fixture(scope="module")
def node():
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node not available")
    return exe

@pytest.fixture(scope="module", params=OMBI_FILTER_SOURCES)
def ombi_filter_js(request):
    path = REPO_ROOT / request.param
    return _extract_js_function(path.read_text(encoding="utf-8"), "_filterOmbiPending")

@pytest.mark.parametrize("name,payload", PAYLOAD_CASES, ids=[c[0] for c in PAYLOAD_CASES])
def test_ombi_filter_js_matches_python(node, ombi_filter_js, name, payload):
    assert _run_js_filter(ombi_filter_js, payload) == _python_filter(payload)

def test_ombi_filter_mirrors_are_identical():
    """The two copies should stay textually identical apart from indentation,
    so a fix applied to one is visibly missing from the other."""
    bodies = []
    for rel in OMBI_FILTER_SOURCES:
        src = _extract_js_function((REPO_ROOT / rel).read_text(encoding="utf-8"), "_filterOmbiPending")
        bodies.append("\n".join(line.strip() for line in src.splitlines()))
    assert bodies[0] == bodies[1]

def test_mixed_state_show_is_dropped_by_both():
    """Pins the specific regression: one season available, one denied, nothing
    pending. Both sides must drop it, and the preview must not label it
    Approved off the back of the already-available season."""
    payload = {"movies": [], "tv": [_show("MixedResolved", [
        _season("2026-07-01T00:00:00Z", approved=True, available=True),
        _season("2026-07-05T00:00:00Z", denied=True),
    ])]}
    assert _python_filter(payload) == []
    for rel in OMBI_FILTER_SOURCES:
        if not shutil.which("node"):
            pytest.skip("node not available")
        js = _extract_js_function((REPO_ROOT / rel).read_text(encoding="utf-8"), "_filterOmbiPending")
        assert _run_js_filter(js, payload) == [], f"{rel} still renders the resolved show"
