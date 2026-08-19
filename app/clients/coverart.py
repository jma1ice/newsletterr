"""Cover Art Archive lookups for the DroppedNeedle wrapped card."""
import re

COVER_ART_ARCHIVE_BASE = "https://coverartarchive.org"

# CAA serves thumbnails at these widths; anything else 404s.
COVER_SIZES = (250, 500, 1200)

_MBID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE
)

def is_mbid(value):
    return bool(value) and bool(_MBID_RE.match(str(value).strip()))

def release_group_cover_url(mbid, size=250):
    if not is_mbid(mbid):
        return None
    if size not in COVER_SIZES:
        size = 250
    return f"{COVER_ART_ARCHIVE_BASE}/release-group/{str(mbid).strip()}/front-{size}"
