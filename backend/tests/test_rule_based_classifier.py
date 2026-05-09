"""Tests for ``RuleBasedClassifier``.

Focus: F103.b narrative skill extraction. Covers the regression case
(explicit ``Skills:`` section still works) and the new behavior
(skills surface from project bullets when no Skills section exists).
"""

from __future__ import annotations

from app.adapters.classifiers.rule_based import RuleBasedClassifier

_RESUME_WITH_SKILLS_SECTION = """\
Jane Doe — Software Engineer
jane@example.com

EXPERIENCE
Senior Engineer, Acme Co (2021-present)
- Led a small team

SKILLS
Python, FastAPI, PostgreSQL, Docker, Kubernetes

EDUCATION
Bachelor's in Computer Science
"""

_RESUME_NARRATIVE_ONLY = """\
Jane Doe
jane@example.com
+1 555 123 4567

PROFESSIONAL SUMMARY
Senior backend engineer with 7 years of experience building payment
infrastructure and data platforms.

EXPERIENCE
Senior Engineer, Acme Co (2021-present)
- Built a Stripe checkout integration handling $2M/mo in payments
- Migrated the data warehouse from Redshift to Snowflake
- Owned the FastAPI service powering the customer portal
- Operated the Postgres replicas and tuned the Redis cache layer

EDUCATION
Bachelor's in Computer Science
"""

_REPORT_TEXT = """\
Quarterly Report — Q3

Executive Summary
Revenue grew 12% over Q2. The methodology section details our analysis.

Findings
- Conversion rate improved.

Conclusion
Recommendation: invest more in onboarding.
"""


class TestRuleBasedClassifier:
    def setup_method(self) -> None:
        self.classifier = RuleBasedClassifier()

    def test_resume_with_skills_section_extracts_skills(self) -> None:
        result = self.classifier.classify(
            _RESUME_WITH_SKILLS_SECTION, "jane_doe_resume.pdf"
        )
        assert result.document_type == "resume"
        skills = result.metadata.get("skills", [])
        assert "python" in skills
        assert "fastapi" in skills
        assert "postgresql" in skills
        assert "docker" in skills
        assert "kubernetes" in skills

    def test_resume_narrative_only_surfaces_project_skills(self) -> None:
        # The original F103 failing case: no "Skills:" section, but the
        # project bullets mention real technologies. They should land
        # in metadata.skills so downstream search/matching can use them.
        result = self.classifier.classify(_RESUME_NARRATIVE_ONLY, "jane_doe_resume.pdf")
        assert result.document_type == "resume"
        skills = result.metadata.get("skills", [])
        assert "stripe" in skills, f"narrative Stripe missed: {skills}"
        assert "snowflake" in skills
        assert "redshift" in skills
        assert "fastapi" in skills
        assert "postgres" in skills
        assert "redis" in skills

    def test_resume_extracts_other_metadata(self) -> None:
        result = self.classifier.classify(_RESUME_NARRATIVE_ONLY, "jane_doe_resume.pdf")
        assert result.metadata.get("experience_years") == 7
        assert "jane@example.com" in result.metadata.get("emails", [])
        assert result.metadata.get("education")

    def test_non_resume_has_no_skills_metadata(self) -> None:
        result = self.classifier.classify(_REPORT_TEXT, "q3_report.pdf")
        assert result.document_type == "report"
        assert "skills" not in result.metadata
