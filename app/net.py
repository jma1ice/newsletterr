import ipaddress
import socket
from urllib.parse import urlparse

# SSRF guard for server-side fetches of user-influenced URLs (the image
# proxy). A self-hosted install legitimately talks to Plex/Tautulli on a
# private LAN address, so those configured hosts are allowed explicitly;
# every other target must resolve to a public address.

def _host_of(url):
    try:
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""

def is_safe_fetch_url(url, allowed_hosts=()):
    """Return (ok, reason). ok=False means do not fetch this URL server-side.

    A URL is allowed when its scheme is http/https AND either its host is in
    allowed_hosts (the operator-configured Plex/Tautulli hosts) or every IP
    the host resolves to is a public address (not loopback, private,
    link-local, reserved, or multicast).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "scheme not allowed"

    host = (parsed.hostname or "").lower()
    if not host:
        return False, "no host"

    def _norm_allowed(a):
        a = (a or "").lower()
        if "://" in a:
            return _host_of(a)
        return a.split(":", 1)[0]  # strip any :port from a bare host

    allowed = {n for n in (_norm_allowed(a) for a in allowed_hosts) if n}
    if host in allowed:
        return True, "allowed host"

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror:
        return False, "dns resolution failed"

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False, f"resolves to non-public address {ip}"

    return True, "public"

def configured_media_hosts():
    """Hosts of the operator-configured media servers (Plex, Tautulli,
    Jellyfin, Jellywatch), allowed even on a private LAN. Imported lazily to
    keep this module leaf-level."""
    from app.settings_store import get_settings
    s = get_settings(decrypt_secrets=False)
    hosts = []
    for key in ("plex_url", "tautulli_url", "jellyfin_url", "jellywatch_url"):
        h = _host_of(s.get(key) or "")
        if h:
            hosts.append(h)
    return hosts
