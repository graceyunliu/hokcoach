# -*- coding: utf-8 -*-
"""手动输入适配器（tech spec 4.4.2）。

阶段0已验证的视频自动检测管线是主路径；本适配器保留为兜底/人工校验路径：
用户打完一局后在命令行输入关键数据（英雄、胜负、死亡次数、每次死亡的
时间点与自我归因）。
"""

from __future__ import annotations

from typing import Any

from adapters.base_adapter import GameDataAdapter
from utils import data_utils

DEATH_TYPES = ["探草死", "掉点死", "换头死", "贪线死", "机制死"]


def _ask(prompt: str) -> str:
    """交互式输入。不预填个人数据，回车即跳过。"""
    try:
        value = input(f"{prompt}\n> ").strip()
    except EOFError:
        value = ""
    return value


class ManualInputAdapter(GameDataAdapter):
    """v1.0: 用户手动输入一局数据。"""

    def get_player_profile(self) -> dict[str, Any]:
        profile = data_utils.load_player_profile()
        if profile is None:
            raise FileNotFoundError(
                "尚无玩家档案，请先运行 python coach.py --init"
            )
        return profile

    def get_match_data(self, match_id: str | None = None) -> dict[str, Any]:
        """命令行逐项收集一局比赛数据，返回replay记录dict。"""
        print("\n== 手动录入一局比赛数据（回车用默认值）==")
        replay = data_utils.default_replay()

        replay["hero_played"] = _ask("这局用的英雄？") or None
        result = _ask("结果？胜利(v) / 失败(d)").lower()
        if result.startswith("v"):
            replay["game_result"] = "victory"
        elif result.startswith("d") or result in ("失败", "负"):
            replay["game_result"] = "defeat"

        rank = _ask("赛后分数（可跳过）")
        replay["rank_after"] = int(rank) if rank.isdigit() else None

        deaths_str = _ask("死亡次数？")
        deaths = int(deaths_str) if deaths_str.isdigit() else 0
        replay["deaths"] = deaths
        replay["death_analysis"]["total"] = deaths

        for i in range(deaths):
            print(f"\n-- 第{i + 1}次死亡 --")
            detail: dict[str, Any] = {
                "timestamp": _ask("时间点（如 6:32，记不清可跳过）"),
                "type": None,
                "location": _ask("死亡地点（如 中路下草，可跳过）"),
                "killer": _ask("被谁击杀？（可跳过）"),
                "self_attribution": _ask("你自己觉得为什么死的？（可跳过）"),
                "ai_comment": None,  # 阶段2由复盘引擎填充
            }
            type_hint = _ask(
                f"死亡类型？{'/'.join(DEATH_TYPES)}（不确定可跳过，阶段2由分类器判定）"
            )
            if type_hint in DEATH_TYPES:
                detail["type"] = type_hint
                replay["death_analysis"]["categories"][type_hint] += 1
            replay["death_analysis"]["details"].append(detail)

        return replay
