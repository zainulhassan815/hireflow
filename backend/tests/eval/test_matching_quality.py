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

_BASELINE_PATH = Path(__file__).parent / "matching_baseline.json"
_MIN_MEAN_SPEARMAN = 0.4  # soft floor; prints if below, does not block


def _average_ranks(values: list[float]) -> list[float]:
    """Rank ``values`` largest→smallest (rank 1 = largest), averaging ties.

    Average ranks keep Spearman correct when two candidates land on the
    same rounded score — using sorted position would hide the tie.
    """
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1  # 1-based average rank for the tie group
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def _spearman(model_scores: list[float], expected_ranks: list[float]) -> float:
    """Spearman ρ — Pearson correlation between the two rank vectors.

    ``model_scores[i]`` is the model's score for the candidate whose
    expected rank is ``expected_ranks[i]``. Returns 0.0 on a degenerate
    (constant) input instead of dividing by zero.
    """
    model_ranks = _average_ranks(model_scores)
    n = len(model_ranks)
    if n < 2:
        return 0.0
    mr = mean(model_ranks)
    er = mean(expected_ranks)
    cov = sum((model_ranks[i] - mr) * (expected_ranks[i] - er) for i in range(n))
    std_m = sum((model_ranks[i] - mr) ** 2 for i in range(n)) ** 0.5
    std_e = sum((expected_ranks[i] - er) ** 2 for i in range(n)) ** 0.5
    if std_m == 0 or std_e == 0:
        return 0.0
    return cov / (std_m * std_e)


def _top_k_overlap(model_order: list[str], expected_order: list[str], k: int) -> float:
    """Fraction of the expected top-k that appears in the model's top-k."""
    return len(set(model_order[:k]) & set(expected_order[:k])) / k


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

            rho = _spearman(model_scores, expected_ranks)
            top1_hit = model_order[0] == expected[0]
            top3 = _top_k_overlap(model_order, expected, 3)

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
