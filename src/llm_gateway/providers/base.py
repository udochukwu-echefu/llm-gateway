from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from llm_gateway.schemas.chat import ChatCompletion, ChatCompletionChunk, ChatCompletionRequest
from llm_gateway.schemas.common import ProviderName
from llm_gateway.schemas.embeddings import EmbeddingRequest, EmbeddingResponse


@dataclass(frozen=True)
class Capabilities:
    supports_embeddings: bool
    supports_stream_usage: bool
    supports_developer: bool
    supports_max_completion_tokens: bool
    unsupported_parameters: frozenset[str] = frozenset()
    supports_multiple_choices: bool = True
    supports_json_schema: bool = True
    unsupported_embedding_parameters: frozenset[str] = frozenset()
    supports_token_inputs: bool = True
    supports_message_names: bool = True


class ChatStream(Protocol):
    """Canonical chunks from a provider stream; the owner must close the connection."""

    def __aiter__(self) -> AsyncIterator[ChatCompletionChunk]: ...
    async def aclose(self) -> None: ...


class ProviderAdapter(Protocol):
    name: ProviderName
    capabilities: Capabilities

    async def chat(self, request: ChatCompletionRequest, model: str) -> ChatCompletion: ...
    async def open_chat_stream(self, request: ChatCompletionRequest, model: str) -> ChatStream: ...
    async def embed(self, request: EmbeddingRequest, model: str) -> EmbeddingResponse: ...
