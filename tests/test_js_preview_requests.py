"""Regression guards for how the builder preview talks to /preview_email.

Two failure modes seen in testing, both covered here by running the real
functions out of static/js/app/01-preview.js under node:

* "Error updating preview: NetworkError when attempting to fetch resource."
  The browser reuses a keep-alive connection the server has just closed. A GET
  would be replayed transparently; a POST is not, so fetch rejects with a bare
  TypeError. postPreview retries the render once, which is safe because
  /preview_email only renders.
* A burst of edits left every superseded render running server side, each one
  paying for live Plex calls (the random and featured picks resolve at render
  time). Each render now aborts the one before it, and a cancelled render must
  never write its own error into the frame the newer render owns.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.js_helpers import _extract_js_function

REPO_ROOT = Path(__file__).resolve().parent.parent
PREVIEW_JS = REPO_ROOT / "static/js/app/01-preview.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is required for the JS parity tests"
)

# Enough of the builder page for updatePreview to run: a preview frame that
# records what it is given, a scripted fetch, and a payload builder that skips
# the chart capture the real one does.
STUB_DOM = """
const calls = [];
const script = JSON.parse(process.env.SCRIPT);
const frame = { srcdoc: '', onload: null };
const APP = { csrfToken: 'test-token' };
let _previewSeq = 0;
let _previewAbort = null;

const document = {
    getElementById(id) { return id === 'preview' ? frame : null; },
};

async function buildPreviewPayload() { return { subject: 'x' }; }

// Each scripted entry is one fetch attempt: {ok, html, error, delay}.
function fetch(url, opts) {
    const step = script[calls.length] || script[script.length - 1];
    calls.push({ url: url, aborted: false, step: step });
    const entry = calls[calls.length - 1];
    return new Promise((resolve, reject) => {
        // Real fetch rejects straight away when handed a signal that is
        // already aborted, which is what a render superseded before it got
        // as far as the network sees.
        const abortNow = () => {
            entry.aborted = true;
            const e = new Error('aborted');
            e.name = 'AbortError';
            reject(e);
        };
        if (opts && opts.signal && opts.signal.aborted) return abortNow();
        const finish = () => {
            if (entry.aborted) return;
            if (step.error) {
                const e = new TypeError('NetworkError when attempting to fetch resource.');
                reject(e);
                return;
            }
            resolve({ ok: step.ok !== false, statusText: 'Bad Request',
                      json: async () => ({ html: step.html, error: step.errorBody }) });
        };
        if (opts && opts.signal) opts.signal.addEventListener('abort', abortNow);
        setTimeout(finish, step.delay || 0);
    });
}
"""


def _run(script_steps, driver):
    """Run the real preview request functions under node against the stubs."""
    source = PREVIEW_JS.read_text(encoding="utf-8")
    program = "\n".join([
        STUB_DOM,
        "async " + _extract_js_function(source, "postPreview"),
        "async " + _extract_js_function(source, "updatePreview"),
        driver,
    ])
    result = subprocess.run(
        ["node", "-e", program],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "SCRIPT": json.dumps(script_steps)},
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_network_error_is_retried_once_and_recovers():
    """The dropped-connection POST is replayed and the preview still renders."""
    out = _run(
        [{"error": True}, {"html": "<p>rendered</p>"}],
        """
        (async () => {
            await updatePreview();
            console.log(JSON.stringify({ attempts: calls.length, srcdoc: frame.srcdoc }));
        })();
        """,
    )
    assert out["attempts"] == 2
    assert out["srcdoc"] == "<p>rendered</p>"


def test_persistent_network_error_surfaces_after_one_retry():
    """A server that is really down still reports, and does not retry forever."""
    out = _run(
        [{"error": True}, {"error": True}, {"error": True}],
        """
        (async () => {
            await updatePreview();
            console.log(JSON.stringify({ attempts: calls.length, srcdoc: frame.srcdoc }));
        })();
        """,
    )
    assert out["attempts"] == 2
    assert "Error updating preview" in out["srcdoc"]


def test_a_newer_render_aborts_the_one_before_it():
    """The superseded request is cancelled rather than left running, and the
    newer render's HTML is what lands in the frame."""
    out = _run(
        [{"html": "<p>stale</p>", "delay": 50}, {"html": "<p>fresh</p>"}],
        """
        (async () => {
            const first = updatePreview();
            const second = updatePreview();
            await Promise.all([first, second]);
            console.log(JSON.stringify({
                attempts: calls.length,
                firstAborted: calls[0].aborted,
                srcdoc: frame.srcdoc,
            }));
        })();
        """,
    )
    assert out["attempts"] == 2
    assert out["firstAborted"] is True
    assert out["srcdoc"] == "<p>fresh</p>"


def test_cancelled_render_never_writes_an_error_into_the_frame():
    """An aborted render's rejection is not an error the user should see."""
    out = _run(
        [{"error": True, "delay": 50}, {"html": "<p>fresh</p>"}],
        """
        (async () => {
            const first = updatePreview();
            const second = updatePreview();
            await Promise.all([first, second]);
            await new Promise(r => setTimeout(r, 80));
            console.log(JSON.stringify({ srcdoc: frame.srcdoc }));
        })();
        """,
    )
    assert out["srcdoc"] == "<p>fresh</p>"
