import httpx
import pytest
import respx

from llm_gateway.providers.registry import ADAPTER_TYPES
from llm_gateway.schemas.chat import ChatCompletionRequest
from llm_gateway.schemas.common import ProviderName
from tests.fixtures import COMPLETION, STREAM, sse


@pytest.mark.parametrize("name", tuple(ADAPTER_TYPES))
async def test_adapters_return_canonical_models(name: ProviderName) -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": f"{name}/model",
            "messages": [{"role": "user", "content": "Hi"}],
        }
    )
    with respx.mock(base_url="https://provider.test/v1") as router:
        route = router.post("/chat/completions").respond(200, json=COMPLETION)
        async with httpx.AsyncClient(base_url="https://provider.test/v1") as http:
            adapter = ADAPTER_TYPES[name](http)

            result = await adapter.chat(request, "model")
            route.respond(200, content=b"".join(sse(*STREAM, "[DONE]")))
            stream = await adapter.open_chat_stream(request, "model")
            try:
                chunks = [chunk async for chunk in stream]
            finally:
                await stream.aclose()

    assert result.model == f"{name}/{COMPLETION['model']}"
    assert result.choices[0].message.content == "hi"
    assert chunks[0].choices[0].delta.content == "h"
    assert chunks[-1].choices[0].finish_reason == "stop"
