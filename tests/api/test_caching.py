"""Cache decisions are exercised through the authenticated HTTP API."""

import asyncio
import time
import uuid
from dataclasses import replace

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from llm_gateway.gateway_state import get_app_state
from llm_gateway.limits.configuration import EffectiveLimits
from llm_gateway.tenants.keys import hash_secret, issue_key
from llm_gateway.tenants.repository import KeyRecord
from tests.api.conftest import MemoryRedis, ResilientApp
from tests.conftest import TEST_PEPPER, MemoryKeyRepository
from tests.fixtures import CHAT_REQUEST, COMPLETION, EMBEDDINGS


async def test_embeddings_default_hit_is_encrypted_free_and_accounted(
    cached: tuple[ResilientApp, MemoryRedis],
) -> None:
    app, redis = cached
    route = app.router.post("https://openai.test/v1/embeddings").respond(200, json=EMBEDDINGS)
    body = {"model": "openai/text-embedding-004", "input": "PRIVATE_MARKER"}

    first = await app.client.post("/v1/embeddings", json=body)
    second = await app.client.post("/v1/embeddings", json=body)
    await get_app_state(app.app).usage_writer.stop()

    assert (first.headers["x-lgw-cache"], second.headers["x-lgw-cache"]) == ("miss", "hit")
    assert route.call_count == 1
    assert len(redis.values) == 1
    assert b"PRIVATE_MARKER" not in next(iter(redis.values.values()))
    assert second.json() == first.json()
    assert [record.outcome for record in app.records] == ["success", "cache_hit"]
    assert app.records[-1].cost_status == "cached"
    assert app.records[-1].cost_usd == 0
    assert app.records[-1].saved_usd == app.records[0].cost_usd
    metrics = get_app_state(app.app).telemetry
    assert metrics is not None
    assert (
        metrics.metrics.registry.get_sample_value(
            "lgw_cache_requests_total", {"endpoint": "embeddings", "result": "hit"}
        )
        == 1
    )


async def test_chat_requires_opt_in_and_disabled_overrides_it(
    cached: tuple[ResilientApp, MemoryRedis],
) -> None:
    app, _ = cached
    route = app.router.post("https://groq.test/v1/chat/completions").respond(200, json=COMPLETION)

    default = await app.client.post("/v1/chat/completions", json=CHAT_REQUEST)
    first = await app.client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"x-lgw-cache": "enabled"}
    )
    hit = await app.client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"x-lgw-cache": "enabled"}
    )
    disabled = await app.client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"x-lgw-cache": "disabled"}
    )

    assert [r.headers["x-lgw-cache"] for r in (default, first, hit, disabled)] == [
        "disabled",
        "miss",
        "hit",
        "disabled",
    ]
    assert route.call_count == 3


async def test_embeddings_explicit_disable_skips_existing_entry(
    cached: tuple[ResilientApp, MemoryRedis],
) -> None:
    app, _ = cached
    route = app.router.post("https://openai.test/v1/embeddings").respond(200, json=EMBEDDINGS)
    body = {"model": "openai/embedding", "input": "same"}

    await app.client.post("/v1/embeddings", json=body)
    disabled = await app.client.post(
        "/v1/embeddings", json=body, headers={"x-lgw-cache": "disabled"}
    )

    assert disabled.headers["x-lgw-cache"] == "disabled"
    assert route.call_count == 2


async def test_two_teams_in_one_org_never_share_and_copied_ciphertext_misses(
    cached: tuple[ResilientApp, MemoryRedis],
    memory_repository: MemoryKeyRepository,
) -> None:
    app, redis = cached
    route = app.router.post("https://openai.test/v1/embeddings").respond(200, json=EMBEDDINGS)
    first_key = next(iter(memory_repository.records.values()))
    second_key = issue_key(TEST_PEPPER.encode())
    memory_repository.records[second_key.key_id] = KeyRecord(
        second_key.key_id,
        hash_secret(TEST_PEPPER.encode(), second_key.full_key.split("_", 2)[-1]),
        first_key.organization_id,
        uuid.uuid4(),
    )
    body = {"model": "openai/embedding", "input": "same content"}

    await app.client.post("/v1/embeddings", json=body)
    first_redis_key = next(iter(redis.values))
    second_redis_key = first_redis_key.replace(
        str(first_key.team_id), str(memory_repository.records[second_key.key_id].team_id)
    )
    redis.values[second_redis_key] = redis.values[first_redis_key]
    second = await app.client.post(
        "/v1/embeddings",
        json=body,
        headers={"authorization": f"Bearer {second_key.full_key}"},
    )

    assert second.headers["x-lgw-cache"] == "miss"
    assert route.call_count == 2
    assert redis.values[first_redis_key] != redis.values[second_redis_key]


async def test_alias_and_concrete_model_share_same_team_entry(
    cached: tuple[ResilientApp, MemoryRedis],
) -> None:
    from llm_gateway.routing.aliases import Alias

    app, _ = cached
    app.service.catalog.aliases["fixture-embed"] = Alias.model_validate(
        {"targets": [{"model": "openai/embedding", "weight": 1}]}
    )
    route = app.router.post("https://openai.test/v1/embeddings").respond(200, json=EMBEDDINGS)
    first = await app.client.post(
        "/v1/embeddings", json={"model": "fixture-embed", "input": "same"}
    )
    second = await app.client.post(
        "/v1/embeddings", json={"model": "openai/embedding", "input": "same"}
    )

    assert first.headers["x-lgw-alias"] == "fixture-embed"
    assert second.headers["x-lgw-cache"] == "hit"
    assert route.call_count == 1


async def test_unknown_cipher_key_id_misses_instead_of_serving_data(
    cached: tuple[ResilientApp, MemoryRedis],
) -> None:
    app, redis = cached
    route = app.router.post("https://openai.test/v1/embeddings").respond(200, json=EMBEDDINGS)
    body = {"model": "openai/embedding", "input": "same"}
    await app.client.post("/v1/embeddings", json=body)
    key = next(iter(redis.values))
    redis.values[key] = b"0" * 50

    response = await app.client.post("/v1/embeddings", json=body)

    assert response.headers["x-lgw-cache"] == "miss"
    assert route.call_count == 2


async def test_lookup_trace_exposes_result_but_not_key_or_content(
    cached: tuple[ResilientApp, MemoryRedis],
) -> None:
    app, _ = cached
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry = get_app_state(app.app).telemetry
    assert telemetry is not None
    telemetry.tracer = provider.get_tracer("cache-test")
    app.router.post("https://openai.test/v1/embeddings").respond(200, json=EMBEDDINGS)
    body = {"model": "openai/embedding", "input": "PRIVATE_MARKER"}

    await app.client.post("/v1/embeddings", json=body)
    await app.client.post("/v1/embeddings", json=body)

    lookups = [item for item in exporter.get_finished_spans() if item.name == "cache.lookup"]
    assert [item.attributes["result"] for item in lookups if item.attributes] == ["miss", "hit"]
    exported = repr([(item.name, item.attributes, item.events) for item in lookups])
    assert "PRIVATE_MARKER" not in exported
    assert "lgw:cache:" not in exported
    provider.shutdown()


async def test_fallback_is_not_stored_under_original_model(
    cached: tuple[ResilientApp, MemoryRedis],
) -> None:
    app, redis = cached
    app.fallbacks("deepseek/model")
    app.service.settings.max_retries = 0
    primary = app.router.post("https://groq.test/v1/chat/completions").respond(503)
    app.router.post("https://deepseek.test/v1/chat/completions").respond(200, json=COMPLETION)

    response = await app.client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"x-lgw-cache": "enabled"}
    )

    assert response.status_code == 200
    assert response.json()["model"].startswith("deepseek/")
    assert response.headers["x-lgw-cache"] == "miss"
    assert primary.call_count == 1
    assert not redis.values


async def test_ten_concurrent_identical_requests_share_one_provider_call(
    cached: tuple[ResilientApp, MemoryRedis],
) -> None:
    app, _ = cached
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def provider(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return httpx.Response(200, json=EMBEDDINGS)

    app.router.post("https://openai.test/v1/embeddings").mock(side_effect=provider)
    body = {"model": "openai/embedding", "input": "same"}
    tasks = [asyncio.create_task(app.client.post("/v1/embeddings", json=body)) for _ in range(10)]
    await started.wait()
    await asyncio.sleep(0.02)
    release.set()
    responses = await asyncio.gather(*tasks)

    assert calls == 1
    assert [response.headers["x-lgw-cache"] for response in responses].count("hit") == 9


async def test_redis_outage_bypasses_without_provider_error(
    cached: tuple[ResilientApp, MemoryRedis],
) -> None:
    app, redis = cached
    redis.available = False
    route = app.router.post("https://openai.test/v1/embeddings").respond(200, json=EMBEDDINGS)

    response = await app.client.post(
        "/v1/embeddings", json={"model": "openai/embedding", "input": "hi"}
    )

    assert response.status_code == 200
    assert response.headers["x-lgw-cache"] == "bypass"
    assert route.call_count == 1


async def test_slow_redis_lookup_is_bounded_by_timeout(
    cached: tuple[ResilientApp, MemoryRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, redis = cached
    app.router.post("https://openai.test/v1/embeddings").respond(200, json=EMBEDDINGS)

    async def slow_lookup(key: str) -> bytes | None:
        await asyncio.sleep(1)
        return redis.values.get(key)

    monkeypatch.setattr(redis, "get", slow_lookup)
    start = time.monotonic()
    response = await app.client.post(
        "/v1/embeddings", json={"model": "openai/embedding", "input": "same"}
    )

    assert response.headers["x-lgw-cache"] == "bypass"
    assert time.monotonic() - start < 0.2


async def test_hit_skips_budget_tpm_and_lease_but_counts_rpm(
    cached: tuple[ResilientApp, MemoryRedis],
) -> None:
    from tests.conftest import OfflineLimitService

    class Guard(OfflineLimitService):
        requests = 0
        remaining = 0

        async def request_admission(
            self, team: uuid.UUID, limits: EffectiveLimits
        ) -> dict[str, str]:
            self.requests += 1
            return {}

        async def remaining_admission(
            self, team: uuid.UUID, limits: EffectiveLimits, rpm_headers: dict[str, str]
        ) -> tuple[str | None, dict[str, str]]:
            self.remaining += 1
            if self.remaining > 1:
                raise AssertionError("budget checked on a free hit")
            return None, {}

    app, _ = cached
    guard = Guard()
    state = get_app_state(app.app)
    app.app.state.gateway = replace(state, limits=guard)
    route = app.router.post("https://openai.test/v1/embeddings").respond(200, json=EMBEDDINGS)
    body = {"model": "openai/embedding", "input": "same"}

    first = await app.client.post("/v1/embeddings", json=body)
    hit = await app.client.post("/v1/embeddings", json=body)

    assert first.status_code == hit.status_code == 200
    assert hit.headers["x-lgw-cache"] == "hit"
    assert (guard.requests, guard.remaining, route.call_count) == (2, 1, 1)


@pytest.mark.parametrize("change", ["stream", "multi", "oversize", "failure"])
async def test_ineligible_responses_never_stored(
    cached: tuple[ResilientApp, MemoryRedis],
    change: str,
) -> None:
    app, redis = cached
    body = {**CHAT_REQUEST, **({"stream": True} if change == "stream" else {})}
    if change == "multi":
        body["n"] = 2
    state = get_app_state(app.app)
    if change == "oversize" and state.response_cache is not None:
        state.response_cache.max_bytes = 1
    if change == "stream":
        from tests.fixtures import STREAM, sse

        app.router.post("https://groq.test/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=b"".join(sse(*STREAM, "[DONE]")),
            )
        )
    elif change == "failure":
        app.service.settings.max_retries = 0
        app.router.post("https://groq.test/v1/chat/completions").respond(400)
    else:
        app.router.post("https://groq.test/v1/chat/completions").respond(200, json=COMPLETION)

    response = await app.client.post(
        "/v1/chat/completions", json=body, headers={"x-lgw-cache": "enabled"}
    )

    expected = "bypass" if change in {"stream", "multi"} else "miss"
    assert response.headers["x-lgw-cache"] == expected
    assert not redis.values


async def test_failed_leader_releases_followers_for_own_calls(
    cached: tuple[ResilientApp, MemoryRedis],
) -> None:
    app, _ = cached
    app.service.settings.max_retries = 0
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def provider(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return httpx.Response(400)

    app.router.post("https://openai.test/v1/embeddings").mock(side_effect=provider)
    body = {"model": "openai/embedding", "input": "same"}
    tasks = [asyncio.create_task(app.client.post("/v1/embeddings", json=body)) for _ in range(3)]
    await started.wait()
    await asyncio.sleep(0.02)
    release.set()
    responses = await asyncio.gather(*tasks)

    assert [r.status_code for r in responses] == [400] * 3
    assert calls == 3
