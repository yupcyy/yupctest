"""Search public web pages without requiring a search-provider account."""
import asyncio
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from qq_deepseek.tools.base import Tool


class WebSearchTool(Tool):
    name = "web_search"
    description = "搜索公开网页及无需登录即可索引的社交/视频页面。先看结果摘要与链接，只有确有必要时再用 web_fetch 阅读。"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "简洁、具体的搜索关键词，最多128字符"},
            "domains": {"type":"array", "items":{"type":"string"}, "maxItems":5,
                        "description":"可选网站域名，如 bilibili.com、zhihu.com、weibo.com、douyin.com、youtube.com、reddit.com"}
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __init__(self, api_key: str, *, max_results: int = 5, timeout: float = 8.0):
        if not api_key:
            raise ValueError("Missing DeepSeek API key")
        self.api_key = api_key
        self.max_results = min(10, max(1, max_results))
        self.timeout = timeout

    def _request(self, query: str) -> str:
        request = Request("https://html.duckduckgo.com/html/?q=" + quote_plus(query),
                          headers={"User-Agent":"Mozilla/5.0 (compatible; DaFeiYu/1.0)"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read(1_000_001)
                if len(data) > 1_000_000:
                    raise ValueError("Search response too large")
                return data.decode("utf-8", "replace")
        except HTTPError as exc:
            raise RuntimeError(f"Search HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("Search API network error") from exc

    def _request_bing_rss(self, query: str) -> list[dict]:
        request = Request("https://www.bing.com/search?format=rss&q=" + quote_plus(query),
                          headers={"User-Agent":"Mozilla/5.0 (compatible; DaFeiYu/1.0)"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read(1_000_001)
            root = ET.fromstring(data)
            return [{"title":(item.findtext("title") or "")[:250],
                     "url":(item.findtext("link") or "")[:2000],
                     "snippet":(item.findtext("description") or "")[:800]}
                    for item in root.findall(".//item")[:self.max_results]]
        except (HTTPError, URLError, ET.ParseError) as exc:
            raise RuntimeError("Fallback search unavailable") from exc

    async def execute(self, arguments: dict) -> dict:
        query = arguments["query"].strip()
        if not (1 <= len(query) <= 128):
            raise ValueError("query must contain 1–128 characters")
        domains = arguments.get("domains") or []
        clean_domains = []
        for domain in domains:
            host = str(domain).lower().strip().removeprefix("www.")
            if not host or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in host):
                raise ValueError("Invalid domain filter")
            clean_domains.append(host)
        effective = query + (" (" + " OR ".join(f"site:{d}" for d in clean_domains) + ")" if clean_domains else "")
        errors = []
        results = []
        try:
            html = await asyncio.to_thread(self._request, effective)
            parser = _DDGParser(); parser.feed(html)
            results = parser.results[:self.max_results]
        except (RuntimeError, OSError, ValueError) as exc:
            errors.append(type(exc).__name__)
        if not results:
            try:
                results = await asyncio.to_thread(self._request_bing_rss, effective)
            except (RuntimeError, OSError, ValueError) as exc:
                errors.append(type(exc).__name__)
        if results:
            return {"query": query, "results": results, "partial": bool(errors)}
        return {"query": query, "results": [], "error": "公开搜索源暂时不可用", "details": errors[:2], "retryable": True}


class _DDGParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.results=[]; self.current=None; self.capture=None
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs); cls=attrs.get("class", "")
        if tag == "a" and "result__a" in cls:
            url=attrs.get("href", "")
            if "uddg=" in url: url=parse_qs(urlsplit(url).query).get("uddg", [url])[0]
            self.current={"title":"", "url":url[:2000], "snippet":""}; self.capture="title"
        elif self.current and tag in {"a","div"} and "result__snippet" in cls: self.capture="snippet"
    def handle_data(self, data):
        if self.current and self.capture: self.current[self.capture] += data
    def handle_endtag(self, tag):
        if self.current and self.capture == "title" and tag == "a": self.capture=None
        elif self.current and self.capture == "snippet" and tag in {"a","div"}:
            self.current={k:(v.strip()[:800] if isinstance(v,str) else v) for k,v in self.current.items()}
            if self.current["url"].startswith(("http://","https://")): self.results.append(self.current)
            self.current=None; self.capture=None
