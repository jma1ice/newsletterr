# newsletterr

_Turn your Plex server analytics into a beautiful weekly (or whenever‑you‑like) newsletter._

Newsletterr is a lightweight Flask application that talks to **[Tautulli](https://tautulli.com/)**, crunches your Plex statistics, renders charts with **Highcharts**, pulls recommendations from **[conjurr](https://github.com/yungsnuzzy/conjurr)** and emails the results to your user base, all without leaving the browser.

---

## Features

### Data & Content
* **One‑click stats pull** - pick a time range (quick buttons: 7 / 30 / 90 / … days) and "recently added" count; Newsletterr queries Tautulli for most watched movies/shows, active users, platforms, libraries, artists and more.
* **User Recommendations** - integrate with **conjurr** to show personalized watch suggestions (per BCC list at fetch time).
* **Snap‑ins (drag/add workflow)** - add Stats, Graphs, Recently Added (library selection supported), Recommendations, Collections, and Text Blocks (Title, Header, Intro, Body, Outro) in any order (Title sticks to the top) to compose a tailored newsletter body.

### Visualization
* **Interactive charts** - Highcharts rendered in‑app; suitable images captured for reliable e‑mail client display.
* **Styled data tables** - Plex / Tautulli metrics rendered as clean, responsive tables prior to embedding.
* **Live WYSIWYG preview** - side‑by‑side iframe updates instantly as you assemble the email.

### Templates & Reuse
* **Email Templates** - save, load, clone, and delete custom templates (tracks chosen snap‑ins & layout) and re‑apply later.
* **Template provenance tracking** - every sent email logs which template (or “Manual”) produced it; visible in Email History.

### Automation & Scheduling
* **Automated Schedules** - create Daily / Weekly / Monthly schedules with start date, fixed send time, and data range.
* **Per‑schedule strict data window** - schedule previews fetch exactly the configured date range (no accidental reuse of broader cached data).
* **Send Now** - manual immediate dispatch per schedule (with flashing progress state) without disturbing the schedule cadence.
* **Color‑coded Schedule Calendar** - compact, modern calendar view showing all upcoming sends; each template assigned a stable color (legend included) with brightening hover effect.
* **Per‑row template color dots** - schedule list includes a left‑edge colored dot consistent with calendar colors.

### Delivery & Recipients
* **SMTP (BCC) sending** - works with Gmail app passwords, generic SMTP, Mailgun, etc.; BCC chip input for recipient management & saved recipient lists.
* **Email list management** - save, load, delete named email lists with instant population of the BCC field.
* **Size tracking** - sent email content size (KB) logged for each history entry.

### Caching & Performance
* **Smart multi‑segment cache** - stores stats, user data, recent additions, recommendations and graph payloads separately.
* **Global cache status badge** - real‑time indicator (fresh / warn / old / stale / missing) with tooltips and animated attention state if segments absent.
* **Manual & automatic refresh** - daily auto refresh plus explicit “Get Stats\Users” trigger; one‑click “Clear Cache” button.

### History & Auditing
* **Email History** - full ledger of subject, send timestamp (compact formatting), template used, size, recipient count.
* **Recipient viewer modal** - drill into any email to list all BCC recipients.
* **Clear History** - bulk purge with confirmation.

### UX & Appearance
* **Light / Dark aware styling** - adaptive colors for dashboard, modals, calendar, and tables.
* **Animated feedback** - loading spinner, flashing Send Now state, subtle hover depth on calendar days & dots.
* **Compact date formatting** - standardized abbreviated month formats (e.g. “Mar. 27, 2025” / “Sunday Sep. 21, 2025  09:00”).
* **Responsive wrapped button groups** - quick time‑range buttons auto‑wrap with padded container.

### Persistence & Local Footprint
* **SQLite storage** - schedules, templates, email history, lists & settings contained in a local database file (no external service dependency).
* **Self‑contained runtime** - pure Python + Flask with all frontend assets vendored locally (no CDN calls); run it bare, as a release binary, or in Docker.

### Extensibility
* **Modular stat / graph command list** - extendable set of Tautulli commands for future metrics.
* **Placeholders system** - simple token replacement for dynamic blocks keeps templating approachable.

### Safety & Transparency
* **Explicit cache clearing** - ensures forced fresh pull when data integrity matters.
* **Exact range enforcement** - avoids quietly reusing mismatched cached spans preventing misleading analytics.

### Quality of Life
* **Pop‑out live preview** - open newsletter preview in new window while editing.
* **Visual template color mapping** - instantly correlate schedule entries and calendar occurrences.
* **Accessible tooltips & titles** - hover details for schedule dots and events.

---

## Quick Start

### 1. Prerequisites

* Python **3.12** or higher  
* A running **Tautulli** instance with an API key  
* SMTP credentials (username & password _or_ an app‑password if using Gmail)

### 2. Installation

You can use newsletterr with Python or Docker:

#### Python
```bash
git clone https://github.com/jma1ice/newsletterr.git
cd newsletterr                 # root of the project
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\\Scripts\\activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

#### Release binaries
Download the zip for your platform from the latest [GitHub release](https://github.com/jma1ice/newsletterr/releases) (newsletterr-linux-x64.zip or newsletterr-windows-x64.zip), unzip it, and run the `newsletterr` executable inside. The app creates its `database/` and `env/` folders next to the executable. For chart images in scheduled emails, install the Playwright browser once with `pip install playwright && playwright install chromium`; without it, emails send without chart images.

#### Docker
Pull `jma1ice/newsletterr:latest` from Docker Hub (or build locally with `docker build -t jma1ice/newsletterr .`), then run:
```
docker run -d --name newsletterr \
  -p 6397:6397 \
  -v newsletterr-db:/app/database \
  -v newsletterr-env:/app/env \
  -v newsletterr-uploads:/app/static/uploads \
  jma1ice/newsletterr:latest
```

Or with docker compose, save this as `docker-compose.yml` and run `docker compose up -d`:
```yaml
services:
  newsletterr:
    image: jma1ice/newsletterr:latest
    container_name: newsletterr
    ports:
      - "6397:6397"
    volumes:
      - newsletterr-db:/app/database
      - newsletterr-env:/app/env
      - newsletterr-uploads:/app/static/uploads
    restart: unless-stopped

volumes:
  newsletterr-db:
  newsletterr-env:
  newsletterr-uploads:
```

### 3. Run

For development:
```bash
python newsletterr.py
```

For production, use gunicorn (a single worker is required because the send scheduler runs in-process; threads provide request concurrency):
```bash
gunicorn -w 1 -k gthread --threads 8 --timeout 180 -b 0.0.0.0:6397 newsletterr:app
```

By default the app listens on **http://127.0.0.1:6397**. Set the `PORT` environment variable to change the port when running `python newsletterr.py`.

On first visit you will be asked to create a login (username and password), then a setup wizard walks you through the initial configuration. Everything the wizard covers can be changed later on the Settings page.

#### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `PORT` | Listen port for `python newsletterr.py`; also determines the internal URL the app uses to call itself for chart capture and image proxying | `6397` |
| `LOG_LEVEL` | Logging verbosity (`DEBUG` shows per-item traces, useful for support) | `INFO` |
| `FLASK_DEBUG` | Set to `1` for the dev server with auto reload | `0` |
| `DATA_ENC_KEY` | Fernet key encrypting stored credentials; auto-generated into `env/.env` on first run | generated |
| `NEWSLETTERR_SECRET_KEY` | Session signing key; auto-generated into `env/.env` so sessions survive restarts | generated |
| `INTERNAL_TOKEN` | Token for the app's internal self-requests | generated per boot |

---

## Configuration

The Settings page is split into sections: **Email Server**, **Connections**, **Data and Stats**, **Email Content**, **Security**, **Hosted Features**, and **Appearance**.

1. Navigate to **Settings** in the navbar.  
2. On the **Connections** section, connect to your Plex server with the **Connect Plex** button. This is used for media posters. Optional connections for **Sonarr** and **Radarr** (coming soon calendar) and **DroppedNeedle** (yearly wrapped music stats) live here too, each with a test button.  
3. Fill in:
   * **From** - e‑mail address that will appear as the sender  
   * **From Name (optional)** - the name you wish to appear when your e-mail is sent  
   * **Alias (optional)** - _Send As_ alias. If blank, **From** will be used, [setup instructions](https://support.google.com/a/answer/33327?hl=en)  
   * **Password** - account or [app‑password](https://support.google.com/mail/answer/185833?hl=en) if using Gmail. App Password is required by Gmail for security, it will not work with your regular Gmail password  
   * **SMTP Username (optional)** - used for SMTP clients that need username login  
   * **SMTP Server** - e.g. `smtp.gmail.com`  
   * **SMTP Port** - `465` for SSL or `587` for TLS  
   * **SMTP Protocol** - select TLS or SSL  
   * **Plex Server Name (optional)** - appears in the newsletter header. This is grabbed when Plex is connected, but can be overwritten if wanted  
   * **Plex URL (optional)** - used to pull posters for recently added items. This is grabbed when Plex is connected, but can be overwritten if wanted  
   * **Tautulli URL (optional)** - e.g. `http://localhost:8181`  
   * **Tautulli API Key (optional)** - make sure 'Enable API' is checked, and copy the API key from your [Tautulli settings.](http://localhost:8181/settings#tabs_tabs-web_interface)  
   * **Conjurr URL (optional)** - e.g. `http://localhost:2665`  
   * **Logo Filename (optional)** - this sets the logo at the top of the newsletter. There are some preset newsletterr options as well as custom and none. To use a custom logo, choose custom as your theme and custom here, then upload your image  
   * **Logo Width (optional)** - use this to adjust the size of your custom logo. A small logo should be ~20, medium ~40, and banner size ~80  
   * **Email Theme** - choose from one of our preset newsletterr blue or plex orange themes, or create your own custom theme! Preset themes use our newsletterr banners, so if you want a custom logo you must choose to use a custom theme  
4. Click **Apply Settings**.  Settings are saved to `database/data.db`.

---

## Sending a Newsletter

1. On the **Dashboard** choose a number of **Recently Added** items to pull from TV, Movies and Audio, a **Time Range** in days for your stats/graphs and click **Get Stats\\Users**.  
2. Wait for the spinner to disappear, then the BCC, charts, and tables will populate.  
3. Alter the BCC field to specify the recipient e‑mails (comma‑separated) if needed.  
4. After altering, if you have connected conjurr, you can click **Get Recommendations** to pull conjurr recommendations for the users currently listed in the BCC field.  
5. Draft the body, use the stats, graphs, recently added, collections, and recommendations snap-ins on the right to include these in your email. 
6. Hit **Send Email**. Success and error messages will show after running.  

---

## Development

```bash
pip install -r requirements-dev.txt
ruff check app/ newsletterr.py tests/   # lint
pytest                                  # test suite, about a minute
```

The email pipeline is covered by golden-master tests: full MIME output is compared against fixtures in `tests/goldens/`. After an intentional change to email output, regenerate them with `UPDATE_GOLDENS=1 pytest tests/test_golden_sends.py` and review the diff.

CI runs lint, tests, and a JS syntax check on every pull request. Docker images publish automatically: pushes to the `nightly` branch build `:nightly`, pushes to `main` build `:pre-release`, and published releases build `:latest`, `:nightly`, `:pre-release`, and the version tag. Release binaries for Linux and Windows are built and attached to each release. The release tag must match the repo `VERSION` file or the build fails.

To back up your data, stop the container (or app) and copy the `database/` and `env/` volumes/folders, or use `sqlite3 database/data.db ".backup backup.db"` while running.

---

## Contributing

Pull requests are welcome. **Open them against the `nightly` branch, not `main`.** `nightly` is the integration branch, so changes get exercised in the `:nightly` image before they reach anyone running a release build. CI fails PRs opened against `main`, and retargeting one is a two-click fix with the "Edit" button next to the PR title.

Before opening a PR, run the same checks CI runs:

```bash
ruff check app/ newsletterr.py tests/                     # lint
pytest                                                    # tests
for f in static/js/app/*.js; do node --check "$f"; done   # JS syntax
```

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the full pre-PR checklist, how to regenerate the golden email fixtures, and the project rules that are easy to break by accident: frozen URL paths, one-way import layering, the central settings store, and settings migrations.

Bug reports are welcome too. Include your newsletterr version, how you are running it (Docker, binary, or from source), and the relevant logs, which the Logs page can export.

---

## License

Released under the **MIT License** - see [LICENSE](LICENSE.txt) for details.

---

## Planned Changes

Work is organized into version sprints. Items may shift between sprints as priorities change.

### v2026.5 - builder features
* More snap-ins: random pick, most watched
* Snap-ins working with custom HTML
* PDF export

### v2026.6 - platform and reach
* Emby/Jellyfin support - jellyfin uses jellywatch over tautulli
* Rootless Docker image with UID/GID support

### v2026.7
* Items pulls episodes in even if it was just a one off, Days only pulls shows in if all the available for that season were added
* Add button to get all available from the 'Get' section

### Community
* GitHub webhook to pull submitted issues to Discord channel
* Ko-fi -> Discord integration for contributor role
* Demo on the website
* Servarr PR

### Blocked on upstream
* Email click for recently added/available recommendations is going to browser on mobile instead of Plex app - this is an issue with the new Plex client, have not seen a fix yet and no info released by Plex at this time

---

## Recent Changes

## v2026.4:

#### New Features:
* Default email layout/UI overhaul with pride theme options
* SVG over emoji where possible in emails
* Clean up looks on DN stats, coming soon, and wrapped
* Email preview: desktop/tablet/phone views
* Custom theme settings
* Searchable settings

#### Fixed:
* UI adjustment to better organize snap-ins sections
* Email BG color not respected by mac mail app

## v2026.3:

#### New Features:
* CSP out of Report-Only after trial run
* Clickable titles in stats tables, going to the item in Plex like recommendations do
* Setting to control how many recommended items appear
* Per library item counts for the Recently Added snap-in
* Show which user requested each item in the Recently Requested snap-in
* Progress bar on the loading spinner where possible

---

## Acknowledgements

* [Tautulli](https://github.com/Tautulli/Tautulli) for the Plex charts, users, and graphs  
* [conjurr](https://github.com/yungsnuzzy/conjurr) for user watchlist based recommendations  
* [DroppedNeedle](https://github.com/HabiRabbu/DroppedNeedle) for user yearly wrapped music  
* [Sonarr](https://github.com/Sonarr/Sonarr) & [Radarr](https://github.com/Radarr/Radarr) for coming soon calendar  
- [Ombi](https://github.com/Ombi-app/Ombi) for recently requested  
- [Seerr](https://github.com/seerr-team/seerr) (works with Overseerr and Jellyseerr) for recently requested  
* [Highcharts](https://www.highcharts.com/) for charting  

Happy streaming!
