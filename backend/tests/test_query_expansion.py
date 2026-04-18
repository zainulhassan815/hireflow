"""F88.b: acronym expansion helper unit tests.

Pure-function tests, no fixtures.
"""

from __future__ import annotations

from app.services.query_expansion import expand_acronyms, normalize_tech_tokens

# ---------- single-word swaps ----------


def test_expands_known_lowercase_acronym() -> None:
    assert expand_acronyms("k8s") == "kubernetes"


def test_expansion_is_case_insensitive_on_lookup() -> None:
    assert expand_acronyms("K8s") == "kubernetes"
    assert expand_acronyms("JS") == "javascript"
    assert expand_acronyms("ML") == "machine learning"


def test_unknown_token_unchanged() -> None:
    assert expand_acronyms("python") == "python"
    assert expand_acronyms("zzz") == "zzz"


def test_empty_input_returns_empty() -> None:
    assert expand_acronyms("") == ""


# ---------- multi-token queries ----------


def test_mixed_query_swaps_only_acronyms() -> None:
    assert expand_acronyms("senior k8s engineer") == "senior kubernetes engineer"


def test_multiple_acronyms_in_one_query() -> None:
    assert (
        expand_acronyms("k8s ml engineer with aws")
        == "kubernetes machine learning engineer with amazon web services"
    )


def test_only_acronyms() -> None:
    assert expand_acronyms("js ts") == "javascript typescript"


# ---------- F88.a syntax preserved ----------


def test_quoted_phrases_pass_through_untouched() -> None:
    """Don't expand inside quoted phrases — F88.a phrase semantics must hold."""
    # "ml" inside a phrase stays literal so the phrase still matches.
    assert expand_acronyms('"ml engineer"') == '"ml engineer"'


def test_negation_token_preserved() -> None:
    """The leading `-` for F88.a negation isn't part of the token; word still expands."""
    # The dash itself is not a word char in our token regex; the word
    # after it expands as normal. websearch_to_tsquery still parses
    # the leading `-` as negation.
    assert expand_acronyms("python -js") == "python -javascript"


def test_or_operator_preserved() -> None:
    assert expand_acronyms("k8s OR docker") == "kubernetes OR docker"


# ---------- ambiguous abbreviations intentionally absent ----------


def test_ambiguous_cv_not_expanded() -> None:
    """`cv` is curriculum vitae *or* computer vision — no expansion."""
    assert expand_acronyms("cv") == "cv"


def test_ambiguous_tf_not_expanded() -> None:
    """`tf` is terraform *or* tensorflow — no expansion."""
    assert expand_acronyms("tf engineer") == "tf engineer"


# ---------- F88.d normalize_tech_tokens ----------


def test_normalize_cpp() -> None:
    assert normalize_tech_tokens("C++ developer") == "cpp developer"
    assert normalize_tech_tokens("c++ skills") == "cpp skills"


def test_normalize_csharp_and_fsharp() -> None:
    assert normalize_tech_tokens("C# .NET Core") == "csharp dotnet Core"
    assert normalize_tech_tokens("F# enthusiast") == "fsharp enthusiast"


def test_normalize_dotnet_only_when_preceded_by_non_letter() -> None:
    """`.NET` after whitespace becomes dotnet; embedded `xnet` shouldn't."""
    assert normalize_tech_tokens("Senior .NET dev") == "Senior dotnet dev"
    # `bonnet` shouldn't be touched.
    assert normalize_tech_tokens("Wear a bonnet") == "Wear a bonnet"


def test_normalize_nodejs_and_objectivec() -> None:
    assert normalize_tech_tokens("Node.js backend") == "nodejs backend"
    assert normalize_tech_tokens("Objective-C iOS dev") == "objectivec iOS dev"


def test_normalize_combined() -> None:
    out = normalize_tech_tokens("Polyglot: C++, C#, F#, .NET, Node.js, Objective-C")
    assert "cpp" in out
    assert "csharp" in out
    assert "fsharp" in out
    assert "dotnet" in out
    assert "nodejs" in out
    assert "objectivec" in out


def test_normalize_idempotent_on_already_normalized() -> None:
    """Running twice must give the same answer."""
    once = normalize_tech_tokens("C++ Node.js")
    twice = normalize_tech_tokens(once)
    assert once == twice


def test_normalize_empty() -> None:
    assert normalize_tech_tokens("") == ""
