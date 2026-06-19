"""Per-job cover letter generation: LLM writes the body, Tectonic renders a PDF."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from src.matching import llm, cvgen

_SPECIALS = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
    "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def _latex_escape(text: str) -> str:
    if not text:
        return ""
    out = []
    for ch in text:
        out.append(_SPECIALS.get(ch, ch))
    return "".join(out)


def _experiences_blurb(experiences: list[dict]) -> str:
    lines = []
    for e in experiences or []:
        stack = ", ".join(e.get("stack") or [])
        desc = (e.get("description") or e.get("ai_summary") or "").strip()
        head = e.get("title", "")
        if e.get("organization"):
            head += f" @ {e['organization']}"
        lines.append(f"- {head}: {desc} [{stack}]")
    return "\n".join(lines) or "(none on file)"


_PROMPT = """Write a concise, professional cover letter for this job, in the candidate's voice.
3 short paragraphs: (1) the role and genuine motivation, (2) the most relevant experience
and skills mapped to the job's needs, (3) a brief closing. Plain prose only — no salutation
line, no "Dear...", no sign-off, no placeholders, no markdown. Ground every claim in the
experience below; never invent employers, titles or facts.

JOB
Title: {title}
Company: {company}
Description: {description}

CANDIDATE
Name: {name}
Target roles: {roles}
Experience:
{experiences}

Write the body now."""


def generate_body(job: dict, experiences: list[dict], profile: dict) -> Optional[str]:
    user = _PROMPT.format(
        title=job.get("title", ""),
        company=job.get("company", ""),
        description=(job.get("description_clean") or job.get("description_raw") or "")[:1500],
        name=profile.get("name") or "the candidate",
        roles=", ".join(profile.get("target_roles") or []) or "—",
        experiences=_experiences_blurb(experiences),
    )
    extra = llm.get_setting("cover_letter_instructions").strip()
    if extra:
        user += f"\n\nADDITIONAL INSTRUCTIONS FROM THE CANDIDATE (follow these, stay truthful):\n{extra}"
    text = llm.chat(
        [
            {"role": "system", "content": "You are an expert career writer. Output plain prose only."},
            {"role": "user", "content": user},
        ],
        max_tokens=900,
        temperature=0.4,
        timeout=120,
    )
    if not text:
        return None
    text = text.strip()
    # drop accidental salutations / sign-offs the model may add anyway
    text = re.sub(r"^(dear[^\n]*\n+)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\n+(sincerely|best regards|kind regards|yours)[^\n]*$", "", text, flags=re.IGNORECASE)
    return text.strip()


def _letter_tex(body: str, profile: dict, job: dict) -> str:
    name = _latex_escape(profile.get("name") or "")
    email = _latex_escape(profile.get("email") or "")
    location = _latex_escape(profile.get("location") or "")
    company = _latex_escape(job.get("company") or "")
    title = _latex_escape(job.get("title") or "")
    contact = "  $\\cdot$  ".join(p for p in [email, location] if p)
    # blank lines in body -> paragraph breaks; escape specials
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    body_tex = "\n\n".join(_latex_escape(p) for p in paras)
    header = (name or "Application") + (f" \\\\ {contact}" if contact else "")
    return r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=2.3cm]{geometry}
\usepackage{parskip}
\usepackage[hidelinks]{hyperref}
\pagestyle{empty}
\begin{document}
\noindent\textbf{%s}

\vspace{1.2em}
\noindent\textbf{%s} \\ Re: %s

\vspace{1.2em}
%s

\vspace{1.6em}
\noindent Sincerely, \\ %s
\end{document}
""" % (header, company or "Hiring Team", title or "your role", body_tex, name or "")


def generate(job: dict, app_id: str, experiences: list[dict], profile: dict) -> dict:
    """Return {pdf, text, compiled}. PDF best-effort; text always present on success."""
    body = generate_body(job, experiences, profile)
    if not body:
        return {"pdf": None, "text": None, "compiled": False}

    work = cvgen.generated_dir() / app_id
    pdf, log = cvgen.compile_tex(_letter_tex(body, profile, job), work, "cover_letter")
    (work / "cover_letter.txt").write_text(body, encoding="utf-8")
    return {"pdf": str(pdf) if pdf else None, "text": body, "compiled": pdf is not None, "log": "" if pdf else log}
