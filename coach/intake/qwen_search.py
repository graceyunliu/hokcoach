# -*- coding: utf-8 -*-
"""检索层备份：通义千问(Qwen) via DashScope，OpenAI兼容接口 + enable_search。

只在GLM检索失败或对某条查询返回空结果时才会被调用（见 run_intake.py 的
_search_with_fallback）——GLM的web_search插件返回结构化的命中网页列表
（title/link/content），信息更丰富；Qwen这里用的是DashScope兼容模式的
`enable_search` 开关，是更粗粒度的"允许模型自己查资料"能力，返回的更多是
综合性回答，未必有结构化的网页列表，所以只作为兜底，不作为主检索源。

注：`enable_search` 字段是DashScope OpenAI兼容模式下的直通参数，具体行为
以官方文档为准；接入真实key后如返回格式有出入，只需要调整下面 `_parse`。

复用 core.knowledge_engine 的项目里已有一个DashScope key
（config.yaml 的 llm.vision.api_key_env，用于视觉模型qwen-vl-plus）。
这里默认优先读取 intake.search_fallback.api_key_env 指定的专用环境变量，
没配置的话退化为直接复用视觉层的 DashScope key，避免让你多管理一个密钥。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from intake.search_types import SearchHit, SearchResult


class QwenSearchError(RuntimeError):
    """Qwen检索调用失败。"""


class QwenSearchClient:
    def __init__(self, base_url: str, model: str, api_key: str,
                 timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "QwenSearchClient | None":
        cfg = ((config or {}).get("intake") or {}).get("search_fallback") or {}
        # DASHSCOPE_BASE_URL环境变量优先——工作空间专属(Token Plan)key的域名是
        # 每个工作空间独有的（形如 ws-xxxxx.ap-southeast-1.maas.aliyuncs.com），
        # 写死在config.yaml里方便本地跑，但如果密钥/工作空间换了，不用改代码，
        # 设个环境变量就能覆盖。
        base_url = (os.environ.get("DASHSCOPE_BASE_URL")
                   or cfg.get("base_url")
                   or "https://dashscope.aliyuncs.com/compatible-mode/v1")
        model = cfg.get("model") or "qwen-plus"
        key_env = cfg.get("api_key_env") or ""
        api_key = os.environ.get(key_env, "") if key_env else ""
        if not api_key:
            # 退化：复用视觉层已有的DashScope key，两者是同一个供应商
            vision_key_env = (((config or {}).get("llm") or {}).get("vision") or {}).get(
                "api_key_env") or ""
            api_key = os.environ.get(vision_key_env, "") if vision_key_env else ""
        if not api_key:
            return None
        return cls(base_url=base_url, model=model, api_key=api_key,
                   timeout=int(cfg.get("timeout_sec") or 120))

    def search(self, query: str, *, recency_days: int | None = None) -> SearchResult:
        system = (
            "你是一个信息检索助手。查找与问题相关的最新中文网页内容，"
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
            "enable_search": True,
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
            raise QwenSearchError(f"Qwen检索HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise QwenSearchError(f"Qwen检索调用失败: {e}") from e

        return self._parse(query, body)

    @staticmethod
    def _parse(query: str, body: dict[str, Any]) -> SearchResult:
        result = SearchResult(query=query, engine="qwen")
        try:
            msg = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise QwenSearchError(f"Qwen检索响应格式异常: {json.dumps(body)[:500]}") from e
        result.answer = msg.get("content") or ""

        # DashScope有时会在 output/search_info 里带引用的网页列表，位置不固定，
        # 尽力找一遍，找不到就只保留综合回答（对起草层来说也够用）。
        candidates: list[Any] = []
        search_info = body.get("search_info") or (body.get("output") or {}).get("search_info")
        if isinstance(search_info, dict) and isinstance(search_info.get("search_results"), list):
            candidates.extend(search_info["search_results"])

        for c in candidates:
            if not isinstance(c, dict):
                continue
            result.hits.append(SearchHit(
                title=c.get("title") or "",
                link=c.get("url") or c.get("link") or "",
                snippet=c.get("snippet") or c.get("content") or "",
            ))
        return result
