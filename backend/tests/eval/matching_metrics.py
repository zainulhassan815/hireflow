"""Rank-agreement metrics shared by the matching evals (F45.a / F45.b).

Pure functions — no DB, no ``app`` imports — so they import cleanly from
any eval module. Extracted from ``test_matching_quality.py`` once the
weight-search eval needed the same maths.
"""

from __future__ import annotations

from statistics import mean


def average_ranks(values: list[float]) -> list[float]:
    """Rank ``values`` largest→smallest (rank 1 = largest), averaging ties.

    Average ranks keep Spearman correct when two candidates land on the
    same score — using sorted position would hide the tie.
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


def spearman(model_scores: list[float], expected_ranks: list[float]) -> float:
    """Spearman ρ — Pearson correlation between the two rank vectors.

    ``model_scores[i]`` is the model's score for the candidate whose
    expected rank is ``expected_ranks[i]``. Returns 0.0 on a degenerate
    (constant) input instead of dividing by zero.
    """
    model_ranks = average_ranks(model_scores)
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


def top_k_overlap(model_order: list[str], expected_order: list[str], k: int) -> float:
    """Fraction of the expected top-k that appears in the model's top-k."""
    return len(set(model_order[:k]) & set(expected_order[:k])) / k
