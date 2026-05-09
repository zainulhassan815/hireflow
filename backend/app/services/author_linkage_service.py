"""F103.c — link non-resume documents back to the candidate who wrote them.

The schema knows how to point from a candidate at their resume
(``Candidate.source_document_id``) but had no way to point from a
portfolio / case-study / contract back at its author until F103.c
added ``Document.authored_by_id``. This service is the inference
layer that fills the new column.

Two entry points:

- ``handle_document_ready(doc)`` runs at ingestion time, beside
  ``SyncCandidateService`` in the worker's ``_on_ready`` chain.
  Looks at the emails the classifier extracted; if any matches a
  ``Candidate`` owned by the same user, sets the FK.

- ``backfill_for_candidate(candidate)`` runs from
  ``SyncCandidateService`` after a candidate is created or its email
  changes. Scans the owner's unlinked documents whose
  ``metadata.emails`` mention this candidate's email and sets the FK.
  Solves the "portfolio uploaded before resume" ordering case.

Contract: never raises (mirrors ``SyncCandidateService``); never
overwrites an existing ``authored_by_id``; owner-scoped (an HR user
can only auto-link docs to candidates from their own pool).

Follow-ups parked for future slices: manual override endpoint,
``authored_by_source`` ENUM column for "manual vs inferred",
``--force`` re-link in the backfill script.
"""

from __future__ import annotations

import logging

from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session
from sqlalchemy.types import Text

from app.models import AuthorSource, Candidate, Document

logger = logging.getLogger(__name__)


class AuthorLinkageService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def handle_document_ready(self, document: Document) -> None:
        """Worker-side hook. Mirrors ``SyncCandidateService`` — never
        raises; a linkage failure must not roll back extraction."""
        try:
            self._link_if_match(document)
        except Exception:
            logger.exception("author linkage failed for document %s", document.id)

    def _link_if_match(self, document: Document) -> None:
        # F103.c.2 — never overwrite an operator-set link. The
        # ``authored_by_id is not None`` guard already covers
        # operator-set FKs (since they're non-null) but checking
        # the source explicitly is belt-and-suspenders against the
        # rare dangling-source case (candidate deleted via
        # ON DELETE SET NULL leaves the source 'manual' on a doc
        # whose FK is now NULL).
        if document.authored_by_id is not None:
            return
        if document.authored_by_source == AuthorSource.MANUAL:
            return
        emails = (document.metadata_ or {}).get("emails") or []
        # ``RuleBasedClassifier`` lowercases at extraction (F103.c).
        # Defend against pre-lowercase data still in transit by
        # normalising again here — cheap and idempotent.
        normalised = sorted({e.strip().lower() for e in emails if isinstance(e, str)})
        if not normalised:
            return

        candidates = (
            self._session.execute(
                select(Candidate).where(
                    Candidate.owner_id == document.owner_id,
                    func.lower(Candidate.email).in_(normalised),
                )
            )
            .scalars()
            .all()
        )
        if not candidates:
            return

        if len(candidates) > 1:
            # Rare in practice — would mean two candidates of the same
            # HR user both list emails that appear in this one doc.
            # First match wins; surface a warning so an operator can
            # audit if it shows up in real corpora.
            logger.warning(
                "doc %s: multiple candidates (%d) matched emails=%s; linking to %s",
                document.id,
                len(candidates),
                normalised,
                candidates[0].id,
            )

        # F103.c.2 — stamp source so future backfills + the F103.c.2
        # PATCH route can distinguish inferred from operator-set.
        document.authored_by_id = candidates[0].id
        document.authored_by_source = AuthorSource.EMAIL_MATCH
        self._session.commit()
        logger.info(
            "linked document %s → candidate %s via email match",
            document.id,
            candidates[0].id,
        )

    def backfill_for_candidate(self, candidate: Candidate) -> int:
        """Link any prior unlinked docs that mention this candidate's
        email. Called from ``SyncCandidateService`` after the candidate
        write commits. Returns count linked.

        No GIN index on ``metadata`` exists today, so the SQL prefilter
        is substring-style (``::text LIKE '%email%'``) and the exact
        membership check happens in Python. Fine on dev corpus sizes;
        revisit with a JSONB GIN index when an owner's unlinked-doc
        count exceeds ~5k.
        """
        if not candidate.email:
            return 0
        target = candidate.email.lower()
        candidates_text = (
            self._session.execute(
                select(Document).where(
                    Document.owner_id == candidate.owner_id,
                    Document.authored_by_id.is_(None),
                    cast(Document.metadata_["emails"], Text).ilike(f"%{target}%"),
                )
            )
            .scalars()
            .all()
        )

        linked = 0
        for doc in candidates_text:
            # F103.c.2 — defensive skip for manual links. The SQL
            # filter already excludes ``authored_by_id IS NOT NULL``,
            # so this only matters for the rare dangling-source case
            # (FK NULL after candidate deletion, source still
            # 'manual'). Keep the operator's intent intact.
            if doc.authored_by_source == AuthorSource.MANUAL:
                continue
            doc_emails = (doc.metadata_ or {}).get("emails") or []
            # Exact element membership — the SQL prefilter can match a
            # substring like "john@example.com" inside
            # "johndoe@example.com" if both sit in the same array.
            if target in {e.lower() for e in doc_emails if isinstance(e, str)}:
                doc.authored_by_id = candidate.id
                doc.authored_by_source = AuthorSource.EMAIL_MATCH
                linked += 1

        if linked:
            self._session.commit()
            logger.info(
                "backfill linked %d docs to candidate %s via email %s",
                linked,
                candidate.id,
                target,
            )
        return linked


__all__ = ["AuthorLinkageService"]
