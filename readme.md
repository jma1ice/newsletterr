# newsletterr

_Turn your Plex server analytics into a beautiful weekly* (or whenever‑you‑like) newsletter._

Newsletterr is a lightweight Flask application that talks to **[Tautulli](https://tautulli.com/)**, crunches your Plex statistics, renders charts with **Highcharts**, pulls recommendations from **[conjurr](https://github.com/yungsnuzzy/conjurr)** and emails the results to your user base, all without leaving the browser.

---

## Features

* **One‑click stats pull** – choose a time‑range and a recently added number and let Newsletterr query Tautulli for the most‑watched items, top users, and more.  
* **Interactive charts & tables** – Highcharts + HTML tables are rendered in the browser, then flattened into inline images with *html2canvas* so every e‑mail client sees exactly what you see.  
* **WYSIWYG e‑mail preview** – compose the subject & body, drop in `[GRAPHS]` or `[STATS]` tokens, and pick a layout.  
* **SMTP delivery with BCC support** – works with Gmail (app‑password), Outlook, Mailgun, or your own server.  
* **Secure local persistence** – all settings are kept in a tiny encrypted SQLite database inside `database/data.db`.  
* **Zero‑install frontend** – Tailwind + Bootstrap served from a CDN; no Node toolchain required.  
* **Friendly loading spinner** – keep users informed while running scripts complete.

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
4. After altering, if you haveconnected conjurr, you can click **Get Recommendations** to pull conjurr recommendations for the users currently listed in the BCC field.  
5. Draft the body, insert `[GRAPHS]` or `[STATS]` where appropriate.  
6. Check the box on the stats and graphs that you wish to include.  
7. Hit **Send Email**. Success and error messages will show after running.  

---

## Project Structure

```
newsletterr/
├── .env              # environment variables, created at first launch
├── newsletterr.py    # Flask routes & helper functions
├── templates/
│   ├── partials/
|   │  └── _recommendations.html
│   ├── about.html
│   ├── base.html
│   ├── index.html
│   └── settings.html
├── static/
│   ├── css/style.css
│   └── img/
|      ├── Asset_94x.png
│      ├── favicon.ico
│      └── load.gif
├── database/data.db  # created at first launch
├── README.md         # this file
└── requirements.txt  # pip requirements
```

---

## License

Released under the **MIT License** – see [LICENSE](LICENSE) for details.

---

## Upcoming Changes

### v0.8.0
* Update functionality (new version available)
* Add width to email/preview subject section
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
* Opt out support?
* (Done) Checking "include XYZ in email" buttons should trigger them to be added to the previewed email in realtime, as snap-ins that can be removed on the fly as well. Maybe a button instead of a check box? 
* (Done) Graph/stat ordering? Should it have a default ordering, or user editable? 
* (Done) Email history - list of when emails were sent, and to whom
* (Done) Email BCC list management
* (Done) clean up UI, move stats/graphs
* Graph titles need to specify the date range
* (Done) made "newsletterr" footer a link
* (Done) pop-out email preview

### v1.0
* Dockerize
* Compile EXE and ELF files

---

## Recent Changes

### v0.7.3
* Get conjurr recommendations into a layout and snap-in for emails

### v0.7.2
* Recently added layout autofills subject
* Server name into recently added layout
* Recently added into server side email
* Recently added placeholder for snap insert

### v0.7.1
* Only get recommendations for users in BCC list
* Buttons added to pull frequent time ranges
* Options for # recently added to pull
* Fixed alert not showing after conjurr pull

### v0.7.0
* Conjurr integration first iteration
* Make recently added area 10 wide

---

## Acknowledgements

* [Tautulli](https://tautulli.com/) for the Plex goodness  
* [Highcharts](https://www.highcharts.com/) for charting  
* [Tailwind CSS](https://tailwindcss.com/) & [Bootstrap](https://getbootstrap.com/) for styling

Happy streaming!
