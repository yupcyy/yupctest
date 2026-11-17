"""Normalize API token accounting; no network calls or external dependencies."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _nonnegative_int(value: Any, field: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


@dataclass(frozen=True, slots=True)
class TokenUsage:
    request_id: str
    created_at: str
    model: str
    conversation_id: str
    prompt_tokens: int
    completion_tokens: int
    cache_hit_tokens: int | None
    cache_miss_tokens: int | None
    operation: str = "chat"

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cache_hit_ratio(self) -> float | None:
        if self.cache_hit_tokens is None or self.prompt_tokens == 0:
            return None
        return self.cache_hit_tokens / self.prompt_tokens

    @classmethod
    def from_response(
        cls,
        response: Any,
        *,
        model: str,
        conversation_id: str,
        operation: str = "chat",
        request_id: str | None = None,
    ) -> TokenUsage | None:
        """Return None when the provider omits usage. Don't silently record zeros."""
        usage = _field(response, "usage")
        if usage is None:
            return None
        prompt = _nonnegative_int(_field(usage, "prompt_tokens"), "prompt_tokens")
        completion = _nonnegative_int(_field(usage, "completion_tokens"), "completion_tokens")
        hit_raw = _field(usage, "prompt_cache_hit_tokens")
        miss_raw = _field(usage, "prompt_cache_miss_tokens")
        hit = None if hit_raw is None else _nonnegative_int(hit_raw, "cache_hit_tokens")
        miss = None if miss_raw is None else _nonnegative_int(miss_raw, "cache_miss_tokens")
        if hit is not None and hit > prompt:
            raise ValueError("cache_hit_tokens exceeds prompt_tokens")
        if hit is not None and miss is not None and hit + miss > prompt:
            raise ValueError("cache_hit_tokens + cache_miss_tokens exceeds prompt_tokens")
        if not model or not conversation_id:
            raise ValueError("model and conversation_id are required")
        return cls(
            request_id=request_id or str(uuid4()),
            created_at=datetime.now(UTC).isoformat(timespec="seconds"),
            model=model,
            conversation_id=conversation_id,
            prompt_tokens=prompt,
            completion_tokens=completion,
            cache_hit_tokens=hit,
            cache_miss_tokens=miss,
            operation=operation,
        )


@dataclass(frozen=True, slots=True)
class TokenRates:
    """USD per 1,000,000 tokens. Provide current prices yourself."""

    uncached_input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal

    def estimate_usd(self, usage: TokenUsage) -> Decimal | None:
        """Unknown cache accounting -> no estimate rather than a false precision."""
        if usage.cache_hit_tokens is None and usage.cache_miss_tokens is None:
            return None
        hit = usage.cache_hit_tokens or 0
        miss = usage.cache_miss_tokens
        if miss is None:
            miss = usage.prompt_tokens - hit
        # Tokens absent from provider hit/miss fields are conservatively uncached.
        miss += max(0, usage.prompt_tokens - hit - miss)
        return (
            Decimal(hit) * self.cached_input_per_million
            + Decimal(miss) * self.uncached_input_per_million
            + Decimal(usage.completion_tokens) * self.output_per_million
        ) / Decimal(1_000_000)
