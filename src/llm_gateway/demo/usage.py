"""Deterministic synthetic 90-day history, priced illustratively at today's rates."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from llm_gateway.catalog import Catalog, ModelPrice
from llm_gateway.cost import compute_cost
from llm_gateway.tenants.models import Organization, Team
from llm_gateway.usage.record import UsageRecord


def usage_rows(
    org: Organization,
    teams: list[Team],
    catalog: Catalog,
    keys: dict[uuid.UUID, list[str]],
    now: datetime,
) -> list[UsageRecord]:
    rows: list[UsageRecord] = []
    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    days = 3 if org.name == "Orbit Labs" else 90
    for day in range(days):
        for team in teams:
            if team.name == "Paused sandbox":
                # The paused team has keys and policy metadata but deliberately no provider calls.
                continue
            for index, entry in enumerate(catalog.models):
                row = _sample(
                    org,
                    team,
                    entry,
                    catalog.version,
                    keys[team.id],
                    now,
                    start,
                    day,
                    index,
                    next(
                        (
                            name
                            for name, definition in catalog.aliases.items()
                            if any(
                                target.model == f"{entry.provider}/{entry.model}"
                                for target in definition.targets
                            )
                        ),
                        None,
                    ),
                )
                rows.append(row)
                if day % 9 == 0 and entry.provider == "groq":
                    rows.pop()
                    destination = next(
                        item for item in catalog.models if item.provider == "deepseek"
                    )
                    rows.extend(_recovery(row, entry, destination, now))
    return rows


def _recovery(
    row: UsageRecord, source: ModelPrice, destination: ModelPrice, now: datetime
) -> list[UsageRecord]:
    """Two unbilled upstream failures followed by a priced, successful fallback."""
    failed = replace(
        row,
        id=uuid.uuid5(row.organization_id, row.request_id + ":attempt1"),
        outcome="upstream_error",
        status_code=502,
        cost_status="not_billed",
        cost_usd=Decimal(0),
        attempt=1,
        saved_usd=None,
        duration_ms=450,
        ttfb_ms=None,
    )
    retried = replace(
        failed,
        id=uuid.uuid5(row.organization_id, row.request_id + ":attempt2"),
        attempt=2,
        created_at=row.created_at + timedelta(milliseconds=450),
    )
    price = destination.at(now)
    cost = compute_cost(price, 40000, 3000, 0) if price and not price.unpriced else None
    recovered = replace(
        row,
        attempt=3,
        provider=destination.provider,
        model=destination.model,
        fallback_from=f"{source.provider}/{source.model}",
        created_at=row.created_at + timedelta(milliseconds=900),
        status_code=200,
        outcome="success",
        cost_status="priced" if cost is not None else "unpriced",
        cost_usd=cost,
        saved_usd=None,
        duration_ms=900,
        ttfb_ms=225 if row.stream else None,
        prompt_tokens=40000,
        completion_tokens=3000,
        cached_tokens=0,
        reasoning_tokens=0,
    )
    return [failed, retried, recovered]


def _sample(
    org: Organization,
    team: Team,
    entry: ModelPrice,
    version: str,
    keys: list[str],
    now: datetime,
    start: datetime,
    day: int,
    index: int,
    alias: str | None,
) -> UsageRecord:
    timestamp = (
        start
        - timedelta(days=day)
        + timedelta(
            seconds=min(max(0, int((now - start).total_seconds()) - 2), 12 * 3600 + index * 600)
        )
    )
    identifier = "demo-" + str(uuid.uuid5(org.id, f"demo-v2:{team.id}:{timestamp.date()}:{index}"))
    varied = (day + index) % 29
    missing, incomplete, rejected, failed = varied == 7, varied == 11, varied == 17, varied == 19
    cache = varied % 6 == 0 and entry.provider != "nvidia"
    prompt, completion = 40000 + index * 500, 3000 if entry.kind == "chat" else 0
    period = entry.at(now)
    cost = compute_cost(period, prompt, completion, 0) if period and not period.unpriced else None
    latency = {
        "groq": 180,
        "deepseek": 900,
        "gemini": 600,
        "openai": 400,
        "zai": 750,
        "nvidia": 22000,
    }[entry.provider] * (1 + (day * 13 + index * 7) % 19 / 10)
    if entry.provider == "groq" and day == 2:
        latency *= 18  # visible slow-day incident, relative to seeding date.
    outcome = (
        "client_disconnected"
        if incomplete
        else "upstream_error"
        if rejected or failed
        else "cache_hit"
        if cache
        else "success"
    )
    status = 400 if rejected else 502 if failed else 200
    cost_status = (
        "stream_incomplete"
        if incomplete
        else "usage_missing"
        if missing
        else "not_billed"
        if rejected or failed
        else "cached"
        if cache
        else "unpriced"
        if cost is None
        else "priced"
    )
    return UsageRecord(
        id=uuid.uuid5(org.id, identifier),
        request_id=identifier,
        created_at=timestamp,
        organization_id=org.id,
        team_id=team.id,
        key_id=keys[index % len(keys)],
        provider=entry.provider,
        model=entry.model,
        endpoint="chat" if entry.kind == "chat" else "embeddings",
        stream=entry.kind == "chat" and (index % 2 == 0 or incomplete),
        status_code=status,
        outcome=outcome,
        cost_status=cost_status,
        prompt_tokens=None if missing or incomplete else prompt,
        completion_tokens=None if missing or incomplete else completion,
        cached_tokens=None if missing or incomplete else 0,
        reasoning_tokens=None if missing or incomplete else 0,
        cost_usd=None
        if missing or incomplete
        else Decimal(0)
        if cache or rejected or failed
        else cost,
        catalog_version=version,
        duration_ms=12 if cache else latency,
        ttfb_ms=None if entry.kind == "embedding" or missing else latency / 4,
        alias=alias if varied % 3 == 0 else None,
        saved_usd=cost if cache else None,
        redaction_count=None if missing else 3 if varied % 4 == 0 else 0,
    )
