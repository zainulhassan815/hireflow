"""Candidate-matching quality eval (F45.a).

Runs ``MatchingService.match_candidates_to_job`` against a labeled corpus
of ``(job, candidate, expected-rank)`` fixtures and reports rank-agreement
metrics — Spearman correlation, top-1 accuracy, and top-3 overlap —
overall and per job. Hard-fails if a ``must_not_top`` candidate is ranked
#1 (the regression we explicitly guard against).

This is the measurement layer F45.b (weight tuning) optimizes against:
without it the 45/20/35 weights are untestable. The run overwrites
``matching_baseline.json`` so a diff shows movement between runs.

Run with ``make eval-matching``.
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from app.repositories.candidate import ApplicationRepository, CandidateRepository
from app.repositories.job import JobRepository
from app.services.matching_service import MatchingService
from tests.eval.matching_dataset import MATCH_CASES
from tests.eval.matching_metrics import spearman, top_k_overlap

_BASELINE_PATH = Path(__file__).parent / "matching_baseline.json"
_MIN_MEAN_SPEARMAN = 0.4  # soft floor; prints if below, does not block


async def test_matching_quality_report(seeded_matching_corpus, eval_owner) -> None:
    """Run matching for every labeled job; print the report; write the
    baseline; fail on must_not_top violations."""
    from app.adapters.chroma_store import ChromaVectorStore
    from app.adapters.embeddings.registry import get_embedding_provider
    from app.core.config import settings
    from app.core.db import SessionLocal

    candidate_ids, job_ids = seeded_matching_corpus
    id_to_slug = {cid: slug for slug, cid in candidate_ids.items()}

    store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        embedder=get_embedding_provider(settings),
    )

    per_case: list[dict] = []
    hard_failures: list[str] = []

    async with SessionLocal() as session:
        service = MatchingService(
            CandidateRepository(session),
            ApplicationRepository(session),
            JobRepository(session),
            store,
        )

        for case in MATCH_CASES:
            results = await service.match_candidates_to_job(
                job_ids[case.job_slug], eval_owner.id
            )
            model_order = [id_to_slug[r["candidate"].id] for r in results]
            score_by_slug = {id_to_slug[r["candidate"].id]: r["score"] for r in results}

            missing = set(case.expected_ranking) - score_by_slug.keys()
            assert not missing, f"{case.job_slug}: candidates not scored: {missing}"

            expected = list(case.expected_ranking)
            model_scores = [score_by_slug[slug] for slug in expected]
            expected_ranks = [float(i + 1) for i in range(len(expected))]

            rho = spearman(model_scores, expected_ranks)
            top1_hit = model_order[0] == expected[0]
            top3 = top_k_overlap(model_order, expected, 3)

            violator = model_order[0] if model_order[0] in case.must_not_top else None
            if violator:
                hard_failures.append(
                    f"{case.job_slug}: must_not_top candidate '{violator}' ranked #1"
                )

            per_case.append(
                {
                    "job": case.job_slug,
                    "spearman": round(rho, 3),
                    "top1_hit": top1_hit,
                    "top3_overlap": round(top3, 3),
                    "model_top3": model_order[:3],
                    "expected_top3": expected[:3],
                    "must_not_top_violation": violator,
                }
            )

    mean_spearman = mean(r["spearman"] for r in per_case)
    top1_accuracy = mean(1.0 if r["top1_hit"] else 0.0 for r in per_case)
    mean_top3 = mean(r["top3_overlap"] for r in per_case)

    _print_report(per_case, mean_spearman, top1_accuracy, mean_top3)
    _write_baseline(per_case, mean_spearman, top1_accuracy, mean_top3)

    if hard_failures:
        lines = "\n  - ".join(hard_failures)
        raise AssertionError(f"must_not_top violations:\n  - {lines}")

    assert per_case, "no match cases ran"


def _print_report(
    per_case: list[dict],
    mean_spearman: float,
    top1_accuracy: float,
    mean_top3: float,
) -> None:
    print("\n\n=== Candidate-matching quality report ===\n")
    print(f"Jobs evaluated:     {len(per_case)}")
    print(f"Mean Spearman:      {mean_spearman:.3f}")
    print(f"Top-1 accuracy:     {top1_accuracy:.3f}")
    print(f"Mean top-3 overlap: {mean_top3:.3f}")
    if mean_spearman < _MIN_MEAN_SPEARMAN:
        print(f"(below soft floor of {_MIN_MEAN_SPEARMAN:.2f} — not a hard fail yet)")

    print("\nPer-job:")
    for row in per_case:
        if row["must_not_top_violation"]:
            status = f"VIOLATION ({row['must_not_top_violation']} @ #1)"
        elif not row["top1_hit"]:
            status = "TOP-1 MISS"
        else:
            status = "OK"
        print(
            f"  [{row['job']:20s}] rho={row['spearman']:+.2f} "
            f"top1={'Y' if row['top1_hit'] else 'n'} "
            f"top3={row['top3_overlap']:.2f}  "
            f"model_top3={row['model_top3']} ({status})"
        )


def _write_baseline(
    per_case: list[dict],
    mean_spearman: float,
    top1_accuracy: float,
    mean_top3: float,
) -> None:
    report = {
        "overall": {
            "mean_spearman": round(mean_spearman, 4),
            "top1_accuracy": round(top1_accuracy, 4),
            "mean_top3_overlap": round(mean_top3, 4),
        },
        "cases": per_case,
    }
    _BASELINE_PATH.write_text(json.dumps(report, indent=2))
