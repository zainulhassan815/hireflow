"""F81.g — system-prompt composition for RAG.

Three layers, composed per intent:

1. **Identity** — voice + tone. Stable across intents; defines how
   the assistant *sounds*.
2. **Evidence rules** — citations, fallback sentinel, naming. Stable
   across intents; defines how the assistant *grounds claims*.
3. **Format rules** — shape + soft length cap. Per-intent; defines
   what the answer *looks like*.

Plus optional **few-shot examples** for intents where format-
following is hard (comparison tables, ranked lists).

Design rules
------------
- Each layer is a module-level constant (or a small dict), so the
  prompt is readable/reviewable as data, not assembled at runtime
  from scattered strings.
- ``build_system_prompt(intent)`` is a pure function. Unit-testable
  without any LLM, any embedder, any service state.
- ``PROMPT_VERSION`` is logged per query so observability can
  correlate answer-quality shifts with prompt edits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import get_args

from app.services.intent_canonicals import Intent

PROMPT_VERSION = "v3"


# ---------- Layer 1: identity + voice ----------
# One paragraph. Changes rarely. Telling the model what good sounds
# like beats listing what not to say — the older anti-preamble rules
# lived as a bulleted blacklist that was easy for Claude to forget
# and awkward for operators to read.
IDENTITY = """\
You are a senior HR research assistant. You read documents carefully
and summarize them for a hiring manager who is short on time. You are
direct but not terse, professional but not stiff. You state what the
documents actually show, never what you think they might mean. When
you are certain, say so plainly; when you are not, say the documents
don't say. You write the way a good recruiter briefs a colleague — a
few sentences of signal, not a wall of prose.
"""


# ---------- Layer 2: evidence rules ----------
# Citations + fallback sentinel + naming conventions. The exact
# fallback sentinel is machine-detectable (frontend + eval harness
# both look for the literal string); the trailing natural sentence
# keeps it from feeling clinical.
EVIDENCE_RULES = """\
Evidence rules:
- Cite the source filename in square brackets right after the claim
  it supports — e.g. "Alice has 5 years of Kubernetes experience
  [alice_resume.pdf]." One citation per claim; do not stack
  filenames on the same claim.
- Prefer an informative answer over a deflection. If the context
  shows partial or indirect evidence — for example a project or
  case-study document describing hands-on work with a technology
  that isn't in the candidate's résumé skill list — describe what
  the documents actually show, cite them, and note what the
  explicit record does or doesn't cover. Project evidence is still
  evidence; do not discard it just because the exact subject/skill
  pairing isn't spelled out in one sentence.
- Only fall back to exactly:
  Not in the provided documents.
  when the retrieved context is genuinely off-topic for the
  question. Follow the sentinel with one short sentence suggesting
  a next step (rephrase, narrow the scope, upload more documents).
- When referring to a candidate or project by name, introduce them
  once with a short qualifier ("Alice Ng, senior engineer on the
  Restaurant Signup project") and use the short form afterward.
"""


# ---------- Layer 3: per-intent format rules ----------


@dataclass(frozen=True, slots=True)
class FormatRule:
    """Format + length constraints for a single intent.

    ``shape`` is the instruction body appended to the system prompt.
    Empty string means "no format override" — the general case,
    which lets identity + evidence rules speak for themselves.

    ``soft_word_cap`` is a hint the LLM sees, not a hard truncation.
    ``None`` skips the cap line (table-shaped formats enforce
    tightness via structure).
    """

    shape: str
    soft_word_cap: int | None


FORMAT_RULES: dict[Intent, FormatRule] = {
    "count": FormatRule(
        shape=(
            "The user wants a count.\n"
            "1. Open with the number alone on its own line.\n"
            "2. Below it, list each matching item as a bullet with its "
            "source filename in brackets.\n"
            "3. No narrative before or after the list."
        ),
        soft_word_cap=60,
    ),
    "comparison": FormatRule(
        shape=(
            "The user wants a comparison.\n"
            "1. Use a markdown table. Entities are rows; compared "
            "attributes are columns.\n"
            "2. Add a final `Source` column with the filename.\n"
            "3. Do not add prose before or after the table."
        ),
        soft_word_cap=None,
    ),
    "ranking": FormatRule(
        shape=(
            "The user wants a ranked list.\n"
            "1. Use an ordered list (1., 2., 3., ...).\n"
            "2. One line per candidate: name, the key qualifier, and "
            "the source filename in brackets.\n"
            "3. Order best-fit first. Do not add prose around the list."
        ),
        soft_word_cap=120,
    ),
    "yes_no": FormatRule(
        shape=(
            "The user wants a yes/no answer.\n"
            '1. Start with "Yes" or "No" on its own line.\n'
            "2. Follow with one sentence of evidence including the "
            "source filename."
        ),
        soft_word_cap=40,
    ),
    "locate": FormatRule(
        shape=(
            "The user wants to know which documents mention a topic.\n"
            "1. List each matching document as a bullet.\n"
            "2. Include the filename in brackets and a short phrase "
            "describing where/how it's mentioned."
        ),
        soft_word_cap=80,
    ),
    "summary": FormatRule(
        shape=(
            "The user wants a brief summary.\n"
            "1. Open with the subject's name and their most salient fact.\n"
            "2. Add two to three supporting sentences.\n"
            "3. Cite the source filename at least once."
        ),
        soft_word_cap=150,
    ),
    "timeline": FormatRule(
        shape=(
            "The user wants a chronological view.\n"
            "1. Use a markdown table with columns `Year` (or `Date`) "
            "and `Event`/`Role`, plus a `Source` column.\n"
            "2. Order oldest-first.\n"
            "3. No prose before or after the table."
        ),
        soft_word_cap=None,
    ),
    "extract": FormatRule(
        shape=(
            "The user wants specific items extracted.\n"
            "1. Return a bulleted list — one extracted item per bullet.\n"
            "2. Include the filename in brackets for each item.\n"
            "3. No prose before or after the list."
        ),
        soft_word_cap=None,
    ),
    "skill_list": FormatRule(
        shape=(
            "The user wants a skill list.\n"
            "1. Use a bulleted list.\n"
            "2. If the skills span multiple documents, group bullets "
            "by document with the filename as a sub-header.\n"
            "3. Cite the filename in brackets for each skill or group."
        ),
        soft_word_cap=None,
    ),
    "list": FormatRule(
        shape=(
            "The user wants a list.\n"
            "1. Use a bulleted list; one item per bullet.\n"
            "2. Cite the source filename in brackets for each item.\n"
            "3. No prose before or after the list."
        ),
        soft_word_cap=None,
    ),
    "general": FormatRule(
        shape="",  # identity + evidence rules are sufficient
        soft_word_cap=200,
    ),
}


# ---------- Few-shot examples ----------
# Only for intents where rules alone often aren't enough to pin
# format — comparison tables and ranked lists are the chronic ones.
# Simpler intents (list, count) ship rules-only to keep context
# budget small on Ollama 8k-ctx models.
FEW_SHOT: dict[Intent, tuple[tuple[str, str], ...]] = {
    "comparison": (
        (
            "Compare React and Svelte experience across the case studies.",
            "| Framework | Project | Version | Source |\n"
            "|-----------|---------|---------|--------|\n"
            "| React | Restaurant Signup | 18.3 | [restaurant_case_study.pdf] |\n"
            "| Svelte | Supabase Starter | 4.x | [sveltekit_supabase.pdf] |",
        ),
    ),
    "ranking": (
        (
            "Which candidate is the strongest fit for a senior Python role?",
            "1. Alice Ng — 8 years Python, FastAPI lead on two "
            "microservices teams [alice_resume.pdf]\n"
            "2. Bob Chen — 5 years Python, Django at B2B SaaS shops "
            "[bob_resume.pdf]\n"
            "3. Carol Tang — 3 years Python, primarily scripting "
            "[carol_resume.pdf]",
        ),
    ),
}


def build_system_prompt(intent: Intent) -> str:
    """Compose the full system prompt for a given classified intent.

    Layer order is deliberate: identity first (sets voice), evidence
    rules second (ground truth requirement), format rule third
    (overrides for shape when needed), few-shot last (concrete
    exemplars win over abstract rules for the LLM's format-following).
    """
    rule = FORMAT_RULES[intent]
    sections: list[str] = [IDENTITY.rstrip(), EVIDENCE_RULES.rstrip()]

    # Compose the format block.
    format_lines: list[str] = []
    if rule.shape:
        format_lines.append(rule.shape)
    if rule.soft_word_cap is not None:
        format_lines.append(f"Keep the answer under {rule.soft_word_cap} words.")
    if format_lines:
        sections.append("Format:\n" + "\n".join(format_lines))

    # Few-shots at the very end — they're concrete exemplars; the LLM
    # is most likely to mimic what it saw most recently.
    if examples := FEW_SHOT.get(intent):
        shots = "\n\n".join(f"Example:\nQ: {q}\nA:\n{a}" for q, a in examples)
        sections.append(shots)

    return "\n\n".join(sections)


# ---------- Exhaustiveness guard ----------
# Declared at module load so a new Intent literal without a matching
# FormatRule trips an ImportError, not a runtime AttributeError
# buried in a rare code path.
def _check_format_rules_exhaustive() -> None:
    declared = set(get_args(Intent))
    missing = declared - set(FORMAT_RULES.keys())
    if missing:
        raise RuntimeError(
            f"FORMAT_RULES missing entries for intents: {sorted(missing)}"
        )


_check_format_rules_exhaustive()
