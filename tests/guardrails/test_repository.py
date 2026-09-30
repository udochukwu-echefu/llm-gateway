from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from llm_gateway.admin.cli import execute, parser
from llm_gateway.audit.chain import first_broken
from llm_gateway.audit.models import AuditEvent
from llm_gateway.guardrails.repository import GuardrailRepository
from llm_gateway.tenants.keys import issue_key
from llm_gateway.tenants.repository import PostgresKeyRepository
from tests.conftest import TEST_PEPPER
from tests.tenants.support import unique_name

pytestmark = pytest.mark.db


async def test_cli_policies_are_audited_and_loaded_with_key(
    repository: PostgresKeyRepository,
) -> None:
    org = await repository.create_org(unique_name("guardrails"))
    team = await repository.create_team(org.name, "team")
    issued = issue_key(TEST_PEPPER.encode())
    await repository.create_key(org.name, team.name, "fake", issued.key_id, issued.secret_hash)

    async def command(*args: str) -> str:
        return await execute(parser().parse_args(args), repository, TEST_PEPPER.encode())

    await command("set-guardrails", org.name, "--action", "email=block")
    await command("set-guardrails", org.name, "--team", "team", "--action", "email=allow")
    await command("set-residency", org.name, "--allow-region", "us", "--allow-region", "eu")
    await command(
        "set-residency", org.name, "--team", "team", "--allow-region", "eu", "--allow-region", "cn"
    )
    shown = await command("show-guardrails", org.name, "--team", "team")
    record = await repository.get_key(issued.key_id)

    assert record is not None
    assert record.guardrails.action("email") == "block"
    assert record.policy.regions == ("eu",)
    assert "email: block" in shown
    assert "Allowed regions: eu" in shown
    for name in ("clear-guardrails", "clear-residency"):
        await command(name, org.name, "--team", "team")
        await command(name, org.name)
    cleared = await repository.get_key(issued.key_id)
    assert cleared is not None
    assert cleared.guardrails.action("email") == "allow"
    assert len(cleared.policy.regions) == 6
    async with repository.sessions() as session:
        events = list((await session.scalars(select(AuditEvent).order_by(AuditEvent.id))).all())
    assert first_broken(events) is None
    changes = [
        e
        for e in events
        if e.target_id in {str(org.id), str(team.id)}
        and e.action.endswith(("guardrails", "residency"))
    ]
    assert len(changes) == 8
    assert changes[0].details == {"actions": "email=block"}


@pytest.mark.parametrize("residency", [True, False])
async def test_policy_and_audit_roll_back_together(
    repository: PostgresKeyRepository, monkeypatch: pytest.MonkeyPatch, residency: bool
) -> None:
    org = await repository.create_org(unique_name("rollback"))
    policies = GuardrailRepository(repository.sessions, repository.actor)
    monkeypatch.setattr(
        "llm_gateway.guardrails.repository.append_event",
        AsyncMock(side_effect=RuntimeError("audit failed")),
    )

    with pytest.raises(RuntimeError, match="audit failed"):
        await policies.set_policy(
            org.name, None, residency=residency, values=["us"] if residency else ["email=block"]
        )

    guardrails, policy = await policies.get_policy(org.name, None)
    assert guardrails.action("email") == "allow"
    assert len(policy.regions) == 6


@pytest.mark.parametrize(
    ("residency", "values"),
    [(True, ["moon"]), (False, ["email=ignore"]), (False, ["madeup=block"])],
)
async def test_invalid_policy_never_mutates(
    repository: PostgresKeyRepository, residency: bool, values: list[str]
) -> None:
    org = await repository.create_org(unique_name("invalid"))
    policies = GuardrailRepository(repository.sessions, repository.actor)

    with pytest.raises(ValueError, match="must be"):
        await policies.set_policy(org.name, None, residency=residency, values=values)

    async with repository.sessions() as session:
        actions = list(
            (
                await session.scalars(
                    select(AuditEvent.action).where(AuditEvent.target_id == str(org.id))
                )
            ).all()
        )
    assert actions == ["create-org"]
