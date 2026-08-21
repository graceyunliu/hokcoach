# -*- coding: utf-8 -*-
"""FastAPI应用入口（AGE-176 epic）。

启动：
    cd coach && uvicorn api.main:app --reload

本地开发用，默认允许localhost跨源请求（前端另起端口跑，如Vite默认5173）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from utils import config_utils

# 复用coach.py同样的本地secrets加载方式，API进程也需要LLM/VLM key。
config_utils.load_local_secrets()

from api.routers import progress, replay, training  # noqa: E402

app = FastAPI(title="Coach API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(replay.router)
app.include_router(training.router)
app.include_router(progress.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
