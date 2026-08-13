# -*- coding: utf-8 -*-
"""复盘引擎（阶段2，tech spec 4.1）。

- 死亡事件输入：utils/video_utils.py（阶段0验证的检测管线）或 ManualInputAdapter
- 死亡归因分类器（4.1.2）：探草死/掉点死/换头死/贪线死/机制死
- 输出决策点 + death_type，供 knowledge_engine 检索（4.1.4步骤1）

分类策略：规则优先，LLM兜底。
1. 结构化证据规则（4.1.2优先级顺序）能命中时直接出结果（零成本、可解释）；
2. 规则不命中且配置了LLM时，用 prompts/death_classifier.txt 让LLM判定；
3. 都不行 → "机制死" + 证据不足（prompt规则6会要求教练诚实说需看回放）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from core.llm_client import LLMClient, LLMError, extract_json

BASE_DIR = Path(__file__).resolve().parent.parent
DEATH_CLASSIFIER_PROMPT = BASE_DIR / "prompts" / "death_classifier.txt"

DEATH_TYPES = ["探草死", "掉点死", "换头死", "贪线死", "机制死"]

# 自述关键词 → 死亡类型（按4.1.2优先级排列）
_SELF_ATTRIBUTION_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("探草死", ("探草", "草丛", "草里", "蹲草", "脸探", "埋伏")),
    ("掉点死", ("掉点", "孤立", "一个人", "单独", "队友撤", "越塔", "深入", "没队友")),
    ("换头死", ("换头", "一换一", "换血", "对拼", "互换")),
    ("贪线死", ("贪线", "贪兵", "收线", "补刀", "清线", "贪塔", "兵线", "贪")),
]


def format_ts(seconds: float | None) -> str:
    """秒 → mm:ss。"""
    if seconds is None:
        return "?"
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def classify_death(evidence: dict[str, Any],
                   llm: Optional[LLMClient] = None) -> dict[str, Any]:
    """死亡归因分类器（4.1.2）。

    Args:
        evidence: {
          "death_time": "6:32" 或秒数,
          "death_location": str|None,    # 死亡地点（见death_location_source）
          "death_location_source": str|None,  # "minimap_x_marker"=系统直接
                                          # 标注（AGE-46，高优先级/可靠）；
                                          # None=未取到，退化为仅靠轨迹推断
          "minimap_context": str|None,   # 死亡前15秒敌方位置轨迹摘要（辅助
                                          # 上下文，用于推断"怎么死的"）
          "self_attribution": str|None,  # 用户自述
          "kill_traded": bool|None,      # 同窗口击杀+1（换头信号，来自阶段0管线）
          "solo_in_enemy_half": bool|None,  # 结构化信号（有则用）
          "near_brush": bool|None,
          "pushing_wave": bool|None,
        }
    Returns:
        {"type": str, "confidence": float, "reason": str, "evidence_sufficient": bool}
    """
    # --- 1. 结构化证据规则（4.1.2优先级） ---
    if evidence.get("near_brush"):
        return _result("探草死", 0.8, "检测到死亡前贴近未探明草丛")
    if evidence.get("solo_in_enemy_half"):
        return _result("掉点死", 0.8, "队友已撤退/阵亡，玩家独自处于敌方半区")
    if evidence.get("kill_traded"):
        return _result("换头死", 0.6, "死亡同窗口内击杀数同步+1（一换一）")
    if evidence.get("pushing_wave"):
        return _result("贪线死", 0.6, "死亡前为推线/收线暴露位置")

    # --- 2. 用户自述关键词 ---
    attribution = (evidence.get("self_attribution") or "").strip()
    for dtype, kws in _SELF_ATTRIBUTION_RULES:
        if any(kw in attribution for kw in kws):
            return _result(dtype, 0.6, f"依据用户自述（“{attribution}”）判定")

    # --- 3. LLM兜底 ---
    if llm is not None:
        result = _classify_with_llm(evidence, llm)
        if result is not None:
            return result

    # --- 4. 证据不足 ---
    return _result("机制死", 0.3, "证据不足，无法在探草/掉点/换头/贪线中判定",
                   sufficient=False)


def _result(dtype: str, conf: float, reason: str,
            sufficient: bool = True) -> dict[str, Any]:
    return {"type": dtype, "confidence": conf, "reason": reason,
            "evidence_sufficient": sufficient}


def _format_death_location(evidence: dict[str, Any]) -> str:
    """把地点+数据源标注拼成prompt用的一句话（AGE-46）。

    死亡"X"标记是系统直接标注的地点，可靠度高于从敌方轨迹反推；
    显式标注来源，让LLM/复盘教练知道该信任哪个信号、两者冲突时怎么办。
    """
    loc = evidence.get("death_location")
    if not loc:
        return "未知（未取到死亡X标记，也无法从轨迹反推）"
    if evidence.get("death_location_source") == "minimap_x_marker":
        return f"{loc}（系统小地图死亡X标记直接读取，高可靠度）"
    return f"{loc}（推断值，未取到系统X标记，可靠度低于直接读取）"


def _classify_with_llm(evidence: dict[str, Any],
                       llm: LLMClient) -> Optional[dict[str, Any]]:
    template = DEATH_CLASSIFIER_PROMPT.read_text(encoding="utf-8")
    prompt = template.format(
        death_time=evidence.get("death_time") or "未知",
        death_location=_format_death_location(evidence),
        minimap_context=evidence.get("minimap_context") or "无（未提取到）",
        self_attribution=evidence.get("self_attribution") or "无",
    )
    try:
        raw = llm.chat_text(system="", user=prompt, temperature=0.0)
        data = extract_json(raw)
    except (LLMError, ValueError):
        return None
    dtype = data.get("type")
    if dtype not in DEATH_TYPES:
        return None
    sufficient = "证据不足" not in str(data.get("reason", ""))
    return _result(dtype, float(data.get("confidence", 0.5)),
                   str(data.get("reason", "LLM判定")), sufficient=sufficient)


# ---------------------------------------------------------------------------
# 复盘记录组装
# ---------------------------------------------------------------------------

def build_replay_from_video(video_path: str,
                            death_events: list[dict[str, Any]],
                            minimap_contexts: list[str | None],
                            llm: Optional[LLMClient] = None) -> dict[str, Any]:
    """把阶段0管线输出（死亡事件+minimap轨迹摘要）组装成replay记录并逐条归因。

    death_events: video_utils.extract_death_events() 输出
    minimap_contexts: 与death_events等长，每项为该死亡前15秒的minimap摘要文本
    """
    from utils import data_utils  # 延迟导入避免循环

    replay = data_utils.default_replay()
    replay["source"] = {"type": "video", "path": str(video_path)}
    replay["deaths"] = len(death_events)
    replay["death_analysis"]["total"] = len(death_events)

    for event, mm in zip(death_events, minimap_contexts):
        evidence = {
            "death_time": format_ts(event.get("ts")),
            "death_location": event.get("location"),
            "death_location_source": event.get("location_source"),  # AGE-46
            "minimap_context": mm,
            "kill_traded": event.get("kill_traded"),
            "self_attribution": None,
        }
        cls = classify_death(evidence, llm=llm)
        detail = {
            "timestamp": format_ts(event.get("ts")),
            "type": cls["type"],
            "confidence": cls["confidence"],
            "classify_reason": cls["reason"],
            "evidence_sufficient": cls["evidence_sufficient"],
            "location": event.get("location"),
            "location_source": event.get("location_source"),  # AGE-46
            "killer": None,
            "minimap_context": mm,
            "self_attribution": None,
            "ai_comment": None,  # orchestrator填充
        }
        replay["death_analysis"]["categories"][cls["type"]] += 1
        replay["death_analysis"]["details"].append(detail)
    return replay


def classify_manual_replay(replay: dict[str, Any],
                           llm: Optional[LLMClient] = None) -> dict[str, Any]:
    """对手动录入的replay记录补齐缺失的死亡类型判定。"""
    cats = replay["death_analysis"]["categories"]
    for detail in replay["death_analysis"]["details"]:
        if detail.get("type"):
            continue
        cls = classify_death({
            "death_time": detail.get("timestamp"),
            "death_location": detail.get("location"),
            "minimap_context": detail.get("minimap_context"),
            "self_attribution": detail.get("self_attribution"),
        }, llm=llm)
        detail["type"] = cls["type"]
        detail["confidence"] = cls["confidence"]
        detail["classify_reason"] = cls["reason"]
        detail["evidence_sufficient"] = cls["evidence_sufficient"]
        cats[cls["type"]] += 1
    return replay
