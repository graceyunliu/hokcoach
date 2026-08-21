# -*- coding: utf-8 -*-
"""/progress + /player/profile 端点（AGE-181）。

支撑v3（成长追踪）视图：返回weakness_tracker/weekly_snapshots的原始数据，
不是ASCII图表本身——前端用真实图表库渲染，替换v3现有heatmap的
Math.random()假数据和SVG折线的写死path。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from utils import data_utils

router = APIRouter(tags=["progress"])


@router.get("/progress")
async def get_progress() -> dict[str, Any]:
    progress = data_utils.load_progress() or data_utils.default_progress()
    return {
        "weakness_tracker": progress.get("weakness_tracker", {}),
        "weekly_snapshots": progress.get("weekly_snapshots", []),
    }


@router.get("/player/profile")
async def get_player_profile() -> dict[str, Any]:
    profile = data_utils.load_player_profile() or data_utils.default_player_profile()
    return profile