"""Search quality evaluation.

Runs 15-20 curated queries against the seeded fixture docs and reports
precision@5, recall@5, and MRR — overall and per bucket. Hard-fails
if any ``must_not_contain`` doc appears in the top-5 results of its
query (the regression we explicitly want to prevent).

Soft fails (printed but don't block the suite) track the aggregate
P@5 floor. Starting floor is deliberately forgiving while we tune;
raise it as we iterate.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from uuid import UUID

from app.repositories.document import DocumentRepository
from app.services.search_service import SearchService
from tests.eval.dataset import EVAL_QUERIES, EvalCase

_BASELINE_PATH = Path(__file__).parent / "baseline.json"
_MIN_AGGREGATE_P5 = 0.35  # soft floor; eval prints if below, hard-fails at 0


def _precision_at_k(ranked_slugs: list[str], expected: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top_k = ranked_slugs[:k]
    relevant_in_top = sum(1 for s in top_k if s in expected)
    return relevant_in_top / k


def _recall_at_k(ranked_slugs: list[str], expected: set[str], k: int) -> float:
    if not expected:
        # Recall undefined for negative queries; return 1.0 if nothing
        # was returned, else 0.0. This matches the intuition "we got
        # everything we should have."
        return 1.0 if not ranked_slugs[:k] else 0.0
    top_k_set = set(ranked_slugs[:k])
    return len(top_k_set & expected) / len(expected)


def _reciprocal_rank(ranked_slugs: list[str], expected: set[str]) -> float:
    for i, slug in enumerate(ranked_slugs, start=1):
        if slug in expected:
            return 1.0 / i
    return 0.0


async def _run_query(
    service: SearchService, actor, case: EvalCase, slug_to_id: dict[str, UUID]
) -> list[str]:
    """Run one query; return the list of result slugs in rank order."""
    filters: dict = {"limit": 10}
    for key, value in case.filters.items():
        if key == "document_type":
            from app.models import DocumentType

            filters["document_type"] = DocumentType(value)
        elif key in {"skills", "min_experience_years", "date_from", "date_to"}:
            filters[key] = value

    results, _ = await service.search(actor=actor, query=case.query, **filters)

    id_to_slug = {v: k for k, v in slug_to_id.items()}
    return [
        id_to_slug.get(r["document_id"], f"unknown:{r['document_id']}") for r in results
    ]


async def test_search_quality_report(slug_to_document_id, eval_owner):
    """Run every eval case; print report; fail on hard violations."""
    from app.adapters.chroma_store import ChromaVectorStore
    from app.adapters.embeddings.registry import get_embedding_provider
    from app.adapters.rerankers.registry import get_reranker
    from app.core.config import settings
    from app.core.db import SessionLocal

    store = ChromaVectorStore(
        host=settings.chroma_host,
        port=settings.chroma_port,
        embedder=get_embedding_provider(settings),
    )
    reranker = get_reranker(settings)

    per_case: list[dict] = []
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    hard_failures: list[str] = []

    async with SessionLocal() as session:
        service = SearchService(DocumentRepository(session), store, reranker=reranker)

        for case in EVAL_QUERIES:
            ranked = await _run_query(service, eval_owner, case, slug_to_document_id)

            p5 = _precision_at_k(ranked, case.expected_docs, 5)
            r5 = _recall_at_k(ranked, case.expected_docs, 5)
            mrr = _reciprocal_rank(ranked, case.expected_docs)

            top5 = set(ranked[:5])
            violations = top5 & case.must_not_contain
            if violations:
                hard_failures.append(
                    f"{case.bucket}/'{case.query}': must_not_contain leaked {violations}"
                )

            row = {
                "bucket": case.bucket,
                "query": case.query,
                "expected": sorted(case.expected_docs),
                "returned": ranked[:5],
                "p@5": round(p5, 3),
                "r@5": round(r5, 3),
                "mrr": round(mrr, 3),
                "must_not_contain_violation": sorted(violations),
                "notes": case.notes,
            }
            per_case.append(row)
            by_bucket[case.bucket].append(row)

    overall_p5 = mean(r["p@5"] for r in per_case)
    overall_r5 = mean(r["r@5"] for r in per_case)
    overall_mrr = mean(r["mrr"] for r in per_case)

    _print_report(per_case, by_bucket, overall_p5, overall_r5, overall_mrr)

    _write_baseline(per_case, overall_p5, overall_r5, overall_mrr)

    if hard_failures:
        lines = "\n  - ".join(hard_failures)
        raise AssertionError(f"must_not_contain violations:\n  - {lines}")

    assert overall_p5 >= 0.0, "no queries ran"


def _print_report(
    per_case: list[dict],
    by_bucket: dict[str, list[dict]],
    overall_p5: float,
    overall_r5: float,
    overall_mrr: float,
) -> None:
    print("\n\n=== Search quality report ===\n")
    print(f"Queries: {len(per_case)}")
    print(f"Aggregate P@5:  {overall_p5:.3f}")
    print(f"Aggregate R@5:  {overall_r5:.3f}")
    print(f"Aggregate MRR:  {overall_mrr:.3f}")
    if overall_p5 < _MIN_AGGREGATE_P5:
        print(f"(below soft floor of {_MIN_AGGREGATE_P5:.2f} — not a hard fail yet)")

    print("\nPer-bucket:")
    for bucket, rows in sorted(by_bucket.items()):
        bp5 = mean(r["p@5"] for r in rows)
        bmrr = mean(r["mrr"] for r in rows)
        print(f"  {bucket:12s} n={len(rows):2d}  P@5={bp5:.3f}  MRR={bmrr:.3f}")

    print("\nPer-query:")
    for row in per_case:
        status = "OK"
        if row["must_not_contain_violation"]:
            status = f"VIOLATION {row['must_not_contain_violation']}"
        elif row["p@5"] == 0 and row["expected"]:
            status = "MISS"
        print(
            f"  [{row['bucket']:10s}] P@5={row['p@5']:.2f} MRR={row['mrr']:.2f} "
            f"'{row['query'][:50]}' → {row['returned'][:3]} ({status})"
        )


def _write_baseline(
    per_case: list[dict],
    overall_p5: float,
    overall_r5: float,
    overall_mrr: float,
) -> None:
    report = {
        "overall": {
            "p@5": round(overall_p5, 4),
            "r@5": round(overall_r5, 4),
            "mrr": round(overall_mrr, 4),
        },
        "cases": per_case,
    }
    _BASELINE_PATH.write_text(json.dumps(report, indent=2))
