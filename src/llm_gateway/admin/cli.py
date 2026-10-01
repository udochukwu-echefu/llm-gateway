"""Offline administrative CLI backed by the shared admin service."""

import argparse
import asyncio
import os
from contextlib import suppress
from datetime import UTC, date, datetime
from decimal import Decimal

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.admin.service.limits import admin_defaults, read_live_limits, render_limits
from llm_gateway.admin.service.service import AdminService
from llm_gateway.audit import commands as audit_commands
from llm_gateway.guardrails import commands as guardrail_commands
from llm_gateway.limits.configuration import resolve
from llm_gateway.limits.service import LimitService
from llm_gateway.routing import commands as model_commands
from llm_gateway.secrets import EnvSecretStore, FileSecretStore, SecretStore
from llm_gateway.tenants.repository import PostgresKeyRepository
from llm_gateway.usage.repository import PostgresUsageRepository


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="gateway-admin")
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("create-org").add_argument("name")
    admin_key = commands.add_parser("create-admin-key")
    admin_key.add_argument("name")
    admin_key.add_argument("--role", choices=("platform", "org", "viewer"), required=True)
    admin_key.add_argument("--org")
    team = commands.add_parser("create-team")
    team.add_argument("org")
    team.add_argument("name")
    key = commands.add_parser("create-key")
    key.add_argument("org")
    key.add_argument("team")
    key.add_argument("name")
    key.add_argument("--expires-in-days", type=int)
    listed = commands.add_parser("list-keys")
    listed.add_argument("org")
    listed.add_argument("team", nargs="?")
    commands.add_parser("revoke-key").add_argument("key_id")
    usage = commands.add_parser("usage")
    usage.add_argument("org")
    usage.add_argument("--team")
    usage.add_argument("--since", type=date.fromisoformat)
    usage.add_argument("--until", type=date.fromisoformat)
    usage.add_argument("--group-by", choices=("team", "key", "model", "day"), default="team")
    for name in ("set-limits", "set-budget", "show-limits", "clear-limits"):
        command = commands.add_parser(name)
        command.add_argument("org")
        command.add_argument("team")
        if name == "set-limits":
            for flag in ("rpm", "tpm", "max-concurrency"):
                command.add_argument(f"--{flag}", type=int)
        if name == "set-budget":
            command.add_argument("usd", type=Decimal)
            command.add_argument("--alert-at", type=Decimal, default=Decimal("0.8"))
    for name in ("set-models", "clear-models", "show-models"):
        model_commands.add_commands(commands.add_parser(name))
    for name in guardrail_commands.COMMANDS:
        guardrail_commands.add_commands(commands.add_parser(name))
    audit_commands.add_commands(commands.add_parser("audit"))
    cache = commands.add_parser("cache").add_subparsers(dest="cache_command", required=True)
    purge_command = cache.add_parser("purge")
    purge_command.add_argument("org")
    purge_command.add_argument("--team")
    return cli


async def execute(
    args: argparse.Namespace,
    repository: PostgresKeyRepository,
    pepper: bytes,
    usage_repository: PostgresUsageRepository | None = None,
    limits_service: LimitService | None = None,
    cache_client: Redis | None = None,
) -> str:
    service = AdminService(
        repository.sessions, pepper, repository.actor, usage_repository=usage_repository
    )
    if args.command == "create-admin-key":
        return await service.create_admin_key(args.name, args.role, args.org)
    if args.command in guardrail_commands.COMMANDS:
        return await guardrail_commands.execute(args, repository, service)
    if args.command == "cache":
        if cache_client is None:
            raise ValueError("Redis is required for cache purge")
        count = await service.purge_cache(args.org, args.team, cache_client)
        return f"Purged {count} cache entries"
    if args.command in {"set-models", "clear-models", "show-models"}:
        return await model_commands.execute(args, repository, service)
    if args.command == "audit":
        return await audit_commands.execute(args, service)
    if args.command in {"set-limits", "set-budget", "show-limits", "clear-limits"}:
        if args.command == "set-limits":
            values = (args.rpm, args.tpm, args.max_concurrency)
            if any(value is not None and value < 0 for value in values):
                raise ValueError("Limits must be nonnegative")
            await service.set_limits(
                args.org,
                args.team,
                rpm=args.rpm,
                tpm=args.tpm,
                max_concurrency=args.max_concurrency,
            )
        elif args.command == "set-budget":
            if (
                args.usd < 0
                or args.usd > Decimal("9223372.036854775807")
                or args.usd != args.usd.quantize(Decimal("0.000000000001"))
                or not 0 < args.alert_at <= 1
            ):
                raise ValueError("Budget must be nonnegative and alert threshold in (0, 1]")
            await service.set_limits(args.org, args.team, budget=args.usd, alert=args.alert_at)
        elif args.command == "clear-limits":
            await service.set_limits(args.org, args.team, clear=True)
        team_id, overrides = await service.team_limits(args.org, args.team)
        defaults = admin_defaults()
        live = None
        if limits_service is not None:
            # Offline administration still succeeds; live counters say unavailable.
            with suppress(RedisError, TimeoutError):
                live = await read_live_limits(limits_service, team_id, resolve(overrides, defaults))
        return render_limits(args.org, args.team, overrides, defaults, live)
    if args.command == "usage":
        if args.since and args.until and args.since > args.until:
            raise ValueError("--since must be on or before --until")
        if usage_repository is None:
            raise ValueError("usage repository unavailable")
        rows = await service.usage(args.org, args.team, args.since, args.until, args.group_by)
        return "\n".join(
            "  ".join(f"{key}={_usage_value(value)}" for key, value in row.items()) for row in rows
        )
    if args.command == "create-org":
        org = await service.create_org(args.name)
        return f"Created organization {org.name} ({org.id})"
    if args.command == "create-team":
        team = await service.create_team(args.org, args.name)
        return f"Created team {team.name} ({team.id})"
    if args.command == "create-key":
        if args.expires_in_days is not None and args.expires_in_days <= 0:
            raise ValueError("--expires-in-days must be positive")
        return await service.create_key(args.org, args.team, args.name, args.expires_in_days)
    if args.command == "list-keys":
        rows = await service.list_keys(args.org, args.team, None, None)
        now = datetime.now(UTC)
        lines: list[str] = []
        for row in rows:
            status = (
                "revoked"
                if row.revoked_at
                else "expired"
                if row.expires_at and row.expires_at <= now
                else "active"
            )
            lines.append(f"{row.key_id}  {row.name}  {status}")
        return "\n".join(lines)
    if args.command == "revoke-key":
        if not await service.revoke_key(args.key_id):
            raise ValueError("Key not found")
        return "Key revoked"
    raise ValueError("Unknown command")


def _usage_value(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value) if value is not None else "NULL"


def admin_store() -> SecretStore:
    from pathlib import Path

    backend = os.getenv("GATEWAY_SECRETS__BACKEND", "env")
    if backend == "file":
        directory = os.getenv("GATEWAY_SECRETS__DIR")
        if not directory:
            raise ValueError("GATEWAY_SECRETS__DIR is required")
        return FileSecretStore(Path(directory))
    if backend == "env":
        return EnvSecretStore()
    raise ValueError("GATEWAY_SECRETS__BACKEND must be env or file")


async def run(args: argparse.Namespace) -> str:
    store = admin_store()
    pepper = store.get("api_key_pepper")
    database_url = store.get("database_url")
    if pepper is None or len(pepper.get_secret_value().encode()) < 32:
        raise ValueError("GATEWAY_API_KEY_PEPPER is required and must be at least 32 bytes")
    if database_url is None:
        raise ValueError("GATEWAY_DATABASE_URL is required")
    engine = create_async_engine(database_url.get_secret_value())
    redis_client: Redis | None = None
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        service = None
        if args.command in {"set-limits", "set-budget", "show-limits", "clear-limits", "cache"}:
            redis_url = store.get("redis_url")
            if args.command in {"show-limits", "cache"} and (
                redis_url is None or not redis_url.get_secret_value()
            ):
                raise ValueError("GATEWAY_REDIS_URL is required")
            if redis_url is not None and redis_url.get_secret_value():
                redis_client = Redis.from_url(  # pyright: ignore[reportUnknownMemberType]  # redis-py types **kwargs as Unknown
                    redis_url.get_secret_value(),
                    socket_timeout=0.05,
                    socket_connect_timeout=0.05,
                )
                service = LimitService(
                    redis_client, spend_total=PostgresUsageRepository(sessions).month_spend
                )
        return await execute(
            args,
            PostgresKeyRepository(sessions),
            pepper.get_secret_value().encode(),
            PostgresUsageRepository(sessions),
            service,
            redis_client,
        )
    finally:
        if redis_client is not None:
            await redis_client.aclose()
        await engine.dispose()


def main() -> None:
    args = parser().parse_args()
    try:
        print(asyncio.run(run(args)))
    except ValueError as exc:
        parser().exit(2, f"gateway-admin: {exc}\n")
