# newsletterr

_Turn your Plex server analytics into a beautiful weekly (or whenever‑you‑like) newsletter._

Newsletterr is a lightweight Flask application that talks to **[Tautulli](https://tautulli.com/)**, crunches your Plex statistics, renders charts with **Highcharts**, pulls recommendations from **[conjurr](https://github.com/yungsnuzzy/conjurr)** and emails the results to your user base, all without leaving the browser.

---

## Features

### Data & Content
* **Plex or Jellyfin** - choose your media server in Settings; Jellyfin uses Jellywatch for stats (the role Tautulli fills for Plex) and Seerr or Ombi for requests, with recently added, library counts, and deep links working the same either way.
* **One‑click stats pull** - pick a time range (quick buttons: 7 / 30 / 90 / … days) and "recently added" count; Newsletterr queries Tautulli for most watched movies/shows, active users, platforms, libraries, artists and more.
* **User Recommendations** - integrate with **conjurr** to show personalized watch suggestions (per BCC list at fetch time).
* **Snap‑ins (drag/add workflow)** - add Stats, Graphs, Recently Added (library selection supported), Most Watched, Random Pick, Featured Pick, Top Viewer, Recommendations, Collections, and Text Blocks (Title, Header, Intro, Body, Outro) in any order to compose a tailored newsletter body.

### Visualization
* **Interactive charts** - Highcharts rendered in‑app; suitable images captured for reliable e‑mail client display.
* **Styled data tables** - Plex / Tautulli metrics rendered as clean, responsive tables prior to embedding.
* **Live WYSIWYG preview** - side‑by‑side iframe updates instantly as you assemble the email.
* **Five email layouts** - Polished Classic, Editorial, Compact Digest, Spotlight, and Legacy; pick one in Settings and every preview and send follows it.
* **Compact or expanded density** - a second setting that applies to whichever layout you picked. Compact drops posters and thumbnails, stacks card grids into one column, and tightens padding and type; Expanded is the roomy version with full artwork.

### Templates & Reuse
* **Email Templates** - save, load, clone, and delete custom templates (tracks chosen snap‑ins & layout) and re‑apply later.
* **Template provenance tracking** - every sent email logs which template (or “Manual”) produced it; visible in Email History.
* **Snap-in tokens in custom HTML** - drop `{{snapin:NAME}}` tokens into hand-written HTML to render live sections; see [Snap-in tokens in custom HTML](#snap-in-tokens-in-custom-html).

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

The image runs as a non-root user (uid 1000) by default. To use linuxserver.io-style
ownership instead, start the container as root with `PUID`/`PGID` set and the
entrypoint will chown the volumes to that user before dropping privileges:
```
docker run -d --name newsletterr \
  -p 6397:6397 \
  --user 0:0 \
  -e PUID=1000 -e PGID=1000 \
  -v newsletterr-db:/app/database \
  -v newsletterr-env:/app/env \
  -v newsletterr-uploads:/app/static/uploads \
  jma1ice/newsletterr:latest
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
| `PUID` / `PGID` | When the Docker container is started as root, the uid/gid to chown volumes to and drop privileges into (linuxserver.io convention) | container's built-in `app` user |
| `DEMO_MODE` | Set to `1` for a public showcase: auth is bypassed (no login or logout), the app runs on a sample library so every page and the live preview have content, appearance/layout/email options apply to the visitor's session instead of being saved, and sends are answered with a notice | `0` |

---

## Configuration

The Settings page is split into sections: **Email Server**, **Connections**, **Data and Stats**, **Email Content**, **Security**, **Hosted Features**, and **Appearance**.

1. Navigate to **Settings** in the navbar.  
2. On the **Connections** section, connect to your Plex server with the **Connect Plex** button. This is used for media posters. Optional connections for **Sonarr** and **Radarr** (coming soon calendar) and **DroppedNeedle** (yearly wrapped music stats) live here too, each with a test button.  
3. Fill in:
   * **From** - e‑mail address that will appear as the sender  
   * **From Name (optional)** - the name you wish to appear when your e-mail is sent  
   * **Alias (optional)** - _Send As_ alias. If blank, **From** will be used, [setup instructions](https://support.google.com/a/answer/33327?hl=en)  
   * **Authentication** - Password (the default, and what every existing install keeps using) or Microsoft OAuth. Outlook.com and Microsoft 365 accounts need OAuth, see [Sending through Outlook.com or Microsoft 365](#sending-through-outlookcom-or-microsoft-365) below  
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
   * **Email Layout** - the overall design of the email. Polished Classic tightens the classic look into one card system, Editorial is a magazine treatment, Compact Digest is a dense one-scroll digest, Spotlight is a dark stack of cards that leads with one featured title and ends with a button to your server, and Legacy is the pre-v2026.4 look unchanged
   * **Email Density** - Compact or Expanded, applied to whichever layout is selected above. Compact drops posters, thumbnails and card backgrounds, stacks card grids into a single column, and tightens the padding and type for a short scroll; Expanded is the roomy version with full artwork. Each layout starts on the density it already rendered at, so nothing moves until you change it: Editorial and Compact Digest start on Compact, Polished Classic, Spotlight and Legacy start on Expanded
   * **Server Name in Header (optional)** - the Polished Classic, Editorial, Compact Digest, and Spotlight layouts can print your server name in the email header. Hidden by default, so the header shows just your logo and header title; set this to Show to add the name back  
   * **Header Eyebrow Text (optional)** - the small uppercase line above the header title in the Editorial and Spotlight layouts. Blank falls back to your server name when Server Name in Header is on, and otherwise prints nothing unless Auto Header Text is enabled  
   * **Auto Header Text (optional)** - off by default. When on, a blank header title or eyebrow falls back to newsletterr's stock wording ("Your server", "This week on the server", "Your server, this month") in the Editorial and Spotlight layouts. When off, a blank field simply leaves the line out  
   * **Header Background (optional)** - the area behind the logo and header title. Theme gradient blends your accent and primary colors; pick Solid color for a single color, which is safer in clients that drop gradients  
4. Click **Apply Settings**.  Settings are saved to `database/data.db`.

### Sending through Outlook.com or Microsoft 365

Microsoft no longer accepts a password for SMTP. Personal Outlook.com mailboxes cannot enable password authentication at all, and Exchange Online is disabling it for organizations by default at the end of December 2026. A password there fails with `535 5.7.139 Authentication unsuccessful, basic authentication is disabled`. Gmail is unaffected and still works with an app password.

SMTP itself still works, it just needs an OAuth token. newsletterr does not ship a Microsoft application registration, so each install registers its own. It takes about five minutes and only has to be done once.

1. Sign in to the [Microsoft Entra admin center](https://entra.microsoft.com) and go to **Applications** then **App registrations** then **New registration**.
2. Give it any name, for example `newsletterr`. Under **Supported account types** choose the option that covers your mailbox. For a personal Outlook.com address pick the one that includes personal Microsoft accounts.
3. Leave **Redirect URI** empty and register. The device code flow does not use one, which is why newsletterr works on any host and port without extra configuration.
4. On the app's **Authentication** page, set **Allow public client flows** to **Yes**. Without this the sign-in fails.
5. On **API permissions** choose **Add a permission**, then **APIs my organization uses**, search for **Office 365 Exchange Online**, choose **Delegated permissions**, and add **SMTP.Send**. Add **offline_access** as well: it is what lets scheduled sends keep working after the first hour.
6. Copy the **Application (client) ID** from the app's Overview page.
7. In newsletterr, open **Settings**, set **Authentication** to **Microsoft OAuth**, paste the client ID, and leave the tenant as `common` unless your organization requires a specific one.
8. Click **Connect Microsoft account**, open the link shown, enter the code, and approve. The page confirms the connected address once consent completes.
9. Set **SMTP Server** to `smtp.office365.com`, **SMTP Port** to `587`, and **SMTP Protocol** to `TLS`, then click **Apply Settings**.

Tokens are stored encrypted in the database and refreshed automatically before each send, including scheduled sends that run with nobody signed in. If the connection is ever revoked on Microsoft's side, sends fail with a message asking you to reconnect, and the **Connect Microsoft account** button re-runs the flow. Note that some organizations block unapproved applications, in which case a tenant administrator has to approve the registration.

---

## Sending a Newsletter

1. On the **Dashboard** choose a number of **Recently Added** items to pull from TV, Movies and Audio, a **Time Range** in days for your stats/graphs and click **Get Stats\\Users**.  
2. Wait for the spinner to disappear, then the BCC, charts, and tables will populate.  
3. Alter the BCC field to specify the recipient e‑mails (comma‑separated) if needed.  
4. After altering, if you have connected conjurr, you can click **Get Recommendations** to pull conjurr recommendations for the users currently listed in the BCC field.  
5. Draft the body, use the stats, graphs, recently added, collections, and recommendations snap-ins on the right to include these in your email. 
6. Hit **Send Email**. Success and error messages will show after running.  

An added Recently Added or Most Watched snap-in stays editable in the email body list, so you do not have to remove and re-add it to change how it renders:

* **Items/Titles** - the per-library count, blank to use the number you pulled
* **Display** (Recently Added) - Layout default, Horizontal grid, or Vertical list. Layout default keeps each email layout's own treatment; the grid uses the Recently Added Grid Columns setting
* **Spotlight feature** (Recently Added, shown when the Spotlight layout is selected) - which title the layout leads with. Defaults to the newest item, and falls back to it if the chosen title is no longer in the pull

### Snap-in tokens in custom HTML

When the **Custom HTML** toggle is on, you write the whole email yourself, but you can still drop rendered snap-in sections into it with tokens. A token looks like `{{snapin:NAME}}` or `{{snapin:NAME:ARG}}` and is replaced at preview and send time by the same section the builder would produce, in your selected email layout. The **Insert snap-in** dropdown above the editor lists every token valid for the data you have pulled and inserts it at the cursor.

| Token | Renders |
|---|---|
| `{{snapin:recently_added:Movies}}` | Recently Added grid for the named library |
| `{{snapin:recently_added:Movies:5}}` | Same, capped to 5 items |
| `{{snapin:recently_added:Movies:list}}` | Same, forced to the vertical list display; combine with a count as `:Movies:5:list` |
| `{{snapin:most_watched:Movies}}` | Most Watched grid for the named library (all-time play counts) |
| `{{snapin:most_watched:Movies:recent}}` | Same, scoped to plays within the pulled time range; combine with a count as `:Movies:5:recent` |
| `{{snapin:random_pick:Movies}}` | One random item from the named library (fresh pick every send) |
| `{{snapin:featured_pick:The Grand Voyage}}` | One title you choose, matched by name at send time |
| `{{snapin:top_viewer}}` | Callout for whoever streamed the most over the pulled time range |
| `{{snapin:stats:Most Watched Movies}}` | The stats table with that title |
| `{{snapin:wrapped}}` | Year in Plex wrapped section |
| `{{snapin:coming_soon_tv}}` | Coming Soon (TV) from Sonarr |
| `{{snapin:coming_soon_movies}}` | Coming Soon (Movies) from Radarr |
| `{{snapin:requests_ombi}}` | Recent requests from Ombi |
| `{{snapin:requests_seerr}}` | Recent requests from Overseerr/Jellyseerr |
| `{{snapin:dn_server}}` | DroppedNeedle server stats |

Library names and stat titles are matched case-insensitively and may contain spaces (but not colons). Sections render from the data cached by the pull buttons, so pull first. A misspelled token never breaks the email; it is replaced with an HTML comment you can spot in the output source. Graph snap-ins are not available as tokens because their images are captured client-side per builder item.

### Personalization tokens

A second, unrelated kind of token that fills in the recipient's own details rather than a whole section. These work anywhere you can type: a text block, the message body, or custom HTML.

| Token | Becomes |
|---|---|
| `{{name}}` | The recipient's saved name, e.g. "Ada Lovelace" |
| `{{first_name}}` | Just the first word of it, e.g. "Ada" |
| `{{email}}` | The address the email is going to |

Names come from your saved contacts, which the CSV import fills in. A recipient with no saved name is greeted as "there", so `Hi {{name}},` reads as "Hi there," rather than "Hi ,".

**A template using one of these sends individually to each recipient rather than as one BCC message**, because the content is no longer the same for everyone. That is slower on a large list, and the builder tells you when a token is in play. Snap-in tokens above do not do this: they render the same section for everyone.

---

## Development

```bash
pip install -r requirements-dev.txt
ruff check app/ newsletterr.py tests/   # lint
pytest                                  # test suite, about six minutes
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

### Community
* GitHub webhook to pull submitted issues to Discord channel
* Ko-fi -> Discord integration for contributor role
* Servarr PR

### Blocked on upstream
* Email click for recently added/available recommendations is going to browser on mobile instead of Plex app - this is an issue with the new Plex client, have not seen a fix yet and no info released by Plex at this time
* Ask Conjurr for N recommendations over the API instead of slicing after enrichment - needs a Conjurr-side count parameter; falls back to the current slice until that exists

---

## Recent Changes

## v2026.4.5:

#### New Features:
* Demo mode's Scheduling and Email History pages now have sample content: four schedules (one paused) laid out across the calendar, and a send log with sent, skipped and failed entries. Both pages used to open on an empty state, which made two of the headline features look like they did nothing
* New warnings when Tautulli is reporting stale libraries that are not found in Plex
* Option for setting up OAuth in Outlook since basic auth is being depreciated there
* 5 SMTP connect instances moved to one central occurrence

#### Fixed:
* The logo could render at its own full size instead of the size you set. Outlook ignores the CSS that held it, and several clients (Thunderbird, Yahoo on Android, the stock Android mail app) drop the stylesheet altogether. The stock logo is 2512px wide, so the header blew open, and because the message was then forced wider than the screen those clients zoomed the whole email out until the body was too small to read. The width is now stated inline and in the stylesheet as well as on the image itself, so no single one of them has to survive
* Poster images in card grids carried a percentage width. Outlook does not honor that on an image and fell back to the file's own size, bursting the cell and pulling the grid out of alignment. Every poster and chart now carries an explicit pixel width
* Card grids never reflowed on a phone in the classic, editorial, digest and spotlight layouts. The responsive rules only matched class names the legacy layout produces, so a phone got five cards across at about 56px each, with titles breaking in the middle of a word. All five layouts now share one grid treatment and stack to three readable columns
* Emails scrolled sideways on a phone. The outer container was full width plus a 1px border and did not count the border in its own width, so it measured two pixels wider than the screen
* The Most Watched table rendered as a white block with dark text in the middle of an otherwise dark email on some clients. Its colors were written in directly as semi transparent white rather than taken from your theme, and clients that do not blend transparency fell back to solid white
* A six column stats table cannot fit a phone, which is what made the legacy layout scroll sideways. Cert. and Score now drop out below 600px, leaving Title, Year and Plays
* IBM Plex Sans was pulled in by an @import at the very top of the stylesheet. Gmail can stop reading a stylesheet when it meets one, which would have taken the mobile rules with it, and it also meant every reader's mail client fetched a file from Google on open. The font is now requested from the document head instead, and hidden from Outlook, which falls back to Times New Roman when it sees a webfont it cannot load
* Yahoo silently drops a CSS rule that has a comment directly in front of it, and drops any !important with a space before it. Both patterns were in the email stylesheet, and one of the rules at risk was the one that collapses empty calendar cells on a phone
* Table cells with a background color now carry a matching bgcolor attribute as well, for the clients that ignore the CSS
* A recommendation score could print as a raw number such as 7.6999999999999999 instead of 7.7
* Emails declared themselves light only while every email theme paints a dark background. Gmail on Android took that at its word and lightened the message, so artwork arrived washed out and pale. The declaration now follows whichever theme you are actually using
* Coming Soon posters in the agenda view were still washed out in Gmail's Android dark mode, which drains the color from any image under about 56px. They are now 64px. Smaller thumbnails elsewhere are still affected: growing them enough to clear that threshold would add several hundred pixels of height to a section in every other client, and the stats thumbnails it would affect most can already be turned off under Stats and Graphs

## v2026.4.4:

#### New Features:
* Standalone mode: run newsletterr with no media server at all, as a plain mailing list tool. Setup now asks which you want, and the media snap-ins stay out of the builder
* Import recipient lists from a CSV or by pasting addresses, with names picked up alongside them. Accepts a header row or none, tabs or commas, and the "Name &lt;address&gt;" form mail clients produce
* Every rejected row from an import is reported with its line number, and addresses that have unsubscribed cannot come back in through a file
* Export any saved list as a CSV
* Link Jellyfin users to email addresses. Jellyfin does not store them, so importing a list with names links what it can automatically, and Settings has a table to fill in or correct the rest
* Once linked, per-user recommendations, per-user DroppedNeedle wrapped and personalized sends work on Jellyfin the same way they do on Plex
* Default landing page after login
* Calendar week can start on Sunday or Monday, in the scheduling calendar and in the Coming Soon calendar view
* Date and time format settings (month/day/year, day/month/year or year/month/day, and 12 or 24 hour), applied everywhere a date is shown to a reader including sent emails
* Skip-on-no-new now lets you pick which sections count as new content, across recently added, most watched, recently released, both Coming Soon snap-ins and both request snap-ins
* Skip-on-no-new also takes a minimum item count, so a schedule can wait for a week worth mailing about rather than firing on a single item
* Album art on the DroppedNeedle wrapped card, matched from the music database
* Choose which DroppedNeedle lists appear (artists, tracks, albums, genres) and how many rows each one shows
* Extra Year in Review highlights: popular movie, popular show, top platform, top library and peak streams
* Year in Review can show the top 1, 3 or 5 of each highlight instead of just the winner
* **Emby support, untested.** Jellyfin forked from Emby, so they speak nearly the same API and share one client here, but this was written against Emby's documentation rather than verified against a real server. Pick it in Settings under Media Server and use the Jellyfin fields for the URL and API key. Reports of what breaks are very welcome
* Graphs on Jellyfin and Emby, via the Playback Reporting plugin. Jellywatch keeps no history over time, so graphs need that plugin installed on your server; it reuses the URL and API key you already entered. Offers Plays by Date, by Day, by Hour, by Top Users and by Top Platforms. The other Plex graphs have no equivalent in the plugin and are not offered, and if the plugin is missing the graph list simply stays empty
* Most Watched now works on Jellyfin, via Jellywatch. Note it groups by media type (Movies, TV Shows, Music) rather than per library, because Jellywatch reports play counts by type; the counts are server-wide, which is what the section means on Plex
* The inactive-recipient filter now works on Jellyfin too, using each account's last activity date. It still fails open everywhere: if the server cannot be asked, nobody is filtered out of a send
* Personalization tokens: `{{name}}`, `{{first_name}}` and `{{email}}` in any text block or custom HTML, filled in per recipient from your saved contacts. A template using one sends individually rather than as one BCC message, and the builder says so while you write it
* New scheduling option: skip the send when the email would come out empty. A catch-all next to the per-section triggers, for when every section returns nothing. Headers, footers and text blocks do not count as content, and a section showing "no items found" counts as empty rather than as content
* Demo mode is now an actual demo: it runs on a sample library (recently added, stats, graphs, recommendations, wrapped, coming soon and requests, with placeholder artwork), the builder opens with a newsletter already assembled, and the live preview renders it for real. Appearance, UI theme, email theme, layout and density can all be switched on the Settings page and take effect immediately for that visitor without saving anything

#### Fixed:
* The per-user DroppedNeedle wrapped card ignored the email layout, rendering the same plain lists under editorial, digest and spotlight instead of matching the rest of the email
* Recommendations, collections and graphs also ignored the email layout, so a classic, editorial, digest or spotlight email had sections that did not match the rest of it. Every data section now follows the layout you picked
* Jellyfin never loaded a user list, so recipients could not be pulled from the server and no per-user section had anyone to address
* The wrapped card fell back to a numeric user id when there was no Tautulli user list to read a name from, which was every Jellyfin install
* Demo mode showed a logout button that emptied the session and dropped the visitor into first-run setup, and the live preview came back empty because the render request was blocked as a write
* The Most Watched snap-in ignored the Stats and Graphs metric setting: it always ranked and labelled by play count, even with Duration picked. It now ranks by time watched and labels cards with it. Tautulli reports no watch time in its per-library media list, so an all-time section on Duration is aggregated from that library's history, which covers its most recent 1000 plays
* Demo mode's Most Watched section listed no libraries, because the sample data was built in the wrong shape for the snap-in

---

## Acknowledgments

* [Tautulli](https://github.com/Tautulli/Tautulli) for the Plex charts, users, and graphs  
* [Jellyfin](https://github.com/jellyfin/jellyfin) & [Jellywatch](https://github.com/JellyWatchteam/JellyWatch) APIs for Jellyfin 'Stats/Graphs' and recently added
* [conjurr](https://github.com/yungsnuzzy/conjurr) for user watchlist based recommendations  
* [DroppedNeedle](https://github.com/HabiRabbu/DroppedNeedle) for user yearly wrapped music  
* [Sonarr](https://github.com/Sonarr/Sonarr) & [Radarr](https://github.com/Radarr/Radarr) for coming soon calendar  
* [Ombi](https://github.com/Ombi-app/Ombi) for recently requested  
* [Seerr](https://github.com/seerr-team/seerr) (works with Overseerr and Jellyseerr) for recently requested  
* [Highcharts](https://www.highcharts.com/) for charting  

Happy streaming!
