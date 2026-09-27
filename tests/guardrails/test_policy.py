import pytest

from llm_gateway.guardrails.policy import ACTIONS, DEFAULTS, Action, GuardrailPolicy


@pytest.mark.parametrize("org", ACTIONS)
@pytest.mark.parametrize("team", ACTIONS)
def test_team_cannot_loosen_organization(org: Action, team: Action) -> None:
    policy = GuardrailPolicy((("email", org),), (("email", team),))

    assert policy.action("email") == max(org, team, key=ACTIONS.index)


def test_defaults_cannot_be_loosened() -> None:
    policy = GuardrailPolicy(tuple((name, "allow") for name in DEFAULTS))

    assert all(policy.action(name) == action for name, action in DEFAULTS.items())
