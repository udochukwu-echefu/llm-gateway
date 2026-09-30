"""Opaque versions include a revision so repeated writes cannot revive an old token."""

import hashlib
import json
import re

from llm_gateway.errors import GatewayError
from llm_gateway.tenants.models import Organization, Team

POLICY_COLUMNS = ("model_patterns", "guardrail_actions", "allowed_regions")


def version(owner: Organization | Team, column: str) -> str:
    value = getattr(owner, column)
    revision = getattr(owner, column + "_revision")
    payload = json.dumps([str(owner.id), column, revision, value], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def check_version(owner: Organization | Team, column: str, expected: str | None) -> None:
    if expected is None:
        return
    if not re.fullmatch(r'"[0-9a-f]{64}"', expected):
        raise ValueError("If-Match must be a quoted policy version")
    if expected != f'"{version(owner, column)}"':
        raise GatewayError(
            412,
            "Someone else changed this policy. Reload to see their version.",
            type="invalid_request_error",
            code="policy_version_conflict",
        )


def advance_version(owner: Organization | Team, column: str) -> None:
    setattr(owner, column + "_revision", getattr(owner, column + "_revision") + 1)
