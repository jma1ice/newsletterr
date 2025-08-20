# newsletterr

_Turn your Plex server analytics into a beautiful weekly* (or whenever‑you‑like) newsletter._

Newsletterr is a lightweight Flask application that talks to **[Tautulli](https://tautulli.com/)**, crunches your Plex statistics, renders charts with **Highcharts**, pulls recommendations from **[conjurr](https://github.com/yungsnuzzy/conjurr)** and emails the results to your user base, all without leaving the browser.

---

## Features

* **One‑click stats pull** - choose a time‑range and a recently added number and let Newsletterr query Tautulli for the most‑watched items, top users, and more.  
* **Interactive charts & tables** - Highcharts + HTML tables are rendered in the browser, then flattened into inline images with *html2canvas* so every e‑mail client sees exactly what you see.  
* **WYSIWYG e‑mail preview** - compose the subject & body, drop in `[GRAPHS]` or `[STATS]` tokens, and pick a layout.  
* **SMTP delivery with BCC support** - works with Gmail (app‑password), Outlook, Mailgun, or your own server.  
* **Secure local persistence** - all settings are kept in a tiny encrypted SQLite database inside `database/data.db`.  
* **Zero‑install frontend** - Tailwind + Bootstrap served from a CDN; no Node toolchain required.  
* **Friendly loading spinner** - keep users informed while running scripts complete.
* **Watch history based recommendations** - use conjurr for recommendations for your users.

---

## Quick Start

### 1. Prerequisites

* Python **3.9** or higher  
* A running **Tautulli** instance with an API key  
* SMTP credentials (username & password _or_ an app‑password if using Gmail)

### 2. Installation

```bash
git clone https://github.com/jma1ice/newsletterr.git
cd newsletterr                 # root of the project
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\\Scripts\\activate
python -m pip install -r requirements.txt
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
   * **From** – e‑mail address that will appear as the sender  
   * **Alias (optional)** – _Send As_ alias. If blank, **From** will be used, [setup instructions](https://support.google.com/a/answer/33327?hl=en)  
   * **Password** – account or [app‑password](https://support.google.com/mail/answer/185833?hl=en) if using Gmail  
   * **SMTP Server** – e.g. `smtp.gmail.com`  
   * **SMTP Port** – `465` for SSL or `587` for TLS  
   * **Plex Server Name** – appears in the newsletter header. This is grabbed when Plex is connected, but can be overwritten if wanted  
   * **Tautulli URL** – e.g. `http://localhost:8181`  
   * **Tautulli API Key** – make sure 'Enable API' is checked, and copy the API key from your [Tautulli settings.](http://localhost:8181/settings#tabs_tabs-web_interface)  
   * **Conjurr URL** – e.g. `http://localhost:2665/`  
4. Click **Apply Settings**.  Settings are saved to `database/data.db`.

---

## Sending a Newsletter

1. On the **Dashboard** choose a number of **Recently Added** items to pull from TV and Movies, a **Time Range** in days and click **Get Stats\\Users**.  
2. Wait for the spinner to disappear, then the BCC, charts, and tables will populate.  
3. Alter the BCC field to specify the recipient e‑mails (comma‑separated) if needed.  
4. After altering, if you have connected conjurr, you can click **Get Recommendations** to pull conjurr recommendations for the users currently listed in the BCC field.  
5. Draft the body, insert `[GRAPHS]` or `[STATS]` where appropriate.  
6. Check the box on the stats and graphs that you wish to include.  
7. Hit **Send Email**. Success and error messages will show after running.  

---

## Project Structure

```
newsletterr/
├── .env              # environment variables, created at first launch
├── newsletterr.py    # Flask routes & helper functions
├── .github/workflows/
│   └── release-to-discord.yml
├── templates/
│   ├── partials/
│   │   └── _recommendations.html
│   ├── about.html
│   ├── base.html
│   ├── email_history.html
│   ├── index.html
│   └── settings.html
├── static/
│   ├── css/style.css
│   └── img/
│       ├── Asset_94x.png
│       ├── favicon.ico
│       └── load.gif
├── database/
│   ├── data.db       # created at first launch
│   ├── email_history.db
│   ├── email_lists.db
│   └── email_templates.db
├── README.md         # this file
└── requirements.txt  # pip requirements
```

---

## License

Released under the **MIT License** – see [LICENSE](LICENSE) for details.

---

## Upcoming Changes

### v0.8.8
* Donate button
* Light mode dash fixes
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

### v0.9.0
* Add in scheduled newsletter functionality
* Mailing lists (Weekly, monthly, Movies, Shows) that you can add users to, to automate some emails. E.g. - Monthly email contains the following users, and uses the following template. 
* Template management to go with lists - Include a few default templates that snap in the most common stats
* Automation management (Which lists, how often?)
* Graph titles need to specify the date range

### v1.0.0
* Dockerize
* Compile EXE and ELF files

### v1.1.0
* Get fonts showing on Gmail receive side
* Api/webhooks
* Opt out support

---

## Recent Changes

### v0.8.7
* Removed graph/stat placeholders
* Got graphs and stats on separate lines

### v0.8.6
* Got images to show in both Spark and Gmail
* Dark mode UI cleanup

### v0.8.5
* Added email templates, history, and BCC list management
* UI cleanup
* Email preview pop out functionality

### v0.8.4
* Snap-ins! Graph/stat ordering pane
* Made footer 'newsletterr' a link

### v0.8.3
* Added width to email/preview subject section

### v0.8.2
* yml fixed for github>discord bot

### v0.8.1
* Fixed some issues with update checker
* Added release bot yaml

### v0.8.0
* Marked optional entries in settings
* Update banner when new version detected

---

## Acknowledgements

* [Tautulli](https://tautulli.com/) for the Plex charts, users, and graphs  
* [Highcharts](https://www.highcharts.com/) for charting  
* [Tailwind CSS](https://tailwindcss.com/) & [Bootstrap](https://getbootstrap.com/) for styling
* [conjurr](https://github.com/yungsnuzzy/conjurr) for user watchlist based recommendations  

Happy streaming!
