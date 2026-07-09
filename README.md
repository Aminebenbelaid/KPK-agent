# KeinplanKarriere

> AI-assisted job search for the German market: scrape postings, match them against your real experience, generate a tailored CV + cover letter per job — now public and multi-user.

**Try it:** [https://keinplankarriere.qantra.dev](https://keinplankarriere.qantra.dev) · every visitor gets their own private workspace

---

## What it does

1. **Scrapes** job postings (with full descriptions) from four German job boards.
2. **Matches** each job against your experience and preferences with a hybrid rule + LLM engine.
3. **Builds an experience base** from your CV (AI-parsed, human-reviewed) or manual entries.
4. **Generates a tailored CV and cover letter** (LaTeX → PDF) for any job, bundled into a one-click Apply Assistant.
5. **Learns from outcomes** — interviews/offers boost the ranking of similar jobs.

### Supported job boards

| Platform | Method | Descriptions |
|----------|--------|--------------|
| **LinkedIn** | Guest search + `jobPosting` detail API | ✅ |
| **StepStone** | HTML search + JSON-LD detail | ✅ |
| **Xing** | HTML search + JSON-LD detail | ✅ |
| **Arbeitsagentur** | Official REST API | ✅ |

---

## Multi-user architecture (final sprint)

```
            Internet ──► Cloudflare Tunnel (keinplankarriere.qantra.dev)
                              │
                    ┌─────────┴──────────┐
                    │   FastAPI + React    │  cookie session per visitor
                    │  ┌───────────────┐  │
                    │  │  Work queue    │  │  ONE worker: scrape/score/
                    │  │  (serial)      │  │  generate run in line
                    │  └───────────────┘  │
                    │  SQLite (per-session │
                    │  scoped rows)        │
                    └─────────┬──────────┘
                              │
                     Tectonic · Kisski LLM
```

- **Sessions** — each browser gets an isolated workspace (jobs, experiences, profile, prompt add-ons, CV template, photo, PDFs). Idle visitor sessions auto-purge after 48 h.
- **Owner workspace** — the pre-existing data sits behind an admin key (Settings → Admin access). Only the owner sees/edits server LLM credentials; visitors never can.
- **Work queue** — all heavy operations run through a single serial worker with live queue positions in the UI, so many visitors can't overload the host.
- **Caps** — 400 jobs / 60 experiences per session, upload size limits.

---

## Features

### Jobs
- Dashboard-triggered scraping with custom query + location (parallel across sources)
- Full descriptions, skill extraction (taxonomy + word-boundary regex), fuzzy cross-source dedup
- Filter / sort / search, status tracking, one-click Clear all

### Matching (hybrid)
- Rule score 0–100: skills 45 · role 20 · location 10 · remote 10 · seniority 10 · salary 5
- LLM refinement of top candidates, grounded in real experiences, with written explanations
- Per-job "best experiences to highlight", re-ranking from past interview/offer outcomes
- Input-hash caching: unchanged jobs reuse their LLM verdict (zero-cost re-runs)

### Documents
- **Tailored CV**: keeps every experience, reformulates bullets to the job; compile-validated with fallback
- **Cover letter**: grounded, per-job, PDF
- **Apply Assistant**: CV + letter + apply link + checklist (deliberately *not* auto-submit)
- **CV photo** upload in Settings (rendered into the CV); per-user prompt add-ons for CV & letter

### Insight
- **Trends tab**: in-demand skills, salary ranges, remote split, top locations/companies + LLM summary

---

## Quick start (self-host)

```bash
git clone <repo-url> KeinplanKarriere && cd KeinplanKarriere
cp .env.example .env         # set ADMIN_KEY, KISSKI_API_KEY, INTERNAL_API_KEY
docker compose up -d --build
open http://localhost:8000
```

The `cloudflared` compose service exposes the app publicly — put your tunnel credentials
in `~/.cloudflared/` and adjust `kpk-config.yml` (or remove the service for LAN-only use).

### Local development

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
cd dashboard && npm install && npm run dev   # :3000, proxies /api → :8000
```

---

## Project structure

```
├── src/
│   ├── main.py            # app factory, session middleware
│   ├── sessions.py        # per-visitor workspaces, owner claim, cleanup
│   ├── task_queue.py      # global serial worker for heavy ops
│   ├── init_db.py         # schema + migrations (session scoping)
│   ├── api/routes/        # jobs, applications, experiences, matching,
│   │                      #   generate, settings, session, internal, health
│   └── matching/          # skills, dedup, scorer, llm, cv, cvgen,
│                          #   coverletter, report, rerank
├── scrapers/              # linkedin, stepstone, xing, arbeitsagentur
├── cv_template/           # generic LaTeX resume (per-session overrides live in data/)
├── dashboard/             # React + Vite frontend
├── presentation/          # sprint decks (HTML)
└── docker-compose.yml     # app + cloudflared tunnel
```

---

## Tech stack

Python 3.12 · FastAPI · SQLite · React 18 + Vite · BeautifulSoup · Tectonic (LaTeX) · Cloudflare Tunnel · Kisski LLM (self-healing model selection)

---

*Built for the AI Agents course at Westfälische Hochschule.*
