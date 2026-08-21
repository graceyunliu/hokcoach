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

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

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


_CHUNK_SIZE = 1024 * 1024  # 1MB


@router.get("/replay/{replay_id}/video")
async def get_replay_video(replay_id: str, request: Request):
    """回放原视频，支持Range请求（v5页"跟教练一起看回放"功能靠这个seek，
    浏览器<video>元素默认就会发Range请求，不支持的话拖进度条会失败）。

    源文件路径来自replay.source.path（上传时落到_UPLOAD_DIR，不主动清理，
    见upload_replay的注释）——但这是本地临时目录，用户重启电脑/系统清理
    /tmp后文件可能已经不在了，找不到时返回明确的404而不是让前端<video>
    卡在加载圈。手写Range解析而非依赖FileResponse的内置支持，因为不同
    starlette版本对Range的支持程度不一致，这个本地工具不想赌用户装的版本。
    """
    path = data_utils.REPLAYS_DIR / f"{replay_id}.json"
    data = data_utils.load_json(path)
    if data is None:
        raise HTTPException(status_code=404, detail=f"未找到复盘记录: {replay_id}")

    video_path_str = ((data.get("source") or {}).get("path"))
    if not video_path_str:
        raise HTTPException(status_code=404, detail="该复盘记录没有关联的原始视频（可能是手动录入的）")

    video_path = Path(video_path_str)
    if not video_path.exists():
        raise HTTPException(
            status_code=404,
            detail="原视频文件已不在（临时目录可能已被系统清理），无法回放，只能看文字点评")

    file_size = video_path.stat().st_size
    range_header = request.headers.get("range")

    media_type = "video/mp4"

    if range_header is None:
        # 无Range请求：整个文件一次性返回（首次加载/不支持Range的客户端）
        def _iter_full():
            with video_path.open("rb") as f:
                while chunk := f.read(_CHUNK_SIZE):
                    yield chunk

        return StreamingResponse(
            _iter_full(), media_type=media_type,
            headers={"Content-Length": str(file_size), "Accept-Ranges": "bytes"})

    # 解析形如 "bytes=1000-2000" / "bytes=1000-" 的Range头
    try:
        units, _, range_spec = range_header.partition("=")
        if units.strip() != "bytes":
            raise ValueError
        start_s, _, end_s = range_spec.partition("-")
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else file_size - 1
        end = min(end, file_size - 1)
        if start > end or start < 0:
            raise ValueError
    except ValueError:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

    length = end - start + 1

    def _iter_range():
        with video_path.open("rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(_CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        _iter_range(), status_code=206, media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(length),
            "Accept-Ranges": "bytes",
        })
