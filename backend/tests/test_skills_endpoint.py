"""F32 — GET /api/search/skills tests.

Returns the canonical KNOWN_SKILLS vocabulary used by the rule-
based classifier + F89.a query parser. Frontends consume this
on page mount for the F32 filter bar's skill-picker suggestions.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_unauthenticated_rejected(client) -> None:
    response = await client.get("/api/search/skills")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_returns_sorted_lowercase_list(
    client, hr_user, hr_token, auth_headers
) -> None:
    response = await client.get(
        "/api/search/skills",
        headers=auth_headers(hr_token),
    )
    assert response.status_code == 200

    skills = response.json()
    assert isinstance(skills, list)
    assert len(skills) > 0
    # Every entry is a non-empty lowercase string.
    for s in skills:
        assert isinstance(s, str)
        assert s == s.lower()
        assert s.strip() != ""
    # Sorted ascending.
    assert skills == sorted(skills)


@pytest.mark.asyncio
async def test_includes_known_canonical_skills(
    client, hr_user, hr_token, auth_headers
) -> None:
    """Spot-check a few skills the F103.b vocab additions added —
    locks in that the endpoint reads from the live ``KNOWN_SKILLS``
    constant rather than a stale copy."""
    response = await client.get(
        "/api/search/skills",
        headers=auth_headers(hr_token),
    )
    skills = response.json()
    for canonical in ("python", "react", "stripe", "fastapi"):
        assert canonical in skills, f"missing canonical skill: {canonical!r}"


@pytest.mark.asyncio
async def test_idempotent_per_user(client, hr_user, hr_token, auth_headers) -> None:
    """Two calls return the same list — the vocabulary is process-
    constant and doesn't depend on the caller's data."""
    first = (
        await client.get("/api/search/skills", headers=auth_headers(hr_token))
    ).json()
    second = (
        await client.get("/api/search/skills", headers=auth_headers(hr_token))
    ).json()
    assert first == second
