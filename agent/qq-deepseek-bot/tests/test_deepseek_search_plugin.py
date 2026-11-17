import asyncio
import json

import httpx

from qq_deepseek.plugins.deepseek_search import DeepSeekSearchClient


def test_official_search_builds_filters_and_compacts_results():
    async def handler(request):
        body = json.loads(request.content)
        assert request.url.path == "/v1/tools/search"
        assert "site:github.com" in body["query"]
        assert "lang:zh,en" in body["query"]
        assert "after:2026-01-01" in body["query"]
        return httpx.Response(200, json={"results": [{
            "title": "Result", "url": "https://github.com/x/y", "summary": "summary",
            "authority": 4, "rerank_score": 2.7, "site_icon": None,
        }]})
    client = DeepSeekSearchClient("key", transport=httpx.MockTransport(handler))
    result = asyncio.run(client.search(query="agent", domains=["github.com"],
                                       languages=["zh", "en"], after="2026-01-01"))
    assert result["results"][0]["authority"] == 4
    assert "site_icon" not in result["results"][0]


def test_official_fetch_rejects_private_address():
    client = DeepSeekSearchClient("key", transport=httpx.MockTransport(lambda _: None))
    try:
        asyncio.run(client.fetch("http://127.0.0.1/private"))
    except ValueError as exc:
        assert "Non-public" in str(exc)
    else:
        raise AssertionError("private URL accepted")


def test_official_search_returns_retryable_timeout():
    async def handler(request):
        raise httpx.ReadTimeout("slow", request=request)
    client = DeepSeekSearchClient("key", transport=httpx.MockTransport(handler))
    result = asyncio.run(client.search(query="test"))
    assert result["retryable"] is True
