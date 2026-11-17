"""Official DeepSeek Search & Fetch API tools for the Pydantic AI agent."""
from __future__ import annotations

import os
import re
from typing import Annotated

import httpx
from pydantic import Field

from qq_deepseek.tools.web.fetch import validate_public_url

_DOMAIN = re.compile(r"^[a-z0-9.-]+$")
_DATE = re.compile(r"^\d{4}(?:-\d{2}-\d{2})?$")


class DeepSeekSearchClient:
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com", timeout: float = 16.0,
                 transport: httpx.AsyncBaseTransport | None = None):
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required by the search plugin")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    async def _post(self, path: str, payload: dict) -> dict:
        timeout = httpx.Timeout(self.timeout, connect=min(6.0, self.timeout))
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self.transport,
                                         headers={"Authorization": f"Bearer {self.api_key}"}) as client:
                response = await client.post(self.base_url + path, json=payload)
                response.raise_for_status()
                value = response.json()
                if not isinstance(value, dict):
                    raise ValueError("DeepSeek returned a non-object response")
                return value
        except httpx.TimeoutException:
            return {"error": "DeepSeek 智能搜索服务超时", "retryable": True}
        except httpx.HTTPStatusError as exc:
            return {"error": f"DeepSeek 智能搜索 HTTP {exc.response.status_code}",
                    "retryable": exc.response.status_code >= 500}
        except (httpx.HTTPError, ValueError) as exc:
            return {"error": f"DeepSeek 智能搜索不可用：{str(exc)[:160]}", "retryable": True}

    async def search(self, *, query: str, original_question: str = "", domains: list[str] | None = None,
                     exclude_domains: list[str] | None = None, languages: list[str] | None = None,
                     after: str = "", before: str = "", need_content: bool = False, count: int = 5) -> dict:
        query = " ".join(query.split())
        if not 1 <= len(query) <= 128:
            raise ValueError("query must contain 1-128 characters")
        operators = []
        for prefix, values in (("site:", domains or []), ("-site:", exclude_domains or [])):
            clean = []
            for raw in values[:5]:
                domain = str(raw).lower().strip().removeprefix("www.")
                if not domain or not _DOMAIN.fullmatch(domain):
                    raise ValueError("invalid domain filter")
                clean.append(prefix + domain)
            if prefix == "site:" and clean:
                operators.append(" OR ".join(clean))
            else:
                operators.extend(clean)
        if languages:
            clean_languages = [value.lower() for value in languages[:4]
                               if re.fullmatch(r"[a-z]{2,3}", value.lower())]
            if clean_languages:
                operators.append("lang:" + ",".join(clean_languages))
        for name, value in (("after", after), ("before", before)):
            if value:
                if not _DATE.fullmatch(value):
                    raise ValueError(f"{name} must be YYYY or YYYY-MM-DD")
                operators.append(f"{name}:{value}")
        effective = " ".join([query, *operators])[:512]
        payload = {"query": effective, "count": max(1, min(10, count)), "need_content": bool(need_content)}
        if original_question.strip():
            payload["ori_question"] = original_question.strip()[:128]
        result = await self._post("/v1/tools/search", payload)
        rows = result.get("results")
        if not isinstance(rows, list):
            return result
        compact = []
        for row in rows[:payload["count"]]:
            if not isinstance(row, dict):
                continue
            compact.append({key: row.get(key) for key in
                            ("title", "url", "snippet", "summary", "content", "site_name", "date",
                             "authority", "rerank_score") if row.get(key) not in (None, "")})
        return {"query": query, "effective_query": effective, "results": compact,
                "guidance": "优先引用 authority>=3 或 rerank_score>=1.5 的来源；只在确有必要时读取正文。"}

    async def fetch(self, url: str, max_chars: int = 12000) -> dict:
        url = validate_public_url(url)
        result = await self._post("/v1/tools/fetch", {"url": url})
        if "error" in result:
            return result
        content = str(result.get("content") or "")
        limit = max(1000, min(20000, max_chars))
        return {"url": url, "title": str(result.get("title") or "")[:250],
                "content": content[:limit], "truncated": len(content) > limit}


def create_tools():
    client = DeepSeekSearchClient(os.getenv("DEEPSEEK_API_KEY", "").strip(),
                                  os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))

    async def deepseek_smart_search(
        query: Annotated[str, Field(description="简洁、具体的检索式，1-128字符")],
        original_question: Annotated[str, Field(description="用户原始问题，用于改善检索理解")] = "",
        domains: Annotated[list[str] | None, Field(description="只检索这些域名，最多5个")] = None,
        exclude_domains: Annotated[list[str] | None, Field(description="排除这些域名，最多5个")] = None,
        languages: Annotated[list[str] | None, Field(description="语言代码，如 zh、en")] = None,
        after: Annotated[str, Field(description="发布日期下限：YYYY或YYYY-MM-DD")] = "",
        before: Annotated[str, Field(description="发布日期上限：YYYY或YYYY-MM-DD")] = "",
        need_content: Annotated[bool, Field(description="是否同时返回页面正文；默认关闭以节省Token")] = False,
        count: Annotated[int, Field(ge=1, le=10, description="结果数量")] = 5,
    ) -> dict:
        """使用 DeepSeek 官方搜索引擎检索实时网页，并返回质量、权威性和时效性信号。"""
        return await client.search(query=query, original_question=original_question, domains=domains,
                                   exclude_domains=exclude_domains, languages=languages, after=after,
                                   before=before, need_content=need_content, count=count)

    async def deepseek_read_page(
        url: Annotated[str, Field(description="从搜索结果或用户消息中选择的公开HTTP(S)链接")],
        max_chars: Annotated[int, Field(ge=1000, le=20000, description="返回正文字符上限")] = 12000,
    ) -> dict:
        """仅在摘要不足以回答时，使用 DeepSeek 官方 Fetch API读取一个公开网页正文。"""
        return await client.fetch(url, max_chars)

    return [deepseek_smart_search, deepseek_read_page]
