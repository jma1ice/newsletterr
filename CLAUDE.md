# newsletterr development notes

Flask app packaged as `app/` with an app factory (`app/__init__.py:create_app`) and per-feature blueprints. `newsletterr.py` is a thin entrypoint that also serves as the gunicorn target (`newsletterr:app`).

## Commands

```bash
pip install -r requirements-dev.txt
pytest                                  # full suite (~1100 tests, ~6 min), hermetic (no network, temp DB)
ruff check app/ newsletterr.py tests/   # lint (F rules and E9 only)
python newsletterr.py                   # dev server, PORT env overrides 6397
```

Regenerate email golden fixtures after intentional output changes:
`UPDATE_GOLDENS=1 pytest tests/test_golden_sends.py` then review the diff of `tests/goldens/*.json`.

## Invariants (do not break these)

- URL paths are frozen. The frontend JS in `static/js/app/` hardcodes fetch paths like `/pull_stats`. Blueprint endpoints are dotted (`main.index`, `auth.login`); the URL-map snapshot test in `tests/test_structure.py` must be updated deliberately when routes change.
- Import layering flows one way: `config -> state -> crypto -> db/store/settings_store/security/theme/cache -> clients -> emails/render -> scheduler -> hooks/blueprints -> factory`. Nothing imports `app/__init__.py` except `newsletterr.py`.
- Mutable shared state lives in `app/state.py` and is accessed only as attributes (`state.cache_storage`), never via `from app.state import X`, which would break cross-module mutation.
- Settings are read through `app/settings_store.py:get_settings()` (single `SELECT *`, central defaults, eager decryption of secret columns). Do not add scattered `FROM settings` queries. The settings POST route keeps its raw SQL writes on purpose. That single chokepoint is also what makes demo mode work: `get_settings()` layers `app/demo.py:apply_settings_overlay()` on top when `DEMO_MODE` is on, so a scattered settings query would read the wrong values there.
- Demo mode (`DEMO_MODE=1`, `app/demo.py`) never writes the database and never lets a request reach an external service. It synthesizes a fully-configured install (`BASE_SETTINGS`) plus a seeded sample dataset in the shapes the real clients return, answers every pull/collection/artwork route from that data, applies settings a visitor changes to a session overlay (whitelisted keys only, `_SHOWCASE_*`), and hides login/logout. Sample artwork is served through `/proxy-art/library/demo/*` from `static/img/demo/`. New routes that call out to a media server need a handler in `_DEMO_GET_HANDLERS`/`_DEMO_WRITE_HANDLERS`, or they will hang the demo on a dead host.
- Database access goes through `app/db.py:db_connect()`. Callers own closing.
- `gunicorn -w 1` is mandatory: the send scheduler is an in-process thread and must be a singleton. Use gthread threads for concurrency.
- The email subpackage is named `emails/` (plural) to avoid colliding with the stdlib `email` module.
- `VERSION` file at the repo root is the single source of release metadata: line 1 is the version, line 2 the publish date. The version format must stay `vYYYY.N` because the update checker compares numerically. Release tags must equal line 1 (CI enforces this).
- Send functions return plain values, never Flask responses. Routes wrap results in `jsonify`.
- Email HTML has a single renderer. Sends assemble through `app/emails/assemble.py`; the live previews (index builder and schedule preview) POST the same builder payload to `/preview_email` (`app/emails/preview.py:render_preview_email`) and the frontend just displays the returned HTML. Do not reintroduce client-side email-HTML construction. The legacy `build*PreviewHTML` functions and the hand-mirrored `_filter*`/`_comingSoon*` copies were deleted in v2026.4.4 once instrumentation confirmed they never ran; `static/js/app/04-stats-graphs.js` now holds only the shared builder state (`selectedItems`, `statsList`) and its two DOMContentLoaded handlers, and `templates/schedule_preview.html` only its chart-capture and preview-sizing helpers. Their parity tests went with them, since there is no longer a second copy to keep in sync.
- Email layouts (`legacy`/`classic`/`editorial`/`digest`/`spotlight`) live in `app/emails/builders/layouts.py`, dispatched from `assemble.py`; the settings-level `email_layout` column selects one. Layout-level chassis colors go through `layouts.apply_theme()` so the shell and the section cards agree; spotlight is the one layout that overrides them today. The `email_templates.layout` column is an unrelated legacy no-op, not the layout selector.
- Email density (`compact`/`expanded`) is a second axis that crosses every layout, settings column `email_density`, resolved in `app/emails/density.py` and carried on the theme dict (`stamp()` writes `density` and `density_layout`; nothing re-reads settings downstream). Each layout has one natural density that must stay byte-identical (`legacy`/`classic`/`spotlight` are naturally expanded, `editorial`/`digest` naturally compact) and one authored variant; blank means natural, which is why an untouched install never shifts. Builders must branch through `picker()`/`picker3()`/`show_art()`/`columns()`, never on `is_compact()` alone. The shared builders that render under every layout (recommendations, collections, the card grid) need the three-way `picker3()` because the same code is one layout's compact variant and another's expanded one. The compact variants carry no artwork at all and stack card grids into one column.
- The Coming Soon snap-ins take a per-item `csView` (`grid`/`calendar`/`agenda`, blank = the layout's own treatment) rendered by `app/emails/builders/calendar_view.py`. Its class names and the `@media (max-width: 600px)` block in `app/theme.py` are hand-synced: the month grid only reflows into a stacked list on phones because of those rules, and `.cs-cal-empty` must stay after `.cs-cal-cell` to win. `tests/test_coming_soon_views.py` fails on a class emitted without a matching rule.
- CSP is enforcing since v2026.3 (`app/hooks.py`). All script tags need `nonce="{{ nonce }}"`; the nonce comes from a context processor backed by `g.csp_nonce`. No inline `onclick=`/`oninput=` handlers in templates.
- Committed text style: no emojis, no em or en dashes in docs, comments, or notes.

## Testing safely on this machine

Production runs in Docker on port 6397 with its DB in a named volume. Never bind 6397 locally. For manual testing, run a scratch copy on another port (`PORT=6398 python newsletterr.py`) with a fresh working directory so the CWD-relative `database/` stays isolated.

The browser check script (playwright headless chromium) exercises the index page UI: window.APP integrity, extracted script functions, chip input, gif modal, preview pipeline.

## Layout quick reference

- `app/blueprints/` routes only; `app/emails/` builders, senders, fetchers; `app/clients/` external APIs (plex, tautulli, conjurr, droppedneedle, github, sonarr, radarr)
- `static/js/app/` first-party frontend (numbered load order matters, classic scripts sharing globals); `static/js/vendor/` third-party, do not lint or edit
- `templates/partials/` included sections of index.html; the inline `window.APP` bootstrap block in `partials/_index_scripts.html` is the only inline script on the index page
- `tests/goldens/` golden MIME fixtures, force-added past the `*.json` gitignore rule
