"""Skill extraction from job listings.

A curated taxonomy maps a canonical skill name to a list of aliases/spellings.
``extract_skills`` scans free text (job title + description) and returns the set
of canonical skills found, using word-boundary matching so "Java" does not match
"JavaScript" and "Go" does not match "Google".

The taxonomy is intentionally dev/IT focused (the target audience of the course
project) and includes common German spellings where they differ.
"""
from __future__ import annotations

import re
from typing import Iterable

# canonical -> list of alias patterns (matched case-insensitively, word-boundary)
SKILL_TAXONOMY: dict[str, list[str]] = {
    # Languages
    "Python": ["python"],
    "JavaScript": ["javascript", "java script"],
    "TypeScript": ["typescript"],
    "Java": ["java"],
    "C#": [r"c#", r"c♯", "c sharp", ".net", "dotnet"],
    "C++": [r"c\+\+", "cpp"],
    "C": [r"\bc\b"],
    "Go": ["golang", r"\bgo\b"],
    "Rust": ["rust"],
    "PHP": ["php"],
    "Ruby": ["ruby", "ruby on rails", "rails"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift"],
    "Scala": ["scala"],
    "R": [r"\br\b"],
    "SQL": ["sql"],
    "Bash": ["bash", "shell scripting", "shell-scripting"],
    # Frontend
    "React": ["react", "react.js", "reactjs"],
    "React Native": ["react native", "react-native"],
    "Vue": ["vue", "vue.js", "vuejs"],
    "Angular": ["angular", "angular.js", "angularjs"],
    "Next.js": ["next.js", "nextjs"],
    "Svelte": ["svelte"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3", "sass", "scss", "tailwind"],
    "Redux": ["redux"],
    # Backend / frameworks
    "Node.js": ["node.js", "nodejs", "node js"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi", "fast api"],
    "Spring": ["spring", "spring boot", "spring-boot"],
    "Express": ["express.js", "express"],
    ".NET": [r"\.net", "asp.net", "asp net"],
    "GraphQL": ["graphql"],
    "REST": ["rest", "rest api", "restful"],
    # Data / ML
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "TensorFlow": ["tensorflow", "tensor flow"],
    "PyTorch": ["pytorch", "py torch"],
    "scikit-learn": ["scikit-learn", "scikit learn", "sklearn"],
    "Machine Learning": ["machine learning", "maschinelles lernen", "ml", "deep learning"],
    "Data Science": ["data science", "data scientist"],
    "NLP": ["nlp", "natural language processing"],
    "LLM": ["llm", "large language model", "gpt", "openai", "langchain"],
    # Databases
    "PostgreSQL": ["postgresql", "postgres"],
    "MySQL": ["mysql"],
    "SQLite": ["sqlite"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search"],
    # DevOps / cloud
    "Docker": ["docker"],
    "Kubernetes": ["kubernetes", "k8s"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "GCP": ["gcp", "google cloud"],
    "Terraform": ["terraform"],
    "CI/CD": ["ci/cd", "ci cd", "continuous integration", "continuous deployment"],
    "Git": ["git", "github", "gitlab", "bitbucket"],
    "Linux": ["linux", "unix"],
    "Jenkins": ["jenkins"],
    "Ansible": ["ansible"],
    # Practices / other
    "Agile": ["agile", "scrum", "kanban"],
    "Microservices": ["microservices", "microservice"],
    "Testing": ["unit testing", "pytest", "jest", "selenium", "test automation", "testautomatisierung"],
    "API": [r"\bapi\b", "apis"],
}

# Pre-compile one regex per canonical skill: alternation of its aliases.
_COMPILED: dict[str, re.Pattern] = {}
for _canon, _aliases in SKILL_TAXONOMY.items():
    parts = []
    for a in _aliases:
        # If the alias already contains regex word-boundaries/escapes, use as-is;
        # otherwise wrap it in word boundaries with escaped literal text.
        if any(c in a for c in "\\+#^$\\b()[]"):
            parts.append(a)
        else:
            parts.append(r"\b" + re.escape(a) + r"\b")
    _COMPILED[_canon] = re.compile("|".join(parts), re.IGNORECASE)


def extract_skills(*texts: str) -> list[str]:
    """Return the sorted list of canonical skills found across the given texts."""
    blob = " ".join(t for t in texts if t)
    if not blob.strip():
        return []
    found = []
    for canon, pattern in _COMPILED.items():
        if pattern.search(blob):
            found.append(canon)
    return sorted(found)


def normalize_skills(skills: Iterable[str]) -> list[str]:
    """Map an arbitrary list of skill strings to canonical names where possible.

    Unknown skills are kept as-is (title-cased) so user-entered profile skills are
    not silently dropped.
    """
    result: list[str] = []
    seen = set()
    for raw in skills:
        if not raw:
            continue
        s = str(raw).strip()
        matched = None
        for canon, pattern in _COMPILED.items():
            if pattern.fullmatch(s) or pattern.search(s):
                matched = canon
                break
        value = matched or s
        key = value.lower()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result
