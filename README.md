# KeinplanKarriere

> Automated job scraping, tracking, and application management for the German job market.

**Live demo:** [http://localhost:8000](http://localhost:8000)

---

## What it does

KeinplanKarriere scrapes job postings from four major German job platforms, stores them in a local database, and provides a web dashboard to search, filter, track, and manage applications. Everything runs in a single Docker container.

### Supported job boards

| Platform | Method | Status |
|----------|--------|--------|
| **LinkedIn** | Guest search API (no login required) | Working |
| **StepStone** | HTML scraping with BeautifulSoup | Working |
| **Xing** | HTML scraping with BeautifulSoup | Working |
| **Arbeitsagentur** | Official REST API (`jobboerse-jobsuche`) | Working |
| **Indeed** | HTML scraping | Blocked (403) |

---

## Architecture

```
                    Browser (port 8000)
                         |
              +----------+-----------+
              |     FastAPI Server    |
              |                      |
              |  /api/*   REST API   |
              |  /        Dashboard  |
              |          (static)    |
              +-----+----------+----+
                    |          |
            +-------+    +----+------+
            | SQLite |    | Scrapers  |
            | (data/ |    | (subprocess)
            | tracker|    |           |
            | .db)   |    | linkedin  |
            +--------+    | stepstone |
                          | xing      |
                          | arbeits.  |
                          +-----------+
```

**Backend:** FastAPI + Uvicorn, pure Python scrapers (requests + BeautifulSoup), SQLite database

**Frontend:** React 18 + Vite 5, served as static files from the same container

**Deployment:** Single Docker container, multi-stage build (Node for dashboard, Python for runtime)

---

## Features

### Dashboard
- **Job browser** with search, sort, and filter (by source, remote type, match score)
- **Search panel** to trigger scraper runs with custom queries and location from the UI
- **Application tracking** with status updates (new, applied, interview, offer, rejected)
- **Settings page** for managing API keys and scraper configuration
- **Light blue theme** matching [agent.keinplankarriere.de](https://agent.keinplankarriere.de)

### Backend
- **Parallel scraping** via ThreadPoolExecutor across all 4 platforms
- **Background execution** with task polling (start scrape, poll status, auto-refresh)
- **Search history** tracking all past scrape queries
- **Internal API** with key-based auth for scraper-to-server job submission
- **Settings stored in DB** (not .env) for runtime configuration

---

## Quick start

### Docker (recommended)

```bash
git clone https://github.com/your-username/KeinplanKarriere.git
cd KeinplanKarriere

# Start the container
docker compose up -d --build

# Open the dashboard
open http://localhost:8000
```

### Local development

```bash
# Backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000

# Frontend (separate terminal)
cd dashboard
npm install
npm run dev   # starts on port 3000, proxies /api to :8000
```

---

## Project structure

```
KeinplanKarriere/
+-- src/                    # FastAPI backend
|   +-- main.py             # App factory, static file serving
|   +-- config.py           # pydantic-settings configuration
|   +-- database.py         # SQLite connection helper
|   +-- init_db.py          # Auto-creates tables on startup
|   +-- api/
|       +-- router.py       # Route registration
|       +-- routes/
|           +-- jobs.py         # GET /api/jobs, GET /api/jobs/:id
|           +-- applications.py # PATCH /api/applications/:id, stats
|           +-- internal.py     # POST /api/internal/jobs/batch, scrape endpoints
|           +-- settings.py     # GET/PUT /api/settings
|           +-- health.py       # GET /health
|           +-- profile.py      # GET/PUT /api/profile
+-- scrapers/               # Job board scrapers
|   +-- base.py             # Shared utilities, API submission
|   +-- run_all.py          # CLI runner (--query, --location, --parallel)
|   +-- linkedin_scraper.py
|   +-- stepstone_scraper.py
|   +-- xing_scraper.py
|   +-- arbeitsagentur_scraper.py
|   +-- indeed_scraper.py
+-- dashboard/              # React frontend
|   +-- src/
|       +-- App.jsx         # Main app (Jobs, Settings, Search panels)
|       +-- App.css         # Light blue theme
|       +-- api.js          # API client functions
+-- data/                   # SQLite DB + user profile (Docker volume)
+-- Dockerfile              # Multi-stage build
+-- docker-compose.yml      # Single-service config
+-- requirements.txt        # Python dependencies
```

---

## API endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/jobs` | - | List jobs with filters, search, sorting |
| GET | `/api/jobs/:id` | - | Single job details |
| PATCH | `/api/applications/:id` | - | Update application status/notes |
| GET | `/api/applications/stats/summary` | - | Dashboard statistics |
| POST | `/api/scrape` | - | Trigger a new scraper run |
| GET | `/api/scrape/:task_id` | - | Poll scrape task status |
| GET | `/api/scrape` | - | List scrapers and recent tasks |
| GET | `/api/search-history` | - | Past search queries |
| GET | `/api/settings` | - | Get settings (API keys masked) |
| PUT | `/api/settings` | - | Update settings |
| POST | `/api/internal/jobs/batch` | API key | Bulk job ingestion (used by scrapers) |
| GET | `/health` | - | Health check |

---

## Configuration

Settings are stored in the SQLite database and managed through the Settings page in the dashboard. Available settings:

| Key | Description |
|-----|-------------|
| `kisski_api_key` | API key for Kisski LLM (Llama 3.3 70B) |
| `kisski_base_url` | LLM endpoint (default: chat-ai.academiccloud.de) |
| `llm_model` | Model identifier |
| `internal_api_key` | Auth key for scraper-to-server communication |
| `scraper_default_location` | Default search location |
| `scraper_max_jobs` | Max jobs per scraper run |

Environment variables in `docker-compose.yml` provide initial values; the Settings page overrides them at runtime.

---

## Tech stack

- **Python 3.12** + FastAPI + Uvicorn
- **React 18** + Vite 5
- **SQLite** (zero-config, file-based)
- **BeautifulSoup 4** + Requests (scraping)
- **Docker** multi-stage build
- **pydantic-settings** for configuration

---

## Roadmap

- [x] Multi-platform job scraping (LinkedIn, StepStone, Xing, Arbeitsagentur)
- [x] Web dashboard with search, filter, and sort
- [x] Dashboard-triggered scraping with custom queries
- [x] Docker deployment (single container)
- [x] Settings management via UI
- [ ] LaTeX CV storage and display
- [ ] LLM-based job-CV match scoring (Kisski / Llama 3.3 70B)
- [ ] Auto-generated cover letters
- [ ] Indeed scraper fix (currently blocked)

---

## Contributors

- **Amine** — Architecture, backend, scrapers, frontend, deployment

---

*Built for the AI Agents course at University of Applied Sciences.*
