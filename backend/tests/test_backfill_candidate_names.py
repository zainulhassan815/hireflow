"""F103.d — backfill_candidate_names script behaviour with stub LLM.

Covers:
- Skip-via-version-tag (the only skip predicate per plan rev 2 §4).
- Non-destructive metadata merge.
- ``Candidate.name`` propagation via ``SyncCandidateService``.
- ``--apply`` requires ``--snapshot``.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.protocols import ClassificationResult
from app.core.db import sync_engine
from app.models import Candidate, Document, DocumentStatus, DocumentType


class _StubLlmClassifier:
    """Returns canned classifications keyed by filename."""

    def __init__(self, by_filename: dict[str, dict[str, Any]]) -> None:
        self._by_filename = by_filename
        self.call_count = 0

    def classify(self, text: str, filename: str) -> ClassificationResult:
        self.call_count += 1
        canned = self._by_filename.get(
            filename, {"document_type": "resume", "metadata": {}}
        )
        return ClassificationResult(
            document_type=canned.get("document_type", "resume"),
            confidence=0.95,
            metadata=canned.get("metadata", {}),
        )


def _seed_resume(
    session: Session,
    *,
    owner_id,
    filename: str,
    metadata: dict | None = None,
) -> Document:
    doc = Document(
        owner_id=owner_id,
        filename=filename,
        mime_type="application/pdf",
        size_bytes=100,
        storage_key=f"key-{uuid4()}",
        status=DocumentStatus.READY,
        document_type=DocumentType.RESUME,
        extracted_text="resume body text",
        metadata_=metadata or {},
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)
    return doc


@pytest.mark.asyncio
async def test_apply_populates_metadata_name_and_candidate_name(
    admin_user, tmp_path
) -> None:
    snapshot_path = tmp_path / "snap.jsonl"

    with Session(sync_engine) as session:
        doc = _seed_resume(session, owner_id=admin_user.id, filename="alice_resume.pdf")
        doc_id = doc.id

    stub = _StubLlmClassifier(
        {
            "alice_resume.pdf": {
                "metadata": {
                    "name": "Alice Ng",
                    "emails": ["alice@example.com"],
                    "skills": ["stripe", "fastapi"],
                }
            }
        }
    )

    from scripts import backfill_candidate_names

    with patch.object(backfill_candidate_names, "_build_classifier", return_value=stub):
        backfill_candidate_names.backfill(apply=True, snapshot_path=snapshot_path)

    assert stub.call_count == 1

    with Session(sync_engine) as session:
        doc = session.get(Document, doc_id)
        assert doc.metadata_["name"] == "Alice Ng"
        assert doc.metadata_["name_backfill_version"] == "v1-llm"
        assert "alice@example.com" in doc.metadata_["emails"]
        assert set(doc.metadata_["skills"]) >= {"stripe", "fastapi"}

        candidate = session.execute(
            select(Candidate).where(Candidate.source_document_id == doc_id)
        ).scalar_one()
        assert candidate.name == "Alice Ng"
        assert candidate.email == "alice@example.com"

    # Snapshot file written.
    rows = [json.loads(line) for line in snapshot_path.read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["document_id"] == str(doc_id)
    assert rows[0]["metadata_name_before"] is None


@pytest.mark.asyncio
async def test_second_run_skips_via_version_tag(admin_user, tmp_path) -> None:
    """Skip predicate is the version tag *only* — even if the LLM never
    extracted a name on the prior run, we don't retry."""
    snapshot_path = tmp_path / "snap.jsonl"

    with Session(sync_engine) as session:
        _seed_resume(
            session,
            owner_id=admin_user.id,
            filename="bob_resume.pdf",
            metadata={"name_backfill_version": "v1-llm"},
        )

    stub = _StubLlmClassifier({"bob_resume.pdf": {"metadata": {"name": "Bob"}}})

    from scripts import backfill_candidate_names

    with patch.object(backfill_candidate_names, "_build_classifier", return_value=stub):
        backfill_candidate_names.backfill(apply=True, snapshot_path=snapshot_path)

    # Skipped — no LLM call should have fired.
    assert stub.call_count == 0


@pytest.mark.asyncio
async def test_dry_run_does_not_write(admin_user) -> None:
    with Session(sync_engine) as session:
        doc = _seed_resume(session, owner_id=admin_user.id, filename="alice_resume.pdf")
        doc_id = doc.id

    stub = _StubLlmClassifier({"alice_resume.pdf": {"metadata": {"name": "Alice Ng"}}})

    from scripts import backfill_candidate_names

    with patch.object(backfill_candidate_names, "_build_classifier", return_value=stub):
        backfill_candidate_names.backfill(apply=False, snapshot_path=None)

    # LLM was called (cost visibility) but no DB writes happened.
    assert stub.call_count == 1
    with Session(sync_engine) as session:
        doc = session.get(Document, doc_id)
        assert "name" not in (doc.metadata_ or {})
        assert "name_backfill_version" not in (doc.metadata_ or {})


@pytest.mark.asyncio
async def test_apply_requires_snapshot() -> None:
    from scripts import backfill_candidate_names

    with (
        patch.object(
            backfill_candidate_names,
            "_build_classifier",
            return_value=_StubLlmClassifier({}),
        ),
        pytest.raises(SystemExit),
    ):
        backfill_candidate_names.backfill(apply=True, snapshot_path=None)


@pytest.mark.asyncio
async def test_no_llm_provider_configured_exits_cleanly() -> None:
    from scripts import backfill_candidate_names

    with (
        patch.object(backfill_candidate_names, "_build_classifier", return_value=None),
        pytest.raises(SystemExit) as exc_info,
    ):
        backfill_candidate_names.backfill(apply=False, snapshot_path=None)

    assert "No LLM provider" in str(exc_info.value)


@pytest.mark.asyncio
async def test_metadata_merge_is_non_destructive(admin_user, tmp_path) -> None:
    """Pre-existing metadata keys (skills from F103.b, etc.) survive
    the backfill."""
    snapshot_path = tmp_path / "snap.jsonl"

    with Session(sync_engine) as session:
        doc = _seed_resume(
            session,
            owner_id=admin_user.id,
            filename="alice_resume.pdf",
            metadata={
                "skills": ["python"],
                "skill_extraction_version": "v1-narrative",
            },
        )
        doc_id = doc.id

    stub = _StubLlmClassifier(
        {
            "alice_resume.pdf": {
                "metadata": {
                    "name": "Alice Ng",
                    "skills": ["stripe", "fastapi"],  # union with existing
                }
            }
        }
    )

    from scripts import backfill_candidate_names

    with patch.object(backfill_candidate_names, "_build_classifier", return_value=stub):
        backfill_candidate_names.backfill(apply=True, snapshot_path=snapshot_path)

    with Session(sync_engine) as session:
        doc = session.get(Document, doc_id)
        # Original key preserved.
        assert doc.metadata_["skill_extraction_version"] == "v1-narrative"
        # Skills union (sorted): python (existing) + stripe + fastapi (new)
        assert set(doc.metadata_["skills"]) == {"python", "stripe", "fastapi"}
        # New key landed.
        assert doc.metadata_["name"] == "Alice Ng"
