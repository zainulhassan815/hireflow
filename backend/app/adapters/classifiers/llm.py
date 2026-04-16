"""LLM-powered document classifier.

Sends extracted text to Claude or Ollama for classification and structured
metadata extraction. More accurate than rule-based on ambiguous documents
and extracts richer metadata from resumes.
"""

from __future__ import annotations

import json
import logging
import re

from app.adapters.protocols import ClassificationResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a document classifier for an HR document management system.
Analyze the provided text and return a JSON object with exactly these fields:

{
  "document_type": "resume" | "report" | "contract" | "letter" | "other",
  "confidence": 0.0 to 1.0,
  "metadata": {
    // For resumes, include as many as detectable:
    "skills": ["skill1", "skill2"],
    "experience_years": 5,
    "education": ["Bachelor's in Computer Science"],
    "job_titles": ["Software Engineer", "Tech Lead"],
    "emails": ["user@example.com"],
    "phones": ["+1234567890"],
    "name": "Full Name",
    "summary": "Brief 1-2 sentence professional summary"
    // For other document types, include relevant key-value pairs
  }
}

Return ONLY valid JSON, no markdown fences, no commentary."""


class LlmClassifier:
    """Uses a text-capable LLM (Claude or Ollama) for classification.

    Accepts a callable that takes a prompt string and returns a response
    string. This decouples the classifier from any specific LLM client.
    """

    def __init__(self, llm_call: LlmCallable) -> None:
        self._llm_call = llm_call

    def classify(self, text: str, filename: str) -> ClassificationResult:
        truncated = text[:8000] if len(text) > 8000 else text
        user_prompt = f"Filename: {filename}\n\nDocument text:\n{truncated}"

        try:
            response = self._llm_call(_SYSTEM_PROMPT, user_prompt)
            return _parse_llm_response(response)
        except Exception:
            logger.exception("LLM classification failed, returning fallback")
            return ClassificationResult(
                document_type="other",
                confidence=0.0,
                metadata={},
            )


def _parse_llm_response(response: str) -> ClassificationResult:
    """Parse the LLM's JSON response, tolerating markdown fences."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip())

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("LLM returned invalid JSON: %s", response[:200])
        return ClassificationResult(document_type="other", confidence=0.0, metadata={})

    valid_types = {"resume", "report", "contract", "letter", "other"}
    doc_type = data.get("document_type", "other")
    if doc_type not in valid_types:
        doc_type = "other"

    confidence = float(data.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))

    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    return ClassificationResult(
        document_type=doc_type,
        confidence=confidence,
        metadata=metadata,
    )


# Type alias for the LLM invocation callable
type LlmCallable = callable[[str, str], str]


def create_claude_llm_call(api_key: str, model: str) -> LlmCallable:
    """Create a callable that sends prompts to Claude."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    def call(system: str, user: str) -> str:
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text

    return call


def create_ollama_llm_call(base_url: str, model: str) -> LlmCallable:
    """Create a callable that sends prompts to Ollama."""
    import urllib.request

    url = f"{base_url.rstrip('/')}/api/generate"

    def call(system: str, user: str) -> str:
        payload = json.dumps(
            {
                "model": model,
                "system": system,
                "prompt": user,
                "stream": False,
            }
        ).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read())
        return body.get("response", "")

    return call
