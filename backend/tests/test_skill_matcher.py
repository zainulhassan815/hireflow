"""Unit tests for ``app.services.skill_matcher``.

The matcher is the single source of truth for "does this text contain
known skill X?". Used by both the query parser (F89.a) and the
rule-based classifier (F103.b). False positives here would inflate
``Candidate.skills`` corpus-wide; false negatives would re-introduce the
narrative-extraction gap F103.b is closing.
"""

from __future__ import annotations

from app.services.skill_matcher import extract_skills, find_skill


class TestFindSkill:
    def test_matches_at_word_boundary(self) -> None:
        assert find_skill("i love python a lot", "python") == (7, 13)

    def test_no_match(self) -> None:
        assert find_skill("nothing relevant here", "python") is None

    def test_left_alphanumeric_blocks_match(self) -> None:
        # "python" inside "cpython" — left side is alphanumeric.
        assert find_skill("cpython is great", "python") is None

    def test_right_alphanumeric_blocks_match(self) -> None:
        # "react" inside "reactor" — right side is alphanumeric.
        assert find_skill("the reactor design", "react") is None
        # "react" inside "reactivity" — right side is alphanumeric.
        assert find_skill("reactivity matters", "react") is None
        # "vue" inside "vues" — right side is alphanumeric.
        assert find_skill("two vues in mvc", "vue") is None

    def test_special_chars_match_standalone(self) -> None:
        assert find_skill("c++ developer", "c++") == (0, 3)
        assert find_skill("worked with .net", ".net") == (12, 16)
        assert find_skill("node.js backend", "node.js") == (0, 7)
        assert find_skill("c# enthusiast", "c#") == (0, 2)

    def test_special_chars_blocked_when_glued(self) -> None:
        # "c++" inside "abc++def" — boundary check fails on both sides.
        assert find_skill("abc++def", "c++") is None

    def test_punctuation_is_a_boundary(self) -> None:
        assert find_skill("python, java, rust", "python") == (0, 6)
        assert find_skill("(python)", "python") == (1, 7)


class TestExtractSkills:
    def test_returns_sorted_unique(self) -> None:
        text = "Python and python and PYTHON; also java"
        assert extract_skills(text) == ["java", "python"]

    def test_finds_skills_in_narrative(self) -> None:
        text = (
            "Built a Stripe checkout integration handling $2M/mo in payments. "
            "Migrated the data warehouse from Redshift to Snowflake. "
            "Owned the FastAPI service powering the customer portal."
        )
        result = extract_skills(text)
        assert "stripe" in result
        assert "snowflake" in result
        assert "fastapi" in result

    def test_special_char_skills(self) -> None:
        text = "Stack: c++, c#, node.js, .net"
        result = extract_skills(text)
        assert "c++" in result
        assert "c#" in result
        assert "node.js" in result
        assert ".net" in result

    def test_longest_first_claim_prevents_substring_double_count(self) -> None:
        # "machine learning" is in the vocab; "learning" is not. This
        # test guards against a future addition of "learning" causing
        # a double-claim regression.
        text = "experienced in machine learning frameworks"
        result = extract_skills(text)
        assert "machine learning" in result

    def test_does_not_match_substrings_inside_other_words(self) -> None:
        # "react" must not match "reactor"; "vue" must not match "vues".
        text = "studying nuclear reactors and three vues of mvc"
        result = extract_skills(text)
        assert "react" not in result
        assert "vue" not in result

    def test_empty_text(self) -> None:
        assert extract_skills("") == []

    def test_no_known_skills(self) -> None:
        assert extract_skills("the quick brown fox jumps") == []

    def test_case_insensitive(self) -> None:
        assert extract_skills("PYTHON") == ["python"]
        assert extract_skills("Postgres and MongoDB") == ["mongodb", "postgres"]
