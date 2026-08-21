# -*- coding: utf-8 -*-
"""/progress + /player/profile 端点（AGE-181）。

支撑v3（成长追踪）视图：返回weakness_tracker/weekly_snapshots的原始数据，
不是ASCII图表本身——前端用真实图表库渲染，替换v3现有heatmap的
Math.random()假数据和SVG折线的写死path。
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from utils import data_utils

router = APIRouter(tags=["progress"])


class PlayerProfilePatch(BaseModel):
    language: Literal["zh", "en"]


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


@router.patch("/player/profile")
async def patch_player_profile(body: PlayerProfilePatch) -> dict[str, Any]:
    """当前只开放语言偏好；避免前端为了一个字段覆盖整份玩家画像。"""
    profile = data_utils.load_player_profile() or data_utils.default_player_profile()
    profile.setdefault("player", {})["language"] = body.language
    data_utils.save_player_profile(profile)
    return profile
