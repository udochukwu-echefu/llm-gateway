"""Offline-only policy administration; arguments never contain matched content."""

import argparse

from llm_gateway.admin.service.service import AdminService
from llm_gateway.guardrails.policy import DETECTORS, REGIONS
from llm_gateway.guardrails.repository import GuardrailRepository
from llm_gateway.tenants.repository import PostgresKeyRepository

COMMANDS = (
    "set-guardrails",
    "set-residency",
    "show-guardrails",
    "clear-guardrails",
    "clear-residency",
)


def add_commands(cli: argparse.ArgumentParser) -> None:
    cli.add_argument("org")
    cli.add_argument("--team")
    if cli.prog.endswith("set-guardrails"):
        cli.add_argument("--action", action="append", required=True)
    if cli.prog.endswith("set-residency"):
        cli.add_argument("--allow-region", action="append", choices=REGIONS, required=True)


async def execute(
    args: argparse.Namespace, repository: PostgresKeyRepository, service: AdminService
) -> str:
    policies = GuardrailRepository(repository.sessions, repository.actor)
    if args.command != "show-guardrails":
        residency = args.command.endswith("residency")
        values = None
        if args.command.startswith("set-"):
            values = args.allow_region if residency else args.action
        await service.set_policy(args.org, args.team, residency=residency, values=values)
    guardrails, policy = await policies.get_policy(args.org, args.team)
    return "\n".join(
        [
            *(f"{name}: {guardrails.action(name)}" for name in DETECTORS),
            "Allowed regions: " + (", ".join(policy.regions) or "none"),
            "Changes take effect within the verified-key cache TTL (30 seconds by default).",
        ]
    )
