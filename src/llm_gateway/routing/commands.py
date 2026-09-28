"""Offline policy administration uses the same reviewed catalogue as the gateway."""

import argparse

from llm_gateway.admin.service.service import AdminService
from llm_gateway.catalog import load_catalog
from llm_gateway.routing.repository import PolicyRepository
from llm_gateway.tenants.repository import PostgresKeyRepository


def add_commands(cli: argparse.ArgumentParser) -> None:
    cli.add_argument("org")
    cli.add_argument("--team")
    if cli.prog.endswith("set-models"):
        cli.add_argument("--allow", action="append", required=True)


async def execute(
    args: argparse.Namespace, repository: PostgresKeyRepository, service: AdminService
) -> str:
    catalog = load_catalog()
    policies = PolicyRepository(repository.sessions, repository.actor)
    if args.command != "show-models":
        await service.set_models(
            args.org, args.team, args.allow if args.command == "set-models" else None
        )
    policy = await policies.get_models(args.org, args.team)
    models = [
        f"{entry.provider}/{entry.model}"
        for entry in catalog.models
        if policy.allows(f"{entry.provider}/{entry.model}", entry.region)
    ]
    aliases = [
        name
        for name, alias in catalog.aliases.items()
        if any(
            policy.allows(target.model, catalog.region(target.model)) for target in alias.targets
        )
    ]
    rows = [
        (
            "Org policy",
            "all catalogued models"
            if policy.organization is None
            else ", ".join(policy.organization) or "none",
        ),
        ("Team policy", "inherit" if policy.team is None else ", ".join(policy.team) or "none"),
        ("Effective models", ", ".join(models) or "none"),
        ("Effective aliases", ", ".join(aliases) or "none"),
    ]
    return "\n".join(
        [
            f"Scope: {args.org}" + (f" / {args.team}" if args.team else ""),
            f"{'Policy':<20} Value",
            *(f"{label:<20} {value}" for label, value in rows),
            "Changes take effect within the verified-key cache TTL (30 seconds by default).",
            "Effective lists show catalogue permissions; "
            "provider configuration and active prices also apply at runtime.",
        ]
    )
