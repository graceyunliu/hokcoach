# -*- coding: utf-8 -*-
"""检索层共享的数据结构（GLM/Qwen等不同搜索后端返回统一形状，方便起草层/
run_intake.py 不用关心是谁检索到的）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SearchHit:
    title: str = ""
    link: str = ""
    snippet: str = ""


@dataclass
class SearchResult:
    query: str
    answer: str = ""            # 模型综合搜索结果给出的文字回答
    hits: list[SearchHit] = field(default_factory=list)  # 命中的网页（尽力解析）
    engine: str = ""            # "glm" | "qwen" —— 记录这条结果实际是谁检索到的

    def is_empty(self) -> bool:
        return not self.answer and not self.hits
