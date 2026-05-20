"""Matching weight audit — grid search over the score 3-simplex (F45.b).

``MatchingService`` combines three signals — skill_match, experience_fit,
vector_similarity — with fixed weights (45/20/35, a guess). This eval
harvests the per-(job, candidate) signal breakdowns once, then sweeps
every weight set on a 0.05 grid (ws+we+wv == 1.0), recomputes the ranking,
and scores it against the F45.a labeled fixtures. It reports whether
45/20/35 is near-optimal and what the best constraint-respecting set is.

Pure measurement — it does not change any weights itself. Run with
``make eval-matching-weights``.
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

_AUDIT_PATH = Path(__file__).parent / "matching_weights_audit.json"
_GRID_STEP = 0.05
# Current production weights: _WEIGHT_SKILLS / _EXPERIENCE / _VECTOR.
_CURRENT_WEIGHTS = (0.45, 0.20, 0.35)
# Mean-Spearman gain over current required before a retune is worthwhile;
# below this, an on-fixture gain is within n=12 overfitting range.
_RETUNE_THRESHOLD = 0.05


def _weight_grid(step: float) -> list[tuple[float, float, float]]:
    """Every (ws, we, wv) on the simplex ws+we+wv == 1.0 at ``step``."""
    n = round(1.0 / step)
    grid: list[tuple[float, float, float]] = []
    for i in range(n + 1):
        for j in range(n + 1 - i):
            k = n - i - j
            grid.append((round(i * step, 4), round(j * step, 4), round(k * step, 4)))
    return grid


def _score_weight_set(
    weights: tuple[float, float, float],
    breakdowns: dict[str, dict[str, dict[str, float]]],
) -> dict:
    """Evaluate one weight set against every ``MATCH_CASE``.

    ``breakdowns`` is ``{job_slug: {candidate_slug: {skill_match, ...}}}``.
    """
    ws, we, wv = weights
    spearmans: list[float] = []
    top1_hits: list[float] = []
    top3s: list[float] = []
    violations = 0

    for case in MATCH_CASES:
        job_bd = breakdowns[case.job_slug]
        combined = {
            slug: ws * bd["skill_match"]
            + we * bd["experience_fit"]
            + wv * bd["vector_similarity"]
            for slug, bd in job_bd.items()
        }
        model_order = sorted(combined, key=lambda s: combined[s], reverse=True)
        expected = list(case.expected_ranking)
        model_scores = [combined[slug] for slug in expected]
        expected_ranks = [float(i + 1) for i in range(len(expected))]

        spearmans.append(spearman(model_scores, expected_ranks))
        top1_hits.append(1.0 if model_order[0] == expected[0] else 0.0)
        top3s.append(top_k_overlap(model_order, expected, 3))
        if model_order[0] in case.must_not_top:
            violations += 1

    return {
        "weights": list(weights),
        "mean_spearman": round(mean(spearmans), 4),
        "top1_accuracy": round(mean(top1_hits), 4),
        "mean_top3_overlap": round(mean(top3s), 4),
        "must_not_top_violations": violations,
    }


async def test_matching_weight_search(seeded_matching_corpus, eval_owner) -> None:
    """Harvest signal breakdowns, sweep the weight grid, write the audit."""
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

    # One matching pass per job to harvest the raw signal breakdowns;
    # everything after this is pure arithmetic over the cached values.
    breakdowns: dict[str, dict[str, dict[str, float]]] = {}
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
            breakdowns[case.job_slug] = {
                id_to_slug[r["candidate"].id]: r["breakdown"] for r in results
            }

    grid = _weight_grid(_GRID_STEP)
    scored = [_score_weight_set(w, breakdowns) for w in grid]

    current = next(
        s
        for s in scored
        if all(
            abs(a - b) < 1e-6
            for a, b in zip(s["weights"], _CURRENT_WEIGHTS, strict=True)
        )
    )

    # A set is valid only if it keeps the decision metrics intact: no
    # must_not_top violation and top-1 no worse than the current weights.
    valid = [
        s
        for s in scored
        if s["must_not_top_violations"] == 0
        and s["top1_accuracy"] >= current["top1_accuracy"]
    ]
    valid.sort(key=lambda s: s["mean_spearman"], reverse=True)
    best = valid[0]

    # Minimal-change pick: among valid sets within 0.01 of the best mean
    # Spearman, the one closest (L1) to the current weights.
    near_best = [s for s in valid if best["mean_spearman"] - s["mean_spearman"] <= 0.01]
    recommended = min(
        near_best,
        key=lambda s: sum(
            abs(a - b) for a, b in zip(s["weights"], _CURRENT_WEIGHTS, strict=True)
        ),
    )

    by_spearman = sorted(scored, key=lambda s: s["mean_spearman"], reverse=True)
    current_rank = by_spearman.index(current) + 1
    lift = round(best["mean_spearman"] - current["mean_spearman"], 4)
    verdict = "retune" if lift >= _RETUNE_THRESHOLD else "validated"

    _print_report(current, best, recommended, lift, verdict, current_rank, by_spearman)
    _write_audit(current, best, recommended, lift, verdict, current_rank, by_spearman)

    assert current["must_not_top_violations"] == 0, (
        "current 45/20/35 weights produce a must_not_top violation"
    )
    assert len(grid) == 231, f"unexpected grid size {len(grid)}"


def _fmt(s: dict) -> str:
    w = s["weights"]
    return (
        f"skill={w[0]:.2f} exp={w[1]:.2f} vec={w[2]:.2f}  "
        f"spearman={s['mean_spearman']:.3f} "
        f"top1={s['top1_accuracy']:.3f} top3={s['mean_top3_overlap']:.3f} "
        f"violations={s['must_not_top_violations']}"
    )


def _print_report(
    current: dict,
    best: dict,
    recommended: dict,
    lift: float,
    verdict: str,
    current_rank: int,
    by_spearman: list[dict],
) -> None:
    print("\n\n=== Matching weight audit (F45.b) ===\n")
    print(f"Grid: {len(by_spearman)} weight sets on a {_GRID_STEP} simplex\n")
    print(f"Current  (rank {current_rank}/{len(by_spearman)}):  {_fmt(current)}")
    print(f"Best valid:                {_fmt(best)}")
    print(f"Recommended (min-change):  {_fmt(recommended)}")
    print(f"\nSpearman lift (best - current): {lift:+.4f}")
    if verdict == "retune":
        print("Verdict: RETUNE — recommended set clears the threshold")
    else:
        print(f"Verdict: VALIDATED — lift below {_RETUNE_THRESHOLD:.2f}, keep 45/20/35")

    print("\nTop 10 by mean Spearman:")
    for i, s in enumerate(by_spearman[:10], start=1):
        print(f"  {i:2d}. {_fmt(s)}")


def _write_audit(
    current: dict,
    best: dict,
    recommended: dict,
    lift: float,
    verdict: str,
    current_rank: int,
    by_spearman: list[dict],
) -> None:
    audit = {
        "grid_step": _GRID_STEP,
        "grid_size": len(by_spearman),
        "retune_threshold": _RETUNE_THRESHOLD,
        "current": current,
        "current_rank": current_rank,
        "best_valid": best,
        "recommended": recommended,
        "spearman_lift": lift,
        "verdict": verdict,
        "top_10": by_spearman[:10],
    }
    _AUDIT_PATH.write_text(json.dumps(audit, indent=2))
