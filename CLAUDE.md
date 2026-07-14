# newsletterr development notes

Flask app packaged as `app/` with an app factory (`app/__init__.py:create_app`) and per-feature blueprints. `newsletterr.py` is a thin entrypoint that also serves as the gunicorn target (`newsletterr:app`).

## Commands

```bash
pip install -r requirements-dev.txt
pytest                                  # full suite, ~1 min, hermetic (no network, temp DB)
ruff check app/ newsletterr.py tests/   # lint (F rules and E9 only)
python newsletterr.py                   # dev server, PORT env overrides 6397
```

Regenerate email golden fixtures after intentional output changes:
`UPDATE_GOLDENS=1 pytest tests/test_golden_sends.py` then review the diff of `tests/goldens/*.json`.

## Invariants (do not break these)

- URL paths are frozen. The frontend JS in `static/js/app/` hardcodes fetch paths like `/pull_stats`. Blueprint endpoints are dotted (`main.index`, `auth.login`); the URL-map snapshot test in `tests/test_structure.py` must be updated deliberately when routes change.
- Import layering flows one way: `config -> state -> crypto -> db/store/settings_store/security/theme/cache -> clients -> emails/render -> scheduler -> hooks/blueprints -> factory`. Nothing imports `app/__init__.py` except `newsletterr.py`.
- Mutable shared state lives in `app/state.py` and is accessed only as attributes (`state.cache_storage`), never via `from app.state import X`, which would break cross-module mutation.
- Settings are read through `app/settings_store.py:get_settings()` (single `SELECT *`, central defaults, eager decryption of secret columns). Do not add scattered `FROM settings` queries. The settings POST route keeps its raw SQL writes on purpose.
- Database access goes through `app/db.py:db_connect()`. Callers own closing.
- `gunicorn -w 1` is mandatory: the send scheduler is an in-process thread and must be a singleton. Use gthread threads for concurrency.
- The email subpackage is named `emails/` (plural) to avoid colliding with the stdlib `email` module.
- `VERSION` file at the repo root is the single source of release metadata: line 1 is the version, line 2 the publish date. The version format must stay `vYYYY.N` because the update checker compares numerically. Release tags must equal line 1 (CI enforces this).
- Send functions return plain values, never Flask responses. Routes wrap results in `jsonify`.
- CSP is currently Report-Only (`app/hooks.py`). All script tags need `nonce="{{ nonce }}"`; the nonce comes from a context processor backed by `g.csp_nonce`. No inline `onclick=` handlers in templates.
- Committed text style: no emojis, no em or en dashes in docs, comments, or notes.

## Testing safely on this machine

Production runs in Docker on port 6397 with its DB in a named volume. Never bind 6397 locally. For manual testing, run a scratch copy on another port (`PORT=6398 python newsletterr.py`) with a fresh working directory so the CWD-relative `database/` stays isolated.

The browser check script (playwright headless chromium) exercises the index page UI: window.APP integrity, extracted script functions, chip input, gif modal, preview pipeline.

## Layout quick reference

- `app/blueprints/` routes only; `app/emails/` builders, senders, fetchers; `app/clients/` external APIs (plex, tautulli, conjurr, droppedneedle, github, sonarr, radarr)
- `static/js/app/` first-party frontend (numbered load order matters, classic scripts sharing globals); `static/js/vendor/` third-party, do not lint or edit
- `templates/partials/` included sections of index.html; the inline `window.APP` bootstrap block in `partials/_index_scripts.html` is the only inline script on the index page
- `tests/goldens/` golden MIME fixtures, force-added past the `*.json` gitignore rule
