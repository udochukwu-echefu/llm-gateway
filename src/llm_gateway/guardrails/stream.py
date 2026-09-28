"""Restore each logical delta independently; scan generated text at stream completion."""

from collections import defaultdict
from collections.abc import AsyncIterator

from llm_gateway.guardrails.redaction import RestoreBuffer
from llm_gateway.guardrails.scheduling import inspect_large
from llm_gateway.guardrails.session import GuardrailSession
from llm_gateway.providers.base import ChatStream
from llm_gateway.schemas.chat import (
    ChatCompletionChunk,
    ChunkChoice,
    Delta,
    ToolCallDelta,
    ToolCallFunctionDelta,
)

Channel = tuple[int, str, int]


class GuardedStream:
    def __init__(self, upstream: ChatStream, session: GuardrailSession) -> None:
        self.upstream, self.session = upstream, session
        self.buffers: dict[Channel, RestoreBuffer] = {}
        self.generated: dict[Channel, list[str]] = defaultdict(list)
        self.detected = False

    def __aiter__(self) -> AsyncIterator[ChatCompletionChunk]:
        return self._chunks()

    async def aclose(self) -> None:
        try:
            await self.upstream.aclose()
        finally:
            await self._detect()

    async def _chunks(self) -> AsyncIterator[ChatCompletionChunk]:
        last: ChatCompletionChunk | None = None
        try:
            async for original in self.upstream:
                chunk = original.model_copy(deep=True)
                last = chunk
                for choice in chunk.choices:
                    self._choice(choice)
                yield chunk
            if last is not None:
                tails = self._tails()
                if tails:
                    yield last.model_copy(update={"choices": tails, "usage": None})
        finally:
            await self._detect()

    def _choice(self, choice: ChunkChoice) -> None:
        for name in ("content", "reasoning_content", "refusal"):
            value: str | None = getattr(choice.delta, name)
            channel = (choice.index, name, -1)
            if value is not None or (choice.finish_reason and channel in self.buffers):
                setattr(
                    choice.delta, name, self._text(channel, value or "", bool(choice.finish_reason))
                )
        for tool in choice.delta.tool_calls or []:
            if tool.function is not None and tool.function.arguments is not None:
                channel = (choice.index, "arguments", tool.index)
                tool.function.arguments = self._text(
                    channel, tool.function.arguments, bool(choice.finish_reason)
                )
        if choice.finish_reason:
            for channel in self.buffers:
                if (
                    channel[0] == choice.index
                    and channel[1] == "arguments"
                    and self.buffers[channel].pending
                ):
                    _append_tool(choice.delta, channel[2], self._text(channel, "", True))

    def _text(self, channel: Channel, text: str, final: bool) -> str:
        self.generated[channel].append(text)
        if channel not in self.buffers:
            self.buffers[channel] = RestoreBuffer(self.session.redactor)
        return self.buffers[channel].push(text, final=final)

    def _tails(self) -> list[ChunkChoice]:
        choices: list[ChunkChoice] = []
        for (index, name, tool_index), buffer in self.buffers.items():
            if not buffer.pending:
                continue
            delta = Delta()
            text = buffer.push("", final=True)
            if name == "arguments":
                _append_tool(delta, tool_index, text)
            else:
                setattr(delta, name, text)
            choices.append(ChunkChoice(index=index, delta=delta))
        return choices

    async def _detect(self) -> None:
        if self.detected:
            return
        self.detected = True
        texts = ["".join(parts) for parts in self.generated.values()]
        await inspect_large(lambda: self.session.detect_stream(texts), texts)
        self.generated.clear()


def _append_tool(delta: Delta, index: int, text: str) -> None:
    delta.tool_calls = [
        *(delta.tool_calls or []),
        ToolCallDelta(index=index, function=ToolCallFunctionDelta(arguments=text)),
    ]
