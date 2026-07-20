# Contributing to newsletterr

Thanks for helping out. This document covers how to get set up, what to run
before you open a pull request, and the handful of project rules that are easy
to break by accident.

## Where to send pull requests

**Open pull requests against `nightly`, not `main`.**

`nightly` is the integration branch. `main` is release-facing: pushes to it
build the `:pre-release` Docker image, and tagged releases build `:latest`.
Changes land in `nightly` first so they get exercised in the `:nightly` image
before they reach anyone running a release build.

If you opened a PR against `main` by mistake, you can retarget it with the
"Edit" button next to the PR title. No need to close and reopen. CI has a
`base-branch` check that fails on PRs into `main` to catch this early.

Branch naming that is easy to scan, for example `feat/custom-plex-web-url`,
`fix/library-filter-exact-match`, is appreciated but not enforced.

## Setup

Requires Python 3.12 or newer.

```bash
pip install -r requirements-dev.txt
python newsletterr.py              # dev server on port 6397, PORT env overrides
```

The database is created on first run under a CWD-relative `database/` folder.
Nothing external is required to run the test suite.

## Before you open a pull request

Run the same three checks CI runs. All of them must pass.

```bash
ruff check app/ newsletterr.py tests/                     # lint (E9 and F rules only)
pytest                                                    # full suite, about two minutes
for f in static/js/app/*.js; do node --check "$f"; done   # JS syntax
```

The suite is hermetic: no network, temp database, safe to run anywhere.

If you changed anything the app renders in a browser, load the page and click
through the part you touched. The tests do not cover the frontend beyond a
syntax check, so UI regressions only get caught by looking.

### Golden email fixtures

The email pipeline is covered by golden-master tests that compare full MIME
output against fixtures in `tests/goldens/`. If your change intentionally
changes email output, those tests will fail until you regenerate them:

```bash
UPDATE_GOLDENS=1 pytest tests/test_golden_sends.py
```

Review the resulting diff of `tests/goldens/*.json` before committing, and
include it in the PR. A golden diff you cannot explain means the change did
something you did not intend.

## Project rules that are easy to break

These are load-bearing. Breaking one usually will not fail a test, which is
exactly why they are written down.

- **URL paths are frozen.** The frontend in `static/js/app/` hardcodes fetch
  paths like `/pull_stats`. Blueprint endpoints are dotted (`main.index`,
  `auth.login`). There is a URL-map snapshot test in `tests/test_structure.py`
  that must be updated deliberately, in the same commit, when routes change.
- **Import layering flows one way:** `config -> state -> crypto ->
  db/store/settings_store/security/theme/cache -> clients -> emails/render ->
  scheduler -> hooks/blueprints -> factory`. Nothing imports `app/__init__.py`
  except `newsletterr.py`.
- **Shared mutable state lives in `app/state.py`** and is accessed only as
  attributes (`state.cache_storage`). Never `from app.state import X`, which
  copies the reference and breaks cross-module mutation.
- **Settings are read through `app/settings_store.py:get_settings()`.** It does
  a single `SELECT *`, applies central defaults, and decrypts secret columns.
  Do not add scattered `FROM settings` queries. A new setting needs its default
  added to `DEFAULTS` (or `INT_COLUMNS`) there, so call sites do not each
  repeat a fallback. The settings POST route keeps its raw SQL on purpose.
- **New settings columns need a migration.** Add a `db.migrate_schema(...)` call
  in `app/__init__.py` alongside the DDL in `app/db.py:init_db`, so existing
  installations pick the column up on next start. Keep the two DDL defaults
  identical.
- **Database access goes through `app/db.py:db_connect()`.** Callers own
  closing the connection.
- **`gunicorn -w 1` is mandatory.** The send scheduler is an in-process thread
  and must be a singleton. Use gthread threads for concurrency.
- **The email subpackage is `emails/`, plural,** to avoid colliding with the
  stdlib `email` module.
- **Send functions return plain values, never Flask responses.** Routes wrap
  results in `jsonify`.
- **All script tags need `nonce="{{ nonce }}"`** and there are no inline
  `onclick=` handlers in templates. CSP is currently Report-Only, so a
  violation here fails quietly rather than loudly.
- **Do not edit `static/js/vendor/`.** Third-party code, not linted.

## Style

- Match the surrounding code: same comment density, naming, and idioms as the
  file you are editing.

## Pull request checklist

Copy this into your PR description and tick it off.

```markdown
- [ ] Targets the `nightly` branch, not `main`
- [ ] `ruff check app/ newsletterr.py tests/` passes
- [ ] `pytest` passes
- [ ] `node --check` passes on any changed file in `static/js/app/`
- [ ] Golden fixtures regenerated and the diff reviewed, if email output changed
- [ ] `tests/test_structure.py` updated, if any route was added, renamed, or moved
- [ ] Migration added in `app/__init__.py`, if a settings column was added
- [ ] New or changed behavior is covered by a test, or the PR says why not
- [ ] Exercised the change in a browser, if it touches the UI
```

## Describing your pull request

Say what changed and why, and how you verified it. If the change alters
existing behavior for current installations, even in a small way, call that out
explicitly.

Draft PRs are welcome if you want feedback on an approach before you polish it.

## Reporting bugs

Open an issue with your newsletterr version (see the `VERSION` file or the
About page), how you are running it (Docker, binary, or from source), and the
relevant portion of the logs. The Logs page has an export button.

## Maintainer notes

The `base-branch` CI job rejects pull requests into `main`. It allows two
cases: the `nightly -> main` promotion opened from a branch named `nightly` in
this repo, and any PR carrying the `override-base` label. Add that label for a
deliberate hotfix straight into `main`.

The `VERSION` file is the single source of release metadata: line 1 is the
version, line 2 the publish date. Line 1 must stay a `v` followed by
dot-separated numbers, for example `v2026.2.2`, because the update checker in
`app/clients/github.py` compares the components numerically against the latest
GitHub release tag. Release tags must equal line 1 or the release build fails.
