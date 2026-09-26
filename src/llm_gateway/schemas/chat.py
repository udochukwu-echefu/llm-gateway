"""The canonical chat format: OpenAI's Chat Completions API (docs/adr/0001, 0003).

Request models are strict (they validate what clients send). Response models are
tolerant (they describe what we rely on from providers and keep everything else).
"""

from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from llm_gateway.schemas.common import (
    ProviderName,
    ProxiedRequest,
    RequestModel,
    ResponseModel,
    ZeroOmittingResponseModel,
)

NAME_PATTERN = r"^[a-zA-Z0-9_-]{1,64}$"

# ---------------------------------------------------------------------------
# Request: message content parts
# ---------------------------------------------------------------------------


class TextPart(RequestModel):
    type: Literal["text"]
    text: str


class ImageURL(RequestModel):
    url: str = Field(min_length=1)  # https URL or a base64 data: URL
    detail: Literal["auto", "low", "high"] | None = None


class ImagePart(RequestModel):
    type: Literal["image_url"]
    image_url: ImageURL


class InputAudio(RequestModel):
    data: str = Field(min_length=1)  # base64
    format: Literal["wav", "mp3"]


class AudioPart(RequestModel):
    type: Literal["input_audio"]
    input_audio: InputAudio


class FileData(RequestModel):
    file_data: str | None = None  # base64 data: URL
    file_id: str | None = None
    filename: str | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> Self:
        if (self.file_data is None) == (self.file_id is None):
            raise ValueError("provide exactly one of file_data or file_id")
        return self


class FilePart(RequestModel):
    type: Literal["file"]
    file: FileData


class RefusalPart(RequestModel):
    type: Literal["refusal"]
    refusal: str


# "discriminator" tells Pydantic to pick the right class by looking at one field,
# instead of trying every class in turn and reporting every failure.
UserContentPart = Annotated[
    TextPart | ImagePart | AudioPart | FilePart, Field(discriminator="type")
]
AssistantContentPart = Annotated[TextPart | RefusalPart, Field(discriminator="type")]

# ---------------------------------------------------------------------------
# Request: messages
# ---------------------------------------------------------------------------


class FunctionCall(RequestModel):
    name: str
    arguments: str  # a JSON document, encoded as a string, exactly as the model wrote it


class ToolCall(RequestModel):
    id: str
    type: Literal["function"]
    function: FunctionCall


class SystemMessage(RequestModel):
    role: Literal["system"]
    content: str | list[TextPart]
    name: str | None = None


class DeveloperMessage(RequestModel):
    role: Literal["developer"]
    content: str | list[TextPart]
    name: str | None = None


class UserMessage(RequestModel):
    role: Literal["user"]
    content: str | list[UserContentPart]
    name: str | None = None


class AssistantMessage(RequestModel):
    """A previous model reply, sent back as conversation history.

    Clients usually append the provider's response message as-is, and that carries
    output-only fields (`annotations`, DeepSeek's `reasoning_content`, ...). Rejecting
    those would break the most common agent loop, so unknown fields are dropped here,
    and only here.
    """

    model_config = ConfigDict(extra="ignore")

    role: Literal["assistant"]
    content: str | list[AssistantContentPart] | None = None
    refusal: str | None = None
    name: str | None = None
    tool_calls: list[ToolCall] | None = None

    @model_validator(mode="after")
    def _has_content_or_tool_calls(self) -> Self:
        if self.content is None and not self.tool_calls:
            raise ValueError("an assistant message needs content or tool_calls")
        return self


class ToolMessage(RequestModel):
    role: Literal["tool"]
    content: str | list[TextPart]
    tool_call_id: str = Field(min_length=1)


Message = Annotated[
    SystemMessage | DeveloperMessage | UserMessage | AssistantMessage | ToolMessage,
    Field(discriminator="role"),
]

# ---------------------------------------------------------------------------
# Request: tools and output format
# ---------------------------------------------------------------------------


class FunctionDefinition(RequestModel):
    name: str = Field(pattern=NAME_PATTERN)
    description: str | None = None
    parameters: dict[str, Any] | None = None  # a JSON Schema
    strict: bool | None = None


class Tool(RequestModel):
    type: Literal["function"]
    function: FunctionDefinition


class NamedFunction(RequestModel):
    name: str


class NamedToolChoice(RequestModel):
    type: Literal["function"]
    function: NamedFunction


class TextFormat(RequestModel):
    type: Literal["text"]


class JSONObjectFormat(RequestModel):
    type: Literal["json_object"]


class JSONSchemaSpec(RequestModel):
    name: str = Field(pattern=NAME_PATTERN)
    description: str | None = None
    # `schema` would shadow a BaseModel attribute, so the Python name differs from the JSON one.
    schema_: dict[str, Any] | None = Field(default=None, alias="schema")
    strict: bool | None = None


class JSONSchemaFormat(RequestModel):
    type: Literal["json_schema"]
    json_schema: JSONSchemaSpec


ResponseFormat = Annotated[
    TextFormat | JSONObjectFormat | JSONSchemaFormat, Field(discriminator="type")
]


class StreamOptions(RequestModel):
    include_usage: bool | None = None


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class ChatCompletionRequest(ProxiedRequest):
    model: str = Field(min_length=1, max_length=256)
    messages: list[Message] = Field(min_length=1)
    stream: bool = False
    stream_options: StreamOptions | None = None

    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1)
    max_completion_tokens: int | None = Field(default=None, ge=1)
    n: int | None = Field(default=None, ge=1, le=128)
    stop: str | Annotated[list[str], Field(min_length=1, max_length=4)] | None = None
    seed: int | None = None
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    logprobs: bool | None = None
    top_logprobs: int | None = Field(default=None, ge=0, le=20)
    logit_bias: dict[str, Annotated[int, Field(ge=-100, le=100)]] | None = None

    tools: list[Tool] | None = Field(default=None, max_length=128)
    tool_choice: Literal["none", "auto", "required"] | NamedToolChoice | None = None
    parallel_tool_calls: bool | None = None
    response_format: ResponseFormat | None = None

    # Values differ by provider and change often, so only the shape is checked here.
    reasoning_effort: str | None = Field(default=None, pattern=r"^[a-z]{1,16}$")
    service_tier: str | None = Field(default=None, pattern=r"^[a-z_]{1,32}$")
    user: str | None = Field(default=None, max_length=256)
    safety_identifier: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def _consistent_options(self) -> Self:
        if self.stream_options is not None and not self.stream:
            raise ValueError("stream_options is only allowed when stream is true")
        if self.top_logprobs is not None and not self.logprobs:
            raise ValueError("top_logprobs requires logprobs to be true")
        if self.tool_choice not in (None, "none") and not self.tools:
            raise ValueError("tool_choice requires tools")
        return self

    @property
    def client_wants_stream_usage(self) -> bool:
        return bool(self.stream_options and self.stream_options.include_usage)

    def to_upstream(self, provider: ProviderName) -> dict[str, Any]:
        payload = super().to_upstream(provider)
        if self.stream:
            # Always ask for token usage: the gateway needs it for cost tracking even when
            # the client didn't ask. The relay removes it again if the client didn't want it.
            payload["stream_options"] = {
                **(payload.get("stream_options") or {}),
                "include_usage": True,
            }
        return payload


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------


class PromptTokensDetails(ResponseModel):
    cached_tokens: int | None = None


class CompletionTokensDetails(ResponseModel):
    reasoning_tokens: int | None = None


class Usage(ZeroOmittingResponseModel):
    # Protobuf JSON omits zero-valued counters within a present usage object.
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_tokens_details: PromptTokensDetails | None = None
    completion_tokens_details: CompletionTokensDetails | None = None


class ResponseFunctionCall(ResponseModel):
    name: str
    arguments: str


class ResponseToolCall(ResponseModel):
    id: str
    type: str = "function"
    function: ResponseFunctionCall


class ResponseMessage(ResponseModel):
    role: str = "assistant"
    content: str | None = None
    reasoning_content: str | None = None
    refusal: str | None = None
    tool_calls: list[ResponseToolCall] | None = None


class Choice(ZeroOmittingResponseModel):
    index: int = 0  # Protobuf JSON omits zero; this is a choice ID, not its array position.
    message: ResponseMessage
    # A string, not a fixed list: providers use values beyond OpenAI's.
    finish_reason: str | None = None
    logprobs: dict[str, Any] | None = None


class ChatCompletion(ResponseModel):
    id: str
    object: str = "chat.completion"
    created: int | None = None
    model: str
    choices: list[Choice]
    usage: Usage | None = None
    system_fingerprint: str | None = None


class ToolCallFunctionDelta(ResponseModel):
    name: str | None = None
    arguments: str | None = None


class ToolCallDelta(ZeroOmittingResponseModel):
    index: int = 0  # Protobuf omits zero; tool-call IDs persist across sparse stream chunks.
    id: str | None = None
    type: str | None = None
    function: ToolCallFunctionDelta | None = None


class Delta(ResponseModel):
    """The new piece of the message in one streamed chunk."""

    role: str | None = None
    content: str | None = None
    reasoning_content: str | None = None
    refusal: str | None = None
    tool_calls: list[ToolCallDelta] | None = None


class ChunkChoice(ZeroOmittingResponseModel):
    index: int = 0  # Protobuf omits zero; streamed choice IDs need not match array positions.
    delta: Delta
    finish_reason: str | None = None
    logprobs: dict[str, Any] | None = None


class ChatCompletionChunk(ResponseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int | None = None
    model: str
    choices: list[ChunkChoice]
    usage: Usage | None = None


class StreamErrorEvent(ResponseModel):
    """What some providers send instead of a chunk when they fail mid-stream."""

    error: dict[str, Any]
