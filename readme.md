# Newsletterr

_Turn your Plex server analytics into a beautiful weekly* (or whenever‑you‑like) newsletter._

Newsletterr is a lightweight Flask application that talks to **[Tautulli](https://tautulli.com/)**, crunches your Plex statistics, renders charts with **Highcharts**, and emails the results to your user base, all without leaving the browser.

---

## Features

* **One‑click stats pull** – choose a time‑range and let Newsletterr query Tautulli for the most‑watched items, top users, and more.  
* **Interactive charts & tables** – Highcharts + HTML tables are rendered in the browser, then flattened into inline images with *html2canvas* so every e‑mail client sees exactly what you see.  
* **WYSIWYG e‑mail preview** – compose the subject & body, drop in `[GRAPHS]` or `[STATS]` tokens, and pick a layout.  
* **SMTP delivery with BCC support** – works with Gmail (app‑password), Outlook, Mailgun, or your own server.  
* **Secure local persistence** – all settings are kept in a tiny SQLite database inside `database/data.db`.  
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
pip install -r requirements.txt
```

> **Note**: If `requirements.txt` is missing, create one containing:  
> `Flask==3.0`, `requests>=2.0`.

### 3. Run

```bash
python app.py
```

By default the app listens on **http://127.0.0.1:9898**.

---

## Configuration

1. Navigate to **Settings** in the navbar.  
2. Fill in:
   * **From** – e‑mail address that will appear as the sender  
   * **Alias (optional)** – _Send As_ alias  
   * **Password** – account or app‑password if using Gmail  
   * **SMTP Server** – e.g. `smtp.gmail.com`  
   * **SMTP Port** – `465` for SSL or `587` for TLS  
   * **Plex Server Name** – appears in the newsletter header  
   * **Plex Base URL** – e.g. `http://localhost:32400`  
   * **Plex Token** – [X-Plex-Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/) view XML in 'Get Info' of a library item  
   * **Tautulli URL** – e.g. `http://tautulli.local:8181`  
   * **Tautulli API Key** – copy from your Tautulli settings  
3. Click **Apply Settings**.  Settings are saved to `database/data.db`.

---

## Sending a Newsletter

1. On the **Dashboard** choose a **Time Range** in days and click **Get Stats\\Users**.  
2. Wait for the spinner to disappear, then the BCC, charts, and tables will populate.  
3. Alter the BCC field to specify the recipient e‑mails (comma‑separated) if needed.  
4. Draft the body, insert `[GRAPHS]` or `[STATS]` where appropriate.  
5. Hit **Send Email**.  Success and error messages will show after running.

---

## Project Structure

```
newsletterr/
├── app.py            # Flask routes & helper functions
├── templates/
│   ├── base.html
│   ├── index.html
│   └── settings.html
├── static/
│   ├── css/style.css
│   └── img/
|      ├── newspaper.png
│      └── bouncing-newspaper.gif
├── database/         # created at first launch
│   └── data.db
└── README.md         # this file
```

---

## License

Released under the **MIT License** – see [LICENSE](LICENSE) for details.

---

## To-Do

* Add in scheduled newsletter functionality
* Dockerize
* Compile EXE and ELF files
* HTML cards and other CSS to add some life to the UI
* Additional email templates
* Get recently added items
* Auto fetch plex token, and make it easier for the user to get tautulli API
* Plex integration/automation to get the server details? See above?
* Include functionality for users without tautulli? Such that they could just provide emails and a text body for the email
* Mailing lists (Weekly, monthly, Movies, Shows) that you can add users to, to automate some emails. E.g. - Monthly email contains the following users, and uses the following template. 
* Template management to go with lists - Include a few default templates that snap in the most common stats
* Automation management (Which lists, how often?)
* Opt out support?
* Version in the top right of each HTML page (or, an 'about' button/section with version info, publish date)
* Update functionality (new version available)
* Longer fields on the Settings page
* Checking "include XYZ in email" buttons should trigger them to be added to the previewed email in realtime, as snap-ins that can be removed on the fly as well. Maybe a button instead of a check box? 
* Graph/stat ordering? Should it have a default ordering, or user editable?
* "API Key" text on Settings should be updated to "Tautulli API Key"
* BCC text appears on the bottom left of the main text field, should be on top or centered. Some form of field validation should be in here to make sure it's "email, email" - regex maybe? Prevent empty emails or duplicates in case the user messes with it. Come to think of it, could the users not be added in a "tag" format style, that is to say, each user entered is an 'item' with a small 'x' next to them to remove if needed. 
* More rounded boxes
* Color options? light and dark? The blue is throwing me lol
* What does "time range" mean? Days? Weeks?
* I don't believe I understand the placeholder boxes...
* Limit maximum days to pull data, and have buttons underneath to pull last 7, 30, 60, 90, 120? Max at like 6 months? 
* Need to put text under "Time Range" to indicate what was just pulled, since the field defaults back to 30 days
* All "hours" values should be rounded down to whole numbers
* "ARE YOU SURE?" after pressing send button


---

## Acknowledgements

* [Tautulli](https://tautulli.com/) for the Plex goodness  
* [Highcharts](https://www.highcharts.com/) for charting  
* [Tailwind CSS](https://tailwindcss.com/) & [Bootstrap](https://getbootstrap.com/) for styling

Happy streaming!
