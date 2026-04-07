# Lead Generation Tool

A standalone tool that helps sales teams find and prioritize new customers near existing delivery routes. Built for non-technical users with simple data input via Excel upload or copy-paste.

## Features

- **Lead Scoring** - Four-dimension scoring system (Proximity, Segment Match, Route Density, Revenue Potential) with letter grades A-F
- **Core Segment Detection** - Automatically flags leads matching your core customer segments
- **Route-to-Prospect Visualization** - Interactive maps showing delivery stops, route paths, and color-coded prospects with connector lines
- **DC-Level Analysis** - Compare routes, see grade distributions, and identify growth opportunities per distribution center
- **Route-Level Analysis** - See every prospect near a route with "Why This Lead?" explanations
- **Duplicate Detection** - Automatically cross-references uploaded prospects against existing customers
- **Excel/CSV Upload** - Import data via file upload or copy-paste from spreadsheets
- **Downloadable Templates** - Pre-formatted templates for easy data entry
- **Export Reports** - Download DC and route reports as multi-sheet Excel workbooks
- **Lead Pipeline** - Track lead status (New → Contacted → Qualified → Converted/Rejected)
- **Configurable Scoring** - Adjust scoring weights and core segment definitions via the UI

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the App

```bash
streamlit run app.py
```

### 3. Load Sample Data (Optional)

On the home page, click **"Load Sample Data"** to generate demo data for the Denver, CO metro area with 3 distribution centers, 15 routes, ~250 customers, and ~500 leads.

### 4. Upload Your Own Data

Go to the **Upload Data** page and follow the three-step process:
1. **Upload Routes & DCs** - Your distribution centers and route definitions
2. **Upload Customers** - Your existing customer list with route assignments
3. **Upload Prospects** - Your lead/prospect list (duplicates auto-detected)

### 5. Score Leads

Click **"Score All Leads"** in the sidebar to run the scoring engine.

## How Scoring Works

| Dimension | Default Weight | What It Measures |
|-----------|---------------|------------------|
| Proximity | 35% | Distance from lead to nearest delivery stop |
| Segment Match | 25% | Does the lead match a core customer segment? |
| Route Density | 25% | How many existing customers are within 1 mile? |
| Revenue Potential | 15% | Estimated weekly revenue percentile rank |

**Letter Grades:** A (80-100) → Hot Lead | B (65-79) → Strong | C (50-64) → Moderate | D (35-49) → Low | F (0-34) → Poor Fit

Weights are adjustable on the **Settings** page.

## Pages

| Page | Description |
|------|-------------|
| Home | Welcome page with quick start guide and sample data loader |
| 📊 Dashboard | KPIs, grade distribution, top leads, leads by route chart |
| 📥 Upload Data | Excel/CSV upload, copy-paste input, templates, data management |
| 🏢 DC View | Distribution center drill-down with coverage map |
| 🚛 Route View | Route analysis with numbered stops map and prospect connectors |
| 🔍 Lead Explorer | Searchable lead table with filters, radar chart, and actions |
| 🗺️ Map View | Full interactive map with layer controls |
| 📋 Reports | Generate and download DC/route reports (Excel) |
| ⚙️ Settings | Configure scoring weights and core segments |

## Tech Stack

- **Python 3.10+**
- **Streamlit** - Web application framework
- **SQLite** - Local database (zero configuration)
- **Pandas** - Data manipulation
- **Folium** - Interactive maps
- **Plotly** - Charts and visualizations
- **scikit-learn** - BallTree for spatial queries
- **Geopy** - Geocoding addresses to coordinates

## Project Structure

```
Lead-Gen/
├── app.py                    # Streamlit entry point
├── config.py                 # Configuration and defaults
├── requirements.txt
├── database/
│   ├── schema.sql            # Database tables
│   ├── connection.py         # SQLite helper
│   ├── models.py             # Data access layer
│   └── seed_data.py          # Sample data generator
├── scoring/
│   ├── engine.py             # Scoring orchestrator
│   ├── proximity.py          # Distance scoring
│   ├── segment.py            # Segment matching
│   └── density.py            # Route density scoring
├── reports/
│   ├── dc_report.py          # DC-level reports
│   ├── route_report.py       # Route-level reports
│   └── export.py             # Excel/CSV export
├── maps/
│   └── visualizations.py     # Folium map generation
├── pages/                    # Streamlit pages
└── tests/                    # Unit tests
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Deploying to Streamlit Community Cloud (Free)

This is the simplest way to make the tool live for your sales team. No servers, no IT setup.

### Step 1: Get the code on GitHub

Make sure this repository is pushed to GitHub (e.g., `github.com/your-org/Lead-Gen`).

### Step 2: Deploy on Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Sign in with your GitHub account
3. Click **"New app"**
4. Select your repository (`Lead-Gen`), branch (`main`), and main file (`app.py`)
5. Click **"Deploy"**

Streamlit will install dependencies and start your app. This takes 2-3 minutes the first time.

### Step 3: Set a password (recommended)

1. In the Streamlit Cloud dashboard, click on your app
2. Click **"Settings"** > **"Secrets"**
3. Add the following:
   ```toml
   password = "your-team-password-here"
   ```
4. Click **"Save"** - the app will restart with password protection enabled

### Step 4: Share with your team

Copy the app URL (e.g., `https://your-app-name.streamlit.app`) and share it with your salespeople. They just open the link in any browser and enter the password.

### Important: Database Backups

Streamlit Community Cloud uses ephemeral storage. Your database file may reset if the app sleeps (after ~7 days of no use) or when you push code updates.

**To protect your data:**
1. Go to the **Upload Data** page in the app
2. Scroll to **"Database Backup & Restore"**
3. Click **"Download Database Backup"** regularly (weekly recommended)
4. If data is lost, use **"Restore from Backup"** to upload your saved `.db` file

### Alternative: Run on your own server

If you need persistent data without manual backups:

```bash
# On a Linux/Windows server your team can access
pip install -r requirements.txt
streamlit run app.py --server.port 8501
```

Your team accesses it at `http://your-server-ip:8501`. The database persists as long as the server is running.
