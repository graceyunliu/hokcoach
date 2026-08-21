# -*- coding: utf-8 -*-
"""数据模型定义与JSON读写工具。

对应 tech spec 3.1 核心数据结构：
- player_profile.json   玩家画像
- weekly_training.json  每周训练记录
- progress.json         进步追踪
- replay_{ts}.json      复盘记录（data/replays/下，每局一份）

阶段1原则：纯标准库，不引入数据库/ORM。文件即数据。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPLAYS_DIR = DATA_DIR / "replays"

PLAYER_PROFILE_PATH = DATA_DIR / "player_profile.json"
WEEKLY_TRAINING_PATH = DATA_DIR / "weekly_training.json"
PROGRESS_PATH = DATA_DIR / "progress.json"


# ---------------------------------------------------------------------------
# 通用读写
# ---------------------------------------------------------------------------

def load_json(path: Path) -> dict[str, Any] | None:
    """读取JSON文件；不存在时返回None。"""
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict[str, Any]) -> None:
    """写入JSON文件（UTF-8、缩进2、保留中文）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ---------------------------------------------------------------------------
# 默认模板（schema 对齐 tech spec 3.1）
# ---------------------------------------------------------------------------

def default_player_profile() -> dict[str, Any]:
    """玩家画像空模板。

    注意：不预填任何具体玩家数据——每个新用户的档案只能来自其本人输入。
    （若未来能接入王者营地等官方数据源，由 OfficialAPIAdapter 自动填充，
    见 tech spec 4.4.1；目前无公开API。）
    """
    return {
        "player": {
            "id": "player_001",
            "language": "zh",
            "main_heroes": [],
            "secondary_heroes": [],
            "current_rank": None,
            "rank_type": None,
            "target_hero": None,
            "target_power": None,
            "total_games": None,
            "join_date": date.today().isoformat(),
            "constraints": {
                "network_latency_ms": None,
                "age_bracket": None,
                "years_gaming_experience": None,
                "hours_per_week": None,
                "notes": (
                    "自评/可测量字段，均为可选。用于让教练在生成建议前检查该建议"
                    "是否假设了玩家不具备的能力（如低延迟反应），而不是用于降低标准"
                    "或替代真实弱点识别。"
                ),
            },
            "baseline": {
                "date": date.today().isoformat(),
                "rank": None,
                "hero_power": {},
                "season_stats": {},
            },
        }
    }


def default_weekly_training(week: str | None = None) -> dict[str, Any]:
    """每周训练记录默认模板。"""
    if week is None:
        iso = date.today().isocalendar()
        week = f"{iso[0]}-W{iso[1]:02d}"
    return {
        "week": week,
        "task": {
            "description": None,
            "skill_tag": None,
            "target_streak": 5,
            "current_streak": 0,
            "start_date": None,
            "status": "not_started",  # not_started / in_progress / done
        },
        "daily_checkins": [],
        "ai_weekly_note": None,
    }


def default_progress() -> dict[str, Any]:
    """进步追踪默认模板。弱点清单按训练引擎基础→进阶顺序（tech spec 4.2.2）。"""
    return {
        "weekly_snapshots": [],
        "weakness_tracker": {
            "探草意识": {"status": "pending", "weeks_trained": 0, "current_level": 0.0},
            "大招时机": {"status": "pending", "weeks_trained": 0, "current_level": 0.0},
            "团战站位": {"status": "pending", "weeks_trained": 0, "current_level": 0.0},
            "优势期决策": {"status": "pending", "weeks_trained": 0, "current_level": 0.0},
        },
        "strength_tracker": {},
    }


def default_replay(hero_played: str | None = None) -> dict[str, Any]:
    """复盘记录默认模板（replay_{timestamp}.json）。"""
    ts = datetime.now()
    return {
        "replay_id": f"replay_{ts.strftime('%Y%m%d_%H%M%S')}",
        "timestamp": ts.isoformat(timespec="seconds"),
        "hero_played": hero_played,
        "game_result": None,  # victory / defeat
        "rank_after": None,
        "deaths": 0,
        "death_analysis": {
            "total": 0,
            "categories": {"探草死": 0, "掉点死": 0, "换头死": 0, "机制死": 0, "贪线死": 0},
            "details": [],
        },
        "decision_points": [],
        "review_quality_self_score": None,
    }


# ---------------------------------------------------------------------------
# 便捷读写
# ---------------------------------------------------------------------------

def load_player_profile() -> dict[str, Any] | None:
    return load_json(PLAYER_PROFILE_PATH)


def save_player_profile(profile: dict[str, Any]) -> None:
    save_json(PLAYER_PROFILE_PATH, profile)


def load_weekly_training() -> dict[str, Any] | None:
    return load_json(WEEKLY_TRAINING_PATH)


def save_weekly_training(data: dict[str, Any]) -> None:
    save_json(WEEKLY_TRAINING_PATH, data)


def load_progress() -> dict[str, Any] | None:
    return load_json(PROGRESS_PATH)


def save_progress(data: dict[str, Any]) -> None:
    save_json(PROGRESS_PATH, data)


def save_replay(replay: dict[str, Any]) -> Path:
    """按 replay_id 落盘一份复盘记录，返回文件路径。"""
    path = REPLAYS_DIR / f"{replay['replay_id']}.json"
    save_json(path, replay)
    return path


def list_replays() -> list[Path]:
    """按时间顺序列出全部复盘记录文件。"""
    if not REPLAYS_DIR.exists():
        return []
    return sorted(REPLAYS_DIR.glob("replay_*.json"))
