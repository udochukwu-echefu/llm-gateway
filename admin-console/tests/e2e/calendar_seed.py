"""Fixed boundary receipts, isolated from the demo org and the real clock."""

import json
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TypedDict, cast

from llm_gateway.admin.service.service import AdminService
from llm_gateway.usage.record import UsageRecord
from llm_gateway.usage.repository import PostgresUsageRepository


class Attempt(TypedDict):
    id: str
    at: str


class CalendarData(TypedDict):
    org: str
    now: str
    attempts: list[Attempt]


async def seed_calendar(admin: AdminService) -> None:
    data = cast(
        CalendarData, json.loads(Path(__file__).with_name("calendar-data.json").read_text())
    )
    org = await admin.create_org(data["org"])
    team = await admin.create_team(data["org"], "UTC boundaries")
    records = [
        UsageRecord(
            id=uuid.uuid5(org.id, attempt["id"]),
            request_id=attempt["id"],
            created_at=datetime.fromisoformat(attempt["at"]),
            organization_id=org.id,
            team_id=team.id,
            key_id="syntheticutc",
            provider="groq",
            model="synthetic-calendar",
            endpoint="chat",
            stream=False,
            status_code=200,
            outcome="success",
            cost_status="priced",
            prompt_tokens=10,
            completion_tokens=5,
            cached_tokens=0,
            reasoning_tokens=0,
            cost_usd=Decimal("0.0001"),
            catalog_version="synthetic-calendar",
            duration_ms=100,
            ttfb_ms=50,
        )
        for attempt in data["attempts"]
    ]
    await PostgresUsageRepository(admin.sessions).insert(records)
