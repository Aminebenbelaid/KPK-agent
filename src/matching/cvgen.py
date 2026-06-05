"""Tailored CV generation: LLM rewrites the LaTeX resume for a job, Tectonic compiles it.

Pipeline: load base template -> LLM tailors bullet points to the job (grounded in the
real experience base, no fabrication) -> compile with Tectonic -> on LaTeX error, retry
once, then fall back to the untailored template so a valid PDF is always produced.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from src.config import get_settings
from src.matching import llm

# Base template bundled in the image (outside the data volume).
BUNDLED_TEMPLATE = Path("cv_template/template.tex")
BUNDLED_ASSETS = Path("cv_template/assets")


def _data_cv_dir() -> Path:
    return Path(get_settings().TRACKER_DB_PATH).parent / "cv"


def override_template() -> Path:
    return _data_cv_dir() / "template.tex"


def generated_dir() -> Path:
    d = _data_cv_dir() / "generated"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_template() -> str:
    """User override in the data volume wins, else the bundled template."""
    ov = override_template()
    if ov.exists():
        return ov.read_text(encoding="utf-8")
    if BUNDLED_TEMPLATE.exists():
        return BUNDLED_TEMPLATE.read_text(encoding="utf-8")
    raise FileNotFoundError("No CV template found")


def _copy_assets(dest: Path):
    """Copy any template assets (e.g. the profile photo) next to the .tex."""
    for src_dir in (BUNDLED_ASSETS, _data_cv_dir() / "assets"):
        if src_dir.exists():
            for f in src_dir.iterdir():
                if f.is_file():
                    shutil.copy2(f, dest / f.name)


_TAILOR_SYSTEM = (
    "You tailor an existing LaTeX resume to a specific job posting. "
    "Output ONLY the complete LaTeX document, nothing else (no markdown, no commentary). "
    "STRICT RULES: keep the document class, preamble, packages, and all layout/formatting "
    "commands EXACTLY as given. Only adjust the WORDING and ORDER of bullet points "
    "(\\item lines) and the SKILLS line to emphasise what is most relevant to this job. "
    "You may reorder experiences/bullets to surface the most relevant first. "
    "NEVER invent employers, job titles, dates, degrees, or technologies that are not "
    "already in the resume. Do not add or remove sections. Keep it to one page of content."
)

_TAILOR_USER = """JOB POSTING:
Title: {title}
Company: {company}
Skills/keywords: {skills}
Description: {description}

CANDIDATE EXPERIENCE CONTEXT (for grounding only, do not copy verbatim):
{experiences}

CURRENT RESUME (LaTeX):
{tex}

Return the tailored LaTeX resume now."""


def _experiences_blurb(experiences: list[dict]) -> str:
    lines = []
    for e in experiences or []:
        stack = ", ".join(e.get("stack") or [])
        lines.append(f"- {e.get('title', '')}: {e.get('ai_summary') or ''} ({stack})")
    return "\n".join(lines) or "(none on file)"


def tailor_tex(template_tex: str, job: dict, experiences: list[dict]) -> Optional[str]:
    """Ask the LLM to tailor the resume. Returns LaTeX string or None on failure."""
    content = llm.chat(
        [
            {"role": "system", "content": _TAILOR_SYSTEM},
            {
                "role": "user",
                "content": _TAILOR_USER.format(
                    title=job.get("title", ""),
                    company=job.get("company", ""),
                    skills=", ".join(job.get("skills_required") or []),
                    description=(job.get("description_clean") or job.get("description_raw") or "")[:1500],
                    experiences=_experiences_blurb(experiences),
                    tex=template_tex,
                ),
            },
        ],
        max_tokens=4000,
        temperature=0.3,
        timeout=180,
    )
    if not content:
        return None
    # Strip accidental markdown fences.
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\n", "", content)
        content = re.sub(r"\n```$", "", content)
    if "\\documentclass" not in content or "\\end{document}" not in content:
        return None
    # Keep only through \end{document} (drop any trailing chatter).
    end = content.rfind("\\end{document}")
    return content[: end + len("\\end{document}")]


def compile_tex(tex: str, work_dir: Path, basename: str = "cv") -> tuple[Optional[Path], str]:
    """Compile LaTeX with Tectonic in work_dir. Returns (pdf_path or None, log)."""
    work_dir.mkdir(parents=True, exist_ok=True)
    tex_file = work_dir / f"{basename}.tex"
    tex_file.write_text(tex, encoding="utf-8")
    _copy_assets(work_dir)
    try:
        proc = subprocess.run(
            ["tectonic", tex_file.name, "--outdir", ".", "--chatter", "minimal"],
            cwd=str(work_dir),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except FileNotFoundError:
        return None, "tectonic not installed"
    except subprocess.TimeoutExpired:
        return None, "compile timed out"
    pdf = work_dir / f"{basename}.pdf"
    if proc.returncode == 0 and pdf.exists():
        return pdf, proc.stderr[-2000:]
    return None, (proc.stderr or proc.stdout)[-2000:]


def _bullets(tex: str) -> list[str]:
    return [m.strip() for m in re.findall(r"\\item\s+(.+)", tex)]


def generate_for_job(job: dict, app_id: str, experiences: list[dict]) -> dict:
    """Tailor + compile a CV for a job. Always returns a result with a PDF if possible.

    Returns: {pdf, tex, tailored, compiled, emphasized, log}
    """
    template = load_template()
    work = generated_dir() / app_id
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)

    tailored = tailor_tex(template, job, experiences) if llm.is_configured() else None
    used_tailored = False
    pdf = None
    log = ""

    if tailored:
        pdf, log = compile_tex(tailored, work, "cv")
        if pdf is None:
            # one repair attempt with the error context
            repaired = _repair(tailored, log)
            if repaired:
                pdf, log = compile_tex(repaired, work, "cv")
                if pdf is not None:
                    tailored = repaired
        if pdf is not None:
            used_tailored = True

    final_tex = tailored if used_tailored else template
    if pdf is None:
        # fall back to the untailored template (the user's known-good resume)
        pdf, log = compile_tex(template, work, "cv")
        final_tex = template

    # persist the .tex alongside the pdf
    (work / "cv.tex").write_text(final_tex, encoding="utf-8")

    emphasized = []
    if used_tailored:
        before = set(_bullets(template))
        emphasized = [b for b in _bullets(final_tex) if b not in before][:8]

    return {
        "pdf": str(pdf) if pdf else None,
        "tex": str(work / "cv.tex"),
        "tailored": used_tailored,
        "compiled": pdf is not None,
        "emphasized": emphasized,
        "log": "" if pdf is not None else log,
    }


def _repair(tex: str, error_log: str) -> Optional[str]:
    content = llm.chat(
        [
            {"role": "system", "content": "Fix the LaTeX so it compiles. Output ONLY the corrected complete LaTeX document."},
            {"role": "user", "content": f"This LaTeX failed to compile.\nERROR:\n{error_log[:1500]}\n\nLATEX:\n{tex}\n\nReturn the corrected LaTeX."},
        ],
        max_tokens=4000,
        temperature=0.1,
        timeout=180,
    )
    if not content:
        return None
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```[a-zA-Z]*\n", "", content)
        content = re.sub(r"\n```$", "", content)
    if "\\documentclass" not in content or "\\end{document}" not in content:
        return None
    end = content.rfind("\\end{document}")
    return content[: end + len("\\end{document}")]
