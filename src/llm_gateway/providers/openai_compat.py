from typing import Any

import httpx

from llm_gateway.errors import GatewayError
from llm_gateway.providers.base import Capabilities, ChatStream
from llm_gateway.providers.stream import CompatibleChatStream
from llm_gateway.providers.transport import UpstreamClient, read_model
from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionChunk, ChatCompletionRequest
from llm_gateway.schemas.common import ProviderName
from llm_gateway.schemas.embeddings import EmbeddingRequest, EmbeddingResponse


class OpenAICompatibleAdapter:
    """Shared wire protocol; subclasses declare only verified provider differences."""

    name: ProviderName
    capabilities: Capabilities
    base_url: str
    request_id_header: str | None = "x-request-id"

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._transport = UpstreamClient(http, self.request_id_header)

    async def chat(self, request: ChatCompletionRequest, model: str) -> ChatCompletion:
        payload = self._chat_payload(request, model)
        payload["stream"] = False
        response = await self._transport.open("chat/completions", payload)
        result = await read_model(response, ChatCompletion)
        self.normalize_chat(result)
        return result

    async def open_chat_stream(self, request: ChatCompletionRequest, model: str) -> ChatStream:
        payload = self._chat_payload(request, model)
        payload["stream"] = True
        if self.capabilities.supports_stream_usage:
            payload["stream_options"] = {"include_usage": True}
        response = await self._transport.open("chat/completions", payload)
        return CompatibleChatStream(response, self.normalize_chat)

    async def embed(self, request: EmbeddingRequest, model: str) -> EmbeddingResponse:
        if not self.capabilities.supports_embeddings:
            raise self.unsupported("embeddings")
        payload = request.to_upstream(self.name)
        self._reject_parameters(payload, self.capabilities.unsupported_embedding_parameters)
        if not self.capabilities.supports_token_inputs and not (
            isinstance(request.input, str) or all(isinstance(x, str) for x in request.input)
        ):
            raise self.unsupported("input (token IDs)")
        payload["model"] = model
        response = await self._transport.open("embeddings", payload)
        result = await read_model(response, EmbeddingResponse)
        result.model = f"{self.name}/{result.model}"
        return result

    def normalize_chat(self, result: ChatCompletion | ChatCompletionChunk) -> None:
        result.model = f"{self.name}/{result.model}"

    def unsupported(self, parameter: str) -> GatewayError:
        return GatewayError(
            400,
            f"Parameter '{parameter}' is unsupported by provider '{self.name}'.",
            type="invalid_request_error",
            code="unsupported_parameter",
        )

    def _chat_payload(self, request: ChatCompletionRequest, model: str) -> dict[str, Any]:
        payload = request.to_upstream(self.name)
        payload["model"] = model
        self._reject_parameters(payload, self.capabilities.unsupported_parameters)
        if not self.capabilities.supports_multiple_choices and request.n not in (None, 1):
            raise self.unsupported("n (only 1 is supported)")
        if not self.capabilities.supports_json_schema and (
            request.response_format and request.response_format.type == "json_schema"
        ):
            raise self.unsupported("response_format.json_schema")
        self._translate_messages(payload)
        if (
            not self.capabilities.supports_max_completion_tokens
            and request.max_completion_tokens is not None
        ):
            if request.max_tokens is not None:
                raise self.unsupported("max_completion_tokens with max_tokens")
            payload["max_tokens"] = payload.pop("max_completion_tokens")
        if not self.capabilities.supports_stream_usage:
            if request.client_wants_stream_usage:
                raise self.unsupported("stream_options.include_usage")
            payload.pop("stream_options", None)
        return payload

    def _translate_messages(self, payload: dict[str, Any]) -> None:
        for message in payload["messages"]:
            if "messages[].name" in self.capabilities.unsupported_parameters and (
                "name" in message
            ):
                raise self.unsupported("messages[].name")
            if not self.capabilities.supports_developer and message["role"] == "developer":
                message["role"] = "system"

    def _reject_parameters(self, payload: dict[str, Any], parameters: frozenset[str]) -> None:
        for parameter in sorted(parameters):
            if parameter in payload:
                raise self.unsupported(parameter)
