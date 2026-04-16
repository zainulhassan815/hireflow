"""Rule-based document classifier.

Fast, free, no API calls. Relies on keyword density and filename heuristics.
Works well for clear-cut documents; delegates to the LLM classifier for
ambiguous cases (via CompositeClassifier's confidence threshold).
"""

from __future__ import annotations

import re

from app.adapters.protocols import ClassificationResult

_RESUME_KEYWORDS = frozenset(
    {
        "resume",
        "curriculum vitae",
        "cv",
        "work experience",
        "education",
        "skills",
        "objective",
        "professional summary",
        "employment history",
        "references",
        "certifications",
        "linkedin",
        "github",
    }
)

_CONTRACT_KEYWORDS = frozenset(
    {
        "agreement",
        "contract",
        "terms and conditions",
        "parties",
        "obligations",
        "effective date",
        "termination",
        "indemnification",
        "governing law",
        "liability",
        "warranty",
        "confidentiality",
    }
)

_REPORT_KEYWORDS = frozenset(
    {
        "executive summary",
        "findings",
        "analysis",
        "conclusion",
        "recommendation",
        "quarterly",
        "annual report",
        "methodology",
        "results",
        "abstract",
    }
)

_LETTER_KEYWORDS = frozenset(
    {
        "dear",
        "sincerely",
        "regards",
        "to whom it may concern",
        "yours faithfully",
        "attached",
        "please find",
        "we are writing",
        "i am writing",
    }
)

_CATEGORIES: list[tuple[str, frozenset[str]]] = [
    ("resume", _RESUME_KEYWORDS),
    ("contract", _CONTRACT_KEYWORDS),
    ("report", _REPORT_KEYWORDS),
    ("letter", _LETTER_KEYWORDS),
]

_SKILL_PATTERN = re.compile(
    r"\b(?:python|java|javascript|typescript|react|angular|vue|node\.?js|"
    r"sql|postgresql|mysql|mongodb|redis|docker|kubernetes|aws|gcp|azure|"
    r"git|linux|c\+\+|c#|go|rust|ruby|php|swift|kotlin|scala|r|matlab|"
    r"tensorflow|pytorch|pandas|numpy|scikit-learn|spark|kafka|airflow|"
    r"fastapi|django|flask|spring|\.net|graphql|rest|grpc|"
    r"html|css|tailwind|sass|webpack|vite|figma|photoshop|"
    r"agile|scrum|jira|ci/cd|devops|mlops|data.?science|"
    r"machine.?learning|deep.?learning|nlp|computer.?vision)\b",
    re.IGNORECASE,
)

_EXPERIENCE_PATTERN = re.compile(
    r"(\d{1,2})\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp\.?)",
    re.IGNORECASE,
)

_EDUCATION_PATTERN = re.compile(
    r"\b(?:bachelor'?s?|master'?s?|ph\.?d\.?|mba|b\.?s\.?|m\.?s\.?|b\.?a\.?|"
    r"m\.?a\.?|b\.?e\.?|m\.?e\.?|b\.?tech|m\.?tech|associate'?s?|diploma)\b",
    re.IGNORECASE,
)

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_PATTERN = re.compile(r"\+?\d[\d\s\-().]{7,}\d")

_CONFIDENCE_THRESHOLD = 0.3


class RuleBasedClassifier:
    """Keyword-density classifier with structured metadata extraction for resumes."""

    def classify(self, text: str, filename: str) -> ClassificationResult:
        text_lower = text.lower()
        filename_lower = filename.lower()

        scores: dict[str, float] = {}
        for doc_type, keywords in _CATEGORIES:
            hits = sum(1 for kw in keywords if kw in text_lower)
            scores[doc_type] = hits / len(keywords)

        # Filename hints boost confidence
        for doc_type in ("resume", "cv", "contract", "report", "letter"):
            normalized = "resume" if doc_type == "cv" else doc_type
            if doc_type in filename_lower:
                scores[normalized] = scores.get(normalized, 0) + 0.3

        best_type = max(scores, key=lambda k: scores[k])
        best_score = scores[best_type]

        if best_score < _CONFIDENCE_THRESHOLD:
            best_type = "other"
            best_score = 0.0

        metadata = self._extract_metadata(text, best_type)

        return ClassificationResult(
            document_type=best_type,
            confidence=min(best_score, 1.0),
            metadata=metadata,
        )

    @staticmethod
    def _extract_metadata(text: str, doc_type: str) -> dict:
        metadata: dict = {}

        if doc_type != "resume":
            return metadata

        skills = sorted({m.group(0).lower() for m in _SKILL_PATTERN.finditer(text)})
        if skills:
            metadata["skills"] = skills

        exp_match = _EXPERIENCE_PATTERN.search(text)
        if exp_match:
            metadata["experience_years"] = int(exp_match.group(1))

        education = sorted(
            {m.group(0).strip() for m in _EDUCATION_PATTERN.finditer(text)}
        )
        if education:
            metadata["education"] = education

        emails = sorted({m.group(0) for m in _EMAIL_PATTERN.finditer(text)})
        if emails:
            metadata["emails"] = emails

        phones = sorted({m.group(0).strip() for m in _PHONE_PATTERN.finditer(text)})
        if phones:
            metadata["phones"] = phones

        return metadata
