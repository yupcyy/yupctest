"""Async recording, grouping and optional USD cost estimates for model usage."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from qq_deepseek.core.usage import TokenRates, TokenUsage
from qq_deepseek.storage.usage import SQLiteUsageStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UsageSummary:
    requests: int
    prompt_tokens: int
    completion_tokens: int
    cache_hit_tokens: int
    cache_miss_tokens: int
    missing_cache_reports: int
    estimated_cost_usd: Decimal | None
    unpriced_requests: int


class UsageService:
    def __init__(
        self,
        store: SQLiteUsageStore,
        rates_by_model: Mapping[str, TokenRates] | None = None,
    ):
        self.store = store
        self.rates_by_model = dict(rates_by_model or {})

    async def record(
        self,
        response: Any,
        *,
        model: str,
        conversation_id: str,
        operation: str = "chat",
    ) -> TokenUsage | None:
        try:
            usage = TokenUsage.from_response(
                response, model=model, conversation_id=conversation_id,
                operation=operation,
            )
            if usage is None:
                logger.warning("Missing usage from model=%s", model)
                return None
            await asyncio.to_thread(self.store.insert, usage)
            logger.info(
                "usage model=%s conversation=%s input=%d output=%d hit=%s miss=%s",
                model, conversation_id, usage.prompt_tokens, usage.completion_tokens,
                usage.cache_hit_tokens, usage.cache_miss_tokens,
            )
            return usage
        except Exception:
            # A database outage must not prevent the QQ bot from sending its answer.
            logger.exception("Unable to persist LLM usage")
            return None

    async def summary(
        self,
        *,
        since: str | None = None,
        until: str | None = None,
        conversation_id: str | None = None,
        limit: int = 10000,
    ) -> UsageSummary:
        records = await asyncio.to_thread(
            self.store.rows, since=since, until=until,
            conversation_id=conversation_id, limit=limit,
        )
        total_cost = Decimal(0)
        unpriced = 0
        for record in records:
            rates = self.rates_by_model.get(record.model)
            cost = rates.estimate_usd(record) if rates else None
            if cost is None:
                unpriced += 1
            else:
                total_cost += cost
        return UsageSummary(
            requests=len(records),
            prompt_tokens=sum(r.prompt_tokens for r in records),
            completion_tokens=sum(r.completion_tokens for r in records),
            cache_hit_tokens=sum(r.cache_hit_tokens or 0 for r in records),
            cache_miss_tokens=sum(r.cache_miss_tokens or 0 for r in records),
            missing_cache_reports=sum(
                r.cache_hit_tokens is None or r.cache_miss_tokens is None
                for r in records
            ),
            estimated_cost_usd=total_cost if unpriced == 0 else None,
            unpriced_requests=unpriced,
        )
