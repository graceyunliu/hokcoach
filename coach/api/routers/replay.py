# -*- coding: utf-8 -*-
"""/replay 端点（AGE-178: 上传+异步任务+状态轮询；AGE-179: 结果详情+列表）。

v5（录像处理）视图靠这个路由驱动：上传视频→轮询进度→拿结果。
"""

from __future__ import annotations

import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile

from api.jobs import job_store, run_replay_job
from core.orchestrator import Orchestrator
from utils import data_utils

# 前缀留空：/replay和/replays路径习惯上一个单数一个复数，没法共用同一个
# prefix，索性每个路由自己写全路径，比硬凑prefix更直白。
router = APIRouter(tags=["replay"])

# 上传的视频文件落到这里，job跑完后不主动清理——单用户本地工具，磁盘由
# 用户自己管，不做自动垃圾回收（避免job还没跑完文件就被误删这种时序坑）。
_UPLOAD_DIR = Path(tempfile.gettempdir()) / "coach_api_uploads"
_UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/replay")
async def upload_replay(file: UploadFile, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """接收视频上传，起后台任务跑完整自动复盘管线，立即返回job_id。

    不同步跑：一份15-20分钟录屏的自动复盘要跑数十次真实VLM调用、数分钟
    耗时（参照AGE-141复验：单录屏约60-80个采样点），同步请求会直接超时。
    """
    dest = _UPLOAD_DIR / f"{threading.get_ident()}_{file.filename}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)

    job = job_store.create(video_path=str(dest))
    background_tasks.add_task(run_replay_job, job, Orchestrator)
    return {"job_id": job.id}


@router.get("/replay/{job_id}/status")
async def get_job_status(job_id: str) -> dict[str, Any]:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"未知job_id: {job_id}")
    return job.to_dict()


@router.get("/replays")
async def list_replays() -> dict[str, Any]:
    paths = data_utils.list_replays()
    items = []
    for p in paths:
        data = data_utils.load_json(p)
        if not data:
            continue
        items.append({
            "replay_id": data.get("replay_id"),
            "timestamp": data.get("timestamp"),
            "hero_played": data.get("hero_played"),
            "game_result": data.get("game_result"),
            "deaths": data.get("deaths"),
        })
    return {"replays": items}


@router.get("/replay/{replay_id}")
async def get_replay(replay_id: str) -> dict[str, Any]:
    path = data_utils.REPLAYS_DIR / f"{replay_id}.json"
    data = data_utils.load_json(path)
    if data is None:
        raise HTTPException(status_code=404, detail=f"未找到复盘记录: {replay_id}")
    return data
