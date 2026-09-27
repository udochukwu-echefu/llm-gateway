import json
import logging

import pytest
import structlog

from llm_gateway.logging import configure_logging


def test_uvicorn_stdlib_and_structlog_are_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "json")
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "ordinary.library"):
        logging.getLogger(name).info("startup shutdown %s", name)
    structlog.get_logger().error("application_error")

    output = capsys.readouterr()
    lines = [json.loads(line) for line in (output.out + output.err).splitlines()]
    assert len(lines) == 5
    assert all("event" in line and "timestamp" in line for line in lines)
