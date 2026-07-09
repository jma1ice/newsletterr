import pytest

from app.net import is_safe_fetch_url

@pytest.mark.parametrize("url,allowed,expected", [
    ("http://169.254.169.254/latest/meta-data/", (), False),  # cloud metadata
    ("http://127.0.0.1:6397/settings", (), False),            # loopback
    ("http://localhost/admin", (), False),                    # loopback by name
    ("http://192.168.1.50:32400/library", (), False),         # private, not allowlisted
    ("http://10.0.0.5/x", (), False),                         # private range
    ("http://192.168.1.50:32400/library", ("192.168.1.50",), True),  # allowlisted host
    ("https://image.tmdb.org/t/p/w500/x.jpg", (), True),      # public poster host
    ("file:///etc/passwd", (), False),                        # non-http scheme
    ("ftp://example.com/x", (), False),
    ("", (), False),                                          # empty
    ("http://", (), False),                                   # no host
])
def test_is_safe_fetch_url(url, allowed, expected):
    ok, _reason = is_safe_fetch_url(url, allowed_hosts=allowed)
    assert ok is expected

def test_allowlist_matches_host_with_port_and_scheme():
    # allowed_hosts entries may be bare hosts or full urls; both should match
    ok, _ = is_safe_fetch_url("http://192.168.1.50:32400/x", allowed_hosts=("http://192.168.1.50:32400",))
    assert ok is True
