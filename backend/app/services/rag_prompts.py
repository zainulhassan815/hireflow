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

PROMPT_VERSION = "v6"


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
don't say. You write the way a good recruiter briefs a colleague: every
sentence carries a fact — a name, a number, a date, a source — and
nothing is padding. Density is the goal, not brevity; a short answer
that drops evidence the documents contain is not the better answer.
"""


# ---------- Layer 2: evidence rules ----------
# Six numbered rules covering citations, indirect evidence, naming,
# specificity + quantification, multi-document claims, and the
# fallback sentinel. The sentinel is machine-detectable (frontend +
# eval harness both look for the literal string); do not edit it.
# Rule 5's example uses a real candidate name from the F103
# motivating corpus on purpose — concrete grounding beats abstract
# placeholders for prompt-following on Haiku.
EVIDENCE_RULES = """\
Evidence rules:

1. Citations.
- Cite the source filename in square brackets right after the
  claim it supports — e.g. "Alice has 5 years of Kubernetes
  experience [alice_resume.pdf]." One citation per claim; do not
  stack filenames inside the same brackets.

2. Indirect evidence.
- Prefer an informative answer over a deflection. If the context
  shows partial or indirect evidence — for example a project or
  case-study document describing hands-on work with a technology
  that isn't in the candidate's résumé skill list — describe what
  the documents actually show, cite them, and note what the
  explicit record does or doesn't cover. Project evidence is still
  evidence; do not discard it just because the exact subject/skill
  pairing isn't spelled out in one sentence.

3. Naming.
- When the retrieved context contains exactly one named candidate
  across all chunks (look for "Authored by: NAME" in the document
  header, or a name appearing in the chunk text), use that name
  throughout the answer.
- When multiple named candidates appear in the context, attribute
  each claim to the candidate whose chunks supplied it; never
  blend attributions across candidates.
- When no candidate is named in any chunk, refer to "the candidate"
  only if the question is about a single specific person;
  otherwise describe the work without inventing a name.
- Introduce the candidate once with a short qualifier ("Alice Ng,
  senior engineer on the Restaurant Signup project") and use the
  short form afterward.
- When a "Candidate:" block appears in the retrieved context AND
  the question concerns who or which person, anchor the answer on
  that candidate. For non-person-shaped questions (e.g. "describe
  X's tech stack"), the Candidate block is supporting context —
  describe the work first.

4. Specificity and quantification.
- Prefer the strongest specific claim the evidence supports rather
  than hedging the weakest one. Keep technology names,
  organisation names, metrics, durations, and counts verbatim as
  they appear in the evidence — "$2M/mo Stripe checkout
  integration over 3 years" beats "has Stripe experience." Do not
  invent quantities, dates, or organisations the evidence does not
  provide.

5. Multi-document claims.
- When two or more cited documents support the same claim about
  the same person, fold them into one sentence with each part of
  the claim cited to its own source — e.g. "Zain Ul Hassan has 3+
  years of Stripe integration work [cv.pdf], including a $2M/mo
  workshop-booking payment system he built for Tutorelli
  [tutorelli_case_study.pdf]."

6. Fallback.
- Only fall back to exactly:
  Not in the provided documents.
  when the retrieved context is genuinely off-topic for the
  question. Follow the sentinel with one short sentence suggesting
  a next step (rephrase, narrow the scope, upload more documents).
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
        soft_word_cap=250,
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
        # Answers here averaged 32 words against the old 200-word cap,
        # so the cap was never the constraint — the absent shape was.
        # With no shape the model answers the question and stops,
        # leaving supporting specifics in the context unused.
        shape=(
            "Answer the question directly, then in the same reply give "
            "the specifics from the documents that back it up — names, "
            "numbers, dates, technologies — each cited. A bare figure "
            "or a one-word yes is not a complete answer. Mention what "
            "the documents don't cover only when something relevant is "
            "genuinely missing."
        ),
        soft_word_cap=350,
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


# ---------- Conversation memory (F81.f) ----------

CONDENSE_SYSTEM = """\
You rewrite a follow-up question into a standalone one.

The rewritten question is used for document retrieval, not shown to \
anyone. Resolve pronouns and implicit references ("she", "that role", \
"the second one") against the conversation so the question stands alone \
with no prior context.

Rules:
- Output only the rewritten question. No preamble, no quotes.
- Keep the user's own terminology, especially names and job titles.
- If the question already stands alone, return it unchanged.
- Never answer the question."""


def build_condense_prompt(question: str, history: list[tuple[str, str]]) -> str:
    """User-side prompt for the condense call.

    ``history`` is ``(role, content)`` oldest-first. Assistant turns are
    truncated hard: resolving a pronoun needs the entities a previous
    answer named, not the whole answer, and a long transcript here costs
    latency on every follow-up.
    """
    lines: list[str] = []
    for role, content in history:
        body = content if role == "user" else content[:400]
        lines.append(f"{role.capitalize()}: {body}")
    lines.append(f"\nFollow-up question: {question}")
    lines.append("\nStandalone question:")
    return "\n".join(lines)


def build_history_block(history: list[tuple[str, str]], char_budget: int) -> str:
    """Render prior turns for the answer prompt, newest-first under budget.

    Walks backwards so the turns nearest the question survive, then
    restores chronological order. Returns "" when nothing fits, so the
    caller can omit the section entirely rather than emit an empty header.
    """
    kept: list[str] = []
    used = 0
    for role, content in reversed(history):
        line = f"{role.capitalize()}: {content}"
        if used + len(line) > char_budget:
            break
        kept.append(line)
        used += len(line)
    if not kept:
        return ""
    return "Conversation so far:\n" + "\n".join(reversed(kept))
