import threading

from llm_gateway.guardrails.scheduling import OFFLOAD_CHARACTERS, inspect_large


async def test_many_small_fields_offload_based_on_total_size() -> None:
    loop_thread = threading.get_ident()

    worker_thread = await inspect_large(
        threading.get_ident, ["x" * 1024] * (OFFLOAD_CHARACTERS // 1024)
    )

    assert worker_thread != loop_thread


async def test_small_inspection_stays_on_event_loop() -> None:
    loop_thread = threading.get_ident()

    actual_thread = await inspect_large(threading.get_ident, "small")

    assert actual_thread == loop_thread


async def test_large_schema_keys_also_offload() -> None:
    loop_thread = threading.get_ident()

    worker_thread = await inspect_large(threading.get_ident, {"x" * OFFLOAD_CHARACTERS: None})

    assert worker_thread != loop_thread
