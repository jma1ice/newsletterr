# newsletterr

_Turn your Plex server analytics into a beautiful weekly (or whenever‑you‑like) newsletter._

Newsletterr is a lightweight Flask application that talks to **[Tautulli](https://tautulli.com/)**, crunches your Plex statistics, renders charts with **Highcharts**, pulls recommendations from **[conjurr](https://github.com/yungsnuzzy/conjurr)** and emails the results to your user base, all without leaving the browser.

---

## Features

### Data & Content
* **One‑click stats pull** - pick a time range (quick buttons: 7 / 30 / 90 / … days) and “recently added” count; Newsletterr queries Tautulli for most watched movies/shows, active users, platforms, libraries, artists and more.
* **Recently Added injection** - drop `[RECENTLY_ADDED]` where you want the curated recently added block to appear (library selection supported).
* **User Recommendations** - integrate with **conjurr** and insert `[RECOMMENDATIONS]` to show personalized watch suggestions (per BCC list at fetch time).
* **Snap‑ins (drag/add workflow)** - add Stats, Graphs, Text Blocks (Title, Intro, Body, Outro) in any order to compose a tailored newsletter body.

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
* **Smart multi‑segment cache** - stores stats, user data, recent additions, and graph payloads separately.
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
* **SQLite storage** - schedules, templates, email history, lists & settings contained in local database files (no external service dependency).
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
   * **Alias (optional)** - _Send As_ alias. If blank, **From** will be used, [setup instructions](https://support.google.com/a/answer/33327?hl=en)  
   * **Password** - account or [app‑password](https://support.google.com/mail/answer/185833?hl=en) if using Gmail. App Password is required by Gmail for security, it will not work with your regular Gmail password  
   * **SMTP Server** - e.g. `smtp.gmail.com`  
   * **SMTP Port** - `465` for SSL or `587` for TLS  
   * **Plex Server Name** - appears in the newsletter header. This is grabbed when Plex is connected, but can be overwritten if wanted  
   * **Plex URL** - used to pull posters for recently added items. This is grabbed when Plex is connected, but can be overwritten if wanted  
   * **Tautulli URL** - e.g. `http://localhost:8181`  
   * **Tautulli API Key** - make sure 'Enable API' is checked, and copy the API key from your [Tautulli settings.](http://localhost:8181/settings#tabs_tabs-web_interface)  
   * **Conjurr URL** - e.g. `http://localhost:2665`  
   * **Logo Filename** - This sets the logo at the top of the newsletter. To use a custom logo, place your logo file in /static/img/ and add the filename here  
   * **Logo Width** - Use this to adjust the size of your custom logo. A small logo should be ~20, medium ~40, and banner size ~80  
4. Click **Apply Settings**.  Settings are saved to `database/data.db`.

---

## Sending a Newsletter

1. On the **Dashboard** choose a number of **Recently Added** items to pull from TV and Movies, a **Time Range** in days and click **Get Stats\\Users**.  
2. Wait for the spinner to disappear, then the BCC, charts, and tables will populate.  
3. Alter the BCC field to specify the recipient e‑mails (comma‑separated) if needed.  
4. After altering, if you have connected conjurr, you can click **Get Recommendations** to pull conjurr recommendations for the users currently listed in the BCC field.  
5. Draft the body, use the stats/graphs pane on the right to include these in your email. 
6. Choose a library option under Recently Added and insert `[RECENTLY_ADDED]` or `[RECOMMENDATIONS]` in the text box to include these.  
7. Hit **Send Email**. Success and error messages will show after running.  

---

---

## License

Released under the **MIT License** - see [LICENSE](LICENSE) for details.

---

## Upcoming Changes

### v0.9.16
* Find email size regulations, warn on too big | reduce image size to better fall with regulations
* Look into email formatting across email clients
* Make clickable posters for available recommendations to take users to Plex to watch
* Graph titles need to specify the date range - or at least show what time range the data is for somewhere in the email
* Custom logo logic needs file select to work with docker | add in small/banner/custom dropdown - and possibly a 'no logo' option?
* Does Tautulli API support recently added music?
* Logo positioning setting
* Plex 'Secure Connections' setting causing image 401
* Rename 'ra' and 'recs' snap in block for clarity?
* In schedule calendar, template names are showing as template #
* Add more date range options in schedule builder to match dashboard

### v1.0.0
* Compile EXE / ELF files

### v1.1.0
* Switch TV Show recently added info out to just show the show name, not episode or season number || use artwork from the show not the episode/season
* Get fonts showing on Gmail receive side
* Api/webhooks
* Opt out support
* Option for small cover art of each item in a stat table
* IMDb ratings in stat tables
* Make sure custom templates can't override defaults
* Auth page for hosted users
* Snap-in for images/gifs
* Functionality for custom HTML templates | ability to add embedded links to services, ie StatusCake, Uptime Robot
* Ombi integration
* Setting to choose duration or play counts for stats/graphs
* Setting to hide play counts in stats/graphs
* Option to sort recently added by IMDb rating
* Option to pull recently added by # of days - when this is in should be able to show 'new items since x date' in email
* Playlist/Collections in email content - helpful for Kometa seasonal lists
* GitHub webhook to pull submitted issues to Discord channel
* Sonarr/Radarr calendar integration for 'coming soon'
* Servarr PR
* Stats for total items in library
* Ratings (G, PG, etc) listed on recently added
* Export email HTML button
* Export logs button | link to discord
* Biweekly/semimonthly option for scheduled emails | possibly CRON
* Option in settings for width of RA/Recs grids
* Improved BCC list editing
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

### v0.9.15
* Managed users no longer show when pulling recommendations
* Added warning message when email content is over 25mb

### v0.9.14
* If recommendations are in email, email is sent to each user separately
* Logo updated in scheduled send and centered everywhere for now
* Fixed issue when sending a second scheduled email
* Switched from one big image to HTML based for stats/recommendations/recently added
* The recommendations in email have clickable posters to the admins overseerr for requesting unavailable items
* Fixed issue where /env was not creating on first start for new users
* Recently added and recommendations snap-ins integrated into scheduled sending
* Added settings for email coloring - plex orange, newsletterr blue, custom

### v0.9.13
* Adjusted tautulli API error reporting
* Fixed app crash when Tautulli settings are missing - thank you dreondre!
* Reply-To field in settings

### v0.9.12
* Fixed error when using 587 to send email - thank you dreondre!
* SMTP username does not require `@`, falls back to from email if SMTP username is not set - thank you dreondre!
* Split SMTP protocol from port and offer both as options in settings

### v0.9.11
* Moved .env file to a folder to assist with docker persistence
* New docker build and docker run instructions to persist .env file

### v0.9.10
* Added use case info for optional settings
* Fixed issue with blank settings causing app crash
* First use messaging in settings page
* Extra padding on top bar

### v0.9.9
* Cache recommendations/filtered users
* Snap-ins UI for adding recommendations to email
* Replaced Plex logo with yellow newsletterr logo, also added a disclaimer at the end of the email
* Added setting so users can use their own logo
* Included Plex url in the settings page so it can be changed if it pulls incorrectly
* Fixed issue where dashboard preview was initially stuck on light mode
* Fixed cache status text color on dark mode
* Redirect empty settings to the settings page
* Fixed issue where sometimes BCC placeholder was missing
* Unlinked subject from newsletter title, replaced with title snap-in and created headers snap-in for smaller section headers

### v0.9.8
* Plex image un-squished
* PUBLIC_BASE_URL remade into an env var in case docker user changes port
* Scheduled send now grabs recently added / recommendations
* Replaced scheduled recommendation API call with selected users instead of all users
* Set to only pull schedule recommendations if \[RECOMMENDATIONS\] is present
* Fixed issue where on dash graph wouldn't show in 'view' until a stat was 'viewed'
* UI added for recently added in snap-ins

### v0.9.7
* Dockerized!

### v0.9.6
* Fixed scheduled send images to match preview
* Fixed muted text not showing in dark mode
* Light mode dashboard fixes
* Fixed threading issue

### v0.9.5
* Changed some buttons (btn-primary) to match rest of style
* Some UI refresh
* Donate button in about and footer
* Link to conjurr in about

---

## Acknowledgements

* [Tautulli](https://tautulli.com/) for the Plex charts, users, and graphs  
* [Highcharts](https://www.highcharts.com/) for charting  
* [Tailwind CSS](https://tailwindcss.com/) & [Bootstrap](https://getbootstrap.com/) for styling
* [conjurr](https://github.com/yungsnuzzy/conjurr) for user watchlist based recommendations  

Happy streaming!
