import pytest

from llm_gateway.catalog import Catalog
from llm_gateway.routing.policy import ModelPolicy, validate_patterns


@pytest.mark.parametrize(
    ("org", "team", "expected"),
    [
        (None, None, (True, True)),
        (("groq/*",), None, (True, False)),
        (None, ("deepseek/*",), (False, True)),
        (("groq/*",), ("groq/*", "deepseek/*"), (True, False)),
        (("groq/*",), ("deepseek/*",), (False, False)),
        ((), None, (False, False)),
        (None, (), (False, False)),
    ],
)
def test_effective_policy_is_intersection(
    org: tuple[str, ...] | None, team: tuple[str, ...] | None, expected: tuple[bool, bool]
) -> None:
    policy = ModelPolicy(org, team)

    assert (policy.allows("groq/model"), policy.allows("deepseek/model")) == expected


@pytest.mark.parametrize("pattern", ["grok/*", "groq/missing", "*", "groq/mod*", "fast", "groq/"])
def test_patterns_must_match_catalogue(pattern: str, test_catalog: Catalog) -> None:
    with pytest.raises(ValueError, match="must match a catalogued model"):
        validate_patterns([pattern], test_catalog)


@pytest.mark.parametrize("pattern", ["groq/*", "groq/openai/gpt-oss-20b"])
def test_exact_and_provider_wildcard_are_valid(pattern: str, test_catalog: Catalog) -> None:
    assert validate_patterns([pattern, pattern], test_catalog) == (pattern,)
