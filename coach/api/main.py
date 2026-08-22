# -*- coding: utf-8 -*-
"""FastAPI应用入口（AGE-176 epic）。

启动：
    cd coach && uvicorn api.main:app --reload

本地开发用。CORS放行所有来源——这是单用户本地工具，且
coach_prototype.html是直接用file://双击打开的（不是跑在localhost:xxxx的
dev server上），file://页面发起fetch时浏览器带的Origin是"null"，白名单式
配置（只允许localhost:5173/3000）根本挡不住"null"，反而会把这个最常见的
用法直接拒了——所以干脆放开，不搞白名单。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.llm_client import LLMClient, VisionClient
from utils import config_utils

# 复用coach.py同样的本地secrets加载方式，API进程也需要LLM/VLM key。
config_utils.load_local_secrets()

from api.routers import progress, replay, training  # noqa: E402

app = FastAPI(title="Coach API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(replay.router)
app.include_router(training.router)
app.include_router(progress.router)


@app.get("/health")
async def health() -> dict[str, object]:
    # AGE-244：暴露LLM/VLM是否已配置，方便前端/运维一眼看出是否在降级模式
    # 运行，不用翻日志。是否为None的语义与core.orchestrator.Orchestrator一致。
    config = config_utils.load_config()
    llm_configured = LLMClient.from_config(config) is not None
    vlm_configured = VisionClient.from_config(config) is not None
    return {
        "status": "ok",
        "llm_configured": llm_configured,
        "vlm_configured": vlm_configured,
    }
