"""Resume ↔ job matching and candidate ranking.

Scores candidates against a job using three signals:
1. Skill overlap (jaccard similarity on required + preferred skills)
2. Experience fit (how well candidate years match job range)
3. Vector similarity (semantic match between resume text and job description)

Weights are tunable. The combined score is stored on the Application record.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.adapters.protocols import VectorStore
from app.core.config import settings
from app.models import Candidate, Job
from app.models.candidate import CREDENTIAL_ROLES
from app.repositories.candidate import ApplicationRepository, CandidateRepository
from app.repositories.job import JobRepository

logger = logging.getLogger(__name__)

# Starting point for the four-signal blend (F46.d). Re-tuned by the
# F45.b weight search once the eval fixture carries cert-bearing
# candidates.
_WEIGHT_SKILLS = 0.40
_WEIGHT_EXPERIENCE = 0.20
_WEIGHT_VECTOR = 0.30
_WEIGHT_CREDENTIALS = 0.10


class MatchingService:
    def __init__(
        self,
        candidates: CandidateRepository,
        applications: ApplicationRepository,
        jobs: JobRepository,
        vector_store: VectorStore | None,
    ) -> None:
        self._candidates = candidates
        self._applications = applications
        self._jobs = jobs
        self._vector_store = vector_store

    async def match_candidates_to_job(self, job_id: UUID, owner_id: UUID) -> list[dict]:
        """Score all candidates owned by the user against a job.

        Creates or updates Application records with computed scores.
        Returns ranked results.
        """
        job = await self._jobs.get(job_id)
        if job is None:
            return []

        candidates = await self._candidates.list_by_owner(owner_id, limit=500)
        if not candidates:
            return []

        vector_scores = self._get_vector_scores(job, candidates)

        results = []
        for candidate in candidates:
            score = self._compute_score(job, candidate, vector_scores)
            # Persist the breakdown alongside the score so the list
            # hover popover can render it without recomputing.
            # ``_breakdown`` returns the shape ``MatchBreakdown``
            # expects; the list endpoint consumes it via model_validate.
            breakdown = self._breakdown(job, candidate, vector_scores)

            app = await self._applications.get_for_job_and_candidate(
                job_id, candidate.id
            )
            if app is None:
                app = await self._applications.create(
                    candidate_id=candidate.id,
                    job_id=job_id,
                    score=score,
                    match_breakdown=breakdown,
                )
            else:
                app.score = score
                app.match_breakdown = breakdown
                app = await self._applications.save(app)

            results.append(
                {
                    "candidate": candidate,
                    "application": app,
                    "score": score,
                    "breakdown": breakdown,
                }
            )

        results.sort(key=lambda r: r["score"], reverse=True)
        logger.info("matched %d candidates to job %s", len(results), job_id)
        return results

    def _compute_score(
        self,
        job: Job,
        candidate: Candidate,
        vector_scores: dict[UUID, float],
    ) -> float:
        skill_score = self._skill_overlap(job, candidate)
        exp_score = self._experience_fit(job, candidate)
        vec_score = vector_scores.get(candidate.id, 0.0)
        cred_score = self._credential_match(job, candidate)

        return round(
            _WEIGHT_SKILLS * skill_score
            + _WEIGHT_EXPERIENCE * exp_score
            + _WEIGHT_VECTOR * vec_score
            + _WEIGHT_CREDENTIALS * cred_score,
            4,
        )

    @staticmethod
    def _skill_overlap(job: Job, candidate: Candidate) -> float:
        if not job.required_skills:
            return 0.0

        candidate_skills = {s.lower() for s in candidate.skills}
        required = {s.lower() for s in job.required_skills}
        preferred = {s.lower() for s in (job.preferred_skills or [])}

        required_match = (
            len(required & candidate_skills) / len(required) if required else 0
        )
        preferred_match = (
            len(preferred & candidate_skills) / len(preferred) if preferred else 0
        )

        base = 0.7 * required_match + 0.3 * preferred_match

        # F45.d — required-skill floor. A required-skill miss can gate the
        # whole skill signal depending on the configured policy.
        if required and required_match < 1.0:
            policy = settings.matching_required_skill_policy
            if policy == "zero":
                return 0.0
            if policy == "halve":
                return base * 0.5
        return base

    @staticmethod
    def _credential_match(job: Job, candidate: Candidate) -> float:
        """Fraction of the job's skills covered by the candidate's
        credential attachments (certificates / transcripts / portfolios).

        Reads each credential document's extracted skills live, so a cert
        covering a required skill the resume missed lifts the candidate.
        Weighted separately (not folded into ``skill_overlap``) so a cert
        that merely restates a resume skill can't inflate that signal past
        its cap.
        """
        targets = {s.lower() for s in job.required_skills} | {
            s.lower() for s in (job.preferred_skills or [])
        }
        if not targets:
            return 0.0

        credential_skills: set[str] = set()
        for attachment in candidate.attachments:
            if attachment.role not in CREDENTIAL_ROLES:
                continue
            meta = (attachment.document.metadata_ or {}) if attachment.document else {}
            for skill in meta.get("skills") or []:
                credential_skills.add(skill.lower())

        if not credential_skills:
            return 0.0
        return len(credential_skills & targets) / len(targets)

    @staticmethod
    def _experience_fit(job: Job, candidate: Candidate) -> float:
        if candidate.experience_years is None:
            return 0.3  # neutral when unknown

        years = candidate.experience_years
        min_exp = job.experience_min
        max_exp = job.experience_max

        if max_exp is not None and min_exp <= years <= max_exp:
            return 1.0
        if max_exp is None and years >= min_exp:
            return 1.0
        if years < min_exp:
            gap = min_exp - years
            return max(0.0, 1.0 - gap * 0.2)
        if max_exp is not None and years > max_exp:
            gap = years - max_exp
            return max(0.0, 1.0 - gap * 0.15)
        return 0.3

    def _get_vector_scores(
        self, job: Job, candidates: list[Candidate]
    ) -> dict[UUID, float]:
        """Query ChromaDB for semantic similarity between job description
        and each candidate's resume chunks."""
        if self._vector_store is None:
            return {}

        hits = self._vector_store.query(
            query_text=f"{job.title} {job.description}",
            n_results=100,
        )

        scores: dict[UUID, float] = {}
        for hit in hits:
            try:
                doc_id = UUID(hit.document_id)
            except ValueError:
                continue
            for c in candidates:
                if c.source_document_id == doc_id:
                    # Cosine distance → similarity (lower distance = higher similarity)
                    similarity = max(0.0, 1.0 - hit.distance)
                    scores[c.id] = max(scores.get(c.id, 0.0), similarity)
                    break

        return scores

    def _breakdown(
        self,
        job: Job,
        candidate: Candidate,
        vector_scores: dict[UUID, float],
    ) -> dict:
        skill = round(self._skill_overlap(job, candidate), 3)
        exp = round(self._experience_fit(job, candidate), 3)
        vec = round(vector_scores.get(candidate.id, 0.0), 3)
        cred = round(self._credential_match(job, candidate), 3)
        return {
            "skill_match": skill,
            "experience_fit": exp,
            "vector_similarity": vec,
            "credential_match": cred,
            # F45.f — extraction produced no skills; the candidate is still
            # scored (vector can rank), but flagged so the UI can separate
            # them rather than bury them at the bottom.
            "unscored": len(candidate.skills) == 0,
            "explanation": self._explanation(
                job, candidate, skill=skill, experience=exp, vector=vec, credential=cred
            ),
        }

    @staticmethod
    def _explanation(
        job: Job,
        candidate: Candidate,
        *,
        skill: float,
        experience: float,
        vector: float,
        credential: float,
    ) -> str:
        """A short, deterministic 'why this score' sentence (F45.e).

        Rule-based on purpose — no LLM call at score time. Describes each
        signal qualitatively plus the concrete skills / experience that
        drove it.
        """
        parts: list[str] = []

        candidate_skills = {s.lower() for s in candidate.skills}
        required = list(job.required_skills)
        if not candidate.skills:
            parts.append("no skills extracted from the résumé")
        elif required:
            matched = [s for s in required if s.lower() in candidate_skills]
            qual = "strong" if skill >= 0.75 else "partial" if skill >= 0.4 else "weak"
            shown = ", ".join(matched[:3])
            detail = f" ({shown})" if shown else ""
            parts.append(
                f"{qual} skills — {len(matched)}/{len(required)} required{detail}"
            )

        if candidate.experience_years is not None:
            rng = (
                f"{job.experience_min}–{job.experience_max}"
                if job.experience_max is not None
                else f"{job.experience_min}+"
            )
            fit = (
                "fits"
                if experience >= 0.9
                else "near"
                if experience >= 0.5
                else "outside"
            )
            parts.append(f"{candidate.experience_years} yrs {fit} the {rng} range")

        vqual = "high" if vector >= 0.6 else "moderate" if vector >= 0.3 else "low"
        parts.append(f"{vqual} semantic similarity")

        if credential > 0:
            parts.append(f"credentials cover {round(credential * 100)}% of role skills")

        sentence = "; ".join(parts)
        return sentence[:1].upper() + sentence[1:] + "." if sentence else ""
