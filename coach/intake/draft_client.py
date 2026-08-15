# -*- coding: utf-8 -*-
"""起草层：DeepSeek，把检索层(glm_search)的原始材料整理成知识库草案条目。

复用 core/llm_client.py 的OpenAI兼容客户端实现，只是从 config.yaml 的
intake.draft 段（而不是顶层 llm 段）读取配置——检索用的模型和起草用的模型
是分开配的，互不影响 coach.py 主程序用的对话模型。
"""

from __future__ import annotations

import os
from typing import Any

from core.llm_client import LLMClient


def draft_client_from_config(config: dict[str, Any]) -> LLMClient | None:
    cfg = ((config or {}).get("intake") or {}).get("draft") or {}
    base_url, model = cfg.get("base_url"), cfg.get("model")
    key_env = cfg.get("api_key_env") or ""
    api_key = os.environ.get(key_env, "") if key_env else ""
    if not (base_url and model and api_key):
        return None
    return LLMClient(base_url=base_url, model=model, api_key=api_key,
                     timeout=int(cfg.get("timeout_sec") or 180))
