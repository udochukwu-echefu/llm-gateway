from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.admin import execute, parser
from llm_gateway.audit.chain import first_broken
from llm_gateway.audit.models import AuditEvent
from llm_gateway.catalog import load_catalog
from llm_gateway.routing.repository import PolicyRepository
from llm_gateway.tenants.keys import issue_key
from llm_gateway.tenants.repository import PostgresKeyRepository
from tests.conftest import TEST_PEPPER
from tests.tenants.support import unique_name

pytestmark = pytest.mark.db


@pytest.fixture
async def repository(migrated_database: str) -> AsyncIterator[PostgresKeyRepository]:
    engine = create_async_engine(migrated_database)
    try:
        yield PostgresKeyRepository(async_sessionmaker(engine, expire_on_commit=False))
    finally:
        await engine.dispose()


async def test_cli_set_clear_show_and_audit(repository: PostgresKeyRepository) -> None:
    org = await repository.create_org(unique_name("policy"))
    team = await repository.create_team(org.name, "team")
    issued = issue_key(TEST_PEPPER.encode())
    await repository.create_key(org.name, team.name, "test", issued.key_id, issued.secret_hash)

    async def command(*args: str) -> str:
        return await execute(parser().parse_args(args), repository, TEST_PEPPER.encode())

    await command("set-models", org.name, "--allow", "groq/*")
    output = await command("set-models", org.name, "--team", team.name, "--allow", "deepseek/*")
    record = await repository.get_key(issued.key_id)
    shown = await command("show-models", org.name, "--team", team.name)

    assert record is not None
    assert record.policy.organization == ("groq/*",)
    assert record.policy.team == ("deepseek/*",)
    assert not record.policy.allows("deepseek/deepseek-flash")
    assert "Effective models     none" in output
    assert shown == output
    assert "cache TTL" in output

    await command("clear-models", org.name, "--team", team.name)
    inherited = await repository.get_key(issued.key_id)
    assert inherited is not None
    assert inherited.policy.team is None
    assert inherited.policy.allows("groq/openai/gpt-oss-20b")
    await command("clear-models", org.name)
    cleared = await repository.get_key(issued.key_id)
    assert cleared is not None
    assert cleared.policy.organization is None
    async with repository.sessions() as session:
        events = list((await session.scalars(select(AuditEvent).order_by(AuditEvent.id))).all())
    assert first_broken(events) is None
    mutations = [
        event
        for event in events
        if event.target_id in {str(org.id), str(team.id)} and event.action.endswith("models")
    ]
    assert [event.action for event in mutations] == [
        "set-models",
        "set-models",
        "clear-models",
        "clear-models",
    ]
    assert mutations[0].details == {"allow": "groq/*"}


async def test_policy_change_rolls_back_when_audit_fails(
    repository: PostgresKeyRepository, monkeypatch: pytest.MonkeyPatch
) -> None:
    org = await repository.create_org(unique_name("rollback"))
    policies = PolicyRepository(repository.sessions, repository.actor)
    monkeypatch.setattr(
        "llm_gateway.routing.repository.append_event",
        AsyncMock(side_effect=RuntimeError("audit failed")),
    )

    with pytest.raises(RuntimeError, match="audit failed"):
        await policies.set_models(org.name, None, ["groq/*"], load_catalog())

    assert (await policies.get_models(org.name, None)).organization is None


async def test_invalid_pattern_does_not_mutate_or_audit(repository: PostgresKeyRepository) -> None:
    org = await repository.create_org(unique_name("invalid"))
    policies = PolicyRepository(repository.sessions, repository.actor)

    with pytest.raises(ValueError, match="must match"):
        await policies.set_models(org.name, None, ["grok/*"], load_catalog())

    assert (await policies.get_models(org.name, None)).organization is None
    async with repository.sessions() as session:
        actions = list(
            (
                await session.scalars(
                    select(AuditEvent.action).where(AuditEvent.target_id == str(org.id))
                )
            ).all()
        )
    assert actions == ["create-org"]
