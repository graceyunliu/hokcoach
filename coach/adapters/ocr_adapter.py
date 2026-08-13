# -*- coding: utf-8 -*-
"""截图OCR适配器（tech spec 4.4.1 ScreenshotOCRAdapter）。

v1.0实现方式：不引入本地OCR引擎，直接用视觉LLM解析战绩截图
（与HUD KDA读数复用同一套vision配置）。未配置视觉模型时给出明确报错，
让用户走 ManualInputAdapter。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from adapters.base_adapter import GameDataAdapter
from utils import data_utils

_OCR_PROMPT = """\
这是一张王者荣耀对局结算/战绩页截图。请提取以下字段并输出JSON：
{
  "hero_played": "英雄名或null",
  "game_result": "victory|defeat|null",
  "deaths": 死亡次数int或null,
  "kills": int或null, "assists": int或null,
  "rank_after": 赛后分数int或null
}
看不清的字段填null，不要猜。只输出JSON。
"""


class ScreenshotOCRAdapter(GameDataAdapter):
    """v1.0: 战绩截图 → 视觉LLM解析 → replay记录。"""

    def __init__(self, vlm_client: Any):
        if vlm_client is None:
            raise RuntimeError(
                "截图OCR需要视觉模型（config.yaml llm.vision段+API key）。"
                "未配置时请用 --replay --manual 手动录入。")
        self.vlm = vlm_client

    def get_player_profile(self) -> dict[str, Any]:
        profile = data_utils.load_player_profile()
        if profile is None:
            raise FileNotFoundError("尚无玩家档案，请先运行 python coach.py --init")
        return profile

    def get_match_data(self, match_id: str | None = None) -> dict[str, Any]:
        """match_id 在本适配器中为截图路径。"""
        from core.llm_client import extract_json

        if not match_id or not Path(match_id).exists():
            raise FileNotFoundError(f"找不到截图: {match_id}")
        raw = self.vlm.chat_image(_OCR_PROMPT, match_id)
        data = extract_json(raw)

        replay = data_utils.default_replay(data.get("hero_played"))
        replay["source"] = {"type": "screenshot_ocr", "path": str(match_id)}
        replay["game_result"] = data.get("game_result")
        replay["rank_after"] = data.get("rank_after")
        deaths = data.get("deaths") or 0
        replay["deaths"] = deaths
        replay["death_analysis"]["total"] = deaths
        # 截图只有汇总数，单次死亡明细留空；归因需用户自述或视频管线补充
        for _ in range(deaths):
            replay["death_analysis"]["details"].append({
                "timestamp": None, "type": None, "location": None,
                "killer": None, "self_attribution": None,
                "minimap_context": None, "ai_comment": None,
            })
        return replay
