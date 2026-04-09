# Setup Guide — Cloud Admin Kit for Tableau

> **日本語版**: [SETUP_ja.md](SETUP_ja.md)

---

## Requirements

- Python **3.11 or later**
- A Tableau Cloud site with a Personal Access Token (PAT)

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/brave-data/Cloud_Admin_Kit_for_Tableau.git
cd Cloud_Admin_Kit_for_Tableau
```

---

## Step 2 — Create a virtual environment

```bash
# Mac / Linux
python3.11 -m venv .venv
source .venv/bin/activate

# Windows
py -3.11 -m venv .venv
.venv\Scripts\activate
```

> **Note:** Make sure to use Python 3.11 explicitly (`python3.11`). Running `python3` may point to an older version (e.g. 3.9) depending on your system, which will cause import errors at runtime.

---

## Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

---

## Step 4 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in your Tableau Cloud credentials:

```ini
TABLEAU_SERVER_URL=https://10ay.online.tableau.com   # Your Tableau Cloud pod URL
TABLEAU_SITE_NAME=mycompany                          # Site name (leave blank for the Default site)
TABLEAU_TOKEN_NAME=my-pat-name                       # Name of your Personal Access Token
TABLEAU_TOKEN_SECRET=xxxxxxxxxxxxxxxxxxxx            # PAT secret (treat like a password)
```

### How to find your pod URL

Your Tableau Cloud URL looks like `https://10ay.online.tableau.com/#/site/mycompany/...`
The pod URL is the `https://10ay.online.tableau.com` part.

### How to create a Personal Access Token

1. Log in to Tableau Cloud
2. Click your account icon (top right) → **Account Settings**
3. Scroll to **Personal Access Tokens** → **Create new token**
4. Give it a name, then **copy the secret immediately** — it is only shown once

---

## Step 5 — Start the server

```bash
python main.py
```

The server starts on **http://localhost:8000** by default.

To use a different port, add `PORT=8080` to your `.env` file.

---

## Step 6 — Fetch data

Open **http://localhost:8000** in your browser. The app will show a blank state until you fetch data.

Click the **↻ Refresh** button in the top-right corner. This pulls all content from Tableau Cloud via the REST API. Expect it to take **10–30 seconds** depending on your site size.

Once complete, all tabs will populate with data.

---

## Upgrading

```bash
git pull
pip install -r requirements.txt   # pick up any new dependencies
python main.py
```

---

## Troubleshooting

| Symptom | Cause | Solution |
|---------|-------|----------|
| `ImportError: tableauserverclient` | Wrong Python version or missing venv | Ensure you activated `.venv` and Python is 3.11+ |
| "Connection failed" on Refresh | Wrong credentials in `.env` | Double-check URL, token name, and secret |
| Stuck on loading screen after Refresh | Server-side error in background thread | Check terminal output for Python tracebacks |
| A tab shows 0 items | No content of that type on your site | Expected — not an error |
| Port 8000 already in use | Another process on the port | Add `PORT=8080` to `.env` |
| SSL certificate error | Corporate proxy / self-signed cert | Set `verify=False` in `tableau_client.py` (dev only) |
