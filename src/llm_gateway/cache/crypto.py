"""Authenticated encryption binds each cached answer to exactly one Redis address."""

import base64
import binascii
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import SecretStr


class CacheCipher:
    def __init__(self, secret: SecretStr) -> None:
        try:
            raw = base64.b64decode(secret.get_secret_value(), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Cache encryption key must be base64-encoded 32 bytes") from exc
        if len(raw) != 32:
            raise ValueError("Cache encryption key must be base64-encoded 32 bytes")
        self._aes = AESGCM(raw)
        self.key_id = hashlib.sha256(raw).hexdigest()[:16]

    def seal(self, key: str, data: bytes) -> bytes:
        nonce = os.urandom(12)
        return self.key_id.encode() + nonce + self._aes.encrypt(nonce, data, key.encode())

    def open(self, key: str, envelope: bytes) -> bytes | None:
        if len(envelope) < 44 or envelope[:16] != self.key_id.encode():
            return None
        try:
            return self._aes.decrypt(envelope[16:28], envelope[28:], key.encode())
        except InvalidTag:
            return None
