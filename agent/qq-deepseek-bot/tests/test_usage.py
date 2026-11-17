import asyncio
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from qq_deepseek.core.usage import TokenRates, TokenUsage
from qq_deepseek.storage.usage import SQLiteUsageStore
from qq_deepseek.services.usage_service import UsageService


class UsageTests(unittest.TestCase):
    def test_parse_response_and_cost(self):
        response = SimpleNamespace(usage=SimpleNamespace(
            prompt_tokens=100, completion_tokens=20,
            prompt_cache_hit_tokens=60, prompt_cache_miss_tokens=40,
        ))
        record = TokenUsage.from_response(response, model="test", conversation_id="private:1")
        self.assertEqual(record.total_tokens, 120)
        self.assertEqual(record.cache_hit_ratio, 0.6)
        rates = TokenRates(Decimal("1"), Decimal("0.1"), Decimal("2"))
        self.assertEqual(rates.estimate_usd(record), Decimal("86") / Decimal("1000000"))

    def test_missing_usage_is_not_fabricated(self):
        self.assertIsNone(TokenUsage.from_response({}, model="test", conversation_id="x"))

    def test_storage_summary_and_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteUsageStore(Path(directory) / "data" / "usage.db")
            service = UsageService(store, {
                "test": TokenRates(Decimal("1"), Decimal("0.1"), Decimal("2")),
            })
            response = {"usage": {
                "prompt_tokens": 100, "completion_tokens": 20,
                "prompt_cache_hit_tokens": 60, "prompt_cache_miss_tokens": 40,
            }}
            saved = asyncio.run(service.record(response, model="test", conversation_id="g1:u2"))
            self.assertIsNotNone(saved)
            self.assertFalse(store.insert(saved))
            stats = asyncio.run(service.summary(conversation_id="g1:u2"))
            self.assertEqual(stats.requests, 1)
            self.assertEqual(stats.prompt_tokens, 100)
            self.assertEqual(stats.estimated_cost_usd, Decimal("0.000086"))
            self.assertEqual(asyncio.run(service.summary(conversation_id="other")).requests, 0)
            store.close()

    def test_missing_cache_fields_not_zero_cost(self):
        record = TokenUsage.from_response({"usage": {"prompt_tokens": 10, "completion_tokens": 2}}, model="test", conversation_id="u")
        self.assertIsNone(TokenRates(Decimal("1"), Decimal("0.1"), Decimal("2")).estimate_usd(record))


if __name__ == "__main__":
    unittest.main()
