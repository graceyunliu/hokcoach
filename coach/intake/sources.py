# -*- coding: utf-8 -*-
"""信源查询清单（tech spec之外的运营配置，按需增删即可）。

每条是一个 (category, query) 元组：category 用于在草案里标注信源类型，
query 是丢给GLM web_search的检索问题——GLM会自己选取最相关的中文网页
（官网/百科/论坛/视频平台的图文页面等）。
"""

from __future__ import annotations

SOURCE_QUERIES: list[tuple[str, str]] = [
    ("official", "王者荣耀 官方 最新版本更新说明 英雄调整"),
    ("official", "王者荣耀 体验服 平衡性调整 公告"),
    ("wiki", "苏苏教你打王者 最新版本 英雄改动解读"),
    ("wiki", "王者荣耀 巴哈姆特 版本 英雄 数值改动"),
    ("social", "王者荣耀 微博 版本更新 英雄削弱 加强"),
    ("social", "王者荣耀 TapTap 最新版本 玩家反馈 削弱加强"),
    ("social", "王者荣耀 NGA 版本改动 讨论"),
    ("creator", "王者荣耀 B站 主播 最新版本 英雄改动解说"),
    ("creator", "王者荣耀 抖音 职业选手 教练 版本解读"),
    ("creator", "王者荣耀 虎牙 职业选手 直播 版本机制讲解"),
    ("creator", "王者荣耀 小红书 版本攻略 英雄改动"),
]

# category → 中文展示名，用于草案文件里的信源分组标题
CATEGORY_LABEL = {
    "official": "官方渠道",
    "wiki": "社区百科/攻略聚合站",
    "social": "社媒/论坛动态",
    "creator": "主播/教练/职业选手内容",
}
