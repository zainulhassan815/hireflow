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
from app.models import Candidate, Job
from app.repositories.candidate import ApplicationRepository, CandidateRepository
from app.repositories.job import JobRepository

logger = logging.getLogger(__name__)

_WEIGHT_SKILLS = 0.45
_WEIGHT_EXPERIENCE = 0.20
_WEIGHT_VECTOR = 0.35


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

            app = await self._applications.get_for_job_and_candidate(
                job_id, candidate.id
            )
            if app is None:
                app = await self._applications.create(
                    candidate_id=candidate.id,
                    job_id=job_id,
                    score=score,
                )
            else:
                app.score = score
                app = await self._applications.save(app)

            results.append(
                {
                    "candidate": candidate,
                    "application": app,
                    "score": score,
                    "breakdown": self._breakdown(job, candidate, vector_scores),
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

        return round(
            _WEIGHT_SKILLS * skill_score
            + _WEIGHT_EXPERIENCE * exp_score
            + _WEIGHT_VECTOR * vec_score,
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

        return 0.7 * required_match + 0.3 * preferred_match

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
            # Map document_id back to candidate via source_document_id
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
        return {
            "skill_match": round(self._skill_overlap(job, candidate), 3),
            "experience_fit": round(self._experience_fit(job, candidate), 3),
            "vector_similarity": round(vector_scores.get(candidate.id, 0.0), 3),
        }
