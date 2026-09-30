"""Default endpoints shared by configuration and pool creation; no runtime dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm_gateway.schemas.common import ProviderName

DEFAULT_BASE_URLS: dict[ProviderName, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "openai": "https://api.openai.com/v1",
    "zai": "https://api.z.ai/api/paas/v4",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}

# Reviewer live evidence (2026-09-30): queued Kimi answered in 180.7 s.
# Trial queueing can take minutes; keep other providers on global timeouts.
DEFAULT_READ_TIMEOUTS: dict[ProviderName, float] = {"nvidia": 300.0}
