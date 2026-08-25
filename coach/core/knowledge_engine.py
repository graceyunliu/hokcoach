# -*- coding: utf-8 -*-
"""知识引擎（阶段2，tech spec 4.5）。

RAG架构：retrieve_principles(category, context) 从 knowledge_base/ 按
death_type标签匹配检索1-3条原则。v1.0规模（数十条）用标签+关键词匹配，
不引入向量库（4.5.3：v1.0阶段embedding属于过度工程）。

信源分层（4.5.2）硬规则：tier 3（3_contested_style）条目**不进入**基本功
检索结果——即使误写进macro_principles.md，加载时也会被过滤并告警。

条目来源：
- knowledge_base/macro_principles.md   宏观原则（Tier 1/2）
- knowledge_base/map_mechanics.md      地图机制（Tier 1为主）
- knowledge_base/hero_mechanics.json   英雄机制事实（Tier 1）

markdown条目格式（与库内示例一致）：
    - **[vision_001]** 打野在小地图消失超过15秒后……
      - tier: 2_converged_consensus
      - tags: 探草死, 视野          # 可选：显式声明适用的死亡类型/主题标签
      - applies_when: jungler_missing_duration_sec > 15
      - requires_capability: null
      - source: 老娘_vod_23, 打萌_vod_08
      - valid_as_of_patch: 3.85
      - last_reviewed: 2026-08-12
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge_base"

# death_type → 关键词（用于没有显式tags的条目做文本匹配）
DEATH_TYPE_KEYWORDS: dict[str, list[str]] = {
    "探草死": ["探草", "草丛", "视野", "消失", "蹲", "眼"],
    "掉点死": ["掉点", "孤立", "单独", "深入", "支援", "撤退", "越塔"],
    "换头死": ["换头", "一换一", "换血", "对拼", "兵线"],
    "贪线死": ["贪线", "兵线", "收线", "补刀", "暴露", "带线"],
    "机制死": ["机制", "技能", "伤害", "数值", "隐身", "防御塔"],
}


@dataclass
class Principle:
    id: str
    text: str
    text_en: str | None = None
    tier: str = ""
    tags: list[str] = field(default_factory=list)
    applies_when: str | None = None
    requires_capability: str | None = None
    source: str = ""
    valid_as_of_patch: str = ""
    last_reviewed: str = ""
    origin_file: str = ""

    def is_tier3(self) -> bool:
        return str(self.tier).strip().startswith("3")

    def format_for_prompt(self, lang: str = "zh") -> str | None:
        if lang == "en":
            if not self.text_en:
                return None
            return (f"[{self.id}] {self.text_en}\n"
                    f"  (tier: {self.tier or 'unmarked'}; version: "
                    f"{self.valid_as_of_patch or 'unmarked'})")
        cap = f"（要求能力：{self.requires_capability}）" if self.requires_capability else ""
        return (f"[{self.id}] {self.text}{cap}\n"
                f"  （tier: {self.tier or '未标'}；来源: {self.source or '未标'}；"
                f"版本: {self.valid_as_of_patch or '未标'}）")


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------

_ENTRY_RE = re.compile(r"^- \*\*\[(?P<id>[^\]]+)\]\*\*\s*(?P<text>.+)$")
_FIELD_RE = re.compile(r"^\s+- (?P<key>[\w_]+):\s*(?P<value>.*)$")


def _parse_md(path: Path) -> list[Principle]:
    """解析markdown原则库。忽略引用块/注释/标题，只认条目格式。"""
    if not path.exists():
        return []
    entries: list[Principle] = []
    current: Principle | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _ENTRY_RE.match(line)
        if m:
            current = Principle(id=m.group("id").strip(),
                               text=m.group("text").strip(),
                               origin_file=path.name)
            entries.append(current)
            continue
        if current is None:
            continue
        f = _FIELD_RE.match(line)
        if not f:
            # 非字段行（空行/新段落）结束当前条目
            if line.strip() and not line.startswith(" "):
                current = None
            continue
        key, value = f.group("key"), f.group("value").strip()
        if value in ("null", "~", ""):
            value = None  # type: ignore[assignment]
        if key == "tier":
            current.tier = value or ""
        elif key == "tags":
            current.tags = [t.strip() for t in
                            (value or "").replace("，", ",").strip("[]").split(",")
                            if t.strip()]
        elif key == "applies_when":
            current.applies_when = value
        elif key == "requires_capability":
            current.requires_capability = value
        elif key == "source":
            current.source = value or ""
        elif key == "valid_as_of_patch":
            current.valid_as_of_patch = str(value or "")
        elif key == "last_reviewed":
            current.last_reviewed = str(value or "")
        elif key == "text_en":
            current.text_en = value
    return entries


def _parse_hero_json(path: Path) -> list[Principle]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for e in data.get("entries", []):
        out.append(Principle(
            id=e.get("id", "hero_?"),
            text=e.get("text", ""),
            text_en=e.get("text_en"),
            tier=e.get("tier", "1_mechanical_fact"),
            tags=list(e.get("tags", [])),
            applies_when=e.get("applies_when"),
            requires_capability=e.get("requires_capability"),
            source=", ".join(e.get("source", [])) if isinstance(e.get("source"), list)
                   else str(e.get("source", "")),
            valid_as_of_patch=str(e.get("valid_as_of_patch", "")),
            last_reviewed=str(e.get("last_reviewed", "")),
            origin_file=path.name,
        ))
    return out


def load_all_principles(knowledge_dir: Path = KNOWLEDGE_DIR) -> list[Principle]:
    """加载全部条目，过滤tier 3（4.5.2硬规则）并对误入者告警。"""
    entries = (
        _parse_md(knowledge_dir / "macro_principles.md")
        + _parse_md(knowledge_dir / "map_mechanics.md")
        + _parse_hero_json(knowledge_dir / "hero_mechanics.json")
    )
    kept = []
    for e in entries:
        if e.is_tier3():
            print(f"[知识引擎] 警告：条目 {e.id} 为tier 3（风格化/有争议），"
                  f"不允许进入基本功检索，已跳过（应移至偶像标准层）。",
                  file=sys.stderr)
            continue
        kept.append(e)
    return kept


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------

def _score(p: Principle, category: str, context: str) -> int:
    score = 0
    if category in p.tags:
        score += 10  # 显式标签命中最高优先
    for kw in DEATH_TYPE_KEYWORDS.get(category, []):
        if kw in p.text or kw in (p.applies_when or ""):
            score += 2
    if context:
        for token in re.findall(r"[一-鿿]{2,4}", context):
            if token in p.text:
                score += 1
    return score


def retrieve_principles(category: str, context: str = "",
                        k: int = 3,
                        principles: list[Principle] | None = None) -> list[Principle]:
    """按death_type标签+关键词检索1-k条原则（tech spec 4.1.4步骤2）。

    检索不到时返回空列表——上层prompt规则6要求此时明确说"证据/原则不足"，
    绝不硬凑无关条目。
    """
    pool = principles if principles is not None else load_all_principles()
    scored = [(_score(p, category, context), p) for p in pool]
    scored = [(s, p) for s, p in scored if s > 0]
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:k]]


def format_principles(principles: list[Principle], lang: str = "zh") -> str:
    """组装进4.1.3提示词 {retrieved_principles} 槽位的文本。"""
    if not principles:
        if lang == "en":
            return ("(No knowledge-base principle matched this death type. "
                    "State that evidence is insufficient; do not invent advice.)")
        return ("（知识库中没有检索到与本次死亡类型匹配的原则条目。"
                "你必须声明证据不足，不得凭空推演。）")
    formatted = [p.format_for_prompt(lang=lang) for p in principles]
    reviewed = [text for text in formatted if text]
    if lang == "en" and not reviewed:
        return ("(Matching principles exist, but no human-reviewed English "
                "translations are available. Treat the knowledge evidence as "
                "unavailable; do not translate or invent it.)")
    return "\n".join(reviewed)
