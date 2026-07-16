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
pytest                                  # test suite, runs in seconds
```

The email pipeline is covered by golden-master tests: full MIME output is compared against fixtures in `tests/goldens/`. After an intentional change to email output, regenerate them with `UPDATE_GOLDENS=1 pytest tests/test_golden_sends.py` and review the diff.

CI runs lint and tests on every pull request. Docker images publish automatically: pushes to the `nightly` branch build `:nightly`, pushes to `main` build `:pre-release`, and published releases build `:latest`, `:nightly`, `:pre-release`, and the version tag. Release binaries for Linux and Windows are built and attached to each release. The release tag must match the repo `VERSION` file or the build fails.

To back up your data, stop the container (or app) and copy the `database/` and `env/` volumes/folders, or use `sqlite3 database/data.db ".backup backup.db"` while running.

---

## License

Released under the **MIT License** - see [LICENSE](LICENSE.txt) for details.

---

## Planned Changes

### For the v2026.3 sprint, these items are to be addressed:
* Email click for recently added/available recommendations is going to browser on mobile instead of Plex app - this is an issue with the new Plex client, have not seen a fix yet and no info released by Plex at this time
* Email BG color not respected by mac mail app

### And these items are feature requests:
--- Integrations ---
 -- newsletterr GitHub / Discord --
* GitHub webhook to pull submitted issues to Discord channel
* Ko-fi -> Discord integration for contributor role
 -- Other --
* Ombi integration
* Does this work with Emby/Jellyfin? - jellyfin doesn't use tautulli
* Servarr PR
* Clean up looks on DN stats, coming soon, and wrapped

--- UI ---
* Email preview: desktop/tablet/phone views
* Spinner board - filled and smaller
* Custom Theme

--- Email ---
* Possible default email layout/UI overhaul with pride theme
* SVG over emoji if possible in emails
* Hosted image retention moved into settings

--- Misc. ---
* Can Snap-Ins work with custom HTML?
* CSP out of Report-Only after trial run
* Searchable settings
* bferd to GH contribs

---

## Recent Changes

### v2026.2.1:

#### New Features:
* Unsubscribed list

#### Fixed:
* Thanks @bferd for the `includes` to `==` to fix similar library name issue
* Fixed whitespace issue that made emails bigger
* Preview now shows unsubscribe and view in browser link

### v2026.2:

#### New Features:
* Added sections to settings page (email server | connections | data and stats | email content | security | hosted features | appearance)
* Settings changes are now kept on error so user won't have to re-enter them
* Added test api buttons for conjurr and tautulli
* Added setting for custom intro/outro text
* Added HSTS option in security settings
* Added option to use or not use [SCHEDULED] in scheduled email subject
* Added setting for logo positioning
* Added setting to hide play counts in stats and graphs
* Added setting to choose if duration or play counts is used for stats/graphs
* Added an option to pull recently added by # of days. When this is used, "Recently Added" snap-in header now shows 'Added since X date'
* Added option to sort recently added by rating
* Added option for item width of recently added and recommendations grids
* Added option for small cover art of each item in stats tables
* Added To: vs BCC: option for email send
* Added option for setting max image heights to reduce email size
* Added API functionality to pull wrapped stats from DroppedNeedle
* Complete codebase overhaul -> app factory
* SQLite hardened with WAL
* Auth required and extra setup page added for first sign-in
* Visibility for failed sends
* Test send button
* Email builder auto-save
* Pagination in email history, history capped to 1000
* RA by days implemented in 'new schedule creator'
* Export logs button with send to discord
* Stats for total items in library
* Settings submit audits the external tools api test
* Setup Wizard
* Resend from history
* Sonarr/Radarr calendar integration for 'coming soon' type email
* Plex Wrapped Yearly Review
* Date range for stats (i.e. 1.1.25 - 1.1.26) (instead of 'last X days')
* Made collections clickable
* Added a hosted 'most recent newsletter' webpage
* Added opt out support
* Added hosted images to reduce email size
* General UI update/modernization
* More mobile CSS optimizations
* Removed use of Tailwind Play CDN
* Pride UI themes
* Option to show or hide description on recently added posters
* Setting for collection group grid width

#### Fixed:
* Thanks @2wheelsdown for the blank emails fix
* Fixed issue where fresh setup `migrate_email_templates_for_header_title()` calls for `server_name` failed creating a missing `email_header_title` column
* Patched up some SSRF/secrete containment
* CSRF fixes
* Fixed possible double send on scheduled emails
* Bimonthly cadence fix
* Schedule fix for recommendation emails
* API fields in settings are now a password field
* Fixed ra/recs card differing width issues when >5 columns used
* Added a 'pop-up blocked' to index for `save_template()` and similar
* Adjusted issue where some email clients show posters as small slivers
* Fixed where contributor area would start clipping out on lower size screens
* Removed plex-api-client as plexapi.plex was no longer supported
* Fixed changing ra/recs grid width to maintain the correct poster ratio

### v2026.1:

#### New Features:
* GitHub link is now a stylized logo
* Page no longer reloads on stats/users pull
* Added separator blocks to add lines between sections in emails
* Made the header title into a text input (under subject) so that it is editable/removable
* Made 'Title' Text Block drag-able and not pinned to top
* Recently Added now filters out 0 length run time items
* Added functionality for full custom HTML templates
* Added an export email HTML button
* Added an import email template button
* Ratings (G, PG, etc) are now listed on recently added
* Added IMDb ratings in stat tables - requires Tautulli PR approval and then update
* Added snap-ins for images/gifs
* Added emoji support to various Text Block Snap-ins
* Pop out preview now updates with changes to the email

#### Fixed:
* Some CSS Optimizations for mobile - more still in the works
* Timeout on safe_get() extended to 120s so that conjurr api call has enough time to generate the recommendations
* Fixed authentication issue with /proxy-art that made art unavailble in the sent email if a login page was set up
* Fixed a bug where libraries that share name similarities were causing both libraries to be pulled into the 'recently added' snap in
* Fixed graph hanging bug by moving some variable declarations higher and packaging highcharts with the app instead of calls to the CDN
* While we're at it, moved all CDN calls to local files
* Fixed missing smtp_username variable from scheduled email send logic
* Added consistent headers to avoid repeated 'New Device Connected' notifications on Plex API calls
* Fixed bug where recommendations pull would hang for a short period if conjurr is not running
* Fixed bug where missing theme_settings in an early return to index was causing an error updating the preview

---

## Acknowledgements

* [Tautulli](https://tautulli.com/) for the Plex charts, users, and graphs  
* [Highcharts](https://www.highcharts.com/) for charting  
* [Tailwind CSS](https://tailwindcss.com/) & [Bootstrap](https://getbootstrap.com/) for styling
* [conjurr](https://github.com/yungsnuzzy/conjurr) for user watchlist based recommendations  
* [DroppedNeedle](https://github.com/HabiRabbu/DroppedNeedle) for user yearly wrapped music  

Happy streaming!
