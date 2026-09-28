"""Read and verify the audit chain without making administrative changes."""

import argparse
import json
from datetime import date

from llm_gateway.admin_service.service import AdminService


def add_commands(audit: argparse.ArgumentParser) -> None:
    subcommands = audit.add_subparsers(dest="audit_command", required=True)
    listing = subcommands.add_parser("list")
    listing.add_argument("--since", type=date.fromisoformat)
    listing.add_argument("--action")
    subcommands.add_parser("verify")


async def execute(args: argparse.Namespace, service: AdminService) -> str:
    if args.audit_command == "verify":
        count, broken = await service.verify_audit()
        if broken is not None:
            raise ValueError(f"Broken audit link at id {broken}")
        return f"Audit chain verified: {count} events"
    events = await service.list_audit(args.since, args.action, None, 1000000000)
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
