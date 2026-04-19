"""F89.a — vocabularies for ``HeuristicQueryParser``.

This file is the product-surface knob for query parsing. PMs and
operators edit these constants to expand recall (more skills, more
document-type keywords) or to catch new seniority tokens.

Editing guidance
----------------
- **Known skills** should be tech-specific enough that false-positive
  matches on common English are rare. "go" is Golang in our world
  but also a ubiquitous English verb; it's intentionally omitted
  from the initial vocab. Add corpus-derived skills via
  ``scripts/extract_skills_from_corpus.py`` (not yet written — F89.a.1
  follow-up).
- **Seniority tokens** map to a *minimum* years-of-experience
  threshold. Thresholds are conservative (senior=5, not senior=7) to
  favor recall over precision; HR users typically mean "at least X"
  when they say a level.
- **Document type keywords** should be unambiguous. "cover" alone
  isn't here because it collides with ``.cover`` in job-posting
  boilerplate; ``"cover letter"`` would match via the "letter"
  keyword instead. Evaluate every addition for collision risk.
"""

from __future__ import annotations

# Seniority token → implicit min_experience_years threshold.
# Applied only when no explicit year extraction fires (explicit
# beats implicit).
SENIORITY_THRESHOLDS: dict[str, int] = {
    # Entry levels.
    "intern": 0,
    "entry-level": 0,
    "entry level": 0,
    # Junior.
    "junior": 1,
    "jr": 1,
    "jr.": 1,
    # Mid.
    "mid": 3,
    "mid-level": 3,
    "mid level": 3,
    # Senior.
    "senior": 5,
    "sr": 5,
    "sr.": 5,
    # Staff / Lead.
    "staff": 7,
    "lead": 7,
    # Principal / Architect tier.
    "principal": 8,
}


# Known technology skills. Matched case-insensitively with a
# non-alphanumeric boundary check (see ``_skill_match`` in
# ``query_parser.py``) — no `\b` because special-character skills
# (``c++``, ``.net``, ``node.js``) break on word-boundary regex.
KNOWN_SKILLS: frozenset[str] = frozenset(
    {
        # Languages.
        "python",
        "javascript",
        "typescript",
        "java",
        "kotlin",
        "swift",
        "rust",
        "golang",
        "ruby",
        "php",
        "c++",
        "c#",
        ".net",
        "scala",
        "elixir",
        # Frontend.
        "react",
        "vue",
        "angular",
        "svelte",
        "next.js",
        "node.js",
        "nuxt",
        "tailwind",
        "tailwind css",
        # Backend frameworks.
        "django",
        "flask",
        "fastapi",
        "express",
        "nestjs",
        "spring",
        "spring boot",
        "rails",
        "laravel",
        # Infra / cloud.
        "aws",
        "gcp",
        "azure",
        "kubernetes",
        "docker",
        "terraform",
        "ansible",
        "jenkins",
        "gitlab",
        "github actions",
        # Data stores.
        "postgres",
        "postgresql",
        "mysql",
        "mongodb",
        "redis",
        "elasticsearch",
        "cassandra",
        "dynamodb",
        # Messaging / workflow.
        "kafka",
        "rabbitmq",
        "celery",
        "airflow",
        # ML / data.
        "tensorflow",
        "pytorch",
        "scikit-learn",
        "pandas",
        "numpy",
        "machine learning",
        "deep learning",
        "nlp",
        "computer vision",
    }
)


# Document-type keyword → ``DocumentType`` enum value (as str).
# Longest-first matching in ``query_parser.py`` ensures
# "job description" wins over "job" as a prefix if we ever add the
# shorter keyword.
DOCUMENT_TYPE_KEYWORDS: dict[str, str] = {
    "resume": "resume",
    "resumes": "resume",
    "cv": "resume",
    "cvs": "resume",
    "job description": "job_description",
    "job post": "job_description",
    "job posting": "job_description",
    "jd": "job_description",
    "role description": "job_description",
    "report": "report",
    "contract": "contract",
    "letter": "letter",
}
