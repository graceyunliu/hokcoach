# -*- coding: utf-8 -*-
"""玩家约束与补偿引擎（阶段2，tech spec 4.6）。

v1.0落地范围（4.6.4）：约束画像字段 + prompt层兼容性提示。
不构建补偿策略知识库（v1.5/v2.0）——check_compatibility 只负责发现
"待引用原则假设了玩家不具备的能力"，标记为需给出补偿版本，具体补偿方案
由LLM在prompt规则7约束下生成。

4.6.3 固定约束识别（"努力兑现但结果不变"模式）在 training_engine 的
每周评估中调用本模块的 detect_fixed_constraint()。
"""

from __future__ import annotations

from typing import Any

from core.knowledge_engine import Principle

# 能力要求关键词 → 判定该要求与哪些约束冲突的谓词
_LATENCY_SENSITIVE_KWS = ("反应", "瞬时", "闪避", "极限", "光速", "帧")
_TIME_SENSITIVE_KWS = ("每天", "高强度", "大量练习", "长时间")

# 高延迟阈值（ms）：超过则认为"依赖瞬时反应"的建议需要补偿版本
HIGH_LATENCY_MS = 120


def check_compatibility(
    principles: list[Principle],
    constraints: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """检查待引用原则是否假设了玩家不具备的能力（tech spec 4.1.4步骤3）。

    Returns:
        与principles等长的列表，每项:
        {"principle": Principle, "compatible": bool, "note": str|None}
        note 非空表示需要在prompt中提示"给出补偿版本"。
    """
    constraints = constraints or {}
    latency = constraints.get("network_latency_ms")
    hours = constraints.get("hours_per_week")

    out: list[dict[str, Any]] = []
    for p in principles:
        req = (p.requires_capability or "").strip()
        note = None
        if req:
            if (latency is not None and latency >= HIGH_LATENCY_MS
                    and any(kw in req for kw in _LATENCY_SENSITIVE_KWS)):
                note = (f"该原则要求「{req}」，但玩家网络延迟约{latency}ms，"
                        f"不能直接要求瞬时反应操作，必须给出补偿版本"
                        f"（如预判、视野控制、提前站位）。")
            elif (hours is not None and hours < 5
                    and any(kw in req for kw in _TIME_SENSITIVE_KWS)):
                note = (f"该原则要求「{req}」，但玩家每周游戏时间仅约{hours}小时，"
                        f"训练建议需压缩到可执行的最小动作。")
        out.append({"principle": p, "compatible": note is None, "note": note})
    return out


def format_constraints(constraints: dict[str, Any] | None,
                       compat_results: list[dict[str, Any]] | None = None) -> str:
    """组装进4.1.3提示词 {player_constraints} 槽位的文本。"""
    constraints = constraints or {}
    lines: list[str] = []
    if constraints.get("network_latency_ms") is not None:
        ms = constraints["network_latency_ms"]
        line = f"- 网络延迟约{ms}ms"
        if ms >= HIGH_LATENCY_MS:
            line += "（偏高：给建议时避免要求瞬时反应操作，除非同时给出补偿说明）"
        lines.append(line)
    if constraints.get("age_bracket"):
        lines.append(f"- 年龄段：{constraints['age_bracket']}")
    if constraints.get("years_gaming_experience") is not None:
        lines.append(f"- 游戏经验：约{constraints['years_gaming_experience']}年")
    if constraints.get("hours_per_week") is not None:
        lines.append(f"- 每周游戏时长：约{constraints['hours_per_week']}小时")
    for r in compat_results or []:
        if r["note"]:
            lines.append(f"- ⚠ {r['note']}")
    if not lines:
        return "（未提供约束画像）"
    return "\n".join(lines)


def detect_fixed_constraint(weakness_entry: dict[str, Any],
                            min_weeks: int = 3,
                            min_execution_rate: float = 0.8,
                            min_improvement: float = 0.05) -> bool:
    """4.6.3：判定某弱点是否呈"努力兑现但结果不变"的固定约束模式。

    条件：连续训练≥min_weeks周，且各周执行率均达标（努力兑现），
    但 current_level 相对训练开始时的提升 < min_improvement（结果不变）。

    weakness_entry 需包含（training_engine维护）：
      weeks_trained, current_level, level_history: [每周level],
      execution_history: [每周执行率]
    """
    weeks = weakness_entry.get("weeks_trained", 0)
    if weeks < min_weeks:
        return False
    exec_hist = weakness_entry.get("execution_history", [])[-min_weeks:]
    if len(exec_hist) < min_weeks or any(r < min_execution_rate for r in exec_hist):
        return False  # 努力未兑现 → 是执行问题，不是固定约束
    level_hist = weakness_entry.get("level_history", [])
    if len(level_hist) < min_weeks + 1:
        return False
    improvement = level_hist[-1] - level_hist[-(min_weeks + 1)]
    return improvement < min_improvement
