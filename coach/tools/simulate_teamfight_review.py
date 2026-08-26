"""Run a deterministic coach-led team-fight replay simulation.

This is a contract/integration simulation, not a claim about real footage. It
exercises replay classification, the reflection question, the evidence ledger,
and the report-facing output with no LLM or video dependency.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Support both `python -m tools.simulate_teamfight_review` from coach/ and direct
# execution from the repository root.
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core import orchestrator, replay_engine  # noqa: E402


def build_scenario() -> dict:
    """A mid-lane fight where the player clears a wave while enemies engage."""
    events = [{
        "ts": 412.0,
        "location": "中路二塔前",
        "location_source": "minimap_x_marker",
        "kill_traded": False,
        "solo_in_enemy_half": False,
        "near_brush": False,
        "visible_enemy_engagement": True,
        # The wave candidate is present, but this is intentionally not enough to
        # label the death as 贪线死: the team-fight signal must remain dominant.
        "pushing_wave": None,
        "minimap_object_evidence": {
            "decision": "unknown",
            "reason_codes": ["mixed_combat_and_wave"],
            "coverage": 0.78,
            "wave_candidates": [{
                "lane": "mid", "side": "ally", "count_estimate": {"min": 2, "max": 4},
                "direction": "toward_enemy", "persistence_samples": 3,
                "confidence": 0.72,
            }],
            "towers": [{"region": "中路二塔", "status": "present", "confidence": 0.91}],
        },
        "kill_feed_events": [{
            "ts": 410.9, "victim_is_player": False, "killer_hero": "敌方打野",
        }],
    }]
    replay = replay_engine.build_replay_from_video(
        "simulated://mid-fight-wave.mp4", events, [
            "死亡前15秒：敌方中野从河道进入中路；己方两名队友在附近；中路小兵持续向敌方二塔移动"
        ], audio_timeline=[{
            "ts": 411.2, "event": "teamfight_engage", "category": "combat",
            "perspective": "system", "score": 0.94, "usage": "context",
        }], llm=None, lang="zh")
    detail = replay["death_analysis"]["details"][0]
    detail["visible_enemy_engagement"] = True
    detail["user_intent"] = "我想先把中路线清掉再接团，但看到对面开团后反应慢了"
    return replay


def build_dragon_contest_scenario() -> dict:
    """A dragon contest with incomplete vision and simultaneous side pressure."""
    events = [{
        "ts": 735.0,
        "location": "暗影暴君坑口",
        "location_source": "minimap_x_marker",
        "kill_traded": False,
        "solo_in_enemy_half": False,
        "near_brush": True,
        "visible_enemy_engagement": None,
        "pushing_wave": None,
        "minimap_object_evidence": {
            "decision": "unknown",
            "reason_codes": ["vision_gap", "side_lane_pressure"],
            "coverage": 0.54,
            "wave_candidates": [{
                "lane": "bottom", "side": "ally", "count_estimate": {"min": 3, "max": 5},
                "direction": "toward_enemy", "persistence_samples": 2,
                "confidence": 0.61,
            }],
            "towers": [{"region": "下路二塔", "status": "present", "confidence": 0.84}],
        },
        "kill_feed_events": [],
    }]
    replay = replay_engine.build_replay_from_video(
        "simulated://dragon-contest-vision-pressure.mp4", events, [
            "死亡前15秒：暗影暴君附近敌方视野缺失；敌方打野连续12秒未在小地图出现；下路兵线正在推向敌方二塔；己方辅助在龙坑入口等待"
        ], audio_timeline=[{
            "ts": 734.3, "event": "objective_warning", "category": "objective",
            "perspective": "system", "score": 0.88, "usage": "context",
        }], llm=None, lang="zh")
    detail = replay["death_analysis"]["details"][0]
    detail["user_intent"] = "我看到下路线在推，想先逼对面回防再进龙坑，但敌方打野消失太久了"
    return replay


def run(scenario: str = "teamfight") -> dict:
    replay = build_dragon_contest_scenario() if scenario == "dragon" else build_scenario()
    detail = replay["death_analysis"]["details"][0]
    detail["coach_question"] = orchestrator.build_reflection_question(detail, lang="zh")
    detail["evidence_ledger"] = orchestrator.build_evidence_ledger(detail, lang="zh")
    # The classifier should abstain from 贪线死 when the wave is unresolved and
    # visible combat is confirmed; the simulation verifies that safety property.
    assert detail["type"] != "贪线死"
    assert detail["evidence_ledger"]["observed"]
    assert detail["evidence_ledger"]["unresolved"]
    assert any("意图" in item for item in detail["evidence_ledger"]["observed"])
    assert any("兵线/防御塔证据" in item for item in detail["evidence_ledger"]["unresolved"])
    if scenario == "dragon":
        assert any("视野不完整" in item for item in detail["evidence_ledger"]["unresolved"])
        assert any("边线小兵压力" in item for item in detail["evidence_ledger"]["observed"])
    else:
        assert any("团战与清线信号重叠" in item for item in detail["evidence_ledger"]["unresolved"])
    return {
        "scenario": "dragon contest with incomplete vision and side-lane pressure" if scenario == "dragon" else "mid-lane team fight while a wave is present",
        "classification": {
            "type": detail["type"],
            "confidence": detail["confidence"],
            "evidence_sufficient": detail["evidence_sufficient"],
            "reason": detail["classify_reason"],
        },
        "coach_question": detail["coach_question"],
        "evidence_ledger": detail["evidence_ledger"],
        "minimap_object_evidence": detail["minimap_object_evidence"],
        "player_intent": detail["user_intent"],
        "coaching_takeaway": ("龙坑投入前先补齐视野并确认敌方打野位置；边线压力是决策背景，不足以替代安全进场条件。" if scenario == "dragon" else "先判断开团与人数优势，再决定是否清线；本次不把同时出现的兵线候选误判成贪线死。"),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate a coach-led replay review")
    parser.add_argument("--scenario", choices=("teamfight", "dragon"), default="teamfight")
    args = parser.parse_args()
    print(json.dumps(run(args.scenario), ensure_ascii=False, indent=2))
