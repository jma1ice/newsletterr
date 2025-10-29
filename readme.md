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
* **Self‑contained runtime** - pure Python + Flask + CDN assets; no Node build or container required (optional packaging roadmap below).

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

* Python **3.9** or higher  
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

#### Docker
On docker hub: jma1ice/newsletterr:latest
or build locally: 
```
docker run -d --name newsletterr \
  -p 6397:6397 \
  -e PUBLIC_BASE_URL=http://127.0.0.1:6397 \
  -v newsletterr-db:/app/database \
  -v newsletterr-env:/app/env \
  -v newsletterr-uploads:/app/static/uploads \
  jma1ice/newsletterr:latest
```

### 3. Run

```bash
python newsletterr.py
```

By default the app listens on **http://127.0.0.1:6397**.

---

## Configuration

1. Navigate to **Settings** in the navbar.  
2. Connect to your Plex server with **Connect Plex** button. This is used for media posters.  
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

---

## License

Released under the **MIT License** - see [LICENSE](LICENSE) for details.

---

## Planned Changes

### For the v2025.2 sprint, these items are to be addressed:
* Email click for recently added/available recommendations is going to chrome on mobile instead of app
* Some clients show posters as small slivers instead of whole poster
* Why is this generating 'New Device Connected' notifications for some?
* Are libraries capped to 5 for some reason?

#### And these items are feature requests:
* Make top title into a text block so it is editable/removable
* Have 'Expand' option on collections to switch to showing items in collection
* Don't have page reload on stats/users pull
* Keep settings details on error so user won't have to re-enter them
* GitHub link should be the stylized logo
* Api/webhooks?
* Option for small cover art of each item in a stat table
* IMDb ratings in stat tables
* Auth page for hosted users | when this is in, add a hosted 'most recent newsletter' webpage | also when this is in, add opt out support | also hosted images to reduce email size
* Snap-in for images/gifs/emojis
* Functionality for full custom HTML templates
* Ombi integration
* Setting to choose duration or play counts for stats/graphs
* Setting to hide play counts in stats/graphs
* Option to sort recently added by IMDb rating
* Option to pull recently added by # of days - when this is in should be able to show 'new items since x date' in email
* GitHub webhook to pull submitted issues to Discord channel
* Sonarr/Radarr calendar integration for 'coming soon'
* Servarr PR
* Stats for total items in library
* Ratings (G, PG, etc) listed on recently added
* Export email HTML button
* Export logs button | link to discord
* Option in settings for width of RA/Recs grids
* Ko-fi -> Discord integration for contributor role
* Logo positioning setting
* Test api button
* Add in To: vs BCC: option
* Make collections clickable - is this possible?
* Mobile optimizations, i.e.:
```
<style>
   @media (max-width: 600px) {
      .stack { display:block !important; width:100% !important; }
      .gpx { padding-left:0 !important; padding-right:0 !important; }
      .poster { width:100% !important; height:auto !important; }
   }
</style>
```

---

## Recent Changes

### v2025.1

#### Fixed:
* Added a wait for certain variables in schedule sender that was affecting some users
* A lot of logic moved into if/main to prep for exe release

#### New Features:
* Compiled EXE and ELF files


### v0.9.17

#### Fixed:
* Allow for multiple named collections sections
* Collections no longer get stuck to bottom of email
* If no collections art it now shows plexs 2x2 'composite' image
* Moved background workers start call to app start instead of webpage visit
* Recently added now uses artwork from the show not the episode/season
* Recently added now filters for when episodes of a show are found and only adds one instance of that show
* Fixed everywhere days and # of items is hardcoded
* Recently added pulls show info over episode info when available
* Switched recently added pull from Tautulli to direct Plex API call. This fixes 100 item limit
* Added 'ALL' BCC list to scheduler options
* Now shows # of items in scheduler table
* Fixed 0m for shows and audio changed to genre
* Fixed the issue with RA cards showing up as different heights in different email clients
* Added a font fallback stack
* Now gets https direct connect plex url by default, fixing issue where Plex 'Secure Connections > Required' setting was causing image 401
* Made BCC lists editable
* Stat titles now include the date range they were pulled for

#### New Features:
* Added more date range options in schedule builder to match dashboard
* Added many more options for scheduled emails frequency
* Added collections snap-in - thank you yungsnuzzy!
* Custom logo logic in settings. Added in small/banner/custom/none dropdown - thanks dreondre!
* Got rid of library name on recently added overlay
* Made posters clickable for available recommendations and recently added items to take users to Plex to watch
* Added option for recs to show email/username/friendly name
* Nixed the view buttons
* Renamed 'ra' and 'recs' snap in block for clarity
* Changed date on recently added to days since added
* Added an HTML Block to text blocks for easy link adding
* Graph overhaul - fixed fonts, sizing, and added date range graph is for to title

---

## Acknowledgements

* [Tautulli](https://tautulli.com/) for the Plex charts, users, and graphs  
* [Highcharts](https://www.highcharts.com/) for charting  
* [Tailwind CSS](https://tailwindcss.com/) & [Bootstrap](https://getbootstrap.com/) for styling
* [conjurr](https://github.com/yungsnuzzy/conjurr) for user watchlist based recommendations  

Happy streaming!
