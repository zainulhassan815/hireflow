"""F81.g — intent canonicals for the EmbeddingIntentClassifier.

This file is the product spec for RAG answer shapes. Each ``Intent``
literal has a small set of canonical queries; the classifier embeds
them once at startup and picks the best match per user query via
cosine similarity.

Editing guidance
----------------
- Canonicals are *paraphrases that a human would classify the same
  way*, not keywords. Aim for natural language, 5-10 per intent.
- When the eval harness (``tests/eval/test_intent_accuracy.py``) logs
  a misclassification, the fix is almost always to add the
  misclassified query (or a paraphrase of it) here — no code change.
- Keep intents distinguishable. If two intents' canonicals start
  looking interchangeable, the taxonomy is wrong, not the data.
"""

from __future__ import annotations

from typing import Literal

Intent = Literal[
    "count",
    "comparison",
    "ranking",
    "yes_no",
    "locate",
    "summary",
    "timeline",
    "extract",
    "skill_list",
    "list",
    "general",
]


CANONICALS: dict[Intent, tuple[str, ...]] = {
    "count": (
        "how many candidates have Kubernetes experience",
        "count of resumes mentioning Python",
        "number of senior engineers in the corpus",
        "how many years of experience does Alice have",
        "how many candidates meet the seniority bar",
        "what is the total count of resumes with AWS",
        "quantify the candidates with React experience",
    ),
    "comparison": (
        "compare Alice and Bob's skills",
        "what is the difference between these two candidates",
        "which is more experienced with Kubernetes, Alice or Bob",
        "Alice vs Bob years of backend experience",
        "side by side comparison of the case studies",
        "contrast React and Svelte usage across the projects",
    ),
    "ranking": (
        "which candidate is the strongest fit for a senior Python role",
        "rank these resumes by relevance",
        "top 3 candidates for a backend position",
        "best match for a frontend role",
        "who should we prioritize for this role",
        "order the candidates from most to least qualified",
    ),
    "yes_no": (
        "does Alice have AWS experience",
        "has anyone worked with Kafka",
        "is this candidate a good fit for the role",
        "do we have a candidate with 10+ years of experience",
        "does the restaurant project use TypeScript",
        "has Bob led a team before",
        "can any candidate handle distributed systems",
    ),
    "locate": (
        "where is Kubernetes mentioned",
        "which document talks about authentication",
        "in which resume does TypeScript appear",
        "which case study discusses payment processing",
        "which file has the deployment architecture",
    ),
    "summary": (
        "summarize Alice's career",
        "tell me about the restaurant signup project",
        "give me an overview of Bob's background",
        "brief description of the menu analyzer project",
        "what is the telemedicine document about",
        "executive summary of this resume",
    ),
    "timeline": (
        "chronological order of Alice's jobs",
        "when did each project happen",
        "timeline of the restaurant project milestones",
        "year-by-year breakdown of Bob's experience",
        "what was the sequence of technical decisions",
    ),
    "extract": (
        "extract all email addresses from the resumes",
        "pull out phone numbers from these documents",
        "get every candidate's email address",
        "list all URLs referenced in the documents",
        "extract the LinkedIn profiles",
    ),
    "skill_list": (
        "what skills does Alice have",
        "tech stack of the restaurant project",
        "technologies used by Bob",
        "what programming languages does this candidate know",
        "which frameworks are mentioned in the resume",
        "tools and platforms in Alice's skillset",
    ),
    "list": (
        "list the frontend libraries used",
        "what technologies are used in the project",
        "enumerate the deployment options mentioned",
        "list the open source tools referenced",
        "what databases are discussed",
        "give me all the APIs mentioned",
    ),
    # ``general`` has no canonicals — it's the below-threshold fallback
    # when no other intent matches strongly enough.
    "general": (),
}
