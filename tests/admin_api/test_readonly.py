import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.admin_api.conftest import AdminHarness

pytestmark = pytest.mark.db


async def test_readonly_role_can_read_usage_but_not_keys_or_write(
    admin_harness: AdminHarness,
) -> None:
    sessions = admin_harness.sessions
    async with sessions() as session:
        await session.execute(text("SET LOCAL ROLE gateway_readonly"))
        await session.execute(text("SELECT id FROM usage_records LIMIT 1"))
        await session.execute(text("SELECT id FROM teams LIMIT 1"))
        await session.execute(
            text("SELECT team_id, monthly_budget_usd FROM usage_team_budgets LIMIT 1")
        )
    for statement in (
        "SELECT id FROM api_keys LIMIT 1",
        "SELECT id FROM admin_keys LIMIT 1",
        "SELECT team_id FROM team_limits LIMIT 1",
        "INSERT INTO organizations (id, name, created_at) "
        "VALUES (gen_random_uuid(), 'fake-ro', now())",
    ):
        with pytest.raises(DBAPIError):
            await _execute_readonly(sessions, statement)


async def _execute_readonly(sessions: async_sessionmaker[AsyncSession], statement: str) -> None:
    async with sessions() as session:
        await session.execute(text("SET LOCAL ROLE gateway_readonly"))
        await session.execute(text(statement))
