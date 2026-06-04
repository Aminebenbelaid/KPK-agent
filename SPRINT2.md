# Sprint 2 — Matching, Profile & Tailored CVs

## Sprint summary

This sprint turned KeinplanKarriere from a job *collector* into a job *matcher*. We set
out to rank scraped jobs for the candidate specifically and to support the application
process end-to-end. We built a hybrid matching engine (deterministic rule-based scoring
plus optional LLM refinement via Kisski), an **experience base** the candidate fills
from an AI-parsed CV or by hand, and automatic **tailored-CV generation** that rewrites a
LaTeX resume per job and compiles it to PDF. We also closed the biggest data gap from
Sprint 1 by scraping full **job descriptions** from all four boards, which makes skill
extraction and matching meaningful.

## What was built

### Matching & Profile (the planned Sprint 2 scope)
- **Skill extraction** from job descriptions using a curated taxonomy with alias normalization.
- **Fuzzy deduplication** across sources (same role on LinkedIn + StepStone + Xing is merged, tracking "also on").
- **Weighted ranking** against the candidate: skills 45 · role 20 · location 10 · remote 10 · seniority 10 · salary 5, with a full score breakdown.
- **Hybrid LLM refinement**: the top-N rule candidates are re-scored by Llama 3.3 70B with a written explanation (rate-limited, with rule-based fallback).
- **Application memory & status tracking** with status history.

### Experience base (capabilities)
- Upload a CV (PDF or LaTeX/text) → AI parses it into structured experiences/projects → review-and-edit popup → save.
- Manual entry where the AI infers the experience type, category tags, and normalized stack.
- Skills used for matching now come entirely from real experience; the LLM scorer reads the actual experiences.

### Tailored CV generation
- Per job, the AI rewrites the resume's bullet points to emphasize the most relevant experience (no fabrication).
- Compiled to PDF with **Tectonic** (bundled, self-contained); falls back to the base template if a tailored version fails to compile.
- The generated PDF is linked to the application and downloadable.

### Foundations & fixes
- **Job descriptions** now scraped from all four boards (LinkedIn detail API, Arbeitsagentur detail API, StepStone/Xing JSON-LD).
- Fixed a LinkedIn location bug (hardcoded geoId forced Madrid) — searches now honour the entered location.
- Re-scraping refreshes job content (descriptions/skills) without downgrading match scores.

## What's new compared to Sprint 1

Sprint 1 delivered scraping + a dashboard (collect and browse). Sprint 2 adds the
intelligence: descriptions, skill extraction, dedup, candidate-specific ranking,
the experience base, and tailored-CV generation.

## Open issues / next

- Profile photo isn't auto-extracted from Overleaf yet (CV compiles with a placeholder box; drop `pdp.png` into `data/cv/assets/` to include it).
- Indeed remains unsupported (bot-blocked) and was removed from the scraper set.
- Cover-letter generation and auto-apply are candidates for a future sprint.

## Links

- **Repository:** `<repo-url>`
- **Live demo:** http://192.168.4.6:8000
