# -*- coding: utf-8 -*-
"""Evidence-gated replay feedback modeled on high-level王者荣耀 coaching.

The module deliberately separates *what a coach may discuss* from *what the
current replay pipeline can prove*.  It emits a feedback card only when the
corresponding event signal is present, and marks proxy/insufficient evidence
instead of inventing details.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class FeedbackCapability:
    key: str
    name: str
    description: str
    required_signals: tuple[str, ...]
    automation_level: str
    evidence_boundary: str


CAPABILITIES: tuple[FeedbackCapability, ...] = (
    FeedbackCapability(
        "vision_bush_check", "探草意识", "进入未知草区前是否建立安全信息优势。",
        ("death_type=探草死", "minimap_context", "enemy_visibility"),
        "partial", "仅在有草区/敌方消失或分类证据时判断；不能从死亡本身断言脸探草。",
    ),
    FeedbackCapability(
        "macro_resource", "兵线与资源意识", "在补线、发育、支援和争夺之间做价值选择。",
        ("death_type=贪线死", "wave_state", "objective_state", "economy_timeline"),
        "partial", "当前可由贪线分类触发；精确价值比较需要逐帧经济、兵线和目标状态。",
    ),
    FeedbackCapability(
        "tempo_rotation", "转线与节奏", "清线后是否按阵容强势期和人数差转线压塔。",
        ("lane_clear", "ally_enemy_positions", "composition_phase", "tower_state"),
        "planned", "需要完整十人轨迹、兵线及防御塔状态；缺任何关键输入都只能给训练问题。",
    ),
    FeedbackCapability(
        "item_awareness", "装备意识", "装备购买是否回应敌方威胁、伤害类型和本局节奏。",
        ("item_purchase_timeline", "enemy_threats", "gold_timeline", "patch_item_data"),
        "planned", "终局装备可做粗评；局内出装顺序需要经济面板逐帧读取。",
    ),
    FeedbackCapability(
        "mechanics_combo", "操作技术（连招/大闪）", "技能顺序、命中、位移和闪现联动是否完成目标。",
        ("skill_casts", "cooldowns", "target_positions", "blink_cast"),
        "planned", "只有明确技能/位移时间线才能评价大闪；不得把死亡归因自动升级为操作失误。",
    ),
    FeedbackCapability(
        "teamfight_position", "团战站位与目标", "进场时机、站位、目标选择及撤退窗口是否合理。",
        ("death_type=掉点死|换头死", "teamfight_window", "ally_enemy_positions", "hp_cooldowns"),
        "partial", "当前死亡类别可给方向性反馈；团战细节需要聚集检测、血量和技能状态。",
    ),
    FeedbackCapability(
        "objective_conversion", "团战转化与推塔", "赢团后是否转化为龙、塔、入侵或安全回城。",
        ("teamfight_result", "objective_state", "tower_state", "wave_state"),
        "planned", "当前没有可靠的团战结果和目标状态联结，不能自动下结论。",
    ),
    FeedbackCapability(
        "mental_attribution", "归因与心态", "区分可控决策、队友依赖和固定操作约束。",
        ("evidence_quality", "repeat_pattern", "player_constraints"),
        "partial", "可做证据质量与重复模式提示；不能读取玩家情绪或替队友臆测动机。",
    ),
)

_CAP_BY_KEY = {c.key: c for c in CAPABILITIES}


def capability_catalog() -> list[dict[str, Any]]:
    """Return a serializable catalog for APIs, reports, and UI discovery."""
    return [asdict(c) for c in CAPABILITIES]


def _quality(detail: dict[str, Any]) -> str:
    if detail.get("evidence_sufficient") is False or detail.get("proxy"):
        return "proxy"
    if detail.get("confidence") is not None and float(detail["confidence"]) < 0.6:
        return "low"
    return "supported"


def _card(capability: str, detail: dict[str, Any], *, title: str,
          feedback: str, next_step: str) -> dict[str, Any]:
    q = _quality(detail)
    confidence = float(detail.get("confidence", 0.5))
    if q == "proxy":
        confidence = min(confidence, 0.4)
    return {
        "capability": capability,
        "name": _CAP_BY_KEY[capability].name,
        "title": title,
        "feedback": feedback,
        "next_step": next_step,
        "evidence_quality": q,
        "confidence": round(max(0.0, min(confidence, 1.0)), 2),
        "source_event": detail.get("timestamp") or detail.get("death_time"),
        "evidence": {
            "type": detail.get("type"),
            "classify_reason": detail.get("classify_reason"),
            "minimap_context": detail.get("minimap_context"),
            "location_source": detail.get("location_source"),
        },
    }


def feedback_for_detail(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """Create only feedback justified by a replay detail's explicit signals."""
    dtype = detail.get("type")
    out: list[dict[str, Any]] = []
    if dtype == "探草死":
        out.append(_card("vision_bush_check", detail,
            title="死亡前的信息检查不足",
            feedback="先确认草区信息、队友位置和敌方消失时间，再进入未知草区；这条反馈只说明探草风险，不证明你一定是机械失误。",
            next_step="训练目标：连续5局记录每次进草前的已知信息与替代探草方式。"))
    elif dtype == "贪线死":
        out.append(_card("macro_resource", detail,
            title="资源收益没有覆盖暴露风险",
            feedback="这次应先比较一波兵线收益与被抓后丢失的时间、塔和野区资源；没有经济时间线时，不输出精确金币结论。",
            next_step="训练目标：每次多吃一波线前，口头说出敌方消失位置和撤退路线。"))
    elif dtype in {"掉点死", "换头死"}:
        out.append(_card("teamfight_position", detail,
            title="团战前的站位或进退边界需要复盘",
            feedback="重点检查是否在队友可支援范围内、是否先暴露在敌方控制链、以及换头是否真的换来目标或推塔。当前证据不足时只给检查清单。",
            next_step="训练目标：团战前标记自己的进场条件、撤退条件和第一目标。"))
    elif dtype == "机制死":
        out.append(_card("mechanics_combo", detail,
            title="可能存在技能机制或执行问题",
            feedback="需要技能释放、命中、冷却和目标位置证据，才能区分连招失误、技能理解错误与不可避免死亡；本条不自动判定大闪失败。",
            next_step="训练目标：保存一段可见技能时间线，再逐帧核对关键技能的释放顺序。"))
    return out


def build_coaching_feedback(replay: dict[str, Any]) -> list[dict[str, Any]]:
    """Aggregate evidence-gated cards from a replay, deduplicating categories."""
    details = replay.get("death_analysis", {}).get("details") or []
    cards: list[dict[str, Any]] = []
    seen: set[tuple[str, Any]] = set()
    for detail in details:
        for card in feedback_for_detail(detail):
            key = (card["capability"], card.get("source_event"))
            if key not in seen:
                seen.add(key)
                cards.append(card)
    return cards


def summarize_capability_gaps() -> list[dict[str, Any]]:
    """Expose the capability/data contract used by the research report."""
    return capability_catalog()
