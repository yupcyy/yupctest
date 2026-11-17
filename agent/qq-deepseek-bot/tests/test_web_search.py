import asyncio

from qq_deepseek.tools.web.search import WebSearchTool, _DDGParser


def test_search_parser_extracts_public_result():
    parser = _DDGParser()
    parser.feed('''<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fv">标题</a>
        <a class="result__snippet">一段摘要</a>''')
    assert parser.results == [{"title":"标题", "url":"https://example.com/v", "snippet":"一段摘要"}]


def test_search_uses_fallback_when_primary_fails(monkeypatch):
    tool = WebSearchTool("test", timeout=0.01)
    monkeypatch.setattr(tool, "_request", lambda _query: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(tool, "_request_bing_rss", lambda _query: [
        {"title": "Bing", "url": "https://example.com", "snippet": "ok"}
    ])
    result = asyncio.run(tool.execute({"query": "test"}))
    assert result["results"][0]["title"] == "Bing"
    assert result["partial"] is True


def test_search_returns_structured_error_when_all_sources_fail(monkeypatch):
    tool = WebSearchTool("test", timeout=0.01)
    def fail(_query):
        raise RuntimeError("offline")
    monkeypatch.setattr(tool, "_request", fail)
    monkeypatch.setattr(tool, "_request_bing_rss", fail)
    result = asyncio.run(tool.execute({"query": "test"}))
    assert result["results"] == []
    assert result["retryable"] is True
