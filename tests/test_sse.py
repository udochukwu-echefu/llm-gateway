from llm_gateway.sse import ServerSentEvent, SSEDecoder


def test_one_event_in_one_chunk() -> None:
    assert SSEDecoder().feed(b"data: hello\n\n") == [ServerSentEvent("hello")]


def test_event_split_across_chunks() -> None:
    decoder = SSEDecoder()

    assert decoder.feed(b"da") == []
    assert decoder.feed(b"ta: hel") == []
    assert decoder.feed(b"lo\n") == []
    assert decoder.feed(b"\n") == [ServerSentEvent("hello")]


def test_many_events_in_one_chunk() -> None:
    events = SSEDecoder().feed(b"data: a\n\ndata: b\n\ndata: [DONE]\n\n")

    assert [event.data for event in events] == ["a", "b", "[DONE]"]


def test_multibyte_character_split_across_chunks() -> None:
    encoded = "data: café 👋\n\n".encode()
    split_inside_emoji = encoded.index("👋".encode()) + 2
    decoder = SSEDecoder()

    events = decoder.feed(encoded[:split_inside_emoji]) + decoder.feed(encoded[split_inside_emoji:])

    assert events == [ServerSentEvent("café 👋")]


def test_crlf_line_endings() -> None:
    assert SSEDecoder().feed(b"data: x\r\n\r\n") == [ServerSentEvent("x")]


def test_comments_are_ignored() -> None:
    assert SSEDecoder().feed(b": keep-alive\n\ndata: x\n\n") == [ServerSentEvent("x")]


def test_multi_line_data_is_joined_with_newlines() -> None:
    assert SSEDecoder().feed(b"data: a\ndata: b\n\n") == [ServerSentEvent("a\nb")]


def test_event_and_id_fields() -> None:
    assert SSEDecoder().feed(b"event: error\nid: 7\ndata: x\n\n") == [
        ServerSentEvent("x", event="error", id="7")
    ]


def test_value_without_space_after_colon() -> None:
    assert SSEDecoder().feed(b"data:x\n\n") == [ServerSentEvent("x")]
