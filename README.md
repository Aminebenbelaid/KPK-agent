# KeinplanKarriere

> AI-assisted job search for the German market: scrape postings, match them against your real experience, and generate a tailored CV per job — all in one Dockerized app.

**Live demo:** [http://192.168.4.6:8000](http://192.168.4.6:8000)

---

## What it does

1. **Scrapes** job postings (with full descriptions) from four German job boards.
2. **Matches** each job against your experience and preferences using a hybrid rule-based + LLM engine.
3. **Builds an experience base** from your CV (AI-parsed) or manual entries.
4. **Generates a tailored CV** (LaTeX → PDF) for any job, emphasizing your most relevant experience.

Everything runs in a single Docker container serving a FastAPI backend + React dashboard.

### Supported job boards

| Platform | Method | Descriptions |
|----------|--------|--------------|
| **LinkedIn** | Guest search + `jobPosting` detail API | ✅ |
| **StepStone** | HTML search + JSON-LD detail | ✅ |
| **Xing** | HTML search + JSON-LD detail | ✅ |
| **Arbeitsagentur** | Official REST API (`jobboerse-jobsuche`) | ✅ |

---

## Architecture

```
                       Browser (port 8000)
                            │
                ┌───────────┴────────────┐
                │      FastAPI server      │
                │  /api/*   REST API       │
                │  /        React SPA      │
                └───┬───────────┬─────┬────┘
                    │           │     │
              ┌─────┴───┐  ┌────┴──┐  └────────┐
              │ SQLite  │  │Scrapers│   ┌───────┴────────┐
              │tracker  │  │(subproc│   │ Kisski LLM      │
              │  .db    │  │ + desc)│   │ (Llama 3.3 70B) │
              └─────────┘  └────────┘   └────────────────┘
                                  │
                            ┌─────┴──────┐
                            │  Tectonic   │  CV .tex → PDF
                            └────────────┘
```

- **Backend:** FastAPI + Uvicorn, SQLite (no ORM), pure `requests` + `BeautifulSoup` scrapers
- **Frontend:** React 18 + Vite 5 (built and served as static files)
- **Matching:** rule-based scorer + optional Kisski LLM refinement
- **CV generation:** Tectonic (self-contained LaTeX engine) bundled in the image

---

## Features

### Jobs
- Dashboard-triggered scraping with custom query + location (parallel across sources)
- Full job descriptions, skill extraction, cross-source fuzzy deduplication
- Filter / sort / search, status tracking (wishlist → applied → … → offer)
- One-click **Clear all** (with confirmation)

### Matching (hybrid)
- **Rule score (0–100):** skills 45 · target role 20 · location 10 · remote 10 · seniority 10 · salary 5
- **LLM refinement** of the top candidates (grounded in your actual experiences), with a written explanation
- Per-job **best-matching experiences** view: which experiences to emphasize, and why

### Experience base
- Upload a CV (PDF or LaTeX/text) → AI parses it into structured experiences → review popup → save
- Manual add: type a description + stack, the AI infers the experience type, tags, and normalized stack
- Skills used for matching come entirely from your experience

### Tailored CV
- Pick a job → AI tailors your LaTeX resume's bullet points to it (no fabrication)
- Compiles to PDF with Tectonic; if a tailored version fails to compile, falls back to your base template
- PDF is linked to the application and downloadable

### Preferences
- Location, remote preference, salary floor, target roles, seniority (used by the matcher)

---

## Quick start

### Docker (recommended)

```bash
git clone <repo-url> KeinplanKarriere
cd KeinplanKarriere
docker compose up -d --build
open http://localhost:8000
```

Add your Kisski API key in the dashboard **Settings** tab to enable LLM refinement and CV tailoring.

### Local development

```bash
# Backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000

# Frontend (separate terminal)
cd dashboard && npm install && npm run dev   # :3000, proxies /api to :8000
```

> CV generation needs the `tectonic` binary on PATH (bundled automatically in Docker).

---

## Project structure

```
KeinplanKarriere/
├── src/                       # FastAPI backend
│   ├── main.py                # app factory + static serving
│   ├── config.py              # pydantic-settings
│   ├── database.py            # SQLite helper (JSON column parsing)
│   ├── init_db.py             # table creation on startup
│   ├── api/routes/            # jobs, applications, profile, matching,
│   │                          #   experiences, settings, internal, health
│   ├── matching/              # the intelligence layer
│   │   ├── skills.py          # skill taxonomy + extraction
│   │   ├── dedup.py           # fuzzy cross-source dedup
│   │   ├── scorer.py          # weighted rule-based scoring
│   │   ├── llm.py             # Kisski client + scoring refinement
│   │   ├── cv.py              # CV parsing + experience matching
│   │   └── cvgen.py           # tailored CV generation (LaTeX → PDF)
│   └── models/schemas.py
├── scrapers/                  # linkedin, stepstone, xing, arbeitsagentur + base
├── cv_template/               # base LaTeX resume template (+ assets)
├── dashboard/                 # React + Vite frontend
├── data/                      # SQLite DB, profile, generated CVs (Docker volume)
├── Dockerfile                 # multi-stage build (Node + Python + Tectonic)
└── docker-compose.yml
```

---

## Key API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/jobs` | List jobs (filter/sort/search) |
| DELETE | `/api/jobs` | Delete all jobs (optional `?source=`) |
| POST | `/api/scrape` | Trigger a scrape; `GET /api/scrape/:id` to poll |
| POST | `/api/score` | Score all jobs; `GET /api/score` for overview |
| GET/PUT | `/api/profile` | Preferences |
| GET/POST | `/api/experiences` | Experience base CRUD |
| POST | `/api/cv/parse-file` · `/api/cv/parse-text` | Parse a CV into experiences |
| POST | `/api/match/experiences/:job_id` | Best-matching experiences for a job |
| POST | `/api/cv/tailor/:job_id` | Generate a tailored CV PDF |
| GET | `/api/applications/:id/cv` | Download a generated CV |
| GET/PUT | `/api/settings` | API keys & config |

---

## Configuration

Settings live in the SQLite `settings` table, editable in the dashboard:

| Key | Purpose |
|-----|---------|
| `kisski_api_key` | Kisski LLM key (enables refinement + CV tailoring) |
| `kisski_base_url` | LLM endpoint (default `chat-ai.academiccloud.de/v1`) |
| `llm_model` | Model id (default `llama-3.3-70b-instruct`) |
| `internal_api_key` | Auth for scraper → server job ingestion |

---

## Tech stack

Python 3.12 · FastAPI · SQLite · React 18 + Vite · BeautifulSoup · Tectonic · Docker · Kisski (Llama 3.3 70B)

---

*Built for the AI Agents course at Westfälische Hochschule.*
