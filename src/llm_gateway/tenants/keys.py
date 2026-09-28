"""High-entropy bearer keys: the database never receives the usable secret."""

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from typing import Literal

KEY_PATTERN = re.compile(r"^lgw_([a-z2-7]{12})_([A-Za-z0-9_-]{43})$")
ADMIN_KEY_PATTERN = re.compile(r"^lgwa_([a-z2-7]{12})_([A-Za-z0-9_-]{43})$")
KeyPrefix = Literal["lgw", "lgwa"]


@dataclass(frozen=True)
class IssuedKey:
    key_id: str
    secret_hash: bytes
    full_key: str


def hash_secret(pepper: bytes, secret: str) -> bytes:
    return hmac.digest(pepper, secret.encode("ascii"), "sha256")


def issue_key(pepper: bytes, *, prefix: KeyPrefix = "lgw") -> IssuedKey:
    key_id = base64.b32encode(secrets.token_bytes(8)).decode("ascii").lower()[:12]
    secret = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    return IssuedKey(key_id, hash_secret(pepper, secret), f"{prefix}_{key_id}_{secret}")


def parse_key(value: str, *, prefix: KeyPrefix = "lgw") -> tuple[str, str] | None:
    pattern = KEY_PATTERN if prefix == "lgw" else ADMIN_KEY_PATTERN
    match = pattern.fullmatch(value)
    if match is None:
        return None
    try:
        if len(base64.urlsafe_b64decode(match[2] + "=")) != 32:
            return None
    except ValueError:
        return None
    return match[1], match[2]


def verify_hash(expected: bytes | None, actual: bytes) -> bool:
    # Unknown IDs still cost one digest comparison; only the public ID indexes the database.
    return hmac.compare_digest(
        expected if expected is not None else bytes(hashlib.sha256().digest_size), actual
    )
