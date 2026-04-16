"""Composite classifier: rule-based first, LLM fallback on low confidence."""

from __future__ import annotations

import logging

from app.adapters.protocols import ClassificationResult, DocumentClassifier

logger = logging.getLogger(__name__)

_CONFIDENCE_THRESHOLD = 0.4


class CompositeClassifier:
    """Try rule-based classification first. If confidence is below the
    threshold, delegate to the LLM classifier for a second opinion.

    When the LLM is unavailable or errors, the rule-based result is kept.
    """

    def __init__(
        self,
        primary: DocumentClassifier,
        fallback: DocumentClassifier,
        *,
        threshold: float = _CONFIDENCE_THRESHOLD,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._threshold = threshold

    def classify(self, text: str, filename: str) -> ClassificationResult:
        result = self._primary.classify(text, filename)

        if result.confidence >= self._threshold:
            logger.info(
                "rule-based classified as %s (%.2f)",
                result.document_type,
                result.confidence,
            )
            return result

        logger.info(
            "rule-based confidence %.2f below threshold, trying LLM",
            result.confidence,
        )
        fallback_result = self._fallback.classify(text, filename)

        if fallback_result.confidence > result.confidence:
            logger.info(
                "LLM classified as %s (%.2f)",
                fallback_result.document_type,
                fallback_result.confidence,
            )
            return fallback_result

        return result
