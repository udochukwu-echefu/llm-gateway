"""Offline administrative commands; never expose key management over HTTP."""

import argparse
import asyncio
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from llm_gateway.secrets import EnvSecretStore, FileSecretStore, SecretStore
from llm_gateway.tenants.keys import issue_key
from llm_gateway.tenants.repository import PostgresKeyRepository


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="gateway-admin")
    commands = cli.add_subparsers(dest="command", required=True)
    commands.add_parser("create-org").add_argument("name")
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
    return cli


async def execute(
    args: argparse.Namespace, repository: PostgresKeyRepository, pepper: bytes
) -> str:
    if args.command == "create-org":
        org = await repository.create_org(args.name)
        return f"Created organization {org.name} ({org.id})"
    if args.command == "create-team":
        team = await repository.create_team(args.org, args.name)
        return f"Created team {team.name} ({team.id})"
    if args.command == "create-key":
        if args.expires_in_days is not None and args.expires_in_days <= 0:
            raise ValueError("--expires-in-days must be positive")
        expiry = (
            datetime.now(UTC) + timedelta(days=args.expires_in_days)
            if args.expires_in_days is not None
            else None
        )
        issued = issue_key(pepper)
        await repository.create_key(
            args.org, args.team, args.name, issued.key_id, issued.secret_hash, expiry
        )
        return issued.full_key
    if args.command == "list-keys":
        rows = await repository.list_keys(args.org, args.team)
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
        if not await repository.revoke_key(args.key_id):
            raise ValueError("Key not found")
        return "Key revoked"
    raise ValueError("Unknown command")


def admin_store() -> SecretStore:
    from pathlib import Path

    if os.getenv("GATEWAY_SECRETS__BACKEND", "env") == "file":
        directory = os.getenv("GATEWAY_SECRETS__DIR")
        if not directory:
            raise ValueError("GATEWAY_SECRETS__DIR is required")
        return FileSecretStore(Path(directory))
    return EnvSecretStore()


async def run(args: argparse.Namespace) -> str:
    store = admin_store()
    pepper = store.get("api_key_pepper")
    database_url = store.get("database_url")
    if pepper is None or len(pepper.get_secret_value().encode()) < 32:
        raise ValueError("GATEWAY_API_KEY_PEPPER is required and must be at least 32 bytes")
    if database_url is None:
        raise ValueError("GATEWAY_DATABASE_URL is required")
    engine = create_async_engine(database_url.get_secret_value())
    try:
        return await execute(
            args,
            PostgresKeyRepository(async_sessionmaker(engine, expire_on_commit=False)),
            pepper.get_secret_value().encode(),
        )
    finally:
        await engine.dispose()


def main() -> None:
    args = parser().parse_args()
    try:
        print(asyncio.run(run(args)))
    except ValueError as exc:
        parser().exit(2, f"gateway-admin: {exc}\n")
