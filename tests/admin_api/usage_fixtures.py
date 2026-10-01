"""Shared synthetic attempt metadata for HTTP reporting regressions."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from llm_gateway.tenants.models import Organization, Team
from llm_gateway.usage.repository import UsageRow
from tests.admin_api.conftest import AdminHarness


async def add_receipts(
    h: AdminHarness, request_id: str = "fake-chain", org_name: str | None = None
) -> None:
    async with h.sessions.begin() as session:
        org = await session.scalar(
            select(Organization).where(Organization.name == (org_name or h.org))
        )
        assert org is not None
        team = await session.scalar(select(Team).where(Team.organization_id == org.id))
        assert team is not None
        now = datetime.now(UTC) - timedelta(seconds=1)
        for attempt in (1, 2, 3):
            session.add(
                UsageRow(
                    id=uuid.uuid4(),
                    request_id=request_id,
                    created_at=now + timedelta(milliseconds=attempt),
                    organization_id=org.id,
                    team_id=team.id,
                    key_id=h.team_key.split("_")[1],
                    provider="groq" if attempt < 3 else "deepseek",
                    model="fake-model",
                    endpoint="chat",
                    stream=True,
                    status_code=502 if attempt < 3 else 200,
                    outcome="upstream_error" if attempt < 3 else "success",
                    cost_status="priced",
                    prompt_tokens=10,
                    completion_tokens=2,
                    cached_tokens=0,
                    reasoning_tokens=0,
                    cost_usd=Decimal("0.000000000001"),
                    saved_usd=None,
                    redaction_count=2,
                    catalog_version="fake-test",
                    duration_ms=100.0 * attempt,
                    ttfb_ms=None,
                    attempt=attempt,
                    fallback_from="groq/fake-model" if attempt == 3 else None,
                    alias="fake-alias",
                )
            )
