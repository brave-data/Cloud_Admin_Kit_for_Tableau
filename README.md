# Tableau Cloud Manager

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)

> **日本語版 README**: [README_ja.md](README_ja.md)

A local web app for **centralized management, change tracking, and maintenance efficiency** of your Tableau Cloud site — built with Python + FastAPI, running entirely on your machine.

---

## Why This Tool?

Tableau Cloud's admin screens are spread across multiple pages. Answering questions like "Which data sources are used by which dashboards?", "What changed since yesterday?", or "Who hasn't logged in for months?" requires navigating between many different views.

**Tableau Cloud Manager** consolidates the information administrators actually need for day-to-day maintenance into a single screen, preventing missed changes before they become problems.

---

## Key Value

### 1. Full Site Overview at a Glance

![Dashboard Overview](docs/screenshots/01_dashboard.png)

Open the app and instantly see the state of your entire site.

- **Workbook / Data Source / View / User / Prep Flow** counts as summary cards
- **Not Viewed 180+ Days** — identify content candidates for cleanup
- **Inactive 90+ Days** — spot users for license optimization
- Click any card to jump directly to the filtered list tab

---

### 2. Data Source & Dashboard Relationships

![Data Sources](docs/screenshots/02_datasources.png)

The Data Sources tab shows each source's **project, owner, type, certification status, and days since last update** in one sortable table.

- Red-highlighted stale data sources are instantly visible
- Expand any row to see which workbooks reference that data source
- Certification status managed in a single column for audit purposes

---

### 3. Content Usage Rankings

![Top Views](docs/screenshots/03_topviews.png)

Bar chart of the top 10 most-viewed content on your site.

- Immediately see which dashboards matter most to users
- Use this to prioritize maintenance effort and decide what to retire

---

### 4. Automatic Daily Change Tracking

![Changes Tab](docs/screenshots/05_diff.png)

Automatically detects what changed between yesterday's snapshot and today's data.

- 🟢 **New**: workbooks, data sources, flows, or users that didn't exist before
- 🟡 **Updated**: name, project, or owner changes
- 🔴 **Deleted**: content that existed yesterday but is gone today
- Workbooks tagged **KTW** are also monitored for calculated field additions, deletions, and formula changes

Tableau Cloud has no built-in change notifications. This tab gives you a daily audit trail — if someone accidentally deletes a workbook or makes an unauthorized change, **you'll know the next day**.

---

### 5. Extract Refresh Schedule Monitoring

![Schedules](docs/screenshots/06_schedules.png)

Keep data fresh by monitoring all extract refresh schedules.

- See every refresh schedule with its next run time
- **Overdue** badge highlights schedules where the next run time has already passed — a sign of a stalled or failed refresh

---

### 6. Calculated Field Dependency Analysis

![Calculated Fields](docs/screenshots/04_fields.png)

Download and analyze a workbook's calculated fields, visualized as a Sankey dependency chart.

- Understand which calculated fields depend on which others
- Invaluable when maintaining or handing off complex workbooks

---

### 7. Dark Mode & Bilingual UI

![Dark Mode](docs/screenshots/07_dark_mode.png)

Toggle between light and dark mode for comfortable long sessions. Full Japanese / English language switching is supported throughout the UI.

---

## Getting Started

```bash
git clone https://github.com/brave-data/Tableau_Cloud_Manager.git
cd Tableau_Cloud_Manager
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your Tableau Cloud credentials
python main.py
```

Then open **http://localhost:8000** and click **↻ Refresh**.

**→ Full setup instructions, PAT creation steps, and troubleshooting: [SETUP.md](SETUP.md)**

---

## KTW Tag — Calculated Field Monitoring

Tag any workbook with `KTW` in Tableau Cloud to enable automatic calculated field monitoring.

- On every **Refresh**, the app downloads up to **10 KTW-tagged workbooks** and extracts their calculated fields
- Field additions, deletions, and formula changes appear in the **Changes tab** under "Calc Fields [KTW Watch]"
- Catch unauthorized or accidental formula edits the next day, automatically

---

## API Endpoints

Swagger UI is available at `http://localhost:8000/docs` while the app is running.

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Fetch status and last updated timestamp |
| `GET /api/summary` | Site-wide summary statistics |
| `GET /api/workbooks` | Workbook list |
| `GET /api/datasources` | Data source list |
| `GET /api/views` | View list with usage counts |
| `GET /api/users` | User list |
| `GET /api/flows` | Prep flow list |
| `GET /api/schedules` | Refresh schedule list |
| `GET /api/workbooks/{id}/fields` | Calculated field analysis for a workbook |
| `GET /api/ktw-fields` | Calculated fields for all KTW-tagged workbooks (up to 10) |
| `POST /api/refresh` | Trigger data re-fetch from Tableau Cloud |

---

## File Structure

```
Tableau_Cloud_Manager/
├── main.py                  # FastAPI server (entry point)
├── tableau_client.py        # Tableau Cloud REST API client
├── content_audit.py         # Manual Tableau content health report (stale WBs, inactive users)
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── .gitignore               # Excludes .env and venv from Git
├── README.md                # This file (English)
├── README_ja.md             # Japanese README
├── SETUP.md                 # Full setup guide (English)
├── SETUP_ja.md              # Full setup guide (Japanese)
├── docs/screenshots/        # UI screenshots for README
└── static/
    └── index.html           # Single-page UI (Bootstrap 5 + DataTables)
```

---

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, uvicorn, tableauserverclient
- **Frontend**: Bootstrap 5.3, Bootstrap Icons, DataTables 1.13, D3.js (Sankey)
- **Data persistence**: Browser `localStorage` for diff snapshots
- **Scheduling**: Claude Code scheduled tasks (biweekly maintenance)
