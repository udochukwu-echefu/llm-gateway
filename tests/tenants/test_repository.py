import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.tenants.keys import issue_key
from llm_gateway.tenants.models import ApiKey
from llm_gateway.tenants.repository import PostgresKeyRepository
from tests.conftest import TEST_PEPPER
from tests.tenants.support import create_cli_key, unique_name

pytestmark = pytest.mark.db


@pytest.fixture
async def repository(migrated_database: str) -> AsyncIterator[PostgresKeyRepository]:
    engine = create_async_engine(migrated_database)
    try:
        yield PostgresKeyRepository(async_sessionmaker(engine, expire_on_commit=False))
    finally:
        await engine.dispose()


async def test_migration_upgrades_empty_database(migrated_database: str) -> None:
    engine = create_async_engine(migrated_database)
    try:
        async with engine.connect() as connection:
            tables = (
                (
                    await connection.execute(
                        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                    )
                )
                .scalars()
                .all()
            )

        assert {"organizations", "teams", "api_keys", "alembic_version"} <= set(tables)
    finally:
        await engine.dispose()


async def test_repository_returns_key_identity_and_hash(repository: PostgresKeyRepository) -> None:
    org = await repository.create_org(unique_name("org"))
    team = await repository.create_team(org.name, "team")
    issued = issue_key(TEST_PEPPER.encode())

    await repository.create_key(org.name, team.name, "client", issued.key_id, issued.secret_hash)
    record = await repository.get_key(issued.key_id)

    assert record is not None
    assert record.organization_id == org.id
    assert record.team_id == team.id
    assert record.secret_hash == issued.secret_hash


async def test_repository_unknown_key_returns_none(repository: PostgresKeyRepository) -> None:
    assert await repository.get_key("aaaaaaaaaaaa") is None


async def test_repository_lists_keys_scoped_to_team(repository: PostgresKeyRepository) -> None:
    org = await repository.create_org(unique_name("org"))
    first = await repository.create_team(org.name, "first")
    second = await repository.create_team(org.name, "second")
    keys = [issue_key(TEST_PEPPER.encode()), issue_key(TEST_PEPPER.encode())]
    await repository.create_key(
        org.name, first.name, "first-key", keys[0].key_id, keys[0].secret_hash
    )
    await repository.create_key(
        org.name, second.name, "second-key", keys[1].key_id, keys[1].secret_hash
    )

    listed = await repository.list_keys(org.name, first.name)

    assert [row.key_id for row in listed] == [keys[0].key_id]


async def test_repository_revokes_without_deleting(repository: PostgresKeyRepository) -> None:
    org = await repository.create_org(unique_name("org"))
    await repository.create_team(org.name, "team")
    issued = issue_key(TEST_PEPPER.encode())
    await repository.create_key(org.name, "team", "client", issued.key_id, issued.secret_hash)

    revoked = await repository.revoke_key(issued.key_id)
    record = await repository.get_key(issued.key_id)

    assert revoked
    assert record is not None
    assert record.revoked_at is not None


async def test_database_never_stores_plaintext_secret(migrated_database: str) -> None:
    issued = create_cli_key(migrated_database)
    engine = create_async_engine(migrated_database)
    try:
        async with async_sessionmaker(engine)() as session:
            row = await session.scalar(select(ApiKey).where(ApiKey.key_id == issued.key_id))

        assert row is not None
        secret = issued.full_key.split("_", 2)[2].encode()
        assert secret not in row.secret_hash
        assert secret not in str(row.__dict__).encode()
    finally:
        await engine.dispose()


async def test_repository_rejects_unknown_team_organization(
    repository: PostgresKeyRepository,
) -> None:
    with pytest.raises(ValueError, match="Organization not found"):
        await repository.create_team(f"missing-{uuid.uuid4().hex}", "team")
