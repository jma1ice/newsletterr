"""Guards on the headless chart capture reaching a page it can actually read."""

import inspect
import re
from pathlib import Path

import pytest

from app import config, render

# Matched as calls, so the prose in the module's own comments explaining why
# these are avoided cannot satisfy or trip the assertions.
RENDER_SRC = Path(render.__file__).read_text()

class _FakePage:
    """Minimal page: answers a scripted sequence of evaluate() results."""

    def __init__(self, results):
        self.results = list(results)
        self.evaluated = []
        self.slept = 0

    def evaluate(self, expression):
        self.evaluated.append(expression)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def wait_for_timeout(self, ms):
        self.slept += ms

def test_wait_returns_as_soon_as_the_expression_is_truthy():
    page = _FakePage([True])
    assert render._wait_for(page, "ready", 1000) is True
    assert page.slept == 0

def test_wait_polls_until_the_expression_flips():
    page = _FakePage([False, False, True])
    assert render._wait_for(page, "ready", 1000, poll_ms=10) is True
    assert len(page.evaluated) == 3

def test_wait_survives_an_evaluate_that_raises_mid_navigation():
    page = _FakePage([RuntimeError("execution context destroyed"), True])
    assert render._wait_for(page, "ready", 1000, poll_ms=10) is True

def test_wait_times_out_rather_than_polling_forever():
    page = _FakePage([False] * 100)
    with pytest.raises(TimeoutError):
        render._wait_for(page, "ready", 30, poll_ms=10)

def test_capture_does_not_use_wait_for_function():
    # wait_for_function needs 'unsafe-eval' in the page CSP. Reintroducing it
    # breaks the capture wherever CSP is enforcing, which is everywhere since
    # v2026.3.
    assert not re.search(r"\.wait_for_function\(", RENDER_SRC)

def test_capture_does_not_disable_csp_to_work_around_that():
    # bypass_csp would also make the waits work, at the cost of the capture no
    # longer running against the policy the real page is served under.
    assert not re.search(r"bypass_csp\s*=", RENDER_SRC)

def test_capture_sends_the_internal_token():
    assert re.search(r'"X-Internal-Token":\s*config\.INTERNAL_TOKEN', RENDER_SRC)

def test_internal_token_is_scoped_to_the_app_origin():
    # set_extra_http_headers would attach the token to every request the page
    # makes, and img-src allows external https hosts, so a poster URL would
    # hand a full auth bypass to a third party.
    assert not re.search(r"\.set_extra_http_headers\(", RENDER_SRC)
    assert re.search(r"context\.route\(", RENDER_SRC)

def test_the_token_the_capture_sends_is_the_one_requires_auth_accepts():
    from app import security

    assert "X-Internal-Token" in inspect.getsource(security.requires_auth)
    assert config.INTERNAL_TOKEN
