"""Read an external HTTP(S) page through the official DeepSeek Fetch API."""
import asyncio
import ipaddress
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from qq_deepseek.tools.base import Tool


def validate_public_url(url: str) -> str:
    if not isinstance(url, str) or not (1 <= len(url) <= 8192):
        raise ValueError("Invalid URL length")
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        _ = parsed.port  # Reject invalid port syntax.
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) URLs without credentials are allowed")
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Local addresses are forbidden")
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        if "." not in host:
            raise ValueError("Public DNS hostname required")
    else:
        if not ip.is_global:
            raise ValueError("Non-public IP addresses are forbidden")
    return url


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "读取公开网页正文并以 Markdown 返回，适合阅读搜索结果或用户提供的网页。"
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "完整的公开 http/https 网页地址"}},
        "required": ["url"],
        "additionalProperties": False,
    }

    def __init__(self, api_key: str, *, max_content_chars: int = 12000, timeout: float = 20.0):
        if not api_key:
            raise ValueError("Missing DeepSeek API key")
        self.api_key = api_key
        self.max_content_chars = max(1000, max_content_chars)
        self.timeout = timeout

    def _request(self, url: str) -> dict:
        request = Request(
            "https://api.deepseek.com/v1/tools/fetch",
            data=json.dumps({"url": url}).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read(2_000_001)
                if len(data) > 2_000_000:
                    raise ValueError("Fetch response too large")
                return json.loads(data)
        except HTTPError as exc:
            raise RuntimeError(f"Fetch API HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError("Fetch API network error") from exc

    async def execute(self, arguments: dict) -> dict:
        url = validate_public_url(arguments["url"])
        result = await asyncio.to_thread(self._request, url)
        return {
            "url": url,
            "title": str(result.get("title") or "")[:250],
            "content": str(result.get("content") or "")[:self.max_content_chars],
            "truncated": len(str(result.get("content") or "")) > self.max_content_chars,
        }
