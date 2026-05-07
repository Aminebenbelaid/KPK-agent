# keinplankarriere

> One command. Every application.

An autonomous CLI agent that scrapes job boards, ranks matches against your profile, and generates tailored CVs and cover letters — fully local, no cloud required.

🌐 **[keinplankarriere.de](https://keinplankarriere.de)**

---

## What it does
```
You run one command. The agent:

1. **Scrapes** 3 job boards in parallel (Arbeitsagentur, LinkedIn, Indeed)
2. **Deduplicates** overlapping listings across sources
3. **Extracts** required skills from each posting
4. **Ranks** jobs against your candidate profile (skills, location, salary, company, recency)
5. **Analyses** salary trends and skill demand across the dataset
6. **Tracks** results and application status in a local database
7. **Generates** a tailored CV and cover letter for each match

```bash
kpk run --role "ML Engineer" --location Berlin --generate

  ● Scraping 3 sources in parallel...
  ● Deduplicating & extracting skills...
  ● Ranked 47 jobs → 12 matches (≥70%)

  ✓ Generated 12 CVs + 12 cover letters
  ✓ Tracked in local DB. Done in 34s.
```

---

## Architecture

The agent follows a **Plan & Execute** pattern. A central orchestrator drives a fixed 7-step pipeline. Each stage is independent — one failure never blocks the others.

```
Interface        →   Orchestrator         →   Storage & External
─────────────────    ─────────────────────    ──────────────────
Command Line         Scrape                   SQLite (history)
REST API (opt.)      Deduplicate              YAML Profile
Web UI (opt.)        Extract                  Local filesystem
                     Rank                     Ollama / OpenRouter
                     Market                   KISSKI (academic API)
                     Track                    Job Board APIs
                     Generate
```

### Scraping strategy

Two approaches depending on the source:

| Source | Method |
|---|---|
| Arbeitsagentur | Official public REST API — no auth required |
| LinkedIn | Public guest API, Playwright fallback if blocked |
| Indeed | Playwright browser automation (embeds data in JS) |

### LLM integration

The agent instructs the LLM to return a strict JSON structure for CV recomposition — not free text. This guarantees consistent output: ordered experience, scored relevance, rewritten bullet points.

Supported providers: **Ollama** (local), **OpenRouter**, **KISSKI** (academic API).

---

## Agentic components

| Component | Role |
|---|---|
| Tool Use | Each scraper is an independent tool with isolated failure handling |
| Structured Output | LLM constrained to JSON schema — no freeform generation |
| Memory | Persistent application tracker across sessions (Wishlist → Offer) |
| Feedback | Outcome recording — foundation for prompt refinement in Sprint 4 |

---

## Getting started

### Prerequisites

- Python 3.12+
- [Playwright](https://playwright.dev/) browsers installed
- One of: Ollama running locally, an OpenRouter API key, or a KISSKI API key

### Installation

```bash
git clone https://github.com/your-username/keinplankarriere
cd keinplankarriere
pip install -e .
playwright install chromium
```

### Configuration

Copy the example profile and fill in your details:

```bash
cp config/profile.example.yaml config/profile.yaml
```

Set your LLM provider in `.env`:

```env
# Choose one
OLLAMA_BASE_URL=http://localhost:11434
OPENROUTER_API_KEY=your_key_here
KISSKI_API_KEY=your_key_here
```

### Usage

```bash
# Scrape and rank jobs
kpk run --role "Software Engineer" --location Berlin

# Scrape, rank, and generate documents
kpk run --role "ML Engineer" --location Munich --generate

# Scout jobs without generating documents
kpk scout --role "Data Scientist" --location Hamburg

# Analyse your market fit
kpk analyze
```

---

## Sprint roadmap

| Sprint | Focus | Deliverable |
|---|---|---|
| 1 | Scraping & Search | Agent collects real job data |
| 2 | Matching & Profile | Agent ranks jobs for you specifically |
| 3 | Generation & Apply | Agent generates tailored documents |
| 4 | Fine-tuning & Polish | Agent improves with each run |

---

## Project structure

```
src/
├── pipeline/        # Orchestrator — 7-step execution
├── scrapers/        # Arbeitsagentur, LinkedIn, Indeed
├── analyzer/        # Ranking, skill extraction, market analysis
├── generator/       # CV and cover letter generation
├── tracker/         # Application memory and status
├── services/        # LLM client (Ollama / OpenRouter / KISSKI)
└── cli/             # Command line interface
```

---

## Docker

```bash
docker compose up
```

---

## License

MIT — see [LICENSE](LICENSE)

---

*Built as part of the Agentic AI course project — SS 2026*  
*Official website: [keinplankarriere.de](https://keinplankarriere.de)*
```
