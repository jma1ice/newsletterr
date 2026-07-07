import time

from app import config, state
from app.security import safe_get

import logging

logger = logging.getLogger(__name__)

def _norm(v: str):
    if not v:
        return (0,)
    v = v.lstrip("vV").split("+", 1)[0].split("-", 1)[0]
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            num = ''.join(ch for ch in p if ch.isdigit())
            parts.append(int(num) if num else 0)
    return tuple(parts) if parts else (0,)

def _check_github_latest():
    headers = {"Accept": "application/vnd.github+json"}
    if state._update_cache["etag"]:
        headers["If-None-Match"] = state._update_cache["etag"]

    url = f"https://api.github.com/repos/{config.GITHUB_OWNER}/{config.GITHUB_REPO}/releases/latest"
    try:
        r = safe_get(url, headers=headers, timeout=10)
        if r.status_code == 304:
            state._update_cache["checked_at"] = time.time()
            return
        r.raise_for_status()
        if "application/json" not in r.headers.get("Content-Type", ""):
            raise RuntimeError(f"Unexpected content type: {r.headers.get('Content-Type')}")
        data = r.json()
        latest_tag = data.get("tag_name") or ""
        current = config.VERSION
        is_newer = _norm(latest_tag) > _norm(current)

        state._update_cache.update({
            "latest": latest_tag,
            "is_newer": is_newer,
            "release_url": data.get("html_url"),
            "notes": data.get("body", ""),
            "checked_at": time.time(),
            "etag": r.headers.get("ETag"),
        })
    except Exception as e:
        logger.debug("suppressed exception; using fallback", exc_info=True)
        state._update_cache["checked_at"] = time.time()

def _ensure_recent_check():
    now = time.time()
    if now - state._update_cache["checked_at"] >= config.UPDATE_CHECK_INTERVAL_SEC:
        _check_github_latest()

def _background_update_checker():
    while True:
        try:
            _check_github_latest()
        finally:
            time.sleep(config.UPDATE_CHECK_INTERVAL_SEC)
