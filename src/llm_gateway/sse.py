"""Server-Sent Events: the text format providers use to stream a response piece by piece.

A stream looks like this, where each blank line ends one event:

    data: {"id": "1", "choices": [...]}

    data: [DONE]

The network delivers bytes in arbitrary pieces, not whole events. One network chunk can
hold half an event, or three events, or stop in the middle of a multi-byte character.
The decoder buffers until it has whole events.
"""

import codecs
import json
from dataclasses import dataclass

from llm_gateway.errors import GatewayError, error_body

DONE = "[DONE]"


@dataclass(frozen=True)
class ServerSentEvent:
    data: str
    event: str | None = None
    id: str | None = None


class SSEDecoder:
    def __init__(self) -> None:
        # Incremental, so a character split across two network chunks decodes correctly.
        self._text = codecs.getincrementaldecoder("utf-8")()
        self._buffer = ""
        self._data: list[str] = []
        self._event: str | None = None
        self._id: str | None = None

    def feed(self, chunk: bytes) -> list[ServerSentEvent]:
        """Add bytes from the network and return every event they complete."""
        self._buffer += self._text.decode(chunk)
        events: list[ServerSentEvent] = []
        # Everything after the last newline is an incomplete line: keep it for next time.
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            event = self._process_line(line.removesuffix("\r"))
            if event is not None:
                events.append(event)
        return events

    def _process_line(self, line: str) -> ServerSentEvent | None:
        if not line:  # a blank line ends the event
            if not self._data:
                return None
            event = ServerSentEvent("\n".join(self._data), self._event, self._id)
            self._data, self._event = [], None
            return event
        if line.startswith(":"):  # a comment, often sent as a keep-alive
            return None
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "data":
            self._data.append(value)
        elif field == "event":
            self._event = value
        elif field == "id":
            self._id = value
        return None


def encode_data(data: str) -> bytes:
    return f"data: {data}\n\n".encode()


def encode_error(error: GatewayError) -> bytes:
    """An error event: OpenAI SDKs raise an exception when they receive one."""
    return encode_data(json.dumps(error_body(error.message, type=error.type, code=error.code)))
