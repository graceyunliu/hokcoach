# -*- coding: utf-8 -*-
"""/training 端点（AGE-180）：本周任务/打卡/历史/AI周评估笔记。

支撑v2（本周训练任务）视图。全部是training_engine.py既有函数的薄封装，
不重新实现打卡/评估逻辑。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core import training_engine
from utils import data_utils

router = APIRouter(prefix="/training", tags=["training"])


class CheckinRequest(BaseModel):
    rate: int = Field(ge=0, le=100, description="今日执行率0-100")
    note: str | None = None
    when: str | None = Field(default=None, description="YYYY-MM-DD，缺省为今天")


@router.get("/current")
async def get_current_week() -> dict[str, Any]:
    """本周任务+打卡状态；没有任务时自动生成（跟CLI --checkin的行为一致，
    见training_engine.checkin里"没有任务先分配一个"的逻辑）。"""
    week = data_utils.load_weekly_training()
    if week is None or not week.get("task", {}).get("description"):
        week = training_engine.assign_task_for_week()
    return {
        "week": week.get("week"),
        "task": week.get("task"),
        "daily_checkins": week.get("daily_checkins", []),
        "execution_rate": training_engine.week_execution_rate(week),
    }


@router.post("/checkin")
async def checkin(body: CheckinRequest) -> dict[str, Any]:
    try:
        week = training_engine.checkin(rate=body.rate, note=body.note,
                                       when=body.when)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {
        "week": week.get("week"),
        "task": week.get("task"),
        "daily_checkins": week.get("daily_checkins", []),
    }


@router.get("/history")
async def get_history() -> dict[str, Any]:
    """历史周快照（v2"历史任务回顾"卡片）。"""
    progress = data_utils.load_progress() or data_utils.default_progress()
    return {"snapshots": progress.get("weekly_snapshots", [])}


@router.get("/weekly-note")
async def get_weekly_note() -> dict[str, Any]:
    """最近一次AI周评估文案（v2"AI每周评估笔记"卡片）。

    注意：这只读已经落盘的ai_weekly_note（由--weekly-report/未来的
    POST触发一次真实LLM调用后写入），本端点本身不触发LLM调用——避免
    GET请求意外产生API费用/耗时。触发生成走单独的POST（暂未建票，
    参照AGE-180描述里的备注：--weekly-report命令本身是否已跑通真实
    LLM调用还没验证过，先假设数据存在）。
    """
    week = data_utils.load_weekly_training()
    note = (week or {}).get("ai_weekly_note")
    if note is None:
        return {"available": False, "note": None}
    return {"available": True, "note": note}