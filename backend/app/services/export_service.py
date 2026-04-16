"""CSV export for candidate match results."""

from __future__ import annotations

import csv
import io
from typing import Any

from app.models import Application, Candidate


def export_candidates_to_csv(results: list[dict[str, Any]]) -> str:
    """Generate a CSV string from match results."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(
        [
            "Name",
            "Email",
            "Phone",
            "Skills",
            "Experience (yrs)",
            "Education",
            "Match Score (%)",
            "Skill Match (%)",
            "Experience Fit (%)",
            "Vector Similarity (%)",
            "Status",
        ]
    )

    for result in results:
        candidate: Candidate = result["candidate"]
        application: Application = result["application"]
        breakdown: dict = result.get("breakdown", {})

        writer.writerow(
            [
                candidate.name or "",
                candidate.email or "",
                candidate.phone or "",
                ", ".join(candidate.skills),
                candidate.experience_years or "",
                ", ".join(candidate.education) if candidate.education else "",
                round(result["score"] * 100, 1),
                round(breakdown.get("skill_match", 0) * 100, 1),
                round(breakdown.get("experience_fit", 0) * 100, 1),
                round(breakdown.get("vector_similarity", 0) * 100, 1),
                application.status.value,
            ]
        )

    return buf.getvalue()
