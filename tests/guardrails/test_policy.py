import pytest

from llm_gateway.guardrails.policy import ACTIONS, DEFAULTS, Action, GuardrailPolicy, Region
from llm_gateway.routing.policy import ModelPolicy


@pytest.mark.parametrize("org", ACTIONS)
@pytest.mark.parametrize("team", ACTIONS)
def test_team_cannot_loosen_organization(org: Action, team: Action) -> None:
    policy = GuardrailPolicy((("email", org),), (("email", team),))

    assert policy.action("email") == max(org, team, key=ACTIONS.index)


def test_defaults_cannot_be_loosened() -> None:
    policy = GuardrailPolicy(tuple((name, "allow") for name in DEFAULTS))

    assert all(policy.action(name) == action for name, action in DEFAULTS.items())


@pytest.mark.parametrize(
    ("org", "team", "expected"),
    [
        (None, None, ("us", "eu", "cn", "sg", "global", "unknown")),
        (("us", "eu"), None, ("us", "eu")),
        (None, ("eu",), ("eu",)),
        (("us", "eu"), ("eu", "cn"), ("eu",)),
        (("us",), ("eu",), ()),
        ((), None, ()),
        (("sg",), ("sg", "eu"), ("sg",)),
    ],
)
def test_residency_is_intersection(
    org: tuple[Region, ...] | None, team: tuple[Region, ...] | None, expected: tuple[Region, ...]
) -> None:
    policy = ModelPolicy(organization_regions=org, team_regions=team)

    assert policy.regions == expected
