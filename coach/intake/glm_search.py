# -*- coding: utf-8 -*-
"""检索层：智谱GLM + 内置web_search插件。

GLM的 /chat/completions 接口支持在请求里加 `tools: [{"type": "web_search", ...}]`，
模型会自己发起搜索并把结果揉进回答里，同时（视模型版本而定）在
`message.tool_calls` 里附带命中的网页列表（title/link/content摘要）。
这里做了防御性解析：结构对不上时退化为只用回答正文，不中断整条流水线
——搜索层的产出本来就是给起草层（DeepSeek）参考的原始材料，不是最终产物，
容错优先于完美解析。

纯标准库实现，风格与 core/llm_client.py 保持一致（不引入openai sdk）。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from intake.search_types import SearchHit, SearchResult


class GLMSearchError(RuntimeError):
    """GLM检索调用失败。"""


class GLMSearchClient:
    def __init__(self, base_url: str, model: str, api_key: str,
                 timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "GLMSearchClient | None":
        import os
        cfg = ((config or {}).get("intake") or {}).get("search") or {}
        base_url, model = cfg.get("base_url"), cfg.get("model")
        key_env = cfg.get("api_key_env") or ""
        api_key = os.environ.get(key_env, "") if key_env else ""
        if not (base_url and model and api_key):
            return None
        return cls(base_url=base_url, model=model, api_key=api_key,
                   timeout=int(cfg.get("timeout_sec") or 120))

    def search(self, query: str, *, recency_days: int | None = None) -> SearchResult:
        """用web_search插件检索并返回综合回答+命中网页列表。"""
        system = (
            "你是一个信息检索助手。用web_search工具查找与问题相关的最新中文网页内容，"
            "然后用中文列出你找到的具体信息点（谁说的/哪个平台/大致时间/具体内容），"
            "不要泛泛而谈，找不到就明确说没找到。"
        )
        user = query
        if recency_days:
            user += f"（只关心最近约{recency_days}天内的动态，忽略明显过时的信息）"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": [{"type": "web_search", "web_search": {"search_result": True}}],
            "temperature": 0.3,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            raise GLMSearchError(f"GLM检索HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise GLMSearchError(f"GLM检索调用失败: {e}") from e

        return self._parse(query, body)

    @staticmethod
    def _parse(query: str, body: dict[str, Any]) -> SearchResult:
        result = SearchResult(query=query, engine="glm")
        try:
            msg = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise GLMSearchError(f"GLM检索响应格式异常: {json.dumps(body)[:500]}") from e
        result.answer = msg.get("content") or ""

        # 命中网页列表可能出现在几个不同位置，视GLM版本而定，尽力都尝试一遍
        candidates: list[Any] = []
        if isinstance(body.get("web_search"), list):
            candidates.extend(body["web_search"])
        for tc in msg.get("tool_calls") or []:
            ws = tc.get("web_search") if isinstance(tc, dict) else None
            if isinstance(ws, list):
                candidates.extend(ws)
            elif isinstance(ws, dict) and isinstance(ws.get("search_result"), list):
                candidates.extend(ws["search_result"])

        for c in candidates:
            if not isinstance(c, dict):
                continue
            result.hits.append(SearchHit(
                title=c.get("title") or c.get("name") or "",
                link=c.get("link") or c.get("url") or "",
                snippet=c.get("content") or c.get("snippet") or c.get("summary") or "",
            ))
        return result
