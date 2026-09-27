"""Read and verify the audit chain without making administrative changes."""

import argparse
import json
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from llm_gateway.audit.chain import first_broken
from llm_gateway.audit.models import AuditEvent


def add_commands(audit: argparse.ArgumentParser) -> None:
    subcommands = audit.add_subparsers(dest="audit_command", required=True)
    listing = subcommands.add_parser("list")
    listing.add_argument("--since", type=date.fromisoformat)
    listing.add_argument("--action")
    subcommands.add_parser("verify")


async def execute(args: argparse.Namespace, sessions: async_sessionmaker[AsyncSession]) -> str:
    query = select(AuditEvent).order_by(AuditEvent.id)
    if args.audit_command == "list":
        if args.since:
            query = query.where(
                AuditEvent.occurred_at >= datetime.combine(args.since, datetime.min.time(), UTC)
            )
        if args.action:
            query = query.where(AuditEvent.action == args.action)
    async with sessions() as session:
        events = list((await session.scalars(query)).all())
    if args.audit_command == "verify":
        broken = first_broken(events)
        if broken is not None:
            raise ValueError(f"Broken audit link at id {broken}")
        return f"Audit chain verified: {len(events)} events"
    return "\n".join(
        json.dumps(
            {
                "id": event.id,
                "occurred_at": event.occurred_at.isoformat(),
                "actor": event.actor,
                "action": event.action,
                "target_type": event.target_type,
                "target_id": event.target_id,
                "details": event.details,
                "prev_hash": event.prev_hash,
                "hash": event.hash,
            },
            sort_keys=True,
        )
        for event in events
    )
