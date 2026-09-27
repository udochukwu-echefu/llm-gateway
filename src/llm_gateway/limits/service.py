"""Cross-replica admission and finalization, with no request bodies in Redis."""

import asyncio
import math
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import structlog
from redis.asyncio import Redis

from llm_gateway.errors import GatewayError
from llm_gateway.limits.configuration import EffectiveLimits
from llm_gateway.limits.redis import Scripts
from llm_gateway.usage.record import UsageRecord

PICOS = Decimal(10) ** 12
log = structlog.get_logger("llm_gateway.limits")


def month_end(now: datetime) -> datetime:
    return (
        now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) + timedelta(days=32)
    ).replace(day=1)


def picos(amount: Decimal) -> int:
    return int(amount * PICOS)


class LimitService:
    def __init__(
        self,
        client: Redis,
        *,
        fail_mode: str = "open",
        lease_ttl: int = 900,
        ip_limit: int = 20,
        rebuild_timeout: float = 0.2,
        clock: Callable[[], float] = time.time,
        spend_total: Callable[[uuid.UUID, datetime, datetime], Awaitable[Decimal]] | None = None,
    ) -> None:
        self.client = client
        self.scripts = Scripts(client)
        self.fail_mode = fail_mode
        self.lease_ttl = lease_ttl
        self.ip_limit = ip_limit
        self.rebuild_timeout = rebuild_timeout
        self.clock = clock
        self.spend_total = spend_total
        self._last_error = 0.0

    async def start(self) -> None:
        await self.scripts.load()

    async def safe(self, operation: Callable[[], Awaitable[object]]) -> object | None:
        try:
            return await operation()
        except Exception as exc:
            if self.clock() - self._last_error >= 1 or self._last_error == 0:
                log.error("limits_dependency_unavailable", error_type=type(exc).__name__)
                self._last_error = self.clock()
            if self.fail_mode == "closed":
                raise GatewayError(
                    503, "Limits unavailable.", type="server_error", code="limits_unavailable"
                ) from exc
            return None

    async def window(
        self, subject: str, kind: str, limit: int, delta: int, update: bool = True
    ) -> list[int]:
        now = self.clock()
        slot = math.floor(now / 60)
        result = await self.scripts.call(
            "window",
            [f"lgw:{kind}:{subject}:{slot}", f"lgw:{kind}:{subject}:{slot - 1}"],
            [now, limit, delta, int(update)],
        )
        if not isinstance(result, list):
            raise ValueError("Invalid window script result")
        return result

    async def ip_check(self, ip: str) -> None:
        result = await self.safe(lambda: self.window(ip, "auth-fail", self.ip_limit, 0, False))
        if isinstance(result, list) and not result[0]:
            reset = cast(list[int], result)[2]
            raise GatewayError(
                429,
                "Too many authentication failures.",
                type="rate_limit_error",
                code="rate_limit_exceeded",
                headers={"Retry-After": str(reset)},
            )

    async def ip_failure(self, ip: str) -> None:
        await self.safe(lambda: self.window(ip, "auth-fail", self.ip_limit, 1))

    async def admission(
        self, team: uuid.UUID, limits: EffectiveLimits
    ) -> tuple[str | None, dict[str, str]]:
        now = datetime.fromtimestamp(self.clock(), UTC)
        headers = {
            f"x-ratelimit-{field}-{kind}": value
            for kind, limit in (("requests", limits.rpm), ("tokens", limits.tpm))
            for field, value in (
                ("limit", str(limit)),
                ("remaining", "unavailable"),
                ("reset", "unavailable"),
            )
        }
        budget = await self.safe(lambda: self.check_budget(team, limits, now))
        if isinstance(budget, list) and not budget[0]:
            retry = math.ceil((month_end(now) - now).total_seconds())
            headers = await self.rate_headers(team, limits)
            raise GatewayError(
                429,
                f"Team budget for {now:%Y-%m} exceeded.",
                type="insufficient_quota",
                code="budget_exceeded",
                headers={"Retry-After": str(retry), **headers},
            )
        for kind, limit in (("requests", limits.rpm), ("tokens", limits.tpm)):
            result = await self.safe(
                lambda kind=kind, limit=limit: self.window(
                    str(team), kind, limit, 1 if kind == "requests" else 0, kind == "requests"
                )
            )
            if isinstance(result, list):
                values = cast(list[int], result)
                headers.update(self._format_headers(kind, limit, values))
                if not values[0]:
                    if kind == "requests":
                        tokens = await self.safe(
                            lambda: self.window(str(team), "tokens", limits.tpm, 0, False)
                        )
                        if isinstance(tokens, list):
                            headers.update(
                                self._format_headers("tokens", limits.tpm, cast(list[int], tokens))
                            )
                    raise GatewayError(
                        429,
                        f"Team {kind} rate limit exceeded.",
                        type="rate_limit_error",
                        code="rate_limit_exceeded",
                        headers={"Retry-After": str(values[2]), **headers},
                    )
        lease = uuid.uuid4().hex
        result = await self.safe(
            lambda: self.scripts.call(
                "lease",
                [f"lgw:leases:{team}"],
                [self.clock(), limits.max_concurrency, lease, self.lease_ttl],
            )
        )
        if result == 0:
            raise GatewayError(
                429,
                "Team concurrency limit exceeded.",
                type="rate_limit_error",
                code="concurrency_limit_exceeded",
                headers={"Retry-After": "1", **headers},
            )
        return (lease if result == 1 else None), headers

    async def rate_headers(self, team: uuid.UUID, limits: EffectiveLimits) -> dict[str, str]:
        headers: dict[str, str] = {}
        for kind, limit in (("requests", limits.rpm), ("tokens", limits.tpm)):
            result = await self.safe(
                lambda kind=kind, limit=limit: self.window(str(team), kind, limit, 0, False)
            )
            if isinstance(result, list):
                headers.update(self._format_headers(kind, limit, cast(list[int], result)))
        return headers

    @staticmethod
    def _format_headers(kind: str, limit: int, values: list[int]) -> dict[str, str]:
        return {
            f"x-ratelimit-limit-{kind}": str(limit),
            f"x-ratelimit-remaining-{kind}": str(values[1]) if limit else "unlimited",
            f"x-ratelimit-reset-{kind}": str(values[2]),
        }

    async def check_budget(
        self, team: uuid.UUID, limits: EffectiveLimits, now: datetime
    ) -> list[int]:
        key = f"lgw:budget:{team}:{now:%Y-%m}"
        if not cast(int, await self.client.exists(key)):
            async with asyncio.timeout(self.rebuild_timeout):
                await self._initialize_budget(team, key, now)
        ttl = max(1, math.ceil((month_end(now) - now).total_seconds()) + 60)
        result = await self.scripts.call(
            "budget",
            [key, f"{key}:alert"],
            [
                picos(limits.monthly_budget_usd),
                0,
                picos(limits.monthly_budget_usd * limits.alert_threshold),
                ttl,
            ],
        )
        if not isinstance(result, list):
            raise ValueError("Invalid budget script result")
        return result

    async def _initialize_budget(self, team: uuid.UUID, key: str, now: datetime) -> None:
        lock = f"{key}:lock"
        owner = uuid.uuid4().hex
        for _ in range(50):
            if cast(bool, await self.client.set(lock, owner, nx=True, ex=5)):
                try:
                    if not cast(int, await self.client.exists(key)):
                        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                        total = (
                            await self.spend_total(team, start, month_end(now))
                            if self.spend_total
                            else Decimal(0)
                        )
                        await self.client.set(
                            key,
                            picos(total),
                            nx=True,
                            ex=max(1, math.ceil((month_end(now) - now).total_seconds()) + 60),
                        )
                finally:
                    await self.scripts.call("unlock", [lock], [owner])
                return
            if cast(int, await self.client.exists(key)):
                return
            await asyncio.sleep(0.01)
        raise TimeoutError("budget rebuild lock timed out")

    async def finish_records(
        self,
        team: uuid.UUID,
        lease: str | None,
        records: Sequence[UsageRecord],
        limits: EffectiveLimits,
    ) -> None:
        """One lease belongs to the client request, but every attempt consumes resources."""
        await self.finish(team, lease, None, limits)
        for record in records:
            await self.finish(team, None, record, limits)

    async def finish(
        self,
        team: uuid.UUID,
        lease: str | None,
        record: UsageRecord | None,
        limits: EffectiveLimits,
    ) -> None:
        if lease is not None:
            await self.safe(lambda: self.scripts.call("release", [f"lgw:leases:{team}"], [lease]))
        if record is None:
            return
        tokens = (record.prompt_tokens or 0) + (record.completion_tokens or 0)
        if tokens:
            await self.safe(lambda: self.window(str(team), "tokens", 0, tokens))
        cost = record.cost_usd
        if record.cost_status != "priced" or cost is None:
            return
        now = record.created_at
        key = f"lgw:budget:{team}:{now:%Y-%m}"
        ttl = max(
            1,
            math.ceil((month_end(now) - datetime.fromtimestamp(self.clock(), UTC)).total_seconds())
            + 60,
        )

        # Initialization also makes the month visible to all other replicas before incrementing.
        async def add_cost() -> None:
            if not cast(int, await self.client.exists(key)):
                async with asyncio.timeout(self.rebuild_timeout):
                    await self._initialize_budget(team, key, now)
            threshold = (
                picos(limits.monthly_budget_usd * limits.alert_threshold)
                if limits.monthly_budget_usd
                else 0
            )
            result = await self.scripts.call(
                "budget", [key, f"{key}:alert"], [0, picos(cost), threshold, ttl]
            )
            if isinstance(result, list) and result[2]:
                log.warning("budget_alert", team_id=str(team), month=f"{now:%Y-%m}")

        await self.safe(add_cost)

    async def keep_lease_alive(self, team: uuid.UUID, lease: str) -> None:
        """Renew while a response is active; cancellation ends this task on disconnect."""
        while True:
            await asyncio.sleep(max(1, self.lease_ttl / 3))
            try:
                result = await self.safe(
                    lambda: self.scripts.call(
                        "renew", [f"lgw:leases:{team}"], [self.clock(), lease, self.lease_ttl]
                    )
                )
            except GatewayError:
                # After headers are sent, a 503 cannot replace the streamed response.
                continue
            if result == 0:
                return
