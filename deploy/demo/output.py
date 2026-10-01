"""Forward child diagnostics with a second credential filter before they reach logs."""

import re
import subprocess
import sys
import time
from threading import Lock, Thread
from typing import BinaryIO, TextIO
from weakref import WeakKeyDictionary

_KEY = re.compile(r"lgw[a]?_[A-Za-z0-9_-]+")
_CREDENTIAL_URL = re.compile(r"(?i)\b((?:postgres(?:ql)?(?:\+asyncpg)?|rediss?)://)[^\s]+@")
_WRITERS = Lock()
_READERS: WeakKeyDictionary[subprocess.Popen[bytes], tuple[Thread, ...]] = WeakKeyDictionary()


def forward_output(name: str, process: subprocess.Popen[bytes]) -> None:
    readers: list[Thread] = []
    for source, destination in ((process.stdout, sys.stdout), (process.stderr, sys.stderr)):
        if source is None:
            continue
        reader = Thread(target=_forward_lines, args=(name, source, destination), daemon=True)
        readers.append(reader)
        reader.start()
    _READERS[process] = tuple(readers)


def drain_output(process: subprocess.Popen[bytes], *, timeout: float = 2) -> None:
    """Flush final diagnostics before reporting an exit, without hanging on inherited pipes."""
    deadline = time.monotonic() + timeout
    for reader in _READERS.pop(process, ()):
        reader.join(timeout=max(0, deadline - time.monotonic()))


def redact(line: str) -> str:
    return _KEY.sub("[redacted]", _CREDENTIAL_URL.sub(r"\1[redacted]@", line))


def _forward_lines(name: str, source: BinaryIO, destination: TextIO) -> None:
    with source:
        for line in source:
            safe = redact(line.decode("utf-8", errors="replace").rstrip("\r\n"))
            with _WRITERS:
                print(f"[{name}] {safe}", file=destination, flush=True)
