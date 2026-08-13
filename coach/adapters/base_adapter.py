# -*- coding: utf-8 -*-
"""数据获取适配层接口（tech spec 4.4.1）。

四级适配器路线：
- ManualInputAdapter  v1.0 手动输入（阶段0视频管线的兜底/校验路径）
- ScreenshotOCRAdapter v1.0 截图OCR（阶段2+）
- ReplayVideoAdapter  回放视频自动分析（接入阶段0验证的检测管线）
- OfficialAPIAdapter  v3.0 官方API（如开放）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class GameDataAdapter(ABC):
    """一局比赛数据的获取接口。返回值为 tech spec 3.1 的 replay dict。"""

    @abstractmethod
    def get_match_data(self, match_id: str | None = None) -> dict[str, Any]:
        """获取一局比赛的结构化数据（replay记录dict）。"""

    @abstractmethod
    def get_player_profile(self) -> dict[str, Any]:
        """获取玩家档案和战力数据（player_profile dict）。"""
