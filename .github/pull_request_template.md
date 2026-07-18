<!--
Thanks for contributing. See CONTRIBUTING.md for setup and the project rules.
Please target the `nightly` branch, not `main`. If you opened this against
`main` by mistake, use the "Edit" button next to the PR title to retarget it.
-->

## Summary

<!-- What changed and why. -->

## How this was verified

<!-- What you ran or clicked to verify it works. -->

## Behavior changes for existing installations

<!--
Anything current users would notice after upgrading: changed defaults, moved
settings, different email output. Write "none" if there are none.
-->

## Checklist

- [ ] Targets the `nightly` branch, not `main`
- [ ] `ruff check app/ newsletterr.py tests/` passes
- [ ] `pytest` passes
- [ ] `node --check` passes on any changed file in `static/js/app/`
- [ ] Golden fixtures regenerated and the diff reviewed, if email output changed
- [ ] `tests/test_structure.py` updated, if any route was added, renamed, or moved
- [ ] Migration added in `app/__init__.py`, if a settings column was added
- [ ] New or changed behavior is covered by a test, or the PR says why not
- [ ] Exercised the change in a browser, if it touches the UI
